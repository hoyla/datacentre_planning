"""Phase 4 — findings query + delta classification.

The delta classifier is the load-bearing piece for the reporter export:
every `findings` row is sorted into one of three editorial categories
relative to what was already known from the application description and
the Stage-1 triage signals.

| Category         | Editorial meaning                                              | Rendered? |
|------------------|----------------------------------------------------------------|-----------|
| NEW DISCLOSURE   | Fact (often quantitative or named-kit) absent from description | Yes       |
| REFINEMENT       | Qualitative signal sharpened by the documents                  | Yes       |
| CONFIRMATION     | Match for something the description already said               | No (noise)|

Algorithm (deliberately simple, table-driven, explainable):

1. **CONFIRMATION** if the finding's value (quantitative or textual) appears
   verbatim in the application description. We normalise whitespace and
   case but otherwise require the value to be there. The description is
   authoritative because the triage step already extracted signals from
   it — if the docs just repeat it, that's no editorial signal.

2. **REFINEMENT** if the finding's `signal_type` is in the
   `_REFINEMENT_SIGNAL_TYPES` set — these are the slot types whose entire
   purpose is to sharpen the description-level vocabulary (e.g.
   `facility_classification` makes "energy reserve" into "STOR for the
   National Grid"; `plant_configuration` makes "ancillary equipment" into
   "acoustic-contained engines paired into step-up transformers"). The
   description always already mentions the broad category, so by
   construction these are sharpenings, not net-new facts.

3. **NEW DISCLOSURE** otherwise. Quantitative slots like
   `engine_rated_kw` and named-kit slots like `engine_model` overwhelmingly
   land here — descriptions rarely give engine manufacturers or per-unit
   ratings, even when they state a total capacity.

When the LLM extractor matures we may want to let the model itself
declare a category hint (`category_hint='REFINEMENT'`) for tricky cases,
overriding the table-driven default. That row would land in the
`findings.raw_response` JSON; for v1 we don't need it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from psycopg2.extensions import connection as PgConnection

# Signal types whose semantic role is to *sharpen* something the description
# typically already names at a coarser level. Anything not in this set falls
# through to NEW DISCLOSURE (unless it's a CONFIRMATION).
_REFINEMENT_SIGNAL_TYPES: frozenset[str] = frozenset({
    "facility_classification",   # "energy reserve" → "standing reserve power plant"
    "plant_configuration",       # "ancillary equipment" → specific paired-engine layout
    "grid_services_role",        # "energy reserve" → "STOR backing wind on the National Grid"
    "fuel_type_detail",          # "gas" → "mains pipeline" vs "LPG tanker"
})


CATEGORY_NEW = "NEW_DISCLOSURE"
CATEGORY_REFINEMENT = "REFINEMENT"
CATEGORY_CONFIRMATION = "CONFIRMATION"


@dataclass(frozen=True)
class Finding:
    """One row from `findings` plus the joined doc metadata + classified category."""

    id: int
    application_id: int
    document_id: int | None
    document_kind: str | None
    document_bytes_path: str | None
    signal_type: str
    value_text: str | None
    value_number: float | None
    value_unit: str | None
    evidence_text: str | None
    evidence_page: int | None
    model: str
    category: str  # NEW_DISCLOSURE | REFINEMENT | CONFIRMATION


def _normalise(s: str) -> str:
    """Lowercase + strip whitespace runs to a single space, for description matching."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _value_is_confirmation(
    *,
    description: str,
    value_text: str | None,
    value_number: float | None,
    value_unit: str | None,
) -> bool:
    """True if the finding's value already appears in the description text."""
    desc = _normalise(description or "")
    if not desc:
        return False
    # Textual: substring after both sides normalised.
    if value_text:
        if _normalise(value_text) in desc:
            return True
    # Quantitative: try several whitespace-variants for "21 MW" vs "21MW".
    if value_number is not None:
        n = value_number
        n_str = f"{int(n)}" if float(n).is_integer() else f"{n}"
        unit = (value_unit or "").lower()
        forms = [f"{n_str}{unit}", f"{n_str} {unit}"]
        # Tolerate the unit being written with surrounding whitespace differently.
        return any(form in desc for form in forms if form.strip())
    return False


def classify(
    *,
    finding: dict[str, Any],
    description: str,
    triage_signals: list[str] | None = None,
) -> str:
    """Decide NEW_DISCLOSURE / REFINEMENT / CONFIRMATION for one finding.

    `triage_signals` is currently informational (the table-driven
    `_REFINEMENT_SIGNAL_TYPES` set is doing the work). It's accepted so
    callers can pass it forward and we can let a future, smarter classifier
    use it without changing the API.
    """
    if _value_is_confirmation(
        description=description,
        value_text=finding.get("value_text"),
        value_number=finding.get("value_number"),
        value_unit=finding.get("value_unit"),
    ):
        return CATEGORY_CONFIRMATION
    if finding.get("signal_type") in _REFINEMENT_SIGNAL_TYPES:
        return CATEGORY_REFINEMENT
    return CATEGORY_NEW


