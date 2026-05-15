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
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

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
   - "adjacent": application for **power, fuel, generation, cooling, or
       energy-storage infrastructure** serving a DC — e.g. substation,
       transformer, cable to a DC, energy centre, BESS, generator yard,
       fuel tanks. The application is for kit that could yield power-
       infrastructure findings if its documents are read.
   - "unrelated": application doesn't fit the categories above. This INCLUDES
       DC-related work whose stated purpose is clearly **not** power /
       generation / fuel / cooling. Examples: goods lifts, loading bays,
       drainage conditions, landscaping, internal layout amendments, access
       roads, parking, NMAs that re-word permitted uses without adding new
       power kit, procedural conditions discharges on a parent DC permission
       where the discharge is about a non-power condition.
   - "unknown": insufficient information; DC embedded in mixed-use of unclear scale

   **Lean inclusive at genuine boundaries.** If a description is sparse or the
   purpose is ambiguous between power and non-power infrastructure → prefer
   "adjacent" over "unrelated". If unsure between DC and adjacent → choose DC.
   We can manually reject false positives downstream; we cannot recover false
   negatives.

   **But:** when an application clearly states a non-power purpose (goods lift,
   loading bay, access road, drainage condition, landscaping etc.) it's
   "unrelated" — being inclusive doesn't mean treating obviously non-power
   work as adjacent.

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
- Grid-connection mentions are common in any large application; ignore unless paired
  with other generation language.

**Procedural follow-on applications are USUALLY UNRELATED, even if the description
contains "data centre".** The parent application is the one we want; procedural
follow-ons add no new substantive content. Default to "unrelated" with
worth_deep_read="no" when the description STARTS or is primarily about:

- "Variation of Conditions …" / "Variation of Condition …" / "Section 73 application to vary …"
- "Non-Material Amendment" / "NMA" / "Non material amendment"
- "Approval of Details Reserved by Condition" / "Approval of details reserved by Condition"
- "Discharge of Condition" / "Discharge of Conditions"
- "Details of Condition NN (…) pursuant to planning permission …"
- "Details pursuant to the discharge of Condition …"
- "Reserved matters following Outline …" if scope is layout/scale/landscaping only
  (i.e. no new substantive change to power infrastructure)

These all reference an underlying DC application; we capture that parent separately.
Mark these "unrelated" / "no". Override only if the application introduces clearly
NEW substantive power infrastructure beyond what the parent already had.

Worked examples (from labelled training data):

- "Variation of Conditions 2 and 3 (plan numbers and development phasing) attached to
  [parent DC permission]" → unrelated. The DC permission is elsewhere.
- "Approval of Details Reserved by Condition 4 Contaminated Land of [parent DC outline]"
  → unrelated. Pure procedural follow-on.
- "Non-Material Amendment to Outline Planning Permission … to amend the description
  of development to read [DC use]" → unrelated. Description is just an admin
  re-wording.
- "Details of condition 35 (Landscaping and Public Realm) for Phase 2 pursuant to
  planning permission [DC outline]" → unrelated. Landscaping is not power kit.
- "Discharge of Condition 25 against planning application … 5,150 dwellings; …
  data centre; …" → unknown (mixed-use master plan with embedded DC of unclear
  scale; the parent application is the relevant DC capture).
- "Erection of a rear extension to the existing data centre to provide a goods lift
  and modular loading bay" → unrelated. Building extension only; no power kit.
- "The creation of an improved all-vehicle access road … to access … Data Centre" →
  unrelated (or at most adjacent). It's a road, not the DC.
- "INSTALLATION OF AN UNDERGROUND CABLE CONNECTION FROM 132KV SUBSTATION TO A DATA
  CENTRE" → adjacent. It's DC-related infrastructure but not a new DC.
- "Reserved matters application … for an electricity substation on Phase 1b of the
  data centre campus" → adjacent. A substation on a DC campus is power-related and
  worth deep-reading.

For SUBSTANTIVE DC applications, the description usually starts with "Erection of …",
"Construction of …", "Outline planning application … for the construction of …
data centre …", "Hybrid planning application … to deliver a data centre campus …",
or similar. These are typically "DC" with worth_deep_read="yes".

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


