"""Worklist query + presentation primitives shared by the preview script
(`scripts/worklist_preview.py`) and the formal Aisha-facing export
(`dcp/export.py`).

Ranking aligns with `data/triage_labelling/rubric.md` tier definitions:
  - Rubric Tier 1 (primary on-site generation) hits × 3
  - + Rubric Tier 4 (storage) hits
  - tie-break by Rubric Tier 2 (backup) hits, then confidence, then date_received

Rubric Tier 2 (backup) is intentionally not summed into the primary score —
every DC has backup, so it's a deep-read trigger, not a finding on its own.
"""

from __future__ import annotations

from dataclasses import dataclass


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
# supporting infrastructure, not primary generation.
TIER_STORAGE_REGEX = r"(bess|battery energy storage|battery storage|energy storage)"

# Rubric Tier 2 — backup / standby. Bare `generator` substring-matches all the
# longer forms (`emergency generator`, `generator yard`, `generator compound`).
TIER_BACKUP_REGEX = r"(generator|generators|back[- ]?up|stand[- ]?by|flue)"


_RANKED_SQL = """
-- `triage` is append-only / versioned per (application_id, model, inserted_at);
-- pick the latest verdict per app so retriage runs supersede earlier ones
-- without losing the audit trail (the older rows stay for inspection).
WITH latest_triage AS (
  SELECT DISTINCT ON (application_id) *
  FROM triage
  WHERE model = %(model)s
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
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~ %(tier1)s)   AS tier1_hits,
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~ %(storage)s) AS storage_hits,
    (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~ %(backup)s)  AS backup_hits
  FROM applications a
  JOIN latest_triage t ON t.application_id = a.id
  LEFT JOIN councils c ON c.gss_code = a.council_gss
  WHERE
      (t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
      OR 'foxglove_top10' = ANY(a.discovered_via)
)
SELECT * FROM ranked
ORDER BY (tier1_hits * 3 + storage_hits) DESC,
         backup_hits DESC,
         CASE confidence WHEN 'sure' THEN 0 WHEN 'probable' THEN 1 ELSE 2 END,
         date_received DESC NULLS LAST
"""


_SUMMARY_SQL = """
WITH latest_triage AS (
  SELECT DISTINCT ON (application_id) *
  FROM triage
  WHERE model = %(model)s
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


@dataclass
class WorklistData:
    summary: dict
    rows: list[dict]
    anchors: dict[str, dict]
    model: str


def fetch(conn, *, model: str, limit: int | None = None) -> WorklistData:
    """Run the worklist query and gather supporting spatial-anchor metadata.
    Returns the full ranked slice (capped by `limit`) plus the universe
    summary and the anchor lookup table needed by `expand_lineage`."""
    params = {
        "model": model,
        "tier1": TIER1_REGEX,
        "storage": TIER_STORAGE_REGEX,
        "backup": TIER_BACKUP_REGEX,
    }
    sql = _RANKED_SQL
    if limit is not None:
        sql += " LIMIT %(limit)s"
        params["limit"] = limit
    with conn.cursor() as cur:
        cur.execute(_SUMMARY_SQL, {"model": model})
        cols = [d[0] for d in cur.description]
        summary = dict(zip(cols, cur.fetchone()))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    anchor_refs: set[str] = set()
    for row in rows:
        for tag in row.get("discovered_via") or []:
            if tag.startswith("spatial:"):
                anchor_refs.add(tag.split(":", 1)[1])
    anchors: dict[str, dict] = {}
    if anchor_refs:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT application_ref, description, address "
                "FROM applications WHERE application_ref = ANY(%s)",
                (list(anchor_refs),),
            )
            anchors = {
                r[0]: {"description": r[1], "address": r[2]}
                for r in cur.fetchall()
            }
    return WorklistData(summary=summary, rows=rows, anchors=anchors, model=model)


# ---------------------------------------------------------------------------
# Presentation helpers (used by both the preview script and the export)
# ---------------------------------------------------------------------------


def trim(text: str | None, n: int = 140) -> str:
    """Trim a string to ~n chars on a word boundary; append ellipsis if cut."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return f"{cut}…"


def expand_lineage(
    discovered_via: list[str] | None, anchors: dict[str, dict],
) -> list[str]:
    """Translate `discovered_via` tags into reader-friendly bullet text.
    Tags are documented in `data/priors/` and in each adapter's docstring;
    this is the single place they get humanised for the worklist export."""
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
            descr = trim(info.get("description"), 140)
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


_CONFIDENCE_GLYPH = {"sure": "★★★", "probable": "★★☆", "guessing": "★☆☆"}


def render_card(rank: int, row: dict, anchors: dict[str, dict]) -> str:
    """Render one worklist application as a Markdown card. Used by both the
    preview script and the formal export."""
    out: list[str] = []
    fx = " · 🔖 Foxglove top-10" if row["foxglove"] else ""
    out.append(f"## {rank}. `{row['application_ref']}`{fx}")
    out.append("")
    bits = [
        f"**Verdict:** {row['verdict']}",
        f"**Deep read recommended:** {row['worth_deep_read']}",
        f"**Confidence:** {row['confidence']} "
        f"{_CONFIDENCE_GLYPH.get(row.get('confidence') or '', '—')}",
        f"**Tier-1 / Storage / Backup signal hits:** "
        f"{row['tier1_hits']} / {row['storage_hits']} / {row['backup_hits']}",
    ]
    out.append(" · ".join(bits))
    out.append("")
    meta: list[str] = []
    if row.get("council_name"):
        meta.append(f"**Council:** {row['council_name']}")
    elif row.get("raw_metadata") and row["raw_metadata"].get("area_name"):
        meta.append(f"**Council:** {row['raw_metadata']['area_name']} (unmapped)")
    if row.get("address"):
        meta.append(f"**Address:** {row['address']}")
    if row.get("date_received"):
        meta.append(f"**Received:** {row['date_received'].isoformat()}")
    if row.get("raw_metadata") and row["raw_metadata"].get("app_type"):
        meta.append(f"**Type:** {row['raw_metadata']['app_type']}")
    if meta:
        out.append("  \n".join(meta))
        out.append("")
    if row.get("signals"):
        out.append(f"**Signals:** {', '.join(row['signals'])}")
        out.append("")
    if row.get("why"):
        out.append(f"**LLM reasoning:** {row['why']}")
        out.append("")
    if row.get("description"):
        descr = row["description"].strip()
        out.append("**Description:**")
        out.append("")
        out.append("> " + descr.replace("\n", "\n> "))
        out.append("")
    lineage = expand_lineage(row.get("discovered_via"), anchors)
    if lineage:
        out.append("**Why this is on the worklist:**")
        out.append("")
        for line in lineage:
            out.append(f"- {line}")
        out.append("")
    if row.get("url"):
        out.append(f"[Source portal]({row['url']})")
        out.append("")
    return "\n".join(out)
