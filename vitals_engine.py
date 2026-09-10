"""
vitals_engine.py
Core, dependency-light logic for the Patient Vital Sign Anomaly Detector.

Deliberately has NO Streamlit and NO network calls in it, so it can be
unit-tested or reused in a different frontend. Everything here is the
deterministic "Phase 1" rule engine described in the PRD:

  Data Ingestion & Preprocessing -> simulate_reading(), clean_reading()
  Anomaly Detection Engine       -> score_risk(), composite_score()
  Alerting                       -> build_alert()

ai_reasoning.py sits on top of this and only explains a decision this
module already made — it never decides risk itself, so the safety-
critical path stays deterministic even if the AI call fails.
"""

import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

RISK_LEVELS = ("Normal", "Low", "Moderate", "High", "Critical")
RISK_ORDER = {lvl: i for i, lvl in enumerate(RISK_LEVELS)}

PARAMS = ("heart_rate", "spo2", "systolic_bp", "temperature", "resp_rate")

PARAM_META = {
    "heart_rate":  {"label": "Heart Rate", "short": "HR",    "unit": "bpm"},
    "spo2":        {"label": "SpO2",       "short": "SpO2",  "unit": "%"},
    "systolic_bp": {"label": "Blood Pressure", "short": "NIBP", "unit": "mmHg"},
    "temperature": {"label": "Temperature", "short": "TEMP", "unit": "°C"},
    "resp_rate":   {"label": "Respiratory Rate", "short": "RR", "unit": "br/min"},
}

# ---------------------------------------------------------------------------
# Patient profiles — PRD explicitly calls for "patient-specific historical
# ranges" in addition to fixed baseline limits. These stand in for that:
# each profile carries its own normal ranges, so the same rule engine
# behaves differently for, say, a pediatric vs. an ICU patient.
# ---------------------------------------------------------------------------

PATIENT_PROFILES = {
    "Adult — General Ward": {
        "heart_rate": (60, 100), "spo2": (95, 100), "systolic_bp": (90, 130),
        "diastolic_bp": (60, 85), "temperature": (36.1, 37.5), "resp_rate": (12, 20),
    },
    "Pediatric": {
        "heart_rate": (80, 120), "spo2": (95, 100), "systolic_bp": (80, 110),
        "diastolic_bp": (50, 70), "temperature": (36.5, 37.7), "resp_rate": (18, 30),
    },
    "Elderly / Post-Op": {
        "heart_rate": (55, 95), "spo2": (93, 100), "systolic_bp": (100, 140),
        "diastolic_bp": (60, 90), "temperature": (36.0, 37.4), "resp_rate": (12, 22),
    },
    "ICU / Critical Care": {
        "heart_rate": (50, 110), "spo2": (92, 100), "systolic_bp": (90, 150),
        "diastolic_bp": (55, 95), "temperature": (35.5, 38.0), "resp_rate": (10, 24),
    },
}

FORCE_ANOMALY_OPTIONS = {
    "None": None,
    "Heart rate spike (tachycardia)": "hr_high",
    "Heart rate drop (bradycardia)": "hr_low",
    "Low oxygen saturation (hypoxia)": "spo2_low",
    "Blood pressure spike (hypertensive)": "bp_high",
    "Blood pressure crash (hypotensive)": "bp_low",
    "Fever spike": "temp_high",
    "Rapid breathing (tachypnea)": "resp_high",
    "Critical multi-parameter event": "critical_combo",
}


# ---------------------------------------------------------------------------
# 1. INGESTION (simulated packet arrival, as if from REST/WebSocket/FHIR)
# ---------------------------------------------------------------------------

def simulate_reading(ranges: dict, prev: dict | None = None, force_anomaly: str | None = None) -> dict:
    """One simulated vital-sign packet, drifting from `prev` if given."""
    hr_lo, hr_hi = ranges["heart_rate"]
    sbp_lo, sbp_hi = ranges["systolic_bp"]
    dbp_lo, dbp_hi = ranges["diastolic_bp"]
    temp_lo, temp_hi = ranges["temperature"]
    rr_lo, rr_hi = ranges["resp_rate"]

    if prev is None:
        hr = random.randint(hr_lo + 5, hr_hi - 5)
        spo2 = random.randint(97, 99)
        sbp = random.randint(sbp_lo + 5, sbp_hi - 10)
        dbp = random.randint(dbp_lo + 3, dbp_hi - 3)
        temp = round(random.uniform(temp_lo + 0.2, temp_hi - 0.3), 1)
        rr = random.randint(rr_lo + 1, rr_hi - 2)
    else:
        hr = prev["heart_rate"] + random.randint(-3, 3)
        spo2 = prev["spo2"] + random.randint(-1, 1)
        sbp = prev["systolic_bp"] + random.randint(-2, 2)
        dbp = prev["diastolic_bp"] + random.randint(-2, 2)
        temp = round(prev["temperature"] + random.uniform(-0.1, 0.1), 1)
        rr = prev["resp_rate"] + random.randint(-1, 1)

    # 5% chance of a one-off sensor artifact (used to demo noise filtering)
    artifact = random.random() < 0.05
    if artifact:
        hr += random.choice([-45, 45, 60])

    if force_anomaly == "hr_high":
        hr = random.randint(hr_hi + 25, hr_hi + 50)
    elif force_anomaly == "hr_low":
        hr = random.randint(max(20, hr_lo - 30), hr_lo - 15)
    elif force_anomaly == "spo2_low":
        spo2 = random.randint(78, 87)
    elif force_anomaly == "bp_high":
        sbp = random.randint(sbp_hi + 30, sbp_hi + 60)
    elif force_anomaly == "bp_low":
        sbp = random.randint(max(50, sbp_lo - 35), sbp_lo - 15)
    elif force_anomaly == "temp_high":
        temp = round(random.uniform(39.0, 40.2), 1)
    elif force_anomaly == "resp_high":
        rr = random.randint(rr_hi + 10, rr_hi + 20)
    elif force_anomaly == "critical_combo":
        hr = random.randint(hr_hi + 30, hr_hi + 55)
        spo2 = random.randint(78, 85)
        sbp = random.randint(max(50, sbp_lo - 35), sbp_lo - 15)

    return {
        "timestamp": datetime.now(timezone.utc),
        "heart_rate": max(20, min(220, hr)),
        "spo2": max(50, min(100, spo2)),
        "systolic_bp": max(50, min(220, sbp)),
        "diastolic_bp": max(30, min(140, dbp)),
        "temperature": max(33.0, min(42.0, temp)),
        "resp_rate": max(4, min(50, rr)),
        "artifact_flag": artifact,
    }