def app_row_to_triage_input(row: dict) -> dict:
    """Map the dict returned by `repo.applications_pending_triage` into the
    shape `render_user_message` expects."""
    return {
        "ref": row.get("application_ref"),
        "council": row.get("council_name") or row.get("council_gss"),
        "app_type": row.get("app_type"),
        "date_received": (
            row["date_received"].isoformat() if row.get("date_received") else None
        ),
        "status": row.get("status"),
        "address": row.get("address"),
        "description": row.get("description"),
    }


# Named retriage cohorts. Each entry maps a CLI-friendly slug to a SQL
# WHERE fragment over `applications a`. Add new cohorts here when a future
# bug or data fix needs a targeted refresh; keep them small and documented.
RETRIAGE_COHORTS: dict[str, tuple[str, tuple, str]] = {
    "council-backfill": (
        # Apps where council_gss was NULL at sweep time because the broken
        # _load_area_gss_map (TEXT-vs-JSONB bug, migrations/004) yielded an
        # empty map for spatial/operator/parent_backfill paths. The original
        # dc_keyword sweep built its map fresh from API and so wasn't affected.
        "a.council_gss IS NOT NULL AND NOT ('dc_keyword' = ANY(a.discovered_via))",
        (),
        "Apps that saw NULL council in their original prompt due to the "
        "TEXT-vs-JSONB bug fixed in migration 004; ~277 apps as of 2026-05-15.",
    ),
}


