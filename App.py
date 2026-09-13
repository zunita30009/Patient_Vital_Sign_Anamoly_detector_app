"""
app.py
Patient Vital Sign Anomaly Detector — ward-level triage dashboard.

Flow: light entrance screen -> ward grid (sorted by AI severity score,
NEWS2 badge shown per bed) -> click a bed to drill into its full
single-patient dashboard.

Deploy target: GitHub + Streamlit Community Cloud (see README.md).
"""

import io
import os
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ai_reasoning import explain_with_groq
from theme import (
    CSS_STYLE, LIGHT_CSS_STYLE, RISK_COLORS, CHANNEL_COLORS,
    alarm_banner_html, risk_pill_html, alarm_audio_html,
    ecg_hero_svg, step_card_html, bed_tile_html,
    monitor_readout_html, monitor_panel_html,
)
from vitals_engine import PARAM_META, PARAMS, FORCE_ANOMALY_OPTIONS
from ward import build_simulated_ward, build_ward_from_csv, CSV_COLUMN_HELP

st.set_page_config(page_title="Ward Vital Sign Anomaly Detector", page_icon="🩺", layout="wide")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "ward" not in st.session_state:
    st.session_state.ward = None            # created once the user starts monitoring
if "running" not in st.session_state:
    st.session_state.running = False
if "selected_bed" not in st.session_state:
    st.session_state.selected_bed = None    # None = ward overview; else drill-down
if "last_alarmed_count" not in st.session_state:
    st.session_state.last_alarmed_count = 0

started = st.session_state.ward is not None
st.markdown(CSS_STYLE if started else LIGHT_CSS_STYLE, unsafe_allow_html=True)


def make_explain_fn(api_key):
    def _fn(reading, risk, confirmed_triggered):
        return explain_with_groq(reading, risk, confirmed_triggered, api_key=api_key)
    return _fn


