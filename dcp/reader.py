"""Integrated reader — the single-file split-screen HTML viewer that brings
the worklist cards and the Leaflet map together with bidirectional sync.

Left pane: chaptered cards (editorial highlights → cohorts → other ranked
→ filtered), every worklist entry rendered as a card. Right pane: Leaflet
map with verdict-coloured markers + foxglove ★ + inferred-coords ⚑ badge.
Click a card → map flies to its pin and opens the popup. Click a pin →
left pane scrolls to that card. Search box (Cmd-K) and filter chips
(verdict / deep-read / Foxglove / has-findings / inferred-coords) filter
both panes simultaneously.

The reader is self-contained: all data is embedded in the HTML as JSON.
Leaflet + marked.js are pulled from CDN — audience is online journalists
on capable desktops, so the dependency is acceptable in exchange for a
~50KB file instead of a ~250KB one with inlined libs.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from dcp import cohorts as cohorts_mod
from dcp import corpus_stats as corpus_stats_mod
from dcp import db, worklist
from dcp.map import OSM_BUNDLED, PLANT_BUCKET_COLOR, _bucket
from dcp.worklist import _ref_anchor


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------


def _build_chapters(rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Group worklist rows into reader-pane chapters.

    Returns (chapters, ref_to_chapter):
      - chapters: ordered list, each {id, title, intro, entries: [ref]}
      - ref_to_chapter: maps each application_ref to its assigned chapter id
        (the one in which it renders as a full card, not cross-references)
    """
    rows_by_ref = {r["application_ref"]: r for r in rows}
    ref_to_chapter: dict[str, str] = {}

    chapters: list[dict] = []

    # Chapter 1: editorial highlights.
    hs = cohorts_mod.highlights()
    if hs:
        highlight_refs = []
        for h in hs:
            if h.app in rows_by_ref:
                highlight_refs.append(h.app)
                ref_to_chapter[h.app] = "highlights"
        chapters.append({
            "id": "highlights",
            "title": "Editorial highlights",
            "intro": (
                "Hand-picked headline applications. Each is the substantive "
                "anchor of an editorial pattern surfaced by the deep-read "
                "pass."
            ),
            "entries": highlight_refs,
        })

    # Chapter 2..N: named cohorts. Each cohort renders its primary-member
    # applications as full cards; cross-refs (apps whose primary cohort is
    # elsewhere) appear as one-liners.
    cohorts = cohorts_mod.cohorts()
    for c in cohorts:
        primary_refs: list[str] = []
        for ref in c.apps:
            row = rows_by_ref.get(ref)
            if row is None:
                continue
            if row.get("primary_cohort") == c.name:
                if ref not in ref_to_chapter:
                    primary_refs.append(ref)
                    ref_to_chapter[ref] = f"cohort:{c.name}"
        if primary_refs:
            chapters.append({
                "id": f"cohort:{c.name}",
                "title": c.display_name,
                "intro": (c.description or "").strip(),
                "entries": primary_refs,
            })

    # Chapter N+1: other ranked applications — everything not already in a
    # chapter, in rank order.
    other_refs = [
        r["application_ref"] for r in rows
        if r["application_ref"] not in ref_to_chapter
    ]
    if other_refs:
        for ref in other_refs:
            ref_to_chapter[ref] = "other"
        chapters.append({
            "id": "other",
            "title": "Other ranked applications",
            "intro": (
                "All other worklist entries not already grouped into the "
                "editorial highlights or a named cohort, in rank order. "
                "These haven't had a full deep-read pass; the description "
                "is the canonical content."
            ),
            "entries": other_refs,
        })

    return chapters, ref_to_chapter


def _build_entry(row: dict, rank: int, anchors: dict[str, dict],
                 ref_to_chapter: dict[str, str]) -> dict:
    """Build the per-entry payload — coords, key metadata, and the
    full-card markdown (rendered client-side via marked.js)."""
    meta = row.get("raw_metadata") or {}
    lon = meta.get("location_x")
    lat = meta.get("location_y")
    is_inferred = False
    inferred_source: str | None = None
    if lat is None or lon is None:
        from dcp.map import _load_inferred_coords
        inferred = _load_inferred_coords(Path("data/priors/inferred_coords.yaml"))
        entry = inferred.get(row["application_ref"])
        if entry:
            lat = entry["lat"]
            lon = entry["lon"]
            is_inferred = True
            inferred_source = entry.get("source")
    coords = None
    if lat is not None and lon is not None:
        try:
            coords = [float(lon), float(lat)]
        except (TypeError, ValueError):
            coords = None

    findings = row.get("findings") or []
    has_findings = bool([f for f in findings if f.category != "CONFIRMATION"])

    council = (
        row.get("council_name")
        or meta.get("area_name")
        or ""
    )
    address = row.get("address") or ""
    description = (row.get("description") or "").strip()
    signals = row.get("signals") or []

    # Search blob: lower-cased concatenation of fields a reader might
    # search by. Doing the lowercasing server-side means client-side
    # search is just a substring check.
    search_parts = [
        row["application_ref"],
        council,
        address,
        description,
        " ".join(signals),
        " ".join(row.get("discovered_via") or []),
    ]
    search_blob = " ".join(p for p in search_parts if p).lower()

    return {
        "ref": row["application_ref"],
        "rank": rank,
        "verdict": row["verdict"],
        "deep_read": row["worth_deep_read"],
        "confidence": row["confidence"],
        "tier1": row["tier1_hits"],
        "storage": row["storage_hits"],
        "backup": row["backup_hits"],
        "foxglove": bool(row.get("foxglove")),
        "inferred_coords": is_inferred,
        "inferred_coords_source": inferred_source,
        "coords": coords,
        "council": council,
        "address": address,
        "primary_cohort": row.get("primary_cohort"),
        "also_in_cohorts": row.get("also_in_cohorts") or [],
        "chapter": ref_to_chapter.get(row["application_ref"], "other"),
        "has_findings": has_findings,
        "signals": signals,
        "portal_url": row.get("url"),
        "card_md": worklist.render_card(rank, row, anchors, base_level=3),
        "search_blob": search_blob,
    }


# ---------------------------------------------------------------------------
# Intro section (the "read this first" briefing that lives above the cards)
# ---------------------------------------------------------------------------


