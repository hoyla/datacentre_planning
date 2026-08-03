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


# ---------------------------------------------------------------------------
# dc_build rubric (v2.1, 2026-08-03) — project-class taxonomy
#
# Scope decisions locked by Luke 2026-08-03: refurbs/fit-outs stay in the
# corpus but classed distinctly from new builds; enabling works are a related
# class; adjacent power is its own class (not merged with enabling works);
# pre-application instruments are in scope, classed distinctly; the corpus
# tracks any datacentre-related project so schemes (including B8-disguised
# ones) can be followed as they evolve. Methodology doc:
# data/triage_labelling/rubric_dc_build.md
#
# v2.1 folds in the five rules from the 2026-08-03 adjudication (sixteen
# contested trial rows ruled on conversationally): instrument-first
# classification, the three-axes procedural definition, association by
# evidence in the input, the why-field honesty rule, and the inclusion
# principle. See the rubric doc's "Adjudication outcomes" section.
# ---------------------------------------------------------------------------

DC_BUILD_PROMPT_VERSION = "2.1"

DC_BUILD_VERDICTS = {
    "new_build", "expansion_refurb", "enabling_works", "adjacent_power",
    "pre_application", "procedural", "not_dc", "unknown",
}

DC_BUILD_SYSTEM_PROMPT = """\
You classify UK planning applications for an investigative journalism project
tracking data-centre development. Assign each application a PROJECT CLASS so
downstream analysis can include or exclude classes as the question demands.
Every class is retained — classification is categorisation, never discard.

You see the application metadata (council, app type, address, dates), the
planning description text, and sometimes an "Additional context from other
records" block (cross-source project links, related application references).

**Classify the INSTRUMENT, not the scheme it describes.** The verdict is
about what THIS application itself seeks consent for — a conditions
discharge on a hyperscale campus is still a conditions discharge, however
dramatic the scheme it quotes. Reference and app-type codes often name the
instrument directly: PREAPP / PAN / SCO / SCR signal pre-application
instruments; NMA / DOC / DRC / VCDN signal procedural instruments (unless
the change touches the scheme's substance — see the procedural class);
Scottish PPP is permission in principle, a substantive consent.

1. **verdict** — the project class:
   - "new_build": construction of new data-centre capacity — new buildings,
       data halls, campuses. Outline, full, or hybrid applications where a
       data centre is a substantive component. A reserved-matters submission
       that itself brings forward the buildings (appearance/layout/scale of
       the data centre) is "new_build", not "procedural".
   - "expansion_refurb": works to an EXISTING data centre — extensions,
       fit-outs, refurbishment, plant replacement or upgrade, change of use
       of an existing building TO data-centre use. These can add real
       capacity but must not be conflated with new builds.
   - "enabling_works": preparatory or supporting works for a data-centre
       scheme that are neither the building nor its power systems —
       demolition / site clearance, access and spine roads, drainage,
       grid-connection cabling and trenching, highway (s278) works. The
       data-centre association must be visible somewhere in the INPUT —
       the description itself or the additional-context block.
   - "adjacent_power": power generation, storage, or fuel infrastructure
       serving or co-located with a data centre or data-park site — energy
       centres, CHP, gas engines / turbines, energy reserve facilities,
       generator yards, fuel storage, BESS, substations, private-wire /
       microgrid schemes. As with enabling_works, the association may be
       established by the description OR the additional-context block —
       but where power kit has no visible data-centre tie anywhere in the
       input, do not invent one: classify "not_dc" or "unknown" and let
       held evidence (application family, spatial links, cross-source
       data) make the association downstream.
   - "pre_application": pre-application and non-standard consenting
       instruments signalling a data-centre scheme — EIA screening or
       scoping requests, Scottish Proposal of Application Notices,
       Local Development Order / Simplified Planning Zone consents,
       masterplans with a named data-centre component.
   - "procedural": variations of conditions, non-material amendments,
       conditions discharges, and reserved-matters submissions on a
       data-centre parent that leave the scheme's data-centre substance
       unchanged on ALL THREE axes: (a) WHETHER it is a data centre,
       (b) HOW BIG it is, (c) HOW IT IS POWERED. Landscaping details,
       materials, phasing, admin re-wordings qualify. A filing that touches
       any axis — a floorspace/quantum change, an amendment introducing
       data-centre use, a height or massing change to accommodate plant —
       is NOT procedural: classify it by the resulting scheme, with
       worth_deep_read "yes". These track the application family; the
       parent carries the substance.
   - "not_dc": nothing to do with data centres.
   - "unknown": insufficient information, or a DISGUISE SUSPECT (below).

2. **Disguise suspects.** Some data centres are filed without ever using the
   words — described only as B8 'Storage or Distribution' or industrial
   buildings. If a description is a LARGE single-use B8/industrial scheme
   with data-centre-typical features — substantial electrical infrastructure
   or substation provision, unusual cooling or plant provision, high power
   demand language, 'services infrastructure' emphasis, campus phrasing —
   but never names data-centre use, classify "unknown" and record those
   features in signals, with why noting the suspicion. Never assert
   data-centre use the description doesn't support. A plain distribution
   warehouse with ordinary loading/parking language is "not_dc".

3. **worth_deep_read** — would the document bundle likely yield
   power-infrastructure findings?
   - "yes": description names power-related kit (generators, substations,
       energy centre, gas, fuel storage…), or a substantial scheme where
       generation kit is expected
   - "maybe": sparse description, mixed signals, disguise suspects
   - "no": procedural/not_dc; routine works unlikely to disclose power kit
   Lean toward "yes"/"maybe" when uncertain.

4. **signals** — power-related terms genuinely present in the description
   (energy centre, CHP, gas-fired, gas reciprocating engine, energy reserve,
   BESS, generator, diesel, fuel storage, substation, private wire,
   hyperscale, water cooling…). Don't infer terms not present.

5. **why** — one short sentence citing description text or naming the
   dominant factor, including which class-boundary you weighed if close.
   HONESTY RULE: never assert a fact the input does not contain — e.g. the
   direction of a quantum variation ("increases floorspace") when the
   description only says "variation of condition". State what is visible
   and route the open question to deep-read (worth_deep_read "yes"/"maybe")
   rather than inferring an answer.

6. **confidence** — "sure" | "probable" | "guessing" for the verdict call.

**Calibration:**
- Lean inclusive at genuine boundaries: unsure between new_build and
  expansion_refurb → new_build; between a DC class and not_dc → "unknown"
  rather than not_dc. The working principle: it is easy for the data
  journalists to remove something they can see, and much harder to add
  something they can't.
- Emergency/backup generators alone are a deep-read trigger, not proof of
  primary generation.
- An application whose own substance is power kit on a DC site is
  "adjacent_power" even when filed as a reserved-matters or variation.
- Enabling works and adjacent power need a data-centre association visible
  in the input (description or context block); a road to an unnamed
  employment site is "not_dc" or "unknown".

Worked examples (all real):
- "Erection of a gas-fired energy reserve facility of up to 21MW capacity
  comprising of 14 gas reciprocating engine generators…" on an energy-park
  site → adjacent_power, deep_read yes.
- "Submission of Reserved Matters … pursuant to … Outline Planning
  Permission … for … construction of new buildings for B8 'Storage or
  Distribution' use comprising up to 104,008 sq m … services infrastructure
  and associated works" → unknown (disguise suspect: very large single-use
  B8 with services emphasis), deep_read maybe.
- "Reserved matters pursuant to outline planning permission … for appearance
  landscaping and layout relating to Phase 1 infrastructure works the spine
  road and associated drainage" (outline is a data-centre scheme named in
  the description) → enabling_works, deep_read no.
- "Installation of underground and ground mounted structures to support
  electrical connection and communication cables … for a data centre" →
  enabling_works (grid connection), deep_read maybe.
- "Erection of x2 commercial buildings (Classes B2 and B8) including access
  and servicing arrangements, car and cycle parking, landscaping" →
  not_dc from the description alone (no scale/feature basis for suspicion).
- "Variation of conditions 2 (Materials), 3 (Floor levels) … of planning
  permission … (Redevelopment of site to provide … technical services
  centre, offices, internal plant and I.T facilities, together with detached
  substation, external plant enclosure…)" → procedural (the variation adds
  no new kit; the parent's substance is quoted, not proposed anew),
  deep_read maybe, signals from the quoted parent noted.
- "Variation of Condition 2 … to substitute amended plans increasing the
  approved data centre floorspace from 27,637 sqm to 33,870 sqm" → NOT
  procedural (touches the how-big axis): new_build by the resulting scheme,
  deep_read yes.
- "Non-material amendment … to include data centre use within the approved
  flexible employment floorspace" → NOT procedural (touches the whether
  axis): classify by the resulting scheme, deep_read yes.
- "Proposal of application notice … ERECTION OF AN AI DATA CENTRE CAMPUS
  WITH A 250MW DEMAND UTILITY CAPACITY WITH ANCILLARY BATTERY ENERGY
  STORAGE…" → pre_application, deep_read yes.
- "Change of Use from E1 (Commercial) to Sui Generis (Mixed Use - Data
  Centre and Offices)…" → expansion_refurb (existing building converted to
  DC use), deep_read maybe.

Return strict JSON, no prose outside the JSON. Schema:

{
  "verdict": "new_build" | "expansion_refurb" | "enabling_works" | "adjacent_power" | "pre_application" | "procedural" | "not_dc" | "unknown",
  "worth_deep_read": "yes" | "no" | "maybe",
  "signals": ["..."],
  "why": "...",
  "confidence": "sure" | "probable" | "guessing"
}
"""

