"""Render the top-N triage-ranked worklist as a markdown card stack, one
section per application, suitable for skimming in an IDE.

Ranking aligns with `data/triage_labelling/rubric.md` tier definitions:
  - rubric Tier 1 (primary on-site generation) hits × 3
  - + rubric Tier 4 (storage) hits
  - tie-break by confidence (sure > probable > guessing), then date_received DESC

Rubric Tier 2 (backup / standby) is intentionally not summed into the rank —
backup is a deep-read trigger (already implicit in worth_deep_read='yes') but
not a finding on its own. Every DC has backup generators; the journalism
question is whether they're grid-services-rated, which only documents resolve.

Output: data/worklist/top<N>_<YYYY-MM-DD>.md  (gitignored — editorial only).

Usage:
    scripts/worklist_preview.py                # top 50, default model
    scripts/worklist_preview.py --top 100
    scripts/worklist_preview.py --model granite4.1:30b --top 50
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402


# Rubric Tier 1 — primary on-site generation. Verbatim union of the terms
# listed under "Tier 1" in data/triage_labelling/rubric.md, lowercased and
# regex-escaped where needed. Update both files together when the rubric
# changes.
#
# Note on `district heating centre` / `district heating unit`: bare
# "district heating" is excluded because the term covers two semantically
# different cases in our data — (a) on-site combustion infrastructure
# producing heat for a network, and (b) connection to an external network
# (a neutral or even positive signal). The specific `centre`/`unit`
# phrasings disambiguate to case (a); "energy centre" elsewhere in the
# regex picks up "district heating energy centre(s)" automatically.
TIER1_REGEX = (
    r"(energy centre|power station|power plant|power facility|prime power|"
    r"gas turbine|gas[- ]fired|gas reciprocating engine|reciprocating engine|"
    r"chp|combined heat and power|cogeneration|"
    r"energy reserve|onsite generation|on[- ]site generation|microgrid|"
    r"behind[- ]the[- ]meter|bridge[- ]to[- ]grid|"
    r"biomass|hydrogen|fuel cell|anaerobic digestion|energy from waste|"
    r"district heating centre|district heating unit)"
)

# Rubric Tier 4 — storage (BESS et al). Distinct from Tier 1: storage is
# supporting infrastructure, not primary generation. Verbatim union of the
# four terms in `data/triage_labelling/rubric.md` Tier 4. `energy storage`
# is its own entry — a signal can legitimately list both `battery storage`
# and `energy storage` (two storage subsystems) and we want both counted.
TIER_STORAGE_REGEX = (
    r"(bess|battery energy storage|battery storage|energy storage)"
)


RANKED_SQL = """
-- `triage` is append-only / versioned per (application_id, model, inserted_at);
-- pick the latest verdict per app so retriage runs supersede earlier ones
-- without losing the audit trail (the older rows stay for inspection).
WITH latest_triage AS (
  SELECT DISTINCT ON (application_id) *
  FROM triage
  WHERE model = %s
  ORDER BY application_id, inserted_at DESC
),
ranked AS (
  SELECT
    a.id, a.application_ref, a.description, a.address,
    a.date_received, a.url, a.raw_metadata,
    c.name AS council_name,
    t.verdict, t.worth_deep_read, t.confidence, t.signals, t.why,
    a.discovered_via,
    'foxglove_top10' = ANY(a.discovered_via) AS foxglove,
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~ %s) AS tier1_hits,
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~ %s) AS storage_hits,
    -- Rubric Tier 2 (backup/standby) — shown on each card and used as a
    -- secondary tie-breaker in ORDER BY (not summed into the primary score
    -- because every DC has backup; it's a deep-read trigger, not a finding).
    -- Verbatim union of rubric Tier 2 (`data/triage_labelling/rubric.md`),
    -- with hyphenation variants per the synonymous-forms convention.
    -- Bare `generator` substring-matches "generators", "generator compound",
    -- "generator yard" etc.; the longer phrases are redundant.
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~
       '(generator|generators|back[- ]?up|stand[- ]?by|flue)'
    ) AS backup_hits
  FROM applications a
  JOIN latest_triage t ON t.application_id = a.id
  LEFT JOIN councils c ON c.gss_code = a.council_gss
  WHERE
      (t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
      OR 'foxglove_top10' = ANY(a.discovered_via)
)
SELECT * FROM ranked
ORDER BY (tier1_hits * 3 + storage_hits) DESC,
         backup_hits DESC,  -- final tiebreaker: more backup language = denser disclosure
         CASE confidence WHEN 'sure' THEN 0 WHEN 'probable' THEN 1 ELSE 2 END,
         date_received DESC NULLS LAST
