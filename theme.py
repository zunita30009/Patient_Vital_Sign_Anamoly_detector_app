"""
theme.py
Visual language for the dashboard: a dark, multi-channel bedside-monitor
aesthetic. Colors follow real patient-monitor convention (ECG=green,
SpO2=cyan, NIBP=amber, Temp=yellow) so the coding is meaningful, not
decorative — a judge who's ever seen a hospital monitor will recognize
it instantly.
"""

import base64
import io
import math
import struct
import wave

# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------

BG = "#0a0e14"
PANEL = "#141b26"
PANEL_BORDER = "rgba(255,255,255,0.12)"
TEXT = "#f3f6fa"
TEXT_DIM = "#98a5b8"

CHANNEL_COLORS = {
    "heart_rate": "#39FF9E",     # ECG green
    "spo2": "#38D6F5",           # SpO2 cyan
    "systolic_bp": "#FF9A3C",    # NIBP orange
    "temperature": "#FFD93D",    # Temp yellow
    "resp_rate": "#C792EA",      # Respiration violet
}

# A clear green -> cyan -> yellow -> orange -> red escalation, each step
# visually distinct at a glance (the earlier green/yellow-green pairing
# for Normal/Low was too close in hue to tell apart quickly).
RISK_COLORS = {
    "Normal": "#39FF9E",
    "Low": "#3DDDD3",
    "Moderate": "#FFD93D",
    "High": "#FF9A3C",
    "Critical": "#FF3B4E",
}

# Light theme — used only for the pre-monitoring entrance screen. The dark
# ICU-monitor theme above is used once real readings start coming in.
LIGHT_BG = "#F5F8FB"
LIGHT_PANEL = "#FFFFFF"
LIGHT_PANEL_BORDER = "rgba(15,23,42,0.08)"
LIGHT_TEXT = "#0F172A"
LIGHT_TEXT_DIM = "#5B6B82"
ACCENT = "#0EA5A4"      # teal — the one bold accent on the entrance screen
ACCENT_DEEP = "#155E75"

# Streamlit's own chrome (main menu, footer, the top decoration bar, the
# floating toolbar/status widget) — hidden everywhere, in both themes.
# display:none removes the space entirely, unlike visibility:hidden.
CHROME_CSS = """
<style>
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    display: none !important;
    height: 0 !important;
}
.block-container { padding-top: 1.4rem !important; }
</style>
"""

