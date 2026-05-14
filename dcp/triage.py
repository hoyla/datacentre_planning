"""Stage 1 triage: given an application's metadata + description, classify it
against the rubric in data/triage_labelling/rubric.md.

Returns a structured verdict + worth-deep-read + signals + why + confidence.
Designed to lean false-positive (Luke 2026-05-13): better to mark something
DC/adjacent that turns out to be unrelated than miss a real DC.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from dcp.llm import LLMBackend, LLMResponse

log = logging.getLogger(__name__)

Verdict = Literal["DC", "adjacent", "unrelated", "unknown"]
DeepRead = Literal["yes", "no", "maybe"]
Confidence = Literal["sure", "probable", "guessing"]

SYSTEM_PROMPT = """\
You triage UK data-centre planning applications for an investigative journalism project.
The story angle: data centres marketed as green/renewable often have on-site fossil-fuel
generation (gas turbines, CHP, diesel) buried in their planning records. We're building a
national dataset and you classify each application before any documents are downloaded.

You'll see the application metadata (council, app type, address, dates) and the planning
officer's description text. Decide:

1. **verdict** — is this a data-centre application?
   - "DC": a new data centre build, or substantial DC redevelopment
   - "adjacent": DC-related infrastructure that isn't itself a new DC
       (substation on a DC campus, cable to a DC, supporting kit)
   - "unrelated": "data centre" keyword matched but isn't a DC application
       (access roads, NMAs referencing past DC use, conditions discharges where
        the parent permission is the substantive DC application)
   - "unknown": insufficient information; DC embedded in mixed-use of unclear scale

   **Lean inclusive.** If genuinely unsure between adjacent and unrelated, choose adjacent.
   If unsure between DC and adjacent, choose DC. We can manually reject false positives
   downstream; we cannot recover false negatives.

2. **worth_deep_read** — would the document bundle likely yield power-infrastructure
   findings?
   - "yes": description names power-related infrastructure (generators, substations,
       energy centre, gas, fuel storage, etc.), or substantial hyperscale DC where
       generation kit is expected
   - "maybe": sparse description, mixed signals, ambiguous (e.g. substation alone)
   - "no": unrelated verdicts; routine ancillary works unlikely to disclose power kit

   Lean toward "yes"/"maybe" over "no" when uncertain.

3. **signals** — power-related terms present in the description. Examples:
   energy centre, power station, gas turbine, CHP, gas-fired, gas reciprocating engine,
   energy reserve, onsite generation, microgrid, behind-the-meter, biomass, hydrogen,
   fuel cell, BESS, battery energy storage, generator, emergency generator, backup,
   standby, generator yard, diesel, gas, LPG, propane, fuel storage, fuel tanks,
   substation, electricity substation, electrical infrastructure, kiosk substation,
   water cooling, water pumping, hyperscale, NSIP, data centre campus.

   Only include terms genuinely present in the description; don't infer from context.

4. **why** — one short sentence citing description text or naming the dominant factor.

5. **confidence** in the generation-signal call:
   - "sure": strong, unambiguous signals
   - "probable": some signals but ambiguity remains
   - "guessing": sparse description or weak signals

**Key calibration rules:**
- Emergency / backup generators alone are NOT a finding — every DC has them. They're a
  *deep-read trigger* (worth_deep_read="yes", confidence likely "probable", not "sure").
  The journalism question is whether they're truly outage-only or used for grid services.
- "Substation" alone is moderate signal; substations exist for many reasons. Higher
  confidence requires explicit generation language (CHP, gas turbine, energy centre,
  power station, hydrogen, biomass, etc.).
- Air-cooled DCs are common and often the greener variant. Generic "cooling" and "air
  cooling" are NOT strong signals; "water cooling" and "water pumping" ARE (local
  environmental impact).
- A conditions-discharge or NMA application is usually "unrelated" — the *parent*
  application carries the substantive content and will be captured separately.
- Grid-connection mentions are common in any large application; ignore unless paired
  with other generation language.