LIMIT %s
"""

SUMMARY_SQL = """
WITH latest_triage AS (
  SELECT DISTINCT ON (application_id) *
  FROM triage
  WHERE model = %s
  ORDER BY application_id, inserted_at DESC
)
SELECT
    count(*) AS total,
    count(*) FILTER (WHERE t.verdict = 'DC') AS dc,
    count(*) FILTER (WHERE t.verdict = 'adjacent') AS adjacent,
    count(*) FILTER (WHERE t.verdict = 'unrelated') AS unrelated,
    count(*) FILTER (WHERE t.verdict = 'unknown') AS unknown,
    count(*) FILTER (
      WHERE (t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
         OR 'foxglove_top10' = ANY(a.discovered_via)
    ) AS worklist
FROM applications a JOIN latest_triage t ON t.application_id = a.id
"""


def _collect_spatial_anchors(rows: list[dict]) -> set[str]:
    """Walk all rows' `discovered_via` arrays and return the unique set of
    spatial-anchor refs (the `X` in `spatial:X` tags). Used to batch-fetch
    anchor metadata in one query rather than one-per-card."""
    out: set[str] = set()
    for row in rows:
        for tag in row.get("discovered_via") or []:
            if tag.startswith("spatial:"):
                out.add(tag.split(":", 1)[1])
    return out


def _fetch_anchor_details(conn, refs: set[str]) -> dict[str, dict]:
    """Batch lookup of spatial-anchor metadata so the card can render a
    natural-language explanation rather than a bare ref. Anchors not in
    `applications` (rare — would only happen if the anchor was deleted
    after the spatial sweep) just won't appear in the returned dict and
    the renderer falls back to the bare ref."""
    if not refs:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT application_ref, description, address "
            "FROM applications WHERE application_ref = ANY(%s)",
            (list(refs),),
        )
        return {
            row[0]: {"description": row[1], "address": row[2]}
            for row in cur.fetchall()
        }


def _trim(text: str | None, n: int = 140) -> str:
    """Trim a string to ~n chars on a word boundary; append ellipsis if cut."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return f"{cut}…"


def _expand_lineage(
    discovered_via: list[str] | None, anchors: dict[str, dict],
) -> list[str]:
    """Translate `discovered_via` tags into reader-friendly bullet text.
    Tags are documented in [data/priors/](data/priors/) and in each adapter's
    docstring; this is the single place they get humanised for the worklist."""
    lines: list[str] = []
    for tag in discovered_via or []:
        if tag == "dc_keyword":
            lines.append(
                "Matched the DC keyword union (data centre / hyperscale / colocation / etc.) "
                "in the description."
            )
        elif tag == "foxglove_top10":
            lines.append(
                "Listed in Foxglove's top-10 ≥100 MW UK DC applications "
                "(see `data/prior_art_sources/foxglove_reconciliation.md`)."
            )
        elif tag.startswith("spatial:"):
            anchor_ref = tag.split(":", 1)[1]
            info = anchors.get(anchor_ref) or {}
            descr = _trim(info.get("description"), 140)
            addr = (info.get("address") or "").strip()
            bits = [f"Spatial neighbour (within 1 km) of `{anchor_ref}`"]
            if descr:
                bits.append(f"— *{descr}*")
            if addr:
                bits.append(f"(at {addr})")
            lines.append(" ".join(bits) + ".")
        elif tag.startswith("operator:"):
            name = tag.split(":", 1)[1]
            lines.append(
                f"Shares agent/applicant **{name}** with another DC application "
                "(operator-name sweep match)."
            )
        elif tag.startswith("parent_backfill:"):
            child_ref = tag.split(":", 1)[1]
            lines.append(
                f"Substantive parent permission for procedural follow-on `{child_ref}` "
                "(recovered by walking PlanIt's `associated_id` chain)."
            )
        else:
            lines.append(f"Discovered via `{tag}` (no humaniser registered).")
    return lines


def _confidence_glyph(confidence: str | None) -> str:
    return {
        "sure": "★★★",
        "probable": "★★☆",
        "guessing": "★☆☆",
    }.get(confidence or "", "—")


def _verdict_glyph(verdict: str) -> str:
    return {
        "DC": "🎯",
        "adjacent": "↔️",
        "unrelated": "○",
        "unknown": "?",
    }.get(verdict, verdict)


def _render_card(rank: int, row: dict, anchors: dict[str, dict]) -> str:
    out: list[str] = []
    fx = " · 🔖 Foxglove top-10" if row["foxglove"] else ""
    out.append(f"## {rank}. `{row['application_ref']}`{fx}")
    out.append("")
    bits = [
        f"**Verdict:** {row['verdict']}",
        f"**Deep read recommended:** {row['worth_deep_read']}",
        f"**Confidence:** {row['confidence']} {_confidence_glyph(row['confidence'])}",
        f"**Tier-1 / Storage / Backup signal hits:** "
        f"{row['tier1_hits']} / {row['storage_hits']} / {row['backup_hits']}",
    ]
    out.append(" · ".join(bits))
    out.append("")
    meta = []
    if row["council_name"]:
        meta.append(f"**Council:** {row['council_name']}")
    elif row["raw_metadata"] and row["raw_metadata"].get("area_name"):
        meta.append(f"**Council:** {row['raw_metadata']['area_name']} (unmapped)")
    if row["address"]:
        meta.append(f"**Address:** {row['address']}")
    if row["date_received"]:
        meta.append(f"**Received:** {row['date_received'].isoformat()}")
    if row["raw_metadata"] and row["raw_metadata"].get("app_type"):
        meta.append(f"**Type:** {row['raw_metadata']['app_type']}")
    if meta:
        out.append("  \n".join(meta))
        out.append("")
    if row["signals"]:
        out.append(f"**Signals:** {', '.join(row['signals'])}")
        out.append("")
    if row["why"]:
        out.append(f"**LLM reasoning:** {row['why']}")
        out.append("")
    if row["description"]:
        descr = row["description"].strip()
        out.append("**Description:**")
        out.append("")
        out.append("> " + descr.replace("\n", "\n> "))
        out.append("")
    lineage = _expand_lineage(row.get("discovered_via"), anchors)
    if lineage:
        out.append("**Why this is on the worklist:**")
        out.append("")
        for line in lineage:
            out.append(f"- {line}")
        out.append("")
    if row["url"]:
        out.append(f"[Source portal]({row['url']})")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="How many ranked entries to include.")
    ap.add_argument("--model", default="granite4.1:30b", help="Triage model to draw from.")
    ap.add_argument("--output", type=Path, default=None,
                    help="Override output path. Default: data/worklist/top<N>_<YYYY-MM-DD>.md")
    args = ap.parse_args()

    today = dt.date.today().isoformat()
    out_path = args.output or (ROOT / f"data/worklist/top{args.top}_{today}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SUMMARY_SQL, (args.model,))
            cols = [d[0] for d in cur.description]
            summary = dict(zip(cols, cur.fetchone()))
        with conn.cursor() as cur:
            cur.execute(RANKED_SQL, (args.model, TIER1_REGEX, TIER_STORAGE_REGEX, args.top))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # Batch-fetch metadata for every spatial anchor referenced in this slice,
        # so each card can render a natural-language explanation rather than a
        # bare `spatial:Council/Ref` tag the reader has to decode.
        anchor_refs = _collect_spatial_anchors(rows)
        anchors = _fetch_anchor_details(conn, anchor_refs)

    header = [
        f"# Triage worklist — top {len(rows)} ranked",
        "",
        f"Generated {dt.datetime.now().isoformat(timespec='seconds')} from model `{args.model}`.",
        "",
        "## Universe summary",
        "",
        f"- **{summary['total']}** applications triaged total",
        f"- DC: {summary['dc']} · adjacent: {summary['adjacent']} · "
        f"unrelated: {summary['unrelated']} · unknown: {summary['unknown']}",
        f"- **Worklist (DC/adjacent ∩ deep-read yes/maybe, or Foxglove-tagged): {summary['worklist']}**",
        "",
        "## Ranking",
        "",
        "Aligned with `data/triage_labelling/rubric.md` tiers. Primary on-site generation "
        "signals (rubric Tier 1) weighted 3×; storage signals (rubric Tier 4) weighted 1×; "
        "backup/standby (rubric Tier 2) shown for context but **not** ranked — every DC has "
        "backup, so it's a deep-read trigger, not a finding. Confidence and recency tie-break.",
        "",
        "- **Tier-1 (×3)**: energy centre, power station/plant/facility, prime power, gas "
        "turbine, gas-fired, gas/reciprocating engine, CHP, combined heat and power, "
        "cogeneration, energy reserve, onsite generation, microgrid, behind-the-meter, "
        "bridge-to-grid, biomass, hydrogen, fuel cell, anaerobic digestion, energy from "
        "waste, district heating centre, district heating unit.",
        "- **Storage (×1)**: BESS, battery energy storage, battery storage, energy storage.",
        "- **Backup (shown, secondary tie-break only)**: generator, generators, "
        "back-up, standby, flue (rubric Tier 2, verbatim).",
        "",
        "Cards below are ordered head-of-list first. Click the source-portal link "
        "for full document bundle.",
        "",
        "---",
        "",
    ]

    body = []
    for i, row in enumerate(rows, 1):
        body.append(_render_card(i, row, anchors))
        body.append("---")
        body.append("")

    out_path.write_text("\n".join(header + body))
    print(f"Wrote {out_path}")
    print(f"Top entry: #{1} `{rows[0]['application_ref']}` "
          f"(t1={rows[0]['tier1_hits']}, t2={rows[0]['storage_hits']})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