def clean_reading(history: deque, new_reading: dict, window: int = 5) -> dict:
    """
    Preprocessing step. Only corrects packets flagged as sensor artifacts
    at the source. A sudden REAL change is deliberately left untouched —
    a monitor that "smooths away" a genuine deterioration defeats its own
    purpose, so noise rejection here is scoped strictly to flagged glitches.
    """
    cleaned = dict(new_reading)
    if not cleaned.get("artifact_flag"):
        return cleaned

    recent = list(history)[-window:]
    if recent:
        avg = sum(r["heart_rate"] for r in recent) / len(recent)
        cleaned["heart_rate"] = round(avg)
    return cleaned


# ---------------------------------------------------------------------------
# 2. ANOMALY DETECTION ENGINE — per-parameter rule-based thresholds
# ---------------------------------------------------------------------------

def _param_risk(value: float, lo: float, hi: float, moderate_pad: float, high_pad: float) -> str:
    if lo <= value <= hi:
        return "Normal"
    if (lo - moderate_pad) <= value < lo or hi < value <= (hi + moderate_pad):
        return "Low"
    if (lo - moderate_pad - high_pad) <= value < (lo - moderate_pad) or \
       (hi + moderate_pad) < value <= (hi + moderate_pad + high_pad):
        return "Moderate"
    return "High"


# (moderate_pad, high_pad) per parameter — how far outside the patient's
# normal range counts as Low / Moderate / High.
_PADS = {
    "heart_rate": (12, 18),
    "spo2": (2, 5),
    "systolic_bp": (10, 20),
    "temperature": (0.4, 0.8),
    "resp_rate": (3, 6),
}


def score_risk(reading: dict, ranges: dict) -> dict:
    """Per-parameter risk + overall risk (worst case, escalated to
    'Critical' when two or more parameters are independently High)."""
    per_param = {}
    for p in PARAMS:
        lo, hi = ranges[p]
        pad_m, pad_h = _PADS[p]
        per_param[p] = _param_risk(reading[p], lo, hi, pad_m, pad_h)

    worst = max(per_param.values(), key=lambda r: RISK_ORDER[r])
    high_count = sum(1 for r in per_param.values() if r == "High")
    overall = "Critical" if high_count >= 2 else worst

    return {**{f"{p}_risk": r for p, r in per_param.items()}, "overall_risk": overall}


def composite_score(reading: dict, ranges: dict) -> int:
    """
    A single 0-100 'severity dial' purely for the headline gauge — it's a
    deterministic function of how far each parameter sits from its normal
    band (not a separate model), so it stays consistent with score_risk().
    """
    total = 0.0
    for p in PARAMS:
        lo, hi = ranges[p]
        pad_m, pad_h = _PADS[p]
        span = max(pad_m + pad_h, 1e-6)
        val = reading[p]
        if val < lo:
            dist = min((lo - val) / span, 1.5)
        elif val > hi:
            dist = min((val - hi) / span, 1.5)
        else:
            dist = 0.0
        total += dist
    return int(min(100, round((total / len(PARAMS)) * 100)))


# ---------------------------------------------------------------------------
# 3. ALERTING
# ---------------------------------------------------------------------------

def build_alert(reading: dict, risk: dict, score: int) -> dict | None:
    if RISK_ORDER[risk["overall_risk"]] < RISK_ORDER["Moderate"]:
        return None

    triggered = [p for p in PARAMS if RISK_ORDER[risk[f"{p}_risk"]] >= RISK_ORDER["Moderate"]]
    return {
        "timestamp": reading["timestamp"],
        "risk_level": risk["overall_risk"],
        "score": score,
        "triggered_params": triggered,
        "reading": reading,
        "risk": risk,
    }


# ---------------------------------------------------------------------------
# Orchestration used directly by the Streamlit app
# ---------------------------------------------------------------------------

@dataclass
class VitalAgentState:
    history: deque = field(default_factory=lambda: deque(maxlen=300))
    alerts: list = field(default_factory=list)

    def step(self, ranges: dict, force_anomaly: str | None = None,
              explain_fn=None) -> tuple[dict, dict | None]:
        prev = self.history[-1] if self.history else None
        raw = simulate_reading(ranges, prev, force_anomaly=force_anomaly)
        cleaned = clean_reading(self.history, raw)
        risk = score_risk(cleaned, ranges)
        score = composite_score(cleaned, ranges)
        cleaned.update(risk)
        cleaned["composite_score"] = score
        self.history.append(cleaned)

        alert = build_alert(cleaned, risk, score)
        if alert:
            alert["explanation"] = explain_fn(cleaned, risk) if explain_fn else None
            self.alerts.append(alert)

        return cleaned, alert
