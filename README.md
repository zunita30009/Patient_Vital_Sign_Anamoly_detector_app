# 🩺 Patient Vital Sign Anomaly Detector — AI Agent

A live-monitoring dashboard that simulates a multi-parameter patient feed
(Heart Rate, SpO2, Blood Pressure, Temperature, Respiratory Rate), scores
every reading against a rule-based anomaly engine, escalates to a
**Critical** alarm when multiple parameters go abnormal together, and
uses **Groq** to explain each alert in plain clinical language. Built
for GitHub + **Streamlit Community Cloud**.

## What's in this repo

| File | Purpose |
|---|---|
| `app.py` | The dashboard — this is the file Streamlit runs |
| `vitals_engine.py` | Simulated ingestion, artifact filtering, rule-based multi-parameter risk engine |
| `ai_reasoning.py` | Sends already-decided alerts to Groq for a plain-language explanation |
| `theme.py` | Dark, bedside-monitor-style visual design + alarm sound generator |
| `requirements.txt` | Python packages Streamlit Cloud installs automatically |
| `.streamlit/config.toml` | Dark theme colors |
| `.streamlit/secrets.toml.example` | Template for your API key (copy it, don't commit the real one) |

---

## Part 1 — Get your project on GitHub (beginner steps)

You only need a free [GitHub account](https://github.com/join).

### Option A: upload through the browser (no command line needed)
1. Go to https://github.com/new, name the repo (e.g. `vital-sign-agent`), keep it **Public** (Streamlit Cloud's free tier needs this, or a linked private repo), click **Create repository**.
2. On the new repo page, click **"uploading an existing file"**.
3. Drag in every file from this project — `app.py`, `vitals_engine.py`, `ai_reasoning.py`, `theme.py`, `requirements.txt`, and the `.streamlit` folder (upload `config.toml` and `secrets.toml.example` — GitHub will recreate the folder for you).
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

## Demoing this to hackathon judges (60-second script)

1. **Open the app** — point out the five live parameter cards (HR, SpO2,
   NIBP, Temp, RR) and the Composite Risk Score gauge; explain each is
   scored independently against the selected patient profile's normal
   range.
2. **Switch patient profile** in the sidebar (e.g. Pediatric → ICU) to
   show the thresholds are patient-specific, not one-size-fits-all.
3. **Use "Demo controls"** in the sidebar: pick a scenario like *"Critical
   multi-parameter event"* and click **Start** (or take one manual
   reading). Watch the alarm banner flash, the gauge jump, and — if you
   added a Groq key — a plain-language explanation appear in the Alert
   Log.
4. **Open "How this agent works"** at the bottom to show the pipeline
   diagram and explain why the AI only *explains* decisions instead of
   *making* them (keeps the safety-critical alerting deterministic).
5. **Mention the roadmap**: this is Phase 1 (rule-based) of a 3-phase
   plan — Phase 2 swaps in an ML model trained on real patient history,
   Phase 3 connects to a real FHIR/EHR feed.

---

## How the "AI agent" actually works

The rule engine (`vitals_engine.py`) is 100% deterministic — it decides
risk levels and fires alerts with no dependency on any network call, so
it keeps working even if Groq is slow or down. Groq's LLM is only called
**after** an alert already exists, purely to translate the decision into
a short note a nurse could read at a glance. This separation is a
deliberate safety choice, not a shortcut — it means the part of the
system that actually raises alarms is fully testable and explainable.

## Roadmap

- ✅ **Phase 1 (this build):** multi-parameter rule-based thresholds,
  patient-specific normal ranges, artifact filtering, live dashboard,
  Critical escalation on combined abnormalities.
- **Phase 2:** ML-based predictive risk scoring trained on real
  historical, multi-parameter patient data.
- **Phase 3:** real ingestion via FHIR/EHR integration and real
  push/SMS notification channels, replacing the simulated feed.