def run_retriage(
    *,
    cohort: str,
    model: str | None = None,
    limit: int | None = None,
    timeout: float = 180.0,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Append a fresh triage verdict for every application in `cohort`,
    regardless of whether an earlier verdict exists. The original verdicts
    stay in place — the `triage` table is versioned per
    `(application_id, model, inserted_at)` and "latest by inserted_at wins"
    is the queryable contract (see worklist_preview's DISTINCT ON pattern).

    Use when a fixable bug retroactively changed the prompt input shape
    (e.g. the council-backfill case where 277 apps saw NULL council in
    their original prompt). For a fresh untriaged-apps sweep, use
    `run_triage` instead — that's resume-aware and skips already-triaged.
    """
    from dcp import db, repo
    from dcp.llm import OllamaBackend

    if cohort not in RETRIAGE_COHORTS:
        raise ValueError(
            f"unknown cohort {cohort!r}; available: {sorted(RETRIAGE_COHORTS)}"
        )
    cohort_sql, cohort_params, _description = RETRIAGE_COHORTS[cohort]

    backend = OllamaBackend(model=model, request_timeout=timeout)
    model_name = backend.model

    summary = {
        "model": model_name,
        "cohort": cohort,
        "scanned": 0,
        "errors": 0,
        "by_verdict": {"DC": 0, "adjacent": 0, "unrelated": 0, "unknown": 0},
    }

    with db.connect() as conn:
        cohort_rows = repo.applications_for_retriage(
            conn, cohort_sql=cohort_sql, cohort_params=cohort_params, limit=limit,
        )
        summary["cohort_size"] = len(cohort_rows)
        for row in cohort_rows:
            t0 = time.time()
            err: str | None = None
            verdict_obj: TriageVerdict | None = None
            try:
                verdict_obj = triage_application(app_row_to_triage_input(row), backend)
            except ValueError as exc:
                err = f"parse_error: {exc}"
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
            elapsed = time.time() - t0

            if verdict_obj is not None:
                repo.record_triage(
                    conn,
                    application_id=row["id"],
                    model=model_name,
                    verdict=verdict_obj.verdict,
                    worth_deep_read=verdict_obj.worth_deep_read,
                    signals=verdict_obj.signals,
                    why=verdict_obj.why,
                    confidence=verdict_obj.confidence,
                    raw_response={"text": verdict_obj.raw_response,
                                  "retriage_cohort": cohort},
                )
                conn.commit()
                if verdict_obj.verdict in summary["by_verdict"]:
                    summary["by_verdict"][verdict_obj.verdict] += 1
            else:
                summary["errors"] += 1

            summary["scanned"] += 1
            if progress is not None:
                progress({
                    "scanned": summary["scanned"],
                    "cohort_size": summary["cohort_size"],
                    "ref": row.get("application_ref"),
                    "verdict": verdict_obj.verdict if verdict_obj else None,
                    "worth_deep_read": verdict_obj.worth_deep_read if verdict_obj else None,
                    "confidence": verdict_obj.confidence if verdict_obj else None,
                    "elapsed": elapsed,
                    "error": err,
                })

    return summary


def run_triage(
    *,
    model: str | None = None,
    limit: int | None = None,
    timeout: float = 180.0,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Production triage sweep: walk applications without a verdict for `model`
    and append one row per call into the `triage` table. Commits per-record so
    a kill at any point loses at most the in-flight call. Resume is automatic:
    apps that already have a verdict for the same model are skipped on re-run.

    `progress`, if supplied, is called with a status dict after every record
    so the CLI can stream live updates. The summary dict is returned at end.
    """
    from dcp import db, repo
    from dcp.llm import OllamaBackend

    backend = OllamaBackend(model=model, request_timeout=timeout)
    model_name = backend.model

    summary = {
        "model": model_name,
        "scanned": 0,
        "errors": 0,
        "by_verdict": {"DC": 0, "adjacent": 0, "unrelated": 0, "unknown": 0},
    }

    with db.connect() as conn:
        pending = repo.applications_pending_triage(conn, model=model_name, limit=limit)
        summary["pending"] = len(pending)
        for row in pending:
            t0 = time.time()
            err: str | None = None
            verdict_obj: TriageVerdict | None = None
            try:
                verdict_obj = triage_application(app_row_to_triage_input(row), backend)
            except ValueError as exc:
                err = f"parse_error: {exc}"
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
            elapsed = time.time() - t0

            if verdict_obj is not None:
                repo.record_triage(
                    conn,
                    application_id=row["id"],
                    model=model_name,
                    verdict=verdict_obj.verdict,
                    worth_deep_read=verdict_obj.worth_deep_read,
                    signals=verdict_obj.signals,
                    why=verdict_obj.why,
                    confidence=verdict_obj.confidence,
                    raw_response={"text": verdict_obj.raw_response},
                )
                conn.commit()
                if verdict_obj.verdict in summary["by_verdict"]:
                    summary["by_verdict"][verdict_obj.verdict] += 1
            else:
                summary["errors"] += 1

            summary["scanned"] += 1
            if progress is not None:
                progress({
                    "scanned": summary["scanned"],
                    "pending": summary["pending"],
                    "ref": row.get("application_ref"),
                    "verdict": verdict_obj.verdict if verdict_obj else None,
                    "worth_deep_read": verdict_obj.worth_deep_read if verdict_obj else None,
                    "confidence": verdict_obj.confidence if verdict_obj else None,
                    "elapsed": elapsed,
                    "error": err,
                })

    return summary


def triage_application(
    app: dict,
    backend: LLMBackend,
    *,
    retry_on_parse_error: bool = True,
) -> TriageVerdict:
    """Run Stage 1 triage on a single application.

    If parse_response fails (smaller models occasionally add prose or wrap things
    oddly) and `retry_on_parse_error` is True, makes one more call with a stricter
    JSON-only reminder appended to the user message. If the retry also fails, the
    original ValueError is raised."""
    user_msg = render_user_message(app)
    resp: LLMResponse = backend.complete(user_msg, system=SYSTEM_PROMPT)
    try:
        return parse_response(resp.text)
    except ValueError:
        if not retry_on_parse_error:
            raise
        log.info("triage parse failed for %s; retrying with JSON-only reminder", app.get("ref"))
        reminder = (
            "\n\nIMPORTANT: Your previous response could not be parsed as JSON. "
            "Return ONLY the JSON object — no prose before or after, no markdown code fences, "
            "no commentary. Just the bare JSON object matching the schema."
        )
        resp = backend.complete(user_msg + reminder, system=SYSTEM_PROMPT)
        return parse_response(resp.text)