# ---------------------------------------------------------------------------
# Query: latest findings per (application, document, signal_type, model)
# ---------------------------------------------------------------------------


_FINDINGS_LATEST_SQL = """
-- Append-only / versioned: pick the latest extraction per
-- (application, document, signal_type, model) tuple, mirroring the
-- triage-table pattern. Re-extraction with a refined prompt is just a
-- new row; the older row stays for audit.
WITH latest AS (
  SELECT DISTINCT ON (application_id, document_id, signal_type, model) f.*
  FROM findings f
  WHERE f.application_id = ANY(%(app_ids)s)
  ORDER BY application_id, document_id, signal_type, model,
           inserted_at DESC
)
SELECT
    l.id, l.application_id, l.document_id, l.signal_type,
    l.value_text, l.value_number, l.value_unit,
    l.evidence_text, l.evidence_page, l.model,
    d.kind AS document_kind,
    d.bytes_path AS document_bytes_path
FROM latest l
LEFT JOIN documents d ON d.id = l.document_id
ORDER BY l.application_id, l.signal_type, l.document_id
"""


def fetch_for_applications(
    conn: PgConnection,
    *,
    application_ids: list[int],
    descriptions: dict[int, str],
    triage_signals: dict[int, list[str]] | None = None,
) -> dict[int, list[Finding]]:
    """Return classified `Finding` rows grouped by application_id.

    Apps with no findings rows yet map to an empty list (so callers can
    iterate the worklist uniformly and just check `if findings: ...`).
    """
    if not application_ids:
        return {}
    triage_signals = triage_signals or {}
    out: dict[int, list[Finding]] = {app_id: [] for app_id in application_ids}
    with conn.cursor() as cur:
        cur.execute(_FINDINGS_LATEST_SQL, {"app_ids": application_ids})
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            row_dict = dict(zip(cols, row))
            app_id = row_dict["application_id"]
            category = classify(
                finding=row_dict,
                description=descriptions.get(app_id, "") or "",
                triage_signals=triage_signals.get(app_id),
            )
            f = Finding(
                id=row_dict["id"],
                application_id=app_id,
                document_id=row_dict["document_id"],
                document_kind=row_dict["document_kind"],
                document_bytes_path=row_dict["document_bytes_path"],
                signal_type=row_dict["signal_type"],
                value_text=row_dict["value_text"],
                value_number=(
                    float(row_dict["value_number"])
                    if row_dict["value_number"] is not None else None
                ),
                value_unit=row_dict["value_unit"],
                evidence_text=row_dict["evidence_text"],
                evidence_page=row_dict["evidence_page"],
                model=row_dict["model"],
                category=category,
            )
            out[app_id].append(f)
    return out


# ---------------------------------------------------------------------------
# Summary helpers used by the xlsx column population
# ---------------------------------------------------------------------------


def disclosed_mw_total(findings: list[Finding]) -> float | None:
    """Sum of NEW-category MW findings (engine_rated_kw promoted from kW).

    Returns None when no MW-bearing NEW findings exist, so callers can render
    a blank cell rather than 0.
    """
    total_mw = 0.0
    saw = False
    for f in findings:
        if f.category != CATEGORY_NEW:
            continue
        if f.value_number is None:
            continue
        unit = (f.value_unit or "").lower()
        if unit == "mw":
            total_mw += float(f.value_number)
            saw = True
        elif unit == "kw":
            # Don't roll per-engine kW ratings up to MW automatically — they need to be
            # multiplied by generator_count to be a facility total, which is the
            # description's already-confirmed MW figure. Skip.
            continue
    return total_mw if saw else None


def category_counts(findings: list[Finding]) -> dict[str, int]:
    """Per-category counts, suitable for the badge + xlsx columns."""
    counts = {CATEGORY_NEW: 0, CATEGORY_REFINEMENT: 0, CATEGORY_CONFIRMATION: 0}
    for f in findings:
        counts[f.category] = counts.get(f.category, 0) + 1
    return counts


def headline_disclosure(findings: list[Finding]) -> str:
    """One-line summary of the most editorially-loud NEW disclosure.

    Heuristic: prefer named-kit / model findings first (engine_model,
    grid_services_role), then quantitative new-disclosures, then anything
    else. Empty string when no NEW findings exist.
    """
    new = [f for f in findings if f.category == CATEGORY_NEW]
    if not new:
        return ""
    priority_order = [
        "engine_model", "grid_services_role", "applicant_name",
        "fuel_supply", "grid_connection",
    ]
    for signal_type in priority_order:
        for f in new:
            if f.signal_type == signal_type:
                return f.value_text or (
                    f"{f.value_number} {f.value_unit}".strip()
                    if f.value_number is not None else f.signal_type
                )
    # Fallback to first NEW row.
    f = new[0]
    return f.value_text or (
        f"{f.signal_type}: {f.value_number} {f.value_unit}".strip()
        if f.value_number is not None else f.signal_type
    )