try:
    groq_key = st.secrets.get("GROQ_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
except Exception:
    groq_key = os.environ.get("GROQ_API_KEY", "")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
force_anomaly, target_bed, manual = None, None, False
data_source, num_beds, uploaded = "Simulated ward", 16, None

with st.sidebar:
    st.markdown("### ⚙️ Ward setup")

    if groq_key:
        st.caption("✅ AI explanations enabled.")
    else:
        st.caption("⚠️ No API key configured — alerts will show rule-based results only.")

    if not started:
        data_source = st.radio("Data source", ["Simulated ward", "Upload historical CSV"])
        if data_source == "Simulated ward":
            num_beds = st.slider("Number of beds", 4, 30, 16)
        else:
            uploaded = st.file_uploader("MIMIC-IV / eICU-style export (.csv)", type=["csv"])
            st.caption(CSV_COLUMN_HELP)

    sound_on = st.checkbox("🔔 Alarm sound on Critical", value=True)
    refresh_seconds = st.slider("Reading interval (sec)", 1, 5, 2)
    debounce_n = st.slider("Alarm confirmation window (readings)", 1, 4, 2,
                            help="Alarm-fatigue mitigation: a parameter must stay abnormal for this "
                                 "many consecutive readings before it's confirmed as an alert, instead "
                                 "of firing on every noisy blip.")

    if started:
        st.session_state.ward.debounce_n = debounce_n
        st.markdown("---")
        st.markdown("### 🧪 Clinical Simulation Suite")
        st.caption("Stress-test the ward AI with an injected event.")
        anomaly_label = st.selectbox("Scenario", list(FORCE_ANOMALY_OPTIONS.keys()))
        force_anomaly = FORCE_ANOMALY_OPTIONS[anomaly_label]
        bed_ids = list(st.session_state.ward.beds.keys())
        target_bed = st.selectbox("Target bed", ["Random bed"] + bed_ids)

        c1, c2, c3 = st.columns(3)
        if c1.button("▶ Start"):
            st.session_state.running = True
        if c2.button("⏸ Stop"):
            st.session_state.running = False
        if c3.button("🔄 New ward"):
            st.session_state.ward = None
            st.session_state.running = False
            st.session_state.selected_bed = None
            st.rerun()
        manual = st.button("➕ Advance one reading", use_container_width=True)

        if st.session_state.selected_bed:
            if st.button("← Back to ward overview", use_container_width=True):
                st.session_state.selected_bed = None
                st.rerun()


# ---------------------------------------------------------------------------
# Entrance screen
# ---------------------------------------------------------------------------
if not started:
    st.markdown('<div class="vsad-hero">', unsafe_allow_html=True)
    st.markdown('<div class="vsad-hero-eyebrow">AI-DRIVEN WARD MONITORING</div>', unsafe_allow_html=True)
    st.markdown('<div class="vsad-hero-title">See which patient needs you<br>before the alarm even fires.</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="vsad-hero-sub">A ward-wide triage view across every bed, ranked by AI severity score, '
        'with a persistence filter that cuts noisy false alarms — the exact problem behind clinical '
        'alarm fatigue.</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(ecg_hero_svg(), unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3)
    s1.markdown(step_card_html("01", "Ingest", "Every bed streams five vitals — from the built-in "
                                "simulator, or replayed from an uploaded historical export."), unsafe_allow_html=True)
    s2.markdown(step_card_html("02", "Triage", "Beds are ranked live by a composite severity score and "
                                "the clinical-standard NEWS2 early warning score."), unsafe_allow_html=True)
    s3.markdown(step_card_html("03", "Confirm", "An alarm only fires once an abnormality persists across "
                                "several readings — filtering the noise behind real-world alarm fatigue."),
                unsafe_allow_html=True)

    st.write("")
    cta_l, cta_c, cta_r = st.columns([1, 1, 1])
    with cta_c:
        if st.button("▶ Start Ward Monitoring", use_container_width=True, type="primary"):
            if data_source == "Upload historical CSV":
                if uploaded is None:
                    st.warning("Upload a CSV first, or switch to Simulated ward.")
                    st.stop()
                try:
                    df = pd.read_csv(io.BytesIO(uploaded.getvalue()))
                    st.session_state.ward = build_ward_from_csv(df)
                except Exception as e:
                    st.error(f"Couldn't load that CSV: {e}")
                    st.stop()
            else:
                st.session_state.ward = build_simulated_ward(num_beds=num_beds)
            st.session_state.running = True
            st.rerun()
    st.stop()

ward = st.session_state.ward

# ---------------------------------------------------------------------------
# Drill-down: single-bed detail dashboard
# ---------------------------------------------------------------------------
if st.session_state.selected_bed:
    bed = ward.beds.get(st.session_state.selected_bed)
    if bed is None or bed.latest is None:
        st.session_state.selected_bed = None
        st.rerun()

    latest = bed.latest
    if st.button("← Back to ward overview", key="back_main"):
        st.session_state.selected_bed = None
        st.rerun()
    st.markdown(f'<div class="vsad-title">🩺 {bed.patient_name} · {bed.bed_id}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="vsad-subtitle">{bed.profile_name} · rule-based detection + NEWS2 + '
                f'Groq reasoning layer</div>', unsafe_allow_html=True)

    triggered = [PARAM_META[p]["label"] for p in latest["confirmed_triggered"]]
    st.markdown(alarm_banner_html(latest["confirmed_risk"], triggered), unsafe_allow_html=True)

    in_alarm = latest["confirmed_risk"] in ("Moderate", "High", "Critical")
    alarm_text = f"⚠ {latest['confirmed_risk'].upper()} — {', '.join(triggered)}" if in_alarm else ""
    readouts = "".join(
        monitor_readout_html(PARAM_META[p]["short"], latest[p], PARAM_META[p]["unit"],
                              CHANNEL_COLORS[p], is_alarm=(p in latest["confirmed_triggered"]))
        for p in PARAMS
    )
    st.markdown(monitor_panel_html(readouts, in_alarm=in_alarm, alarm_text=alarm_text), unsafe_allow_html=True)

    gauge_col, chart_col = st.columns([1, 2.4])
    with gauge_col:
        gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=latest["composite_score"],
            number={"font": {"family": "JetBrains Mono", "color": "#e7edf5"}},
            title={"text": f"Composite Score · NEWS2 {latest['news2']['total']} ({latest['news2']['band']})",
                   "font": {"size": 12, "color": "#8a97a8"}},
            gauge={"axis": {"range": [0, 100], "tickcolor": "#8a97a8"},
                   "bar": {"color": RISK_COLORS.get(latest["confirmed_risk"], "#39FF9E")},
                   "bgcolor": "rgba(0,0,0,0)",
                   "steps": [{"range": [0, 20], "color": "rgba(52,229,140,0.18)"},
                             {"range": [20, 45], "color": "rgba(255,194,75,0.18)"},
                             {"range": [45, 70], "color": "rgba(255,138,61,0.2)"},
                             {"range": [70, 100], "color": "rgba(255,71,87,0.22)"}]},
        ))
        gauge.update_layout(height=260, margin=dict(t=40, b=10, l=20, r=20),
                             paper_bgcolor="rgba(0,0,0,0)", font_color="#e7edf5")
        st.plotly_chart(gauge, use_container_width=True, config={"displayModeBar": False})

    with chart_col:
        df = pd.DataFrame(bed.agent.history)
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.14, horizontal_spacing=0.08,
                             subplot_titles=("Heart Rate", "SpO2", "Blood Pressure (systolic)", "Temperature"))
        chart_map = [("heart_rate", 1, 1), ("spo2", 1, 2), ("systolic_bp", 2, 1), ("temperature", 2, 2)]
        for p, r, c in chart_map:
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df[p], mode="lines",
                                      line=dict(color=CHANNEL_COLORS[p], width=2.5), showlegend=False), row=r, col=c)
            flagged = df[df[f"{p}_risk"].isin(["Moderate", "High"])]
            if not flagged.empty:
                fig.add_trace(go.Scatter(x=flagged["timestamp"], y=flagged[p], mode="markers",
                                          marker=dict(color="#FF3B4E", size=8, symbol="x"), showlegend=False),
                              row=r, col=c)
        fig.update_layout(height=340, margin=dict(t=30, b=10, l=10, r=10), paper_bgcolor="rgba(0,0,0,0)",
                           plot_bgcolor="rgba(255,255,255,0.02)", font_color="#8a97a8")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### 📋 Alert Log")
    if not bed.agent.alerts:
        st.caption(f"No confirmed alerts yet · {bed.agent.suppressed_count} transient blip(s) filtered so far.")
    else:
        st.caption(f"{bed.agent.suppressed_count} transient blip(s) filtered without alarming.")
        for a in reversed(bed.agent.alerts[-12:]):
            color = RISK_COLORS.get(a["risk_level"], "#8a97a8")
            pills = "".join(risk_pill_html(PARAM_META[p]["short"], latest[f"{p}_risk"]) for p in a["triggered_params"])
            st.markdown(
                f"""<div class="vsad-alert" style="border-left-color:{color};">
                    <div class="vsad-alert-meta">{a['timestamp'].strftime('%H:%M:%S')} · score {a['score']}/100 · {a['risk_level']}</div>
                    <div style="margin-bottom:6px;">{pills}</div>
                    <div class="vsad-alert-explain">{a['explanation'] or ''}</div>
                </div>""",
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Ward overview grid
# ---------------------------------------------------------------------------
else:
    st.markdown('<div class="vsad-title">🏥 Ward Overview — AI Triage</div>', unsafe_allow_html=True)
    st.markdown('<div class="vsad-subtitle">Sorted by composite severity score, highest risk first · '
                'click a bed to open its full monitor</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Beds", len(ward.beds))
    m2.metric("Critical now", ward.critical_bed_count())
    m3.metric("Confirmed alerts", ward.total_alerts())
    m4.metric("Blips filtered", ward.total_suppressed(),
              help="Readings that briefly crossed a threshold but didn't persist long enough to "
                   "become a confirmed alarm — the alarm-fatigue mitigation at work.")

    ordered = ward.ordered_bed_ids()
    cols = st.columns(4)
    for i, bed_id in enumerate(ordered):
        bed = ward.beds[bed_id]
        if bed.latest is None:
            continue
        with cols[i % 4]:
            st.markdown(bed_tile_html(bed.bed_id, bed.patient_name, bed.profile_name, bed.latest),
                        unsafe_allow_html=True)
            if st.button("Open monitor", key=f"open_{bed_id}", use_container_width=True):
                st.session_state.selected_bed = bed_id
                st.rerun()

    with st.expander("ℹ️ How this ward AI works (architecture, for judges)"):
        st.markdown("""
**Pipeline:** `Ingestion (sim or historical CSV) → Preprocessing → Per-Patient Rule Engine + NEWS2 → Persistence Filter → Alerting → AI Explanation → Ward-wide Triage Ranking`

- **AI triage:** every bed gets a composite severity score (0-100) and a real **NEWS2** early
  warning score computed independently; the grid re-sorts every reading so the sickest
  patient is always at the top-left — this is the ward-level decision-support layer, not
  just a bank of single-patient displays.
- **Alarm-fatigue mitigation:** a parameter must stay abnormal for a configurable number of
  consecutive readings before it's confirmed as an alert (see the sidebar slider). This is a
  transparent, rule-based persistence filter — explicitly not framed as ML, since real ICUs
  report the large majority of bedside alarms are non-actionable, and an honest fix here is
  a debounce rule, not a black box.
- **Data source:** simulated by default, or an uploaded CSV shaped like a flattened
  PhysioNet MIMIC-IV/eICU export, replayed per bed through the identical scoring pipeline.
  Real hospitals integrate via HL7/FHIR against live hospital infrastructure — that's out of
  scope for a hackathon build and is called out here rather than faked.
- **Drill-down:** clicking a bed opens the full single-patient dashboard — live charts,
  confirmed alert log, and a Groq-generated plain-language note per alert.

**Out of scope, and why:** a production version of this would need a time-series store
(e.g. TimescaleDB/Redis) for high-frequency multi-bed throughput, and a real ML model for
deterioration prediction (e.g. early sepsis risk) trained on historical outcomes — both
need infrastructure and licensed data this build doesn't have access to.
""")

# ---------------------------------------------------------------------------
# Step / auto-run loop
# ---------------------------------------------------------------------------
resolved_target = None if target_bed in (None, "Random bed") else target_bed

if manual:
    ward.step_all(force_anomaly=force_anomaly, force_bed_id=resolved_target, explain_fn=make_explain_fn(groq_key))
    st.rerun()

if st.session_state.running:
    ward.step_all(force_anomaly=force_anomaly, force_bed_id=resolved_target, explain_fn=make_explain_fn(groq_key))
    if sound_on and ward.critical_bed_count() > 0 and ward.total_alerts() != st.session_state.last_alarmed_count:
        st.markdown(alarm_audio_html(), unsafe_allow_html=True)
    st.session_state.last_alarmed_count = ward.total_alerts()
    time.sleep(refresh_seconds)
    st.rerun()
