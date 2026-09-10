"""
app.py
Patient Vital Sign Anomaly Detector — interactive Streamlit dashboard.

Deploy target: GitHub + Streamlit Community Cloud (see README.md).
"""

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ai_reasoning import explain_with_groq
from theme import (
    CSS_STYLE, RISK_COLORS, CHANNEL_COLORS,
    param_card_html, alarm_banner_html, risk_pill_html, alarm_audio_html,
)
from vitals_engine import (
    VitalAgentState, PATIENT_PROFILES, FORCE_ANOMALY_OPTIONS, PARAM_META, PARAMS, RISK_ORDER,
)

st.set_page_config(page_title="Vital Sign Anomaly Detector", page_icon="🩺", layout="wide")
st.markdown(CSS_STYLE, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "agent" not in st.session_state:
    st.session_state.agent = VitalAgentState()
if "running" not in st.session_state:
    st.session_state.running = False
if "profile_name" not in st.session_state:
    st.session_state.profile_name = list(PATIENT_PROFILES.keys())[0]
if "last_alarmed_alert_id" not in st.session_state:
    st.session_state.last_alarmed_alert_id = -1

agent = st.session_state.agent

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Monitor setup")

    profile_name = st.selectbox("Patient profile", list(PATIENT_PROFILES.keys()),
                                 index=list(PATIENT_PROFILES.keys()).index(st.session_state.profile_name))
    if profile_name != st.session_state.profile_name:
        st.session_state.profile_name = profile_name
        st.session_state.agent = VitalAgentState()
        st.rerun()
    ranges = PATIENT_PROFILES[profile_name]

    try:
        default_key = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        default_key = ""

    groq_key = st.text_input(
        "Groq API key", type="password",
        value=default_key,
        help="Free key: console.groq.com/keys. On Streamlit Cloud you can also "
             "set this once as a secret instead of typing it here.",
    )
    sound_on = st.checkbox("🔔 Alarm sound on Critical", value=True)
    refresh_seconds = st.slider("Reading interval (sec)", 1, 5, 2)

    st.markdown("---")
    st.markdown("### 🧪 Demo controls (for judges)")
    anomaly_label = st.selectbox("Inject a scenario on the next reading", list(FORCE_ANOMALY_OPTIONS.keys()))
    force_anomaly = FORCE_ANOMALY_OPTIONS[anomaly_label]

    c1, c2, c3 = st.columns(3)
    if c1.button("▶ Start"):
        st.session_state.running = True
    if c2.button("⏸ Stop"):
        st.session_state.running = False
    if c3.button("🔄 Reset"):
        st.session_state.agent = VitalAgentState()
        st.session_state.running = False
        st.session_state.last_alarmed_alert_id = -1
        st.rerun()

    manual = st.button("➕ Take one reading manually", use_container_width=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="vsad-title">🩺 Patient Vital Sign Anomaly Detector</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="vsad-subtitle">Live monitoring · <b>{profile_name}</b> · '
    f'rule-based detection engine + Groq reasoning layer</div>',
    unsafe_allow_html=True,
)

latest = agent.history[-1] if agent.history else None

# ---------------------------------------------------------------------------
# Alarm banner (+ optional sound on new Critical alert)
# ---------------------------------------------------------------------------
if latest:
    triggered = [PARAM_META[p]["label"] for p in PARAMS
                 if RISK_ORDER[latest[f"{p}_risk"]] >= RISK_ORDER["Moderate"]]
    st.markdown(alarm_banner_html(latest["overall_risk"], triggered), unsafe_allow_html=True)

    if (sound_on and agent.alerts and latest["overall_risk"] == "Critical"
            and agent.alerts[-1] is not None):
        last_alert_idx = len(agent.alerts) - 1
        if agent.alerts[-1]["risk_level"] == "Critical" and last_alert_idx != st.session_state.last_alarmed_alert_id:
            st.markdown(alarm_audio_html(), unsafe_allow_html=True)
            st.session_state.last_alarmed_alert_id = last_alert_idx
else:
    st.info("Press **Start** in the sidebar (or take one manual reading) to begin monitoring.")

# ---------------------------------------------------------------------------
# Parameter cards + composite gauge
# ---------------------------------------------------------------------------
if latest:
    card_cols = st.columns(5)
    for col, p in zip(card_cols, PARAMS):
        meta = PARAM_META[p]
        col.markdown(
            param_card_html(meta["short"], latest[p], meta["unit"], latest[f"{p}_risk"]),
            unsafe_allow_html=True,
        )

    gauge_col, chart_col = st.columns([1, 2.4])

    with gauge_col:
        gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=latest["composite_score"],
            number={"suffix": "", "font": {"family": "JetBrains Mono", "color": "#e7edf5"}},
            title={"text": "Composite Risk Score", "font": {"size": 13, "color": "#8a97a8"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#8a97a8"},
                "bar": {"color": RISK_COLORS.get(latest["overall_risk"], "#34E58C")},
                "bgcolor": "rgba(0,0,0,0)",
                "steps": [
                    {"range": [0, 20], "color": "rgba(52,229,140,0.18)"},
                    {"range": [20, 45], "color": "rgba(255,194,75,0.18)"},
                    {"range": [45, 70], "color": "rgba(255,138,61,0.2)"},
                    {"range": [70, 100], "color": "rgba(255,71,87,0.22)"},
                ],
            },
        ))
        gauge.update_layout(height=260, margin=dict(t=40, b=10, l=20, r=20),
                             paper_bgcolor="rgba(0,0,0,0)", font_color="#e7edf5")
        st.plotly_chart(gauge, use_container_width=True, config={"displayModeBar": False})

    with chart_col:
        df = pd.DataFrame(agent.history)
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.14,
                             horizontal_spacing=0.08,
                             subplot_titles=("Heart Rate", "SpO2", "Blood Pressure (systolic)", "Temperature"))
        chart_map = [("heart_rate", 1, 1), ("spo2", 1, 2), ("systolic_bp", 2, 1), ("temperature", 2, 2)]
        for p, r, c in chart_map:
            color = CHANNEL_COLORS[p]
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df[p], mode="lines",
                                      line=dict(color=color, width=2.5), showlegend=False), row=r, col=c)
            flagged = df[df[f"{p}_risk"].isin(["Moderate", "High"])]
            if not flagged.empty:
                fig.add_trace(go.Scatter(x=flagged["timestamp"], y=flagged[p], mode="markers",
                                          marker=dict(color="#FF4757", size=8, symbol="x"),
                                          showlegend=False), row=r, col=c)
        fig.update_layout(height=340, margin=dict(t=30, b=10, l=10, r=10),
                           paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.02)",
                           font_color="#8a97a8")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ---------------------------------------------------------------------------
