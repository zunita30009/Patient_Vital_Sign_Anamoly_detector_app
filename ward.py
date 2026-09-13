"""
ward.py
Multi-patient ward orchestration on top of vitals_engine.py.

Design note on data sources (see README for the full write-up):
Real hospitals don't hand out raw CSVs — they speak HL7/FHIR over a live
integration engine, which isn't something a hackathon build can stand up
against a real hospital. What we CAN do honestly is make the data source
swappable: this module drives every bed from either (a) the built-in
simulator, or (b) a user-uploaded CSV shaped like a PhysioNet MIMIC-IV /
eICU export, replayed row-by-row per bed. That's the "Patient Data
Simulator Engine" the pivot calls for, without pretending we shipped a
real hospital feed.
"""

import random
from dataclasses import dataclass, field

import pandas as pd

from vitals_engine import VitalAgentState, PATIENT_PROFILES, PARAMS, RISK_ORDER

FIRST_NAMES = ["Amara", "Bilal", "Chen", "Diego", "Elif", "Farah", "Grace", "Hamza",
               "Imani", "Javier", "Kavya", "Liam", "Maya", "Noah", "Omar", "Priya",
               "Qasim", "Rina", "Sara", "Tariq", "Uma", "Victor", "Wei", "Yusuf",
               "Zara", "Aiden", "Bella", "Carlos", "Dana", "Eshaan"]

CSV_COLUMN_HELP = (
    "Expected columns (one row per timestep, any extra columns are ignored): "
    "bed_id, heart_rate, spo2, systolic_bp, diastolic_bp, temperature, resp_rate. "
    "This matches a simple flattening of PhysioNet MIMIC-IV/eICU vitals tables — "
    "export your cohort to this shape before uploading."
)


@dataclass
class Bed:
    bed_id: str
    patient_name: str
    profile_name: str
    agent: VitalAgentState = field(default_factory=VitalAgentState)
    csv_rows: list = None   # only used when the ward is running in "uploaded CSV" mode
    csv_index: int = 0

    @property
    def ranges(self):
        return PATIENT_PROFILES[self.profile_name]

    @property
    def latest(self):
        return self.agent.history[-1] if self.agent.history else None


@dataclass
class WardState:
    beds: dict = field(default_factory=dict)   # bed_id -> Bed
    debounce_n: int = 2

    def ordered_bed_ids(self):
        """Severity-sorted (highest composite score first) — the AI triage view."""
        def severity(bed_id):
            latest = self.beds[bed_id].latest
            return latest["composite_score"] if latest else -1
        return sorted(self.beds.keys(), key=severity, reverse=True)

    def step_all(self, force_anomaly=None, force_bed_id=None, explain_fn=None):
        """Advance every bed by one reading. If force_bed_id is set, only that
        bed receives the injected scenario (the Clinical Simulation Suite)."""
        for bed_id, bed in self.beds.items():
            anomaly_for_this_bed = force_anomaly if (force_bed_id is None or force_bed_id == bed_id) else None
            if bed.csv_rows is not None:
                _step_from_csv(bed, self.debounce_n, explain_fn)
            else:
                bed.agent.step(bed.ranges, force_anomaly=anomaly_for_this_bed,
                                explain_fn=explain_fn, debounce_n=self.debounce_n)
    def total_alerts(self):
        return sum(len(b.agent.alerts) for b in self.beds.values())

    def total_suppressed(self):
        return sum(b.agent.suppressed_count for b in self.beds.values())

    def critical_bed_count(self):
        return sum(1 for b in self.beds.values() if b.latest and b.latest["confirmed_risk"] == "Critical")


def build_simulated_ward(num_beds: int = 16, seed: int | None = None) -> WardState:
    rng = random.Random(seed)
    names = rng.sample(FIRST_NAMES, min(num_beds, len(FIRST_NAMES)))
    while len(names) < num_beds:
        names.append(f"Patient {len(names) + 1}")

    profile_names = list(PATIENT_PROFILES.keys())
    beds = {}
    for i in range(num_beds):
        bed_id = f"Bed {i + 1:02d}"
        beds[bed_id] = Bed(
            bed_id=bed_id,
            patient_name=names[i],
            profile_name=rng.choice(profile_names),
        )
    return WardState(beds=beds)


def build_ward_from_csv(df: pd.DataFrame) -> WardState:
    """Replays an uploaded historical export instead of simulating vitals.
    Each unique bed_id in the file becomes one bed; rows are replayed in
    the order they appear, looping once exhausted."""
    required = {"bed_id", "heart_rate", "spo2", "systolic_bp", "temperature", "resp_rate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}. {CSV_COLUMN_HELP}")

    if "diastolic_bp" not in df.columns:
        df = df.copy()
        df["diastolic_bp"] = (df["systolic_bp"] * 0.65).round()

    beds = {}
    for bed_id, group in df.groupby("bed_id"):
        rows = group[["heart_rate", "spo2", "systolic_bp", "diastolic_bp", "temperature", "resp_rate"]].to_dict("records")
        # a CSV patient still needs a normal-range profile for scoring; default to general adult
        beds[str(bed_id)] = Bed(bed_id=str(bed_id), patient_name=str(bed_id),
                                 profile_name="Adult — General Ward", csv_rows=rows, csv_index=0)
    return WardState(beds=beds)


def _step_from_csv(bed: Bed, debounce_n: int, explain_fn):
    """Pulls the next row from the uploaded historical file and runs it
    through the exact same pipeline as the simulator (VitalAgentState.step)
    — cleaning, scoring, NEWS2, debounce, and alerting are identical either
    way; only where the raw reading comes from differs."""
    from datetime import datetime, timezone

    if not bed.csv_rows:
        return None, None
    row = bed.csv_rows[bed.csv_index % len(bed.csv_rows)]
    bed.csv_index += 1

    raw = dict(row)
    raw["timestamp"] = datetime.now(timezone.utc)
    raw["artifact_flag"] = False

    return bed.agent.step(bed.ranges, explain_fn=explain_fn, debounce_n=debounce_n, raw_reading=raw)
