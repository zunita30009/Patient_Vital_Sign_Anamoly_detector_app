# 🏥 Ward Vital Sign Anomaly Detector — AI Triage Dashboard

A multi-bed ward monitoring dashboard: every bed streams five vitals
(Heart Rate, SpO2, Blood Pressure, Temperature, Respiratory Rate), gets
scored by a rule-based engine **and** a real clinical **NEWS2** early
warning score, and the whole ward grid re-sorts live so the sickest
patient is always top-left — AI triage, not just a bank of single-patient
displays. An alarm only fires once an abnormality persists across
several readings, directly targeting the real-world "alarm fatigue"
problem where most bedside alarms are non-actionable noise. Click any
bed to drill into its full live dashboard with charts, alert log, and a
Groq-generated plain-language note per alert. Built for GitHub +
**Streamlit Community Cloud**.

## Honest scope note

This build does **not** include a real HL7/FHIR hospital integration,
a live time-series database (Redis/TimescaleDB), or a trained ML
deterioration-prediction model — those need real hospital
infrastructure, licensed patient data, and time this project doesn't
have. What it does include: a severity-ranked ward view, a real NEWS2
score, an explainable rule-based alarm-fatigue mitigation, and a
data-source layer that can replay an uploaded historical CSV shaped
like a flattened MIMIC-IV/eICU export instead of the built-in
simulator. The in-app "How this ward AI works" panel says all of this
to judges directly — nothing here is oversold.

## What's in this repo

| File | Purpose |
|---|---|
| `app.py` | The dashboard — entrance screen → ward grid → per-bed drill-down |
| `ward.py` | Multi-bed orchestration: bed roster, severity sort, CSV replay mode |
| `vitals_engine.py` | Simulated ingestion, artifact filtering, rule-based risk engine, NEWS2, alarm-fatigue debounce |
| `ai_reasoning.py` | Sends already-decided alerts to Groq for a plain-language explanation |
| `theme.py` | Dark bedside-monitor dashboard theme + light entrance-screen theme + alarm sound generator |
| `requirements.txt` | Python packages Streamlit Cloud installs automatically |
| `.streamlit/config.toml` | Dark theme colors |
| `.streamlit/secrets.toml.example` | Template for your API key (copy it, don't commit the real one) |

---

## Part 1 — Get your project on GitHub (beginner steps)

You only need a free [GitHub account](https://github.com/join).

### Option A: upload through the browser (no command line needed)
1. Go to https://github.com/new, name the repo (e.g. `vital-sign-agent`), keep it **Public** (Streamlit Cloud's free tier needs this, or a linked private repo), click **Create repository**.
2. On the new repo page, click **"uploading an existing file"**.
3. Drag in every file from this project — `app.py`, `ward.py`, `vitals_engine.py`, `ai_reasoning.py`, `theme.py`, `requirements.txt`, and the `.streamlit` folder (upload `config.toml` and `secrets.toml.example` — GitHub will recreate the folder for you).
4. Scroll down, click **Commit changes**.

### Option B: using Git (if you have it installed)
```bash
git init
git add .
git commit -m "Initial commit: vital sign anomaly detector"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/vital-sign-agent.git
git push -u origin main
```

> ⚠️ Never commit a real `secrets.toml` with your API key inside it — the
> `.gitignore` file already prevents this by accident.

---

## Part 2 — Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and **sign in with your GitHub account**.
2. Click **"Create app"** → **"Deploy a public app from GitHub"**.
3. Pick:
   - **Repository:** the one you just created
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Before clicking Deploy, open **"Advanced settings" → Secrets** and paste:
   ```
   GROQ_API_KEY = "your-real-groq-key-here"
   ```
   (Get a free key first at https://console.groq.com/keys — sign up, then
   "Create API Key". This step means judges never see your key, and you
   won't have to paste it into the sidebar every demo.)
5. Click **Deploy**. First build takes 1–3 minutes.
6. You'll get a public URL like `https://vital-sign-agent-yourname.streamlit.app` — this is what you share with hackathon judges.

### Updating the app later
Any time you push a new commit to `main` on GitHub, Streamlit Cloud
automatically redeploys — no extra step needed.

---

## Part 3 — Running it locally first (optional but recommended)

```bash
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste your real Groq key
streamlit run app.py
```
Opens at `http://localhost:8501`.

---

## Demoing this to hackathon judges (90-second script)

1. **Land on the entrance screen** — the pitch is about ward-level triage,
   not a single monitor. Click **Start Ward Monitoring** (Simulated ward,
   ~16 beds is a good demo size).
2. **The ward grid appears, sorted by severity.** Point out the top metrics
   (Beds / Critical now / Confirmed alerts / Blips filtered) and explain
   that the grid re-sorts every reading — the sickest patient always
   surfaces to the top automatically.
3. **Open "How this ward AI works"** briefly to show the pipeline and the
   explicit, honest "out of scope" section — this is where you show
   judges you understand production constraints, not just demo tricks.
4. **Use the "Clinical Simulation Suite"** in the sidebar: pick a scenario
   (e.g. *"Critical multi-parameter event"*), target a specific bed, and
   click **Advance one reading** a couple of times. Show that the first
   abnormal reading is filtered as a "blip" and the alarm only confirms
   once it persists — this is the alarm-fatigue mitigation in action.
5. **Click into the flagged bed** to show the full single-patient
   dashboard: live charts, NEWS2 score, and (if a Groq key is configured)
   a plain-language clinical note per alert.
6. **Mention the roadmap**: real deployment would replace the simulator
   with an HL7/FHIR feed and add a time-series store for throughput —
   name-drop this proactively so judges see you already know it.

---

## How the "AI" in this actually works

Three separate, honestly-scoped pieces:
- **Patient-specific rule engine** (`vitals_engine.py`) — deterministic thresholds against each patient profile's own normal range. No ML, no network dependency, fully testable.
- **NEWS2** — the real, population-standard early warning score used across NHS wards, computed independently as a cross-check against the rule engine's own severity number.
- **Groq LLM** — called only *after* an alert is already confirmed, purely to write a plain-language note. It never decides risk; if the API is unavailable, alerting still works, you just don't get the note.

None of this claims to be a trained predictive model. If asked "is this
actually AI," the honest answer is: rule-based detection + a standard
clinical score + an LLM explanation layer — which is a legitimate,
explainable clinical decision-support pattern, and arguably safer than a
black-box model for a first version.

## What a real next phase would need

- **HL7/FHIR integration** against a real hospital's Epic/Cerner instance, replacing the simulator entirely.
- **A time-series store** (TimescaleDB/Redis) to handle real multi-bed, high-frequency throughput without bottlenecking the UI.
- **A trained deterioration-prediction model** (e.g. early sepsis or cardiac-event risk) built on licensed historical outcomes data (MIMIC-IV/eICU require a completed PhysioNet credentialing process — they can't be casually downloaded).
- **ML-based artifact detection** (motion/noise vs. true arrhythmia) to replace today's simple flagged-artifact smoothing.