FONT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');
</style>
"""

CSS_STYLE = CHROME_CSS + FONT_CSS + """
<style>
html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
.stApp {
    background: radial-gradient(circle at 15% 0%, #101823 0%, #0a0e14 55%);
    color: __TEXT__;
}
#MainMenu, footer, header {visibility: hidden;}
.block-container { max-width: 1200px; }

.vsad-title { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0; }
.vsad-subtitle { color: __TEXT_DIM__; font-size: 0.95rem; margin-top: 2px; margin-bottom: 1.2rem; }

.vsad-mono { font-family: 'JetBrains Mono', monospace; }

/* Alarm banner */
.vsad-banner {
    border-radius: 12px;
    padding: 14px 20px;
    margin-bottom: 1.1rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.95rem;
    display: flex;
    align-items: center;
    gap: 12px;
    border: 1px solid rgba(255,255,255,0.08);
}
.vsad-banner-normal { background: rgba(52,229,140,0.08); color: #B7F5D2; }
.vsad-banner-warning {
    background: rgba(255,217,61,0.12); color: #FFE4B0;
    animation: vsad-pulse-warn 1.8s ease-in-out infinite;
}
.vsad-banner-critical {
    background: rgba(255,59,78,0.16); color: #FFC9CE;
    animation: vsad-pulse-crit 1s ease-in-out infinite;
}
@keyframes vsad-pulse-warn {
    0%, 100% { box-shadow: 0 0 0px rgba(255,217,61,0); }
    50% { box-shadow: 0 0 22px rgba(255,217,61,0.45); }
}
@keyframes vsad-pulse-crit {
    0%, 100% { box-shadow: 0 0 0px rgba(255,59,78,0); }
    50% { box-shadow: 0 0 28px rgba(255,59,78,0.65); }
}

/* Parameter cards */
.vsad-card {
    background: __PANEL__;
    border: 1px solid __PANEL_BORDER__;
    border-radius: 12px;
    padding: 14px 16px;
    height: 100%;
}
.vsad-card-label {
    font-size: 0.72rem; letter-spacing: 0.06em; color: __TEXT_DIM__;
    text-transform: uppercase; margin-bottom: 4px;
}
.vsad-card-value {
    font-family: 'JetBrains Mono', monospace; font-size: 1.9rem; font-weight: 700;
    line-height: 1.1;
}
.vsad-card-unit { font-size: 0.85rem; color: __TEXT_DIM__; font-weight: 400; margin-left: 4px; }
.vsad-card-risk {
    display: inline-block; margin-top: 8px; font-size: 0.72rem; font-weight: 600;
    padding: 2px 9px; border-radius: 999px;
}

/* Alert log */
.vsad-alert {
    border-left: 4px solid;
    background: rgba(255,255,255,0.03);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 0.88rem;
}
.vsad-alert-meta { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: __TEXT_DIM__; margin-bottom: 4px; }
.vsad-alert-explain { color: __TEXT__; font-style: italic; }

.vsad-pill {
    display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 600;
    margin-right: 4px;
}

/* Ward grid */
.vsad-bed {
    background: __PANEL__; border: 1px solid __PANEL_BORDER__; border-radius: 12px;
    padding: 12px 14px; margin-bottom: 8px;
}
.vsad-bed-critical { border-color: rgba(255,59,78,0.55); animation: vsad-pulse-crit 1.2s ease-in-out infinite; }
.vsad-bed-high { border-color: rgba(255,154,60,0.5); }
.vsad-bed-id { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: __TEXT_DIM__; }
.vsad-bed-name { font-weight: 600; font-size: 1rem; margin: 2px 0 6px 0; }
.vsad-bed-score { font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 700; }
.vsad-bed-vitals { font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; color: __TEXT_DIM__; margin-top: 6px; }

/* Bedside monitor bezel (drill-down screen) */
.vsad-monitor {
    background: #000000;
    border: 3px solid #1c2531;
    border-radius: 14px;
    padding: 14px 10px 6px 10px;
    margin-bottom: 1rem;
}
.vsad-monitor-alarm {
    border-color: #FF3B4E;
    animation: vsad-monitor-flash 0.9s ease-in-out infinite;
}
@keyframes vsad-monitor-flash {
    0%, 100% { box-shadow: 0 0 0px rgba(255,59,78,0); }
    50% { box-shadow: 0 0 26px rgba(255,59,78,0.75); }
}
.vsad-monitor-topbar {
    display: flex; justify-content: space-between; align-items: center;
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: __TEXT_DIM__;
    padding: 0 6px 10px 6px;
}
.vsad-monitor-alarmtag {
    color: #FF3B4E; font-weight: 700; letter-spacing: 0.08em;
    animation: vsad-blink 0.6s steps(1) infinite;
}
@keyframes vsad-blink { 50% { opacity: 0.15; } }

.vsad-readout {
    border-right: 1px solid rgba(255,255,255,0.08);
    padding: 6px 12px;
    text-align: left;
}
.vsad-readout:last-child { border-right: none; }
.vsad-readout-label {
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 2px;
}
.vsad-readout-value {
    font-family: 'JetBrains Mono', monospace; font-size: 2.3rem; font-weight: 700; line-height: 1;
}
.vsad-readout-unit { font-size: 0.75rem; font-weight: 400; opacity: 0.75; margin-left: 3px; }
.vsad-readout-alarm {
    animation: vsad-blink 0.5s steps(1) infinite;
}

/* Buttons — override Streamlit's default white button so it's readable
   against the dark theme (this was invisible: white bg, near-white text).
   Multiple selectors because Streamlit's internal button markup has
   changed across versions — this covers both old and current DOM shapes. */
.stButton > button,
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"] {
    background: __PANEL__ !important;
    color: __TEXT__ !important;
    border: 1px solid rgba(255,255,255,0.35) !important;
}
.stButton > button:hover,
[data-testid="stBaseButton-secondary"]:hover,
[data-testid="baseButton-secondary"]:hover {
    border-color: #39FF9E !important;
    color: __TEXT__ !important;
    background: rgba(57,255,158,0.08) !important;
}
.stButton > button *,
[data-testid="stBaseButton-secondary"] *,
[data-testid="baseButton-secondary"] * {
    color: __TEXT__ !important;
    fill: __TEXT__ !important;
}
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"],
[data-testid="baseButton-primary"] {
    background: #39FF9E !important;
    border: none !important;
}
.stButton > button[kind="primary"] *,
[data-testid="stBaseButton-primary"] *,
[data-testid="baseButton-primary"] * {
    color: #04241a !important;
    fill: #04241a !important;
}
[data-testid="stSidebar"] { background: __PANEL__; }
[data-testid="stSidebar"] * { color: __TEXT__ !important; }
</style>
"""
CSS_STYLE = (CSS_STYLE
             .replace("__TEXT_DIM__", TEXT_DIM)
             .replace("__TEXT__", TEXT)
             .replace("__PANEL_BORDER__", PANEL_BORDER)
             .replace("__PANEL__", PANEL))


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

def param_card_html(label: str, value, unit: str, risk: str) -> str:
    color = RISK_COLORS.get(risk, TEXT_DIM)
    return f"""
    <div class="vsad-card">
        <div class="vsad-card-label">{label}</div>
        <div class="vsad-card-value">{value}<span class="vsad-card-unit"> {unit}</span></div>
        <div class="vsad-card-risk" style="background:{color}22; color:{color};">{risk}</div>
    </div>
    """


def monitor_readout_html(label: str, value, unit: str, channel_color: str, is_alarm: bool) -> str:
    """One numeric readout in a real bedside-monitor's numeric column: big
    mono digits in the channel's own color, flashing when THIS specific
    parameter (not just the overall banner) is in a confirmed alarm state."""
    alarm_cls = "vsad-readout-alarm" if is_alarm else ""
    return f"""
    <div class="vsad-readout">
        <div class="vsad-readout-label" style="color:{channel_color};">{label}</div>
        <div class="vsad-readout-value {alarm_cls}" style="color:{channel_color};">{value}<span class="vsad-readout-unit">{unit}</span></div>
    </div>
    """


def monitor_panel_html(readouts_html: str, in_alarm: bool, alarm_text: str = "") -> str:
    cls = "vsad-monitor vsad-monitor-alarm" if in_alarm else "vsad-monitor"
    topbar = (f'<div class="vsad-monitor-topbar"><span>BEDSIDE MONITOR</span>'
              f'<span class="vsad-monitor-alarmtag">{alarm_text}</span></div>' if in_alarm else
              '<div class="vsad-monitor-topbar"><span>BEDSIDE MONITOR</span><span>ALL PARAMS NOMINAL</span></div>')
    return f"""
    <div class="{cls}">
        {topbar}
        <div style="display:flex;">{readouts_html}</div>
    </div>
    """


def alarm_banner_html(overall_risk: str, triggered_labels: list) -> str:
    if overall_risk in ("Normal", "Low"):
        cls = "vsad-banner-normal"
        icon = "✅"
        msg = "All monitored parameters within expected range."
    elif overall_risk in ("Moderate", "High"):
        cls = "vsad-banner-warning"
        icon = "⚠️"
        msg = f"{overall_risk.upper()} RISK — flagged: " + ", ".join(triggered_labels)
    else:
        cls = "vsad-banner-critical"
        icon = "🚨"
        msg = "CRITICAL — multiple parameters abnormal simultaneously: " + ", ".join(triggered_labels)
    return f'<div class="vsad-banner {cls}"><span style="font-size:1.3rem;">{icon}</span><span>{msg}</span></div>'


def risk_pill_html(label: str, risk: str) -> str:
    color = RISK_COLORS.get(risk, TEXT_DIM)
    return f'<span class="vsad-pill" style="background:{color}22; color:{color};">{label}: {risk}</span>'


def bed_tile_html(bed_id: str, name: str, profile_name: str, reading: dict) -> str:
    risk = reading["confirmed_risk"]
    cls = "vsad-bed"
    if risk == "Critical":
        cls += " vsad-bed-critical"
    elif risk == "High":
        cls += " vsad-bed-high"
    color = RISK_COLORS.get(risk, TEXT_DIM)
    news2 = reading["news2"]
    news2_color = {"Low": RISK_COLORS["Normal"], "Medium": RISK_COLORS["Moderate"],
                   "High": RISK_COLORS["High"]}.get(news2["band"], TEXT_DIM)
    return f"""
    <div class="{cls}">
        <div class="vsad-bed-id">{bed_id} · {profile_name}</div>
        <div class="vsad-bed-name">{name}</div>
        <div class="vsad-bed-score" style="color:{color};">{reading['composite_score']}<span style="font-size:0.7rem; color:{TEXT_DIM};"> /100</span></div>
        <span class="vsad-card-risk" style="background:{color}22; color:{color};">{risk}</span>
        <span class="vsad-pill" style="background:{news2_color}22; color:{news2_color};">NEWS2 {news2['total']}</span>
        <div class="vsad-bed-vitals">HR {reading['heart_rate']} · SpO2 {reading['spo2']}% · NIBP {reading['systolic_bp']} · T {reading['temperature']}°C · RR {reading['resp_rate']}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Alarm tone — generated in-process (no external audio file needed)
# ---------------------------------------------------------------------------

def beep_data_uri(freq: int = 880, duration: float = 0.35, volume: float = 0.35) -> str:
    """Return a data: URI for a short sine-wave beep, for an autoplay <audio> tag."""
    rate = 22050
    n_samples = int(rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(n_samples):
            t = i / rate
            sample = volume * math.sin(2 * math.pi * freq * t)
            # quick fade-out to avoid a click at the end
            fade = min(1.0, (n_samples - i) / (rate * 0.05))
            wf.writeframes(struct.pack("<h", int(sample * fade * 32767)))
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{b64}"


def alarm_audio_html(freq: int = 880) -> str:
    uri = beep_data_uri(freq=freq)
    return f'<audio autoplay="true" src="{uri}"></audio>'


# ---------------------------------------------------------------------------
# LIGHT THEME — entrance screen only
# ---------------------------------------------------------------------------

LIGHT_CSS_STYLE = CHROME_CSS + FONT_CSS + """
<style>
.stApp {
    background: __LIGHT_BG__ !important;
    color: __LIGHT_TEXT__ !important;
}
.block-container { max-width: 900px; padding-top: 2rem; }
[data-testid="stSidebar"] {
    background: __LIGHT_PANEL__ !important;
    border-right: 1px solid __LIGHT_PANEL_BORDER__;
}
[data-testid="stSidebar"] * { color: __LIGHT_TEXT__ !important; }

.vsad-hero { text-align: center; padding: 1.2rem 0 0.4rem 0; }
.vsad-hero-eyebrow {
    font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: __ACCENT__;
    letter-spacing: 0.04em; margin-bottom: 10px;
}
.vsad-hero-title {
    font-size: 2.6rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1.1;
    color: __LIGHT_TEXT__; margin-bottom: 14px;
}
.vsad-hero-sub {
    font-size: 1.05rem; color: __LIGHT_TEXT_DIM__; max-width: 620px; margin: 0 auto 1.6rem auto;
    line-height: 1.55;
}

.vsad-step-card {
    background: __LIGHT_PANEL__; border: 1px solid __LIGHT_PANEL_BORDER__; border-radius: 14px;
    padding: 20px 18px; height: 100%;
}
.vsad-step-num {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: __ACCENT__; font-weight: 700;
    margin-bottom: 8px;
}
.vsad-step-title { font-weight: 600; font-size: 1.02rem; margin-bottom: 6px; color: __LIGHT_TEXT__; }
.vsad-step-body { font-size: 0.88rem; color: __LIGHT_TEXT_DIM__; line-height: 1.5; }

.vsad-ecg-wrap { display: flex; justify-content: center; margin: 0.4rem 0 1.6rem 0; }
</style>
"""
LIGHT_CSS_STYLE = (LIGHT_CSS_STYLE
                    .replace("__LIGHT_BG__", LIGHT_BG)
                    .replace("__LIGHT_PANEL_BORDER__", LIGHT_PANEL_BORDER)
                    .replace("__LIGHT_PANEL__", LIGHT_PANEL)
                    .replace("__LIGHT_TEXT_DIM__", LIGHT_TEXT_DIM)
                    .replace("__LIGHT_TEXT__", LIGHT_TEXT)
                    .replace("__ACCENT__", ACCENT))


def ecg_hero_svg(width: int = 460, height: int = 90) -> str:
    """
    A single animated ECG trace — the one deliberate moment of motion on the
    entrance screen (the line draws itself once, then holds), grounded in
    the product's actual subject matter rather than decorative flourish.
    """
    path = (
        f"M0,{height*0.5} L{width*0.16},{height*0.5} "
        f"L{width*0.22},{height*0.5} L{width*0.26},{height*0.15} L{width*0.30},{height*0.85} "
        f"L{width*0.34},{height*0.5} L{width*0.42},{height*0.5} "
        f"L{width*0.5},{height*0.5} L{width*0.55},{height*0.3} L{width*0.6},{height*0.5} "
        f"L{width*0.68},{height*0.5} L{width*0.74},{height*0.15} L{width*0.78},{height*0.85} "
        f"L{width*0.82},{height*0.5} L{width},{height*0.5}"
    )
    return f"""
    <div class="vsad-ecg-wrap">
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="{path}" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
              stroke-dasharray="1400" stroke-dashoffset="1400">
            <animate attributeName="stroke-dashoffset" from="1400" to="0" dur="1.6s" fill="freeze" />
        </path>
    </svg>
    </div>
    """


def step_card_html(number: str, title: str, body: str) -> str:
    return f"""
    <div class="vsad-step-card">
        <div class="vsad-step-num">{number}</div>
        <div class="vsad-step-title">{title}</div>
        <div class="vsad-step-body">{body}</div>
    </div>
    """