_INTRO_HEAD = """\
# Read this first

Welcome — this is the **integrated viewer** for the {version} release of
the UK data-centre energy review. Three things to know before you read:

1. **Absence of findings is not absence of fossil generation.** Cards in
   the highlights and named cohort sections have document-extracted
   findings (verbatim quotes from the application's submitted documents);
   cards in *"Other ranked applications"* don't, yet. A card without
   findings doesn't mean the application is clean — it means the
   deep-read pass hasn't reached it.

2. **Source-portal URLs may rot in 6-24 months.** Idox uses
   session-scoped URLs that degrade as councils re-index; Ocella's
   reference-scoped URLs last longer but still subject to portal
   re-platforming. The canonical reference is the local SHA-keyed PDF
   under `data/raw/<adapter>/<application_ref>/<sha16>.pdf` — every
   finding card line ends with that filename + page number.

3. **This dataset is a hypothesis-generator, not a fact-base.** Triage
   verdicts are LLM-classified ({model}); the worklist surfaces
   *candidates worth deep-reading*, not confirmed facts. Verify any
   quotable claim against its source document before publication. The
   `Self-scrutiny/` folder in this release carries the QA artefacts
   (findings verification, privacy sweep, Foxglove reconciliation,
   map spot-check) that document how the dataset was checked.
"""


_INTRO_HOW_TO_READ = """\

## How to read each card

Each card carries:

- **Header**: rank, application reference, verdict badge, and any
  applicable badges — `★ Foxglove` (on Foxglove's top-10 list),
  `⚑ Inferred coords` (map coords backfilled by us, not from the
  source portal), `📄 Findings` (has document-extracted findings).
- **Description**: the council's own application summary, verbatim.
- **Signals**: power-infrastructure keywords surfaced by the triage
  Stage-1 LLM from the description.
- **LLM reasoning**: one-line model rationale for the verdict.
- **Document-extracted findings** (where present): structured facts
  pulled from submitted documents — verbatim quote + source filename
  + page number. Three categories:
  - **NEW DISCLOSURE** — fact the document reveals that the
    description doesn't mention. Editorially the most valuable.
  - **REFINEMENT** — fact the document sharpens (more specific than
    the description's framing). Same fact, sharpened.
  - **CONFIRMATION** — fact the document repeats at the same level
    of specificity as the description. Filtered out of the cards but
    counted in the xlsx for audit. (You won't see these here; they
    add nothing the description doesn't.)
- **Why this is on the worklist**: which discovery path(s) brought
  the application into the universe (description keyword match,
  spatial sweep around an anchor site, operator-name match, Foxglove
  prior, parent-application backfill, etc.).
- **Source portal** link: opens the live council page in a new tab.
  See caveat #2 above on URL durability.

## Filtering and navigation

- The **Filter** chips in the header restrict the visible cards and
  pins by verdict / deep-read flag / Foxglove / has-findings /
  inferred-coords. Multiple filters combine as AND.
- The **chapter links** (top of the header, with `↗` prefixes)
  navigate to a section and fit-bounds the map to that section's
  pins. They don't filter — they jump.
- The **search box** (top-left, ⌘K to focus) matches against the
  application reference, council, address, description, signals,
  and discovery tags simultaneously. Esc clears it.
- **Click a card → map** flies to its pin and opens the popup.
- **Click a pin → cards** scrolls the matching card into view and
  flashes it.
"""


_INTRO_METHODOLOGY = """\

## Methodology in one paragraph

We index UK planning applications from PlanIt (national aggregator,
all councils 2018+) plus the Planning Inspectorate NSIP register,
complemented by a parent-application backfill that walks PlanIt's
`associated_id` chain to recover pre-2018 substantive permissions
referenced from procedural follow-ons. A spatial sweep within 1 km of
each DC anchor pulls in neighbouring applications regardless of
description language. An LLM (`{model}`, run locally via Ollama)
classifies each application against the rubric in
`data/triage_labelling/rubric.md` — verdict (DC / adjacent / unrelated
/ unknown), deep-read recommendation, signals, and confidence. This
worklist filters to `verdict ∈ {{DC, adjacent}} AND deep-read ∈
{{yes, maybe}}`, plus a safety-net tag for the Foxglove top-10 (which
captures procedural follow-ons the LLM correctly classifies as
unrelated but where the family lineage is still editorially
important). Ranking weights primary on-site generation signals
(rubric Tier 1) at 3× and storage signals (rubric Tier 4) at 1×;
backup is a deep-read trigger, not a finding, so it serves only as a
tie-break. Council names follow the current unitary; legacy district
names are preserved in raw metadata.
"""


_INTRO_FOXGLOVE = """\

## Foxglove top-10 cross-check

The worklist has been cross-checked against the top-10 DC list
Foxglove published in earlier reporting, at two layers:

- **Universe layer** (was each Foxglove case found in our ingest at
  all?) — 8/10 confirmed, 1/10 probable (#8 G-Park Docklands), 1/10
  unidentified (#4 DC01, no PlanIt match).
- **Worklist-position layer** (where did each ref land in our
  ranked worklist?) — see
  `Self-scrutiny/dc_energy_review_foxglove_reconciliation_v{version}.md`.
  Every ref in every resolved family is present in the worklist.

The `★ Foxglove` badge on a card means it carries the
`foxglove_top10` discovery tag — i.e. it's part of one of those nine
resolved families.
"""


_INTRO_COMPANIONS = """\

## Companion files in this release folder

This integrated viewer is the **primary** artefact — everything you
need for reading the dataset is on this page. The same release folder
contains companion files for specific external use cases:

- **`dc_energy_review_spreadsheet_v{version}.xlsx`** — flat sortable
  / filterable Excel companion of all 806 worklist entries. Useful
  for sort-by-column, custom filtering, and offline review.
- **`dc_energy_review_text_only_v{version}.md`** — markdown version
  of the same cards, for grep / cmd-F / printing / archival. Same
  data as this viewer; no JS, no map.
- **`dc_energy_review_map_only_v{version}.html`** — standalone
  Leaflet map (the same one embedded in this viewer, no cards).
- **`Map data/`** — `.geojson` + `.kml` for QGIS / kepler.gl /
  Google Earth, plus the OSM power-plants context layer.
- **`Self-scrutiny/`** — pre-publication QA artefacts: findings
  verification (every quote re-checked against the source PDF),
  privacy sweep, Foxglove reconciliation, map spot-check.
- **`How to read this.md`** — slim pointer file (essentially says
  "open this HTML to start").
"""