Return strict JSON, no prose outside the JSON. Schema:

{
  "verdict": "DC" | "adjacent" | "unrelated" | "unknown",
  "worth_deep_read": "yes" | "no" | "maybe",
  "signals": ["..."],
  "why": "...",
  "confidence": "sure" | "probable" | "guessing"
}
"""


def render_user_message(app: dict) -> str:
    """Build the per-application user prompt."""
    parts = [
        f"Application: {app.get('ref') or '?'}",
        f"Council: {app.get('council') or '?'}",
    ]
    if app.get("app_type"):
        parts.append(f"App type: {app['app_type']}")
    if app.get("date_received"):
        parts.append(f"Date received: {app['date_received']}")
    if app.get("status"):
        parts.append(f"Status: {app['status']}")
    if app.get("address"):
        parts.append(f"Address: {app['address']}")
    parts.append("")
    parts.append("Description:")
    parts.append(app.get("description") or "(no description)")
    return "\n".join(parts)


@dataclass
class TriageVerdict:
    verdict: Verdict | str
    worth_deep_read: DeepRead | str
    signals: list[str] = field(default_factory=list)
    why: str = ""
    confidence: Confidence | str = "guessing"
    raw_response: str = ""  # the raw LLM text, for debugging


_VALID_VERDICTS = {"DC", "adjacent", "unrelated", "unknown"}
_VALID_DEEP_READS = {"yes", "no", "maybe"}
_VALID_CONFIDENCE = {"sure", "probable", "guessing"}


def parse_response(text: str) -> TriageVerdict:
    """Extract the JSON object from the LLM response and validate fields.

    Tolerates leading/trailing prose and code fences — the prompt asks for strict JSON
    but Ollama / smaller models often add wrappers.
    """
    # Strip code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```\s*$", "", cleaned)
    # Find the first JSON object in the cleaned text
    m = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not m:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    obj = json.loads(m.group(0))

    verdict = str(obj.get("verdict", "")).strip()
    if verdict not in _VALID_VERDICTS:
        # Common LLM slip: lowercase, or "data centre" instead of "DC"
        v_lower = verdict.lower()
        if v_lower == "dc" or "data" in v_lower:
            verdict = "DC"
        elif "adjac" in v_lower:
            verdict = "adjacent"
        elif "unrelat" in v_lower:
            verdict = "unrelated"
        elif "unknown" in v_lower:
            verdict = "unknown"
        # else: leave as-is, caller can flag

    worth_deep_read = str(obj.get("worth_deep_read", "")).strip().lower()
    if worth_deep_read not in _VALID_DEEP_READS:
        if worth_deep_read.startswith(("yes", "y")):
            worth_deep_read = "yes"
        elif worth_deep_read.startswith(("no", "n")):
            worth_deep_read = "no"
        elif worth_deep_read.startswith("may"):
            worth_deep_read = "maybe"

    confidence = str(obj.get("confidence", "guessing")).strip().lower()
    if confidence not in _VALID_CONFIDENCE:
        if confidence.startswith("sure"):
            confidence = "sure"
        elif confidence.startswith("prob"):
            confidence = "probable"
        elif confidence.startswith("guess"):
            confidence = "guessing"

    signals_raw = obj.get("signals", [])
    if isinstance(signals_raw, str):
        signals = [s.strip() for s in signals_raw.split(",") if s.strip()]
    elif isinstance(signals_raw, list):
        signals = [str(s).strip() for s in signals_raw if str(s).strip()]
    else:
        signals = []

    return TriageVerdict(
        verdict=verdict,
        worth_deep_read=worth_deep_read,
        signals=signals,
        why=str(obj.get("why", "")).strip(),
        confidence=confidence,
        raw_response=text,
    )


def triage_application(app: dict, backend: LLMBackend) -> TriageVerdict:
    """Run Stage 1 triage on a single application."""
    user_msg = render_user_message(app)
    resp: LLMResponse = backend.complete(user_msg, system=SYSTEM_PROMPT)
    return parse_response(resp.text)