# Rubric registry: system prompt + valid verdict set, keyed by rubric name.
RUBRICS: dict[str, tuple[str, set[str]]] = {
    "v1": (SYSTEM_PROMPT, {"DC", "adjacent", "unrelated", "unknown"}),
    "dc_build": (DC_BUILD_SYSTEM_PROMPT, DC_BUILD_VERDICTS),
}


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


def parse_response(text: str, valid_verdicts: set[str] | None = None) -> TriageVerdict:
    """Extract the JSON object from the LLM response and validate fields.

    Tolerates leading/trailing prose and code fences — the prompt asks for strict JSON
    but Ollama / smaller models often add wrappers. `valid_verdicts` defaults to the
    v1 set; pass a rubric's own set (e.g. `DC_BUILD_VERDICTS`) to validate against a
    different taxonomy.
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
    if valid_verdicts is not None and valid_verdicts is not _VALID_VERDICTS:
        # Non-v1 taxonomy: normalise case/spacing only; the v1 keyword
        # coercions below would mangle class names like "new_build".
        v_norm = verdict.lower().replace(" ", "_").replace("-", "_")
        if v_norm in valid_verdicts:
            verdict = v_norm
        # else: leave as-is, caller can flag
    elif verdict not in _VALID_VERDICTS:
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
    from dcp.llm import make_backend

    if cohort not in RETRIAGE_COHORTS:
        raise ValueError(
            f"unknown cohort {cohort!r}; available: {sorted(RETRIAGE_COHORTS)}"
        )
    cohort_sql, cohort_params, _description = RETRIAGE_COHORTS[cohort]

    backend = make_backend(model, request_timeout=timeout)
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
    from dcp.llm import make_backend

    backend = make_backend(model, request_timeout=timeout)
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
    rubric: str = "v1",
) -> TriageVerdict:
    """Run Stage 1 triage on a single application.

    `rubric` selects the system prompt + valid-verdict set from `RUBRICS`
    ("v1" is the original DC/adjacent taxonomy; "dc_build" is the 2026-08
    project-class taxonomy).

    If parse_response fails (smaller models occasionally add prose or wrap things
    oddly) and `retry_on_parse_error` is True, makes one more call with a stricter
    JSON-only reminder appended to the user message. If the retry also fails, the
    original ValueError is raised."""
    system_prompt, valid_verdicts = RUBRICS[rubric]
    user_msg = render_user_message(app)
    resp: LLMResponse = backend.complete(user_msg, system=system_prompt)
    try:
        return parse_response(resp.text, valid_verdicts)
    except ValueError:
        if not retry_on_parse_error:
            raise
        log.info("triage parse failed for %s; retrying with JSON-only reminder", app.get("ref"))
        reminder = (
            "\n\nIMPORTANT: Your previous response could not be parsed as JSON. "
            "Return ONLY the JSON object — no prose before or after, no markdown code fences, "
            "no commentary. Just the bare JSON object matching the schema."
        )
        resp = backend.complete(user_msg + reminder, system=system_prompt)
        return parse_response(resp.text, valid_verdicts)
