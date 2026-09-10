"""
ai_reasoning.py
The "agent" layer on top of the deterministic rule engine in
vitals_engine.py. Groq (fast Llama inference) turns an already-decided
risk level into a short, clinician-readable note. It never sets the risk
level itself — that keeps the safety-critical path testable and correct
even when this call is slow, rate-limited, or unavailable.
"""

import os

from vitals_engine import PARAM_META

DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _format_abnormal(reading: dict, risk: dict, triggered_params: list) -> str:
    lines = []
    for p in triggered_params:
        meta = PARAM_META[p]
        lines.append(f"- {meta['label']}: {reading[p]} {meta['unit']} (risk: {risk[f'{p}_risk']})")
    return "\n".join(lines) if lines else "- (no parameters currently above threshold)"


def explain_with_groq(reading: dict, risk: dict, triggered_params: list,
                       api_key: str | None = None, model: str = DEFAULT_MODEL) -> str:
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Add a Groq API key in the sidebar to get an AI-generated clinical note for this alert."

    try:
        from groq import Groq
    except ImportError:
        return "The `groq` package isn't installed — add it to requirements.txt."

    abnormal = _format_abnormal(reading, risk, triggered_params)

    prompt = f"""You are a clinical decision-support assistant reviewing vitals
that a rule-based patient monitor already scored as {risk['overall_risk']} risk.

Abnormal parameters:
{abnormal}

In 2-3 short sentences: describe what clinical pattern this combination
suggests and one concrete next step for the care team. Do not give a
diagnosis. Do not just repeat the numbers — interpret them."""

    try:
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=160,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"AI explanation unavailable right now ({e})."