# Alert log
# ---------------------------------------------------------------------------
st.markdown("#### 📋 Alert Log")
if not agent.alerts:
    st.caption("No anomalies flagged yet — alerts will appear here the moment a parameter crosses threshold.")
else:
    for a in reversed(agent.alerts[-12:]):
        color = RISK_COLORS.get(a["risk_level"], "#8a97a8")
        pills = "".join(risk_pill_html(PARAM_META[p]["short"], a["risk"][f"{p}_risk"]) for p in a["triggered_params"])
        st.markdown(
            f"""<div class="vsad-alert" style="border-left-color:{color};">
                <div class="vsad-alert-meta">{a['timestamp'].strftime('%H:%M:%S')} · score {a['score']}/100 · {a['risk_level']}</div>
                <div style="margin-bottom:6px;">{pills}</div>
                <div class="vsad-alert-explain">{a['explanation'] or ''}</div>
            </div>""",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# About / architecture — quick read for hackathon judges
# ---------------------------------------------------------------------------
with st.expander("ℹ️ How this agent works (architecture, for judges)"):
    st.markdown("""
**Pipeline:** `Ingestion → Preprocessing → Rule-Based Risk Engine → Alerting → AI Explanation Layer → Dashboard`

- **Ingestion & preprocessing** (`vitals_engine.py`) simulates a live vital-sign feed and
  filters flagged sensor artifacts — without ever smoothing away a genuine change, since
  that would defeat the point of a monitor.
- **Detection engine** scores each parameter independently against the selected patient
  profile's normal range (Normal / Low / Moderate / High), then escalates to **Critical**
  automatically when two or more parameters are abnormal at once.
- **Alerting** fires the moment any parameter reaches Moderate or above — this logic is
  deterministic and unit-testable on its own, with no dependency on the AI call succeeding.
- **AI reasoning layer** (`ai_reasoning.py`) sends only the *already-decided* risk data to
  Groq's Llama model, which writes a short plain-language note for the care team. The LLM
  never sets the risk level itself.

**Roadmap (per the product's phased plan):** this build is Phase 1 — rule-based thresholds
for a fixed parameter set. Phase 2 would swap in an ML model trained on real historical
patient data for predictive, multi-parameter risk scoring. Phase 3 would replace the
simulated feed with a real FHIR/EHR integration and real push/SMS notification channels.
""")

# ---------------------------------------------------------------------------
# Manual step / auto-run loop
# ---------------------------------------------------------------------------
def make_explain_fn(api_key):
    def _fn(reading, risk):
        triggered = [p for p in PARAMS if RISK_ORDER[risk[f"{p}_risk"]] >= RISK_ORDER["Moderate"]]
        return explain_with_groq(reading, risk, triggered, api_key=api_key)
    return _fn


if manual:
    agent.step(ranges, force_anomaly=force_anomaly, explain_fn=make_explain_fn(groq_key))
    st.rerun()

if st.session_state.running:
    agent.step(ranges, force_anomaly=force_anomaly, explain_fn=make_explain_fn(groq_key))
    time.sleep(refresh_seconds)
    st.rerun()