def _build_intro_markdown(
    *, version: str, model: str, stats: dict, rows: list[dict],
) -> str:
    """Render the intro briefing as markdown. Embedded in the viewer as
    the first 'Read this first' section above the chapters."""
    parts: list[str] = [_INTRO_HEAD.format(version=version, model=model)]

    # At a glance — mirrors the export header but lives here so the
    # integrated viewer is self-contained.
    u = stats["universe"]
    v = stats["verdicts"]
    f = stats["filters"]
    d = stats["documents"]
    fn = stats["findings"]
    date_span = ""
    if u["date_min"] and u["date_max"]:
        date_span = (
            f" (date received {u['date_min'].isoformat()} → "
            f"{u['date_max'].isoformat()})"
        )
    src_parts = ", ".join(f"{n} from `{name}`" for name, n in u["by_source"])
    parts.append("\n## At a glance\n")
    parts.append(
        f"- **Universe:** {u['total']} applications ingested{date_span}, "
        f"all triaged by `{model}`."
        + (f" Sources: {src_parts}." if src_parts else "")
    )
    parts.append(
        f"- **Verdict mix:** DC {v['dc']} · adjacent {v['adjacent']} · "
        f"unrelated {v['unrelated']} · unknown {v['unknown']}."
    )
    worklist_size = len(rows)
    parts.append(
        f"- **Worklist size:** {worklist_size} applications "
        f"(DC/adjacent ∩ deep-read yes/maybe, or Foxglove-tagged) — "
        f"{f['excluded']} confirmed-not-a-DC after deep-read and "
        f"{f['duplicates']} consultation-stage duplicates filtered."
    )
    parts.append(
        f"- **Documents on file:** {d['docs_total']} fetched, covering "
        f"{d['apps_with_docs']} applications."
    )
    parts.append(
        f"- **Document-extracted findings:** {fn['findings_total']} "
        f"findings on {fn['apps_with_findings']} applications from "
        f"{fn['documents_with_findings']} documents — an editorially-"
        f"selected sample, not the full worklist."
    )

    # Editorial highlights — one-liners with clickable links to each card.
    parts.append("\n## Editorial highlights\n")
    parts.append(
        "Hand-picked headline applications. Each is the substantive "
        "anchor of an editorial pattern surfaced by the deep-read pass; "
        "click through to the full card."
    )
    parts.append("")
    rows_by_ref = {r["application_ref"]: r for r in rows}
    rank_by_ref = {r["application_ref"]: i for i, r in enumerate(rows, 1)}
    for h in cohorts_mod.highlights():
        row = rows_by_ref.get(h.app)
        rank = rank_by_ref.get(h.app)
        anchor = _ref_anchor(h.app)
        rank_str = f"rank {rank}" if rank else "filtered"
        if row is not None:
            link = f"[`{h.app}`](#{anchor}) ({rank_str})"
        else:
            link = f"`{h.app}` ({rank_str})"
        parts.append(f"- **{link}** — {h.one_liner.strip()}")
        parts.append("")

    parts.append(_INTRO_HOW_TO_READ)
    parts.append(_INTRO_METHODOLOGY.format(model=model))
    parts.append(_INTRO_FOXGLOVE.format(version=version))
    parts.append(_INTRO_COMPANIONS.format(version=version))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Data-centre energy review v{version} — integrated reader</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin="">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
          crossorigin=""></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {{
      --left-width: 720px;
      --bg: #ffffff;
      --fg: #1a1a1a;
      --muted: #6a6a6a;
      --rule: #e6e6e6;
      --accent: #1f6feb;
      --accent-soft: #e6efff;
      --dc: #1a7f37;
      --adjacent: #bf8700;
      --unknown: #777;
      --highlight: #fff2c0;
      --foxglove: #9467bd;
      --inferred: #d35400;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; height: 100%; }}
    body {{
      font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
      color: var(--fg);
      background: var(--bg);
      display: flex; flex-direction: column;
      overflow: hidden;
    }}
    /* --- Header ----------------------------------------------------- */
    header {{
      flex: 0 0 auto;
      background: #fafafa;
      border-bottom: 1px solid var(--rule);
      padding: 6px 16px;
      display: flex; flex-direction: column; gap: 5px;
    }}
    .head-row {{ display: flex; align-items: baseline; gap: 14px;
                 flex-wrap: wrap; }}
    .head-title {{ font-weight: 600; font-size: 14px; }}
    .head-meta  {{ color: var(--muted); font-size: 12px; }}
    .controls   {{ display: flex; gap: 10px; align-items: center;
                   flex-wrap: wrap; }}
    .control-label {{
      font-size: 11px; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.5px;
      flex: 0 0 auto;
    }}
    .search-box {{
      flex: 0 0 320px;
      padding: 4px 10px; font-size: 13px;
      border: 1px solid var(--rule); border-radius: 4px;
      background: white;
    }}
    .search-box:focus {{ outline: 2px solid var(--accent); border-color: var(--accent); }}
    .count {{ font-size: 12px; color: var(--muted); white-space: nowrap; }}
    /* Filter chips — togglable, look like switches (on/off state) */
    .chips {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
    .chip {{
      font-size: 12px;
      padding: 2px 8px; border-radius: 11px;
      border: 1px solid var(--rule); background: white;
      cursor: pointer; user-select: none;
    }}
    .chip.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
    .chip:hover:not(.active) {{ background: var(--accent-soft); }}
    /* Chapter navigation — link-style buttons, navigation not filter.
       Visually distinct from chips: no border by default, link-coloured
       text, subtle underline on hover. Multi-row wrapping. */
    #chapter-index {{
      display: flex; flex-wrap: wrap; gap: 2px 10px;
    }}
    .chapter-link {{
      flex: 0 0 auto;
      padding: 1px 4px;
      color: var(--accent); text-decoration: none;
      font-size: 12.5px; white-space: nowrap;
      border-radius: 3px;
    }}
    .chapter-link::before {{ content: "↗ "; font-size: 11px; opacity: 0.75; }}
    .chapter-link:hover {{ background: var(--accent-soft); text-decoration: underline; }}
    .chapter-link .count-pill {{
      color: var(--muted); margin-left: 3px; font-size: 11px;
      font-variant-numeric: tabular-nums;
    }}
    /* --- Two-pane layout -------------------------------------------- */
    main {{
      flex: 1 1 0; min-height: 0;
      display: flex;
    }}
    #left {{
      width: var(--left-width);
      border-right: 1px solid var(--rule);
      background: var(--bg);
      overflow: hidden;
    }}
    #cards {{
      height: 100%; overflow-y: auto; padding: 16px 22px;
    }}
    #right {{ flex: 1; position: relative; }}
    #map {{ position: absolute; inset: 0; }}
    /* Map legend — bottom-left overlay matching the standalone map's
       layout. Sits above Leaflet's default tile layer but below the
       attribution + zoom controls. */
    .map-legend {{
      position: absolute;
      bottom: 24px; left: 10px;
      z-index: 800;
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid var(--rule);
      border-radius: 4px;
      padding: 8px 12px;
      font-size: 11px; line-height: 1.4;
      box-shadow: 0 1px 4px rgba(0,0,0,0.15);
      max-width: 240px;
      pointer-events: none;
    }}
    .map-legend .legend-title {{
      font-weight: 600; font-size: 11px;
      text-transform: uppercase; letter-spacing: 0.4px;
      color: var(--muted);
      margin: 0 0 3px;
    }}
    .map-legend .legend-row {{ margin: 2px 0; }}
    .map-legend .legend-dot {{
      display: inline-block;
      width: 9px; height: 9px;
      border-radius: 50%;
      margin-right: 5px;
      vertical-align: middle;
    }}
    /* Outline-only variant for OSM power plants, matching the map's
       hollow plant markers. */
    .map-legend .legend-ring {{
      display: inline-block;
      width: 9px; height: 9px;
      border-radius: 50%;
      border: 1.8px solid;
      box-sizing: border-box;
      margin-right: 5px;
      vertical-align: middle;
      background: transparent;
    }}
    .map-legend hr {{
      border: 0; border-top: 1px solid var(--rule); margin: 5px 0;
    }}
    .map-legend .legend-note {{ color: var(--muted); font-size: 10px; }}
    /* Tighten Leaflet's layer-control box to match the legend's density */
    .leaflet-control-layers {{ font-size: 12px; }}
    .leaflet-control-layers-expanded {{ padding: 8px 10px; }}
    /* --- Cards ------------------------------------------------------- */
    .chapter {{ margin-bottom: 24px; }}
    .chapter > h2 {{
      font-size: 16px; margin: 4px 0 4px;
      padding-bottom: 4px; border-bottom: 2px solid var(--fg);
    }}
    /* Intro chapter — the "Read this first" briefing. Same chapter shell
       but with a soft tinted background so it reads as a distinct
       welcome page rather than a card. */
    #intro {{
      margin: 0 0 28px;
      padding: 14px 18px;
      border: 1px solid var(--accent);
      background: var(--accent-soft);
      border-radius: 6px;
    }}
    #intro h1 {{ font-size: 18px; margin: 0 0 8px;
                 border-bottom: 1px solid var(--accent); padding-bottom: 6px; }}
    #intro h2 {{ font-size: 14px; margin: 14px 0 6px;
                 text-transform: uppercase; letter-spacing: 0.5px;
                 color: var(--muted); border: none; padding-bottom: 0; }}
    #intro h3 {{ font-size: 13px; margin: 10px 0 4px; }}
    #intro p, #intro li {{ font-size: 13px; }}
    #intro ol, #intro ul {{ padding-left: 22px; margin: 6px 0; }}
    #intro li {{ margin: 4px 0; }}
    #intro code {{ background: rgba(255,255,255,0.7); padding: 0 4px;
                   border-radius: 3px; font-size: 12px; }}
    #intro a {{ color: var(--accent); }}
    .chapter > .intro {{
      font-size: 13px; color: var(--muted); margin: 4px 0 12px;
    }}
    .card {{
      border: 1px solid var(--rule); border-radius: 4px;
      padding: 12px 14px; margin: 0 0 14px;
      background: var(--bg);
      scroll-margin-top: 12px;  /* breathing room for scrollIntoView */
      transition: background 0.15s, border-color 0.15s;
    }}
    .card.highlight-frame {{ box-shadow: 0 0 0 2px var(--accent) inset; }}
    .card:hover {{ border-color: var(--accent); }}
    .card.flash {{ background: var(--highlight); }}
    .card h3 {{ margin: 0 0 6px; font-size: 14px; font-weight: 600;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .card h3 a {{ color: var(--fg); text-decoration: none; }}
    .card h3 a:hover {{ color: var(--accent); }}
    .card .verdict-line {{
      font-size: 12px; color: var(--muted); margin-bottom: 6px;
    }}
    .badge {{
      display: inline-block; padding: 1px 6px;
      border-radius: 9px; font-size: 11px; margin-right: 4px;
    }}
    .badge.dc       {{ background: #ddf4e1; color: var(--dc); }}
    .badge.adjacent {{ background: #fff1cf; color: var(--adjacent); }}
    .badge.unknown  {{ background: #eee;    color: var(--unknown); }}
    .badge.foxglove {{ background: #f0e5fa; color: var(--foxglove); }}
    .badge.inferred {{ background: #fbe7d4; color: var(--inferred); }}
    .badge.findings {{ background: #e0eaff; color: #2b51c0; }}
    .actions {{ float: right; }}
    .actions a {{
      font-size: 12px; color: var(--accent);
      text-decoration: none; margin-left: 8px;
    }}
    .actions a:hover {{ text-decoration: underline; }}
    .card-md table {{ border-collapse: collapse; font-size: 13px; }}
    .card-md p     {{ margin: 6px 0; }}
    .card-md h2, .card-md h3, .card-md h4 {{
      font-size: 13px; margin: 10px 0 4px; font-weight: 600;
    }}
    .card-md blockquote {{
      border-left: 3px solid var(--rule); margin: 6px 0;
      padding: 4px 10px; color: var(--muted); font-size: 13px;
    }}
    .card-md code {{ background: #f4f4f4; padding: 0 4px; border-radius: 3px;
                     font-size: 12px; }}
    .card-md ul, .card-md ol {{ padding-left: 22px; margin: 6px 0; }}
    .card-md li {{ margin: 2px 0; }}
    .card-md a {{ color: var(--accent); }}
    .card-md a[id^="app-"] {{ display: none; }}  /* Hide the anchor empties */
    .card-md em {{ color: var(--muted); }}

    /* No-results state */
    .no-results {{
      padding: 24px; text-align: center; color: var(--muted);
    }}
    /* Leaflet popup polish */
    .leaflet-popup-content {{ font: 12px/1.4 system-ui, sans-serif;
                              margin: 8px 10px; }}
    .leaflet-popup-content b {{ color: var(--fg); }}
    .leaflet-popup-content .pop-ref {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px; font-weight: 600;
    }}
    .leaflet-popup-content .pop-line {{ margin: 2px 0; }}
    .leaflet-popup-content .pop-link {{
      display: inline-block; margin-top: 4px;
      color: var(--accent); text-decoration: none;
    }}
    .leaflet-popup-content .pop-link:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>

<header>
  <div class="head-row">
    <div class="head-title">Data-centre energy review · v{version}</div>
    <div class="head-meta">Generated {generated} · Triage model <code>{model}</code></div>
    <div class="head-meta" id="visible-count"></div>
  </div>
  <div class="controls">
    <input id="search" class="search-box" type="search"
           placeholder="Search ref / council / address / description / signals (⌘K)"
           title="Search across application ref, council, address, description, signals, and discovery tags. Press ⌘K (Mac) or Ctrl-K to focus. Esc to clear."
           autofocus>
    <span class="control-label" title="Filter the visible applications. Multiple filters combine as AND. Click to toggle.">Filter</span>
    <div class="chips" id="filters">
      <span class="chip" data-filter="verdict:DC"
            title="Show only applications the triage classified as DC (data centre).">DC verdict</span>
      <span class="chip" data-filter="verdict:adjacent"
            title="Show only applications classified as power-adjacent (not the DC itself, but power infrastructure next to one).">Adjacent</span>
      <span class="chip" data-filter="deep_read:yes"
            title="Show only applications flagged by the triage as worth a deep document read.">Deep-read yes</span>
      <span class="chip" data-filter="foxglove"
            title="Show only applications on Foxglove's published UK DC top-10 list (used as a prior reference set).">Foxglove ★</span>
      <span class="chip" data-filter="has_findings"
            title="Show only applications with at least one document-extracted finding (the editorially-selected deep-read sample).">Has findings</span>
      <span class="chip" data-filter="inferred_coords"
            title="Show only applications whose map coordinates were backfilled by us (no location_x/y in the raw PlanIt record). See data/priors/inferred_coords.yaml for provenance.">Inferred coords</span>
    </div>
  </div>
  <nav id="chapter-index"
       title="Jump to a section. Map will fit-bounds to that section's pins. These don't filter — they navigate."></nav>
</header>

<main>
  <div id="left">
    <div id="cards"></div>
  </div>
  <div id="right">
    <div id="map"></div>
    <div class="map-legend" id="map-legend">
      <div class="legend-title">Worklist applications</div>
      <div class="legend-row"><span class="legend-dot" style="background:#1a7f37"></span> DC verdict</div>
      <div class="legend-row"><span class="legend-dot" style="background:#bf8700"></span> Adjacent</div>
      <div class="legend-row"><span class="legend-dot" style="background:#777"></span> Unknown</div>
      <div class="legend-row"><span style="color:#9467bd">★</span> Foxglove top-10 ·
        <span style="color:#d35400">⚑</span> Inferred coords</div>
      <hr>
      <div class="legend-title">UK power plants <span style="text-transform:none;color:var(--muted);font-weight:400">(OSM, hollow rings)</span></div>
      <div class="legend-row"><span class="legend-ring" style="border-color:#d62728"></span> Fossil</div>
      <div class="legend-row"><span class="legend-ring" style="border-color:#ff7f0e"></span> Biomass / waste</div>
      <div class="legend-row"><span class="legend-ring" style="border-color:#9467bd"></span> Nuclear</div>
      <div class="legend-row"><span class="legend-ring" style="border-color:#2ca02c"></span> Renewable</div>
      <div class="legend-row"><span class="legend-ring" style="border-color:#1f77b4"></span> Storage</div>
      <hr>
      <div class="legend-note">Worklist filled · plants hollow. Worklist marker size = Tier-1 signal count. Toggle layers top-right.</div>
    </div>
  </div>
</main>

<script>
const RELEASE = {release_json};
const CHAPTERS = {chapters_json};
const ENTRIES = {entries_json};
const INTRO_MD = {intro_md_json};
const PLANTS = {plants_json};
const PLANT_BUCKET_COLOR = {plant_bucket_color_json};

// ----- Map setup ---------------------------------------------------------
const map = L.map('map', {{ zoomControl: true, preferCanvas: true }})
  .setView([54.0, -2.5], 6);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; OpenStreetMap contributors',
  maxZoom: 19,
}}).addTo(map);

const VERDICT_COLOR = {{
  "DC": "#1a7f37",
  "adjacent": "#bf8700",
  "unknown": "#777",
  "unrelated": "#bcbcbc",
}};

// Worklist points sit in a layer group so the layer control can toggle
// the whole layer. Filter logic (search / chips) adds/removes individual
// markers from this group rather than from the map directly.
const worklistLayer = L.layerGroup().addTo(map);
const markers = {{}};  // ref -> L.circleMarker
for (const ref in ENTRIES) {{
  const e = ENTRIES[ref];
  if (!e.coords) continue;
  const [lon, lat] = e.coords;
  const radius = 5 + Math.min(e.tier1, 3) * 3;
  const colour = VERDICT_COLOR[e.verdict] || "#000";
  const m = L.circleMarker([lat, lon], {{
    radius: radius,
    color: colour,
    weight: 1,
    fill: true,
    fillColor: colour,
    fillOpacity: e.foxglove ? 0.9 : 0.7,
  }});
  m.bindPopup(() => popupHtml(e), {{ maxWidth: 360 }});
  m.on("click", () => {{
    scrollCardIntoView(ref);
  }});
  m.addTo(worklistLayer);
  markers[ref] = m;
}}

// ----- Power-plant overlays (OSM) ---------------------------------------
// One Leaflet LayerGroup per bucket so the user can toggle fossil /
// biomass+waste / nuclear / renewable / storage independently. Default
// visibility mirrors the standalone folium map: editorially-relevant
// buckets (fossil, biomass/waste, nuclear) on; renewable + storage +
// other off.
const plantLayers = {{
  fossil:        L.layerGroup(),
  biomass_waste: L.layerGroup(),
  nuclear:       L.layerGroup(),
  renewable:     L.layerGroup(),
  storage:       L.layerGroup(),
  other:         L.layerGroup(),
}};

function plantPopupHtml(p) {{
  const name = p.name || '(unnamed)';
  return `
    <div style="font-family:system-ui,sans-serif;font-size:12px;">
      <div style="font-weight:bold">${{escapeHtml(name)}}</div>
      <table style="border-collapse:collapse;width:100%">
        <tr><td><b>Operator</b></td><td>${{escapeHtml(p.operator || '?')}}</td></tr>
        <tr><td><b>Source</b></td><td>${{escapeHtml(p.plant_source || '?')}}</td></tr>
        <tr><td><b>Method</b></td><td>${{escapeHtml(p.plant_method || '?')}}</td></tr>
        <tr><td><b>Capacity</b></td><td>${{escapeHtml(p.plant_output_electricity || '?')}}</td></tr>
      </table>
      <div style="color:#888;font-size:11px;margin-top:2px">OSM ${{p.osm_type || '?'}}/${{p.osm_id || '?'}}</div>
    </div>
  `;
}}

for (const p of PLANTS) {{
  const bucket = p.bucket || 'other';
  const color = PLANT_BUCKET_COLOR[bucket] || PLANT_BUCKET_COLOR.other;
  // Plants render as hollow (outline-only) circles to stay visually
  // distinct from worklist applications (filled circles), independent
  // of the colour palette — so DC-green and renewable-green don't
  // clash on the map. Slightly thicker stroke so the ring stays
  // visible at small sizes.
  const m = L.circleMarker([p.lat, p.lon], {{
    radius: 4.5, color: color, weight: 1.8,
    fill: false, fillOpacity: 0, opacity: 0.85,
  }});
  m.bindTooltip(`${{p.name || '(unnamed)'}} (${{p.plant_source || '?'}})`);
  m.bindPopup(() => plantPopupHtml(p), {{ maxWidth: 280 }});
  m.addTo(plantLayers[bucket] || plantLayers.other);
}}

// Default-on for the editorially-relevant buckets.
plantLayers.fossil.addTo(map);
plantLayers.biomass_waste.addTo(map);
plantLayers.nuclear.addTo(map);

L.control.layers(
  null,
  {{
    "Worklist applications":          worklistLayer,
    "Power plants · fossil":          plantLayers.fossil,
    "Power plants · biomass / waste": plantLayers.biomass_waste,
    "Power plants · nuclear":         plantLayers.nuclear,
    "Power plants · renewable":       plantLayers.renewable,
    "Power plants · storage":         plantLayers.storage,
    "Power plants · other":           plantLayers.other,
  }},
  {{ position: 'topright', collapsed: false }}
).addTo(map);

function popupHtml(e) {{
  const fx = e.foxglove ? ' <span style="color:#9467bd">★ Foxglove top-10</span>' : '';
  const inf = e.inferred_coords ? ' <span style="color:#d35400">⚑ Inferred coords</span>' : '';
  const portal = e.portal_url
    ? ` <span style="color:var(--muted)">|</span> <a class="pop-link" href="${{e.portal_url}}" target="_blank">Source portal ↗</a>` : '';
  const findings = e.has_findings ? '<span class="pop-line"><b>Has findings:</b> yes</span>' : '';
  return `
    <div>
      <div class="pop-ref">#${{e.rank}} ${{e.ref}}${{fx}}${{inf}}</div>
      <div class="pop-line" style="color:#555">${{escapeHtml(e.council)}} · ${{escapeHtml(e.address)}}</div>
      <div class="pop-line"><b>Verdict:</b> ${{e.verdict}} · deep-read ${{e.deep_read}} · conf ${{e.confidence}}</div>
      <div class="pop-line"><b>Tier-1 / Stor / Bkp:</b> ${{e.tier1}} / ${{e.storage}} / ${{e.backup}}</div>
      ${{findings}}
      <div style="margin-top:4px">
        <a class="pop-link" href="#" data-scroll-to="${{e.ref}}">↧ Scroll to card</a>
        ${{portal}}
      </div>
    </div>
  `;
}}
// Popup → scroll uses event delegation since popups are re-created.
map.on("popupopen", (ev) => {{
  const root = ev.popup.getElement();
  root.querySelectorAll('a[data-scroll-to]').forEach(a => {{
    a.addEventListener('click', (e) => {{
      e.preventDefault();
      scrollCardIntoView(a.dataset.scrollTo);
    }});
  }});
}});

function escapeHtml(s) {{
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, c => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }}[c]));
}}

// ----- Cards: render server-rendered markdown via marked.js --------------
const cardsRoot = document.getElementById('cards');
const cardEls = {{}};   // ref -> card div
const chapterEls = {{}}; // chapter id -> section div
const chapterCountEls = {{}}; // chapter id -> visible-count <span>

// Intro section — the "Read this first" briefing above the chapters.
// Built server-side as markdown, rendered client-side via marked. Sits
// outside the chapter loop so it isn't affected by filter / search.
const intro = document.createElement('section');
intro.id = 'intro';
intro.innerHTML = openExternalLinksInNewTab(marked.parse(INTRO_MD || ''));
cardsRoot.appendChild(intro);

const markedOpts = {{ breaks: false, gfm: true }};
if (window.marked && marked.setOptions) marked.setOptions(markedOpts);

// Section id helper. For cohort chapters, match the markdown export's
// `_cohort_anchor()` convention so the card-internal "Also relevant to"
// cross-references (which generate `#cohort-<name-with-underscores-as-hyphens>`
// markdown links) resolve in-page. Other chapters use `chapter-<id>`.
function chapterSectionId(chId) {{
  if (chId.startsWith('cohort:')) {{
    return 'cohort-' + chId.slice(7).replace(/_/g, '-');
  }}
  return 'chapter-' + cssEscape(chId);
}}

for (const ch of CHAPTERS) {{
  const sec = document.createElement('section');
  sec.className = 'chapter';
  sec.id = chapterSectionId(ch.id);
  sec.innerHTML = `<h2>${{escapeHtml(ch.title)}}</h2>` +
                  (ch.intro ? `<div class="intro">${{escapeHtml(ch.intro)}}</div>` : '');
  for (const ref of ch.entries) {{
    const e = ENTRIES[ref];
    if (!e) continue;
    const card = document.createElement('div');
    card.className = 'card';
    card.id = `card-${{cssEscape(ref)}}`;
    card.dataset.ref = ref;
    card.innerHTML = renderCard(e);
    const showOnMap = card.querySelector('a[data-action="show-on-map"]');
    if (showOnMap) {{
      showOnMap.addEventListener('click', (ev) => {{
        ev.preventDefault();
        focusOnMap(ref);
      }});
    }}
    sec.appendChild(card);
    cardEls[ref] = card;
  }}
  cardsRoot.appendChild(sec);
  chapterEls[ch.id] = sec;
}}

function renderCard(e) {{
  const fxBadge  = e.foxglove        ? '<span class="badge foxglove">★ Foxglove</span>' : '';
  const infBadge = e.inferred_coords ? '<span class="badge inferred">⚑ Inferred coords</span>' : '';
  const fdBadge  = e.has_findings    ? '<span class="badge findings">📄 Findings</span>' : '';
  const vBadge   = `<span class="badge ${{e.verdict.toLowerCase()}}">${{e.verdict}}</span>`;
  const onMap    = e.coords
    ? `<a href="#" data-action="show-on-map">↗ Show on map</a>`
    : `<a style="color:#999;pointer-events:none">no pin</a>`;
  const portal   = e.portal_url
    ? ` <span style="color:var(--muted)">|</span> <a href="${{e.portal_url}}" target="_blank" rel="noopener">Source portal ↗</a>` : '';
  const bodyHtml = openExternalLinksInNewTab(marked.parse(e.card_md || ''));
  return `
    <div class="actions">${{onMap}}${{portal}}</div>
    <h3>#${{e.rank}} <a href="#card-${{cssEscape(e.ref)}}">${{escapeHtml(e.ref)}}</a></h3>
    <div class="verdict-line">
      ${{vBadge}} ${{fxBadge}} ${{infBadge}} ${{fdBadge}}
      · deep-read ${{e.deep_read}} · conf ${{e.confidence}}
      · ${{escapeHtml(e.council)}}
    </div>
    <div class="card-md">${{bodyHtml}}</div>
  `;
}}

// Add target="_blank" to absolute http(s) anchors in a rendered HTML
// string. In-page (#cohort-X / #app-X / #card-X) anchors stay local so
// the cross-references still scroll within the reader.
function openExternalLinksInNewTab(html) {{
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  tmp.querySelectorAll('a').forEach(a => {{
    const href = a.getAttribute('href') || '';
    if (href.startsWith('http:') || href.startsWith('https:')) {{
      a.target = '_blank';
      a.rel = 'noopener';
    }}
  }});
  return tmp.innerHTML;
}}

// ----- Chapter index ---------------------------------------------------
const idxRoot = document.getElementById('chapter-index');

// "Read this first" chapter link — jumps to the intro section. Sits
// outside the CHAPTERS loop since the intro isn't a worklist chapter.
{{
  const a = document.createElement('a');
  a.href = '#intro';
  a.className = 'chapter-link intro-link';
  a.title = 'Jump to the welcome / methodology / how-to-read briefing at the top of the page.';
  a.innerHTML = '<b>Read this first</b>';
  a.addEventListener('click', (e) => {{
    e.preventDefault();
    intro.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
  idxRoot.appendChild(a);
}}

for (const ch of CHAPTERS) {{
  const a = document.createElement('a');
  a.href = '#' + chapterSectionId(ch.id);
  a.className = 'chapter-link';
  a.dataset.chapter = ch.id;
  a.title = `Jump to "${{ch.title}}" (${{ch.entries.length}} application${{ch.entries.length === 1 ? '' : 's'}}) and fit-bounds the map to its pins.`;
  a.innerHTML = `${{escapeHtml(ch.title)}}` +
                `<span class="count-pill" data-count-for="${{ch.id}}">${{ch.entries.length}}</span>`;
  a.addEventListener('click', (e) => {{
    e.preventDefault();
    chapterEls[ch.id].scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    fitMapToChapter(ch.id);
  }});
  idxRoot.appendChild(a);
  chapterCountEls[ch.id] = a.querySelector('[data-count-for]');
}}
// Header height may change as chapter links wrap to new rows; nudge
// Leaflet to recompute the map size once the layout settles.
requestAnimationFrame(() => map.invalidateSize());

function fitMapToChapter(chapterId) {{
  const ch = CHAPTERS.find(c => c.id === chapterId);
  if (!ch) return;
  const ll = ch.entries
    .map(ref => ENTRIES[ref])
    .filter(e => e && e.coords)
    .map(e => [e.coords[1], e.coords[0]]);
  if (ll.length === 0) return;
  map.flyToBounds(L.latLngBounds(ll), {{ padding: [40, 40], maxZoom: 11 }});
}}

// ----- Bidirectional sync ----------------------------------------------
function scrollCardIntoView(ref) {{
  const el = cardEls[ref];
  if (!el) return;
  // 'start' lines up the card's header at the top of the scroll
  // container, so long cards always show their headline first rather
  // than dumping the reader mid-text.
  el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1100);
}}

function focusOnMap(ref) {{
  const e = ENTRIES[ref];
  if (!e || !e.coords) return;
  const m = markers[ref];
  if (!m) return;
  map.flyTo([e.coords[1], e.coords[0]], Math.max(map.getZoom(), 14));
  m.openPopup();
}}

// ----- Search + filters ------------------------------------------------
const searchInput = document.getElementById('search');
const filtersRoot = document.getElementById('filters');
const visibleCountEl = document.getElementById('visible-count');
const activeFilters = new Set();

filtersRoot.querySelectorAll('.chip').forEach(chip => {{
  chip.addEventListener('click', () => {{
    const k = chip.dataset.filter;
    if (activeFilters.has(k)) {{ activeFilters.delete(k); chip.classList.remove('active'); }}
    else                       {{ activeFilters.add(k);    chip.classList.add('active'); }}
    applyFilters();
  }});
}});
searchInput.addEventListener('input', () => applyFilters());

document.addEventListener('keydown', (e) => {{
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {{
    e.preventDefault();
    searchInput.focus(); searchInput.select();
  }} else if (e.key === 'Escape' && document.activeElement === searchInput) {{
    searchInput.value = ''; applyFilters();
  }}
}});

function matchesFilters(e) {{
  for (const f of activeFilters) {{
    if (f.startsWith('verdict:'))   {{ if (e.verdict   !== f.slice(8))  return false; }}
    else if (f.startsWith('deep_read:')) {{ if (e.deep_read !== f.slice(10)) return false; }}
    else if (f === 'foxglove')         {{ if (!e.foxglove)        return false; }}
    else if (f === 'has_findings')     {{ if (!e.has_findings)    return false; }}
    else if (f === 'inferred_coords')  {{ if (!e.inferred_coords) return false; }}
  }}
  return true;
}}

function applyFilters() {{
  const q = (searchInput.value || '').trim().toLowerCase();
  const chapterVisible = {{}};
  let total = 0;

  // Cards
  for (const ref in ENTRIES) {{
    const e = ENTRIES[ref];
    const matchSearch = !q || e.search_blob.includes(q);
    const matchFilter = matchesFilters(e);
    const visible = matchSearch && matchFilter;
    const el = cardEls[ref];
    if (el) el.style.display = visible ? '' : 'none';
    if (visible) {{
      chapterVisible[e.chapter] = (chapterVisible[e.chapter] || 0) + 1;
      total++;
    }}
  }}

  // Chapter index counts + hide empty chapters
  for (const ch of CHAPTERS) {{
    const n = chapterVisible[ch.id] || 0;
    chapterCountEls[ch.id].textContent = `${{n}} / ${{ch.entries.length}}`;
    chapterEls[ch.id].style.display = n === 0 ? 'none' : '';
  }}

  visibleCountEl.textContent = `${{total}} of ${{Object.keys(ENTRIES).length}} visible`;

  // Map markers — add/remove against the worklist layer group rather
  // than the map directly so the layer control's toggle still works.
  for (const ref in markers) {{
    const m = markers[ref];
    const e = ENTRIES[ref];
    const visible = (!q || e.search_blob.includes(q)) && matchesFilters(e);
    if (visible && !worklistLayer.hasLayer(m))      worklistLayer.addLayer(m);
    else if (!visible && worklistLayer.hasLayer(m)) worklistLayer.removeLayer(m);
  }}
}}

function cssEscape(s) {{
  return String(s).replace(/[^a-zA-Z0-9_-]/g, '-');
}}

// Initial render: paint all counts + show all.
applyFilters();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _load_plants_for_viewer(osm_path: Path = OSM_BUNDLED) -> list[dict]:
    """Load the OSM power-plants geojson and project to the minimum field
    set the viewer needs (coordinates + bucket + popup-relevant props).
    Pre-stamping the bucket here means the client doesn't repeat the
    classification logic.
    """
    if not osm_path.exists():
        return []
    raw = json.loads(osm_path.read_text())
    out: list[dict] = []
    for feat in raw.get("features", []):
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords or len(coords) != 2:
            continue
        props = feat.get("properties") or {}
        out.append({
            "lon": coords[0],
            "lat": coords[1],
            "bucket": _bucket(props.get("plant_source")),
            "name": props.get("name"),
            "operator": props.get("operator"),
            "plant_source": props.get("plant_source"),
            "plant_method": props.get("plant_method"),
            "plant_output_electricity": props.get("plant_output_electricity"),
            "osm_type": props.get("osm_type"),
            "osm_id": props.get("osm_id"),
        })
    return out


def build_reader(
    *,
    model: str = "granite4.1:30b",
    output_path: Path,
    geojson_path: Path | None = None,
    text_md_path: Path | None = None,
    version: str = "1.0",
    generated_at: dt.datetime | None = None,
    osm_path: Path | None = None,
) -> Path:
    """Build the integrated split-screen viewer HTML at `output_path`.

    `geojson_path` and `text_md_path` are accepted for API symmetry with
    the release orchestrator but the viewer reads from the DB directly —
    embedding the same data ensures the four artefacts (viewer, map,
    geojson, markdown) stay in lock-step. `osm_path` overrides the
    bundled OSM power-plants source for the toggleable overlay.
    """
    generated_at = generated_at or dt.datetime.now()
    with db.connect() as conn:
        data = worklist.fetch(conn, model=model)
        stats = corpus_stats_mod.collect(conn, model=model)

    # Assemble the per-application payload.
    chapters, ref_to_chapter = _build_chapters(data.rows)
    entries: dict[str, dict] = {}
    for rank, row in enumerate(data.rows, 1):
        e = _build_entry(row, rank, data.anchors, ref_to_chapter)
        entries[e["ref"]] = e

    plants = _load_plants_for_viewer(osm_path or OSM_BUNDLED)

    release_payload = {
        "version": version,
        "generated": generated_at.isoformat(timespec="seconds"),
        "model": model,
        "universe": stats["universe"]["total"],
        "verdict_dc": stats["verdicts"]["dc"],
        "verdict_adjacent": stats["verdicts"]["adjacent"],
        "verdict_unrelated": stats["verdicts"]["unrelated"],
        "worklist_size": len(data.rows),
        "plants_total": len(plants),
    }

    intro_md = _build_intro_markdown(
        version=version, model=model, stats=stats, rows=data.rows,
    )

    html = _HTML_TEMPLATE.format(
        version=version,
        generated=generated_at.isoformat(timespec="minutes"),
        model=model,
        release_json=json.dumps(release_payload, ensure_ascii=False),
        chapters_json=json.dumps(chapters, ensure_ascii=False),
        entries_json=json.dumps(entries, ensure_ascii=False),
        intro_md_json=json.dumps(intro_md, ensure_ascii=False),
        plants_json=json.dumps(plants, ensure_ascii=False),
        plant_bucket_color_json=json.dumps(PLANT_BUCKET_COLOR, ensure_ascii=False),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html)
    return output_path
