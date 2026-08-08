"""Generate the data-team handover workbook: sites + applications tabs.

Two-grain export of the dc_build universe from the materialised sites
tables (migration 006): one row per active site, one row per member
application, linked by the stable ``site_key``. Every heuristic column
carries its source; nothing here is hand-maintained — regenerate after
any pipeline change and the workbook reflects the database.

The workbook is an *interface*, not a store: annotations belong in the
designated annotation tab of the shared copy (or a separate sheet),
never in generated columns.

Usage:
    .venv/bin/python scripts/export_handover.py
        [--out data/exports/dc_build_handover_<date>.xlsx]
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402


SITE_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (application_id) application_id, verdict, confidence, model
  FROM triage ORDER BY application_id, inserted_at DESC),
app_docs AS (
  SELECT application_id, count(*) AS n FROM documents GROUP BY application_id),
app_findings AS (
  -- signal_family, not signal_type: the extraction prompt asks the model
  -- to name what it found in its own words, which produced 54,044
  -- distinct labels. Aggregating those per application yields a
  -- spreadsheet cell nobody can read or filter. The family is the
  -- 25-value canonical index over them (dcp/signal_families.py); the
  -- original label is still on every findings row for anyone drilling in.
  SELECT application_id, count(*) AS n,
         array_agg(DISTINCT signal_family) FILTER (
             WHERE signal_family IS NOT NULL
               AND signal_family <> 'unclassified')            AS signal_families
  FROM findings GROUP BY application_id),
app_power AS (
  -- Adjudicated capacity ONLY. The previous version of this query took
  -- max(value_number) over every finding carrying a 'MW' unit, which is
  -- wrong in a way that reaches the reader: planning statements argue for
  -- approval by quoting market forecasts, policy targets and other
  -- schemes, so the largest MW figure in a site's documents is usually
  -- not about that site. Under that rule a Slough application reported
  -- 30GW (an NGESO storage target) and a Chiltern one 22,700MW (a Savills
  -- market forecast).
  --
  -- power_adjudication resolves whose figure each one is; only
  -- verdict='site_capacity' is admitted here. The quantities stay in
  -- separate columns because IT load, grid connection and standby
  -- generation are different numbers for the same site — medians across
  -- the corpus are 44 MW, 99 MW and 3.3 MW — and a single "site MW"
  -- column would silently mix them.
  SELECT application_id,
         max(value_mw) FILTER (WHERE quantity_type = 'it_load')     AS it_load_mw,
         max(value_mw) FILTER (WHERE quantity_type = 'total_site')  AS total_site_mw,
         max(value_mw) FILTER (WHERE quantity_type = 'grid_connection')
                                                                    AS grid_mw,
         max(value_mw) FILTER (WHERE quantity_type = 'onsite_generation')
                                                                    AS gen_mw,
         count(*)                                                   AS n_capacity,
         count(*) FILTER (WHERE is_maximum)                         AS n_ultimate
  FROM power_adjudication
  WHERE verdict = 'site_capacity' AND value_mw IS NOT NULL
  GROUP BY application_id),
app_power_excluded AS (
  -- Recorded so a reader can see that figures were considered and set
  -- aside, rather than wondering why a number in the documents is absent
  -- from the workbook.
  SELECT application_id, count(*) AS n_excluded
  FROM power_adjudication WHERE verdict <> 'site_capacity'
  GROUP BY application_id),
app_provenance AS (
  -- How this application's documents were obtained. Hand-ingested
  -- documents carry file:// URIs (no portal link to offer a reader);
  -- exports must label them rather than leave an apparent gap.
  SELECT application_id,
         count(*) FILTER (WHERE url LIKE 'file://%%') AS manual_docs,
         count(*) FILTER (WHERE url NOT LIKE 'file://%%') AS portal_docs
  FROM documents GROUP BY application_id),
app_eia AS (
  -- Heuristic EIA indicators, two independent signals: the application
  -- reference carries an EIA-shaped suffix (FULEA/OUTES/EIASR/SCR/SCO/
  -- SCREEN), or the held documents include Environmental Statement
  -- material. Authoritative status (screening outcomes) comes from
  -- deep-read; the column is deliberately labelled heuristic.
  SELECT a.id AS application_id,
         (a.application_ref ~* '(EA|ES)$|EIASR|/SCR|/SCO|SCREEN') AS ref_hit,
         EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id
                 AND (d.url ~* 'ENVIRONMENTAL_STATEMENT|ES_APPENDIX|ENV_STATEMENT'
                      OR d.kind ~* 'environmental statement')) AS doc_hit
  FROM applications a)
SELECT s.site_key, s.classification, s.display_name,
       s.latitude, s.longitude, s.coord_source,
       array_agg(DISTINCT split_part(a.application_ref,'/',1))
           FILTER (WHERE a.id IS NOT NULL)                    AS councils,
       count(DISTINCT a.id)                                   AS n_apps,
       array_agg(DISTINCT a.application_ref)
           FILTER (WHERE a.id IS NOT NULL)                    AS app_refs,
       array_agg(DISTINCT coalesce(l.verdict,'?'))
           FILTER (WHERE a.id IS NOT NULL)                    AS verdicts,
       coalesce(sum(ad.n), 0)                                 AS docs_held,
       coalesce(sum(af.n), 0)                                 AS findings_n,
       max(pw.it_load_mw)                                     AS it_load_mw,
       max(pw.total_site_mw)                                  AS total_site_mw,
       max(pw.grid_mw)                                        AS grid_mw,
       max(pw.gen_mw)                                         AS gen_mw,
       coalesce(sum(pw.n_capacity), 0)                        AS n_capacity,
       coalesce(sum(px.n_excluded), 0)                        AS n_excluded,
       -- Correlated rather than joined: array_agg cannot flatten the
       -- per-application arrays across a site group, and this runs once
       -- per site against an indexed column.
       (SELECT array_agg(DISTINCT f2.signal_family)
          FROM findings f2
          JOIN site_members m3 ON m3.application_id = f2.application_id
               AND m3.retired_at IS NULL
         WHERE m3.site_id = s.id
           AND f2.signal_family IS NOT NULL
           AND f2.signal_family <> 'unclassified')            AS signal_families,
       bool_or(ae.ref_hit)                                    AS eia_ref_hit,
       bool_or(ae.doc_hit)                                    AS eia_doc_hit,
       coalesce(sum(ap.manual_docs), 0)                       AS manual_docs,
       (SELECT p2.external_ref FROM site_members m2
          JOIN projects p2 ON p2.id = m2.project_id
        WHERE m2.site_id = s.id AND m2.retired_at IS NULL
        ORDER BY p2.external_ref LIMIT 1)                     AS ptno,
       max(p.title)                                           AS barbour_title,
       max(p.stage_summary)                                   AS barbour_stage,
       max(p.value_gbp)                                       AS barbour_value_gbp,
       max(p.floor_area)                                      AS barbour_floor_area,
       max(p.site_area)                                       AS barbour_site_area,
       max(p.plan_date)                                       AS barbour_plan_date,
       max(p.decision_date)                                   AS barbour_decision_date
FROM sites s
LEFT JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
LEFT JOIN applications a ON a.id = m.application_id
LEFT JOIN latest l ON l.application_id = a.id
LEFT JOIN app_docs ad ON ad.application_id = a.id
LEFT JOIN app_findings af ON af.application_id = a.id
LEFT JOIN app_power pw ON pw.application_id = a.id
LEFT JOIN app_power_excluded px ON px.application_id = a.id
LEFT JOIN app_eia ae ON ae.application_id = a.id
LEFT JOIN app_provenance ap ON ap.application_id = a.id
LEFT JOIN projects p ON p.id = m.project_id
WHERE s.retired_at IS NULL
GROUP BY s.id
ORDER BY s.site_key
"""

APP_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (application_id) application_id, verdict, confidence,
         model, why, signals
  FROM triage ORDER BY application_id, inserted_at DESC),
app_docs AS (
  SELECT application_id, count(*) AS n FROM documents GROUP BY application_id),
app_findings AS (
  SELECT application_id, count(*) AS n FROM findings GROUP BY application_id)
SELECT s.site_key, a.application_ref, m.joined_via,
       split_part(a.application_ref,'/',1) AS council,
       a.status, a.date_received, a.date_decided,
       l.verdict, l.confidence, l.model, l.why,
       array_to_string(l.signals, ', ') AS signals,
       a.url, coalesce(ad.n,0) AS docs_held, coalesce(af.n,0) AS findings_n,
       a.address, a.description
FROM sites s
JOIN site_members m ON m.site_id = s.id AND m.retired_at IS NULL
JOIN applications a ON a.id = m.application_id
LEFT JOIN latest l ON l.application_id = a.id
LEFT JOIN app_docs ad ON ad.application_id = a.id
LEFT JOIN app_findings af ON af.application_id = a.id
WHERE s.retired_at IS NULL
ORDER BY s.site_key, a.application_ref
"""

SITE_HEADERS = [
    "Site key", "Classification", "Site name", "Latitude", "Longitude",
    "Coordinate source", "Councils", "Applications", "Application refs",
    "Verdict mix (v1 triage)", "Documents held", "Verified findings",
    # Power, adjudicated. Four columns rather than one because these are
    # different quantities, not alternative estimates of one: a campus
    # commonly holds more standby generation than IT load, behind a larger
    # grid connection again. The counts let a reader see how much evidence
    # sits behind a figure and how much was set aside as not-this-site.
    "IT load MW (adjudicated)", "Total site MW (adjudicated)",
    "Grid connection MW (adjudicated)", "On-site generation MW (adjudicated)",
    "Capacity figures attributed to site", "Power figures excluded (context)",
    "Facility character", "Scale band", "Scale basis",
    "Finding subjects (families)",
    "Documents obtained by hand", "EIA indicators (heuristic)",
    "Environmental subjects (description keywords)",
    "Barbour Ptno", "Barbour title",
    "Barbour stage", "Barbour value £", "Barbour floor area sqm",
    "Barbour site area", "Barbour plan date", "Barbour decision date",
]

APP_HEADERS = [
    "Site key", "Application ref", "Joined site via", "Council", "Status",
    "Date received", "Date decided", "Verdict (latest)", "Verdict confidence",
    "Verdict model", "Verdict reasoning", "Signals", "Portal URL",
    "Documents held", "Verified findings",
    "Environmental signals (description keywords)", "Address", "Description",
]


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=Path(__file__).parent.parent,
        ).stdout.strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    default_out = Path(
        f"data/exports/dc_build_handover_{dt.date.today().isoformat()}.xlsx")
    ap.add_argument("--out", type=Path, default=default_out)
    args = ap.parse_args()

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    from collections import defaultdict

    from dcp import signals as sig
    from dcp import site_scale as scale

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(SITE_SQL)
        site_rows = cur.fetchall()
        cur.execute(APP_SQL)
        app_rows = cur.fetchall()

    # Environmental signals are extracted deterministically from the
    # description text (dcp/signals.py) rather than asked of the model:
    # reproducible, free, and carrying no risk to a validated prompt.
    # A floor, not a census — descriptions are terse, and the substantive
    # environmental content lives in the documents, which deep-read covers.
    app_env: dict[str, list[str]] = {}
    site_env: dict[str, set[str]] = defaultdict(set)
    site_desc: dict[str, list[str]] = defaultdict(list)
    for r in app_rows:
        site_key, ref, description = r[0], r[1], r[-1]
        found = sig.environmental_signals(description)
        flat = sig.flatten(found)
        app_env[ref] = flat
        site_env[site_key].update(found.keys())
        if description:
            site_desc[site_key].append(description)

    # Best floor area per site, for the scale band where no capacity has
    # been adjudicated. Deliberately a fallback, never a conversion: the
    # kW/m2 ratio spans an order of magnitude between fitted white space
    # and a shell-and-core shed, so area indicates physical size only.
    site_area_sqm: dict[str, float] = {}
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.site_key, max(f.value_number), min(lower(f.value_unit))
            FROM findings f
            JOIN site_members sm ON sm.application_id = f.application_id
                 AND sm.retired_at IS NULL
            JOIN sites s ON s.id = sm.site_id
            WHERE f.value_number IS NOT NULL
              AND lower(f.value_unit) IN ('sqm','m2','sq m','square metres',
                                          'square meters','sqft','ft2')
            GROUP BY s.site_key""")
        for site_key, value, unit in cur.fetchall():
            sqm = scale.area_to_sqm(float(value), unit)
            if sqm:
                site_area_sqm[site_key] = sqm

    wb = Workbook()

    def _sheet(title, headers):
        ws = wb.create_sheet(title) if wb.sheetnames != ["Sheet"] else wb.active
        ws.title = title
        ws.append(headers)
        for i in range(1, len(headers) + 1):
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDDDDD")
            c.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"
        return ws

    ws = _sheet("Sites", SITE_HEADERS)
    for r in site_rows:
        (key, cls, name, lat, lon, csrc, councils, n_apps, refs, verdicts,
         docs, findings_n, it_load_mw, total_site_mw, grid_mw, gen_mw,
         n_capacity, n_excluded, families, eia_ref, eia_doc, manual_docs,
         ptno, btitle, bstage, bvalue, bfloor, bsite, bplan, bdecision) = r
        eia = " + ".join(
            label for hit, label in
            [(eia_ref, "ref pattern"), (eia_doc, "ES documents")] if hit)

        # Character from the site's own descriptions, rolled up by
        # significance; scale from the strongest evidence available, with
        # the basis stated so a floor-area inference is never mistaken for
        # a disclosed capacity.
        character = scale.rollup_character(
            [scale.character_for(d) for d in site_desc.get(key, ())]
            or [scale.character_for(name)])
        headline_mw = it_load_mw or total_site_mw
        if headline_mw:
            band_key, band_label = scale.scale_from_mw(float(headline_mw))
            basis = "stated_capacity"
        elif site_area_sqm.get(key):
            band_key, band_label = scale.scale_from_area_sqm(site_area_sqm[key])
            basis = "floor_area"
        else:
            band_key, band_label, basis = "", "", "none"

        ws.append([
            key, cls, name, lat, lon, csrc,
            ", ".join(councils or []), n_apps, "\n".join(refs or []),
            ", ".join(sorted(verdicts or [])), docs, findings_n,
            it_load_mw, total_site_mw, grid_mw, gen_mw,
            n_capacity or "", n_excluded or "",
            scale.CHARACTERS[character].label, band_label,
            scale.BASIS_NOTE[basis],
            ", ".join(sorted(families or [])),
            manual_docs or "", eia,
            ", ".join(sorted(site_env.get(key, ()))),
            ptno, btitle, bstage, bvalue, bfloor, bsite,
            str(bplan or ""), str(bdecision or ""),
        ])

    ws = _sheet("Applications", APP_HEADERS)
    for r in app_rows:
        vals = [str(x) if isinstance(x, (dt.date, dt.datetime)) else x for x in r]
        # Insert the derived signals column just before Address/Description.
        ws.append(vals[:-2] + ["\n".join(app_env.get(r[1], ()))] + vals[-2:])

    ws = _sheet("Provenance", ["Field", "Value"])
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents")
        n_docs = cur.fetchone()[0]
    for k, v in [
        ("Generated at (UTC)", dt.datetime.now(dt.timezone.utc)
                                 .isoformat(timespec="seconds")),
        ("Pipeline commit", _git_commit()),
        ("Sites (active)", len(site_rows)),
        ("Applications in sites", len(app_rows)),
        ("Documents in corpus", n_docs),
        ("Verdict column source", "v1 triage rubric — dc_build v2.1 "
         "catalogue sweep pending; column will switch to dc_build classes"),
        ("Barbour columns", "Barbour ABI, licensed, credit required in "
         "published output; contact/role fields deliberately excluded"),
        ("Findings columns", "verified deep-read findings (v1, quote-gated); "
         "coverage partial until v2 deep-read"),
    ]:
        ws.append([k, str(v)])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)
    print(f"Wrote {args.out}")
    print(f"  Sites: {len(site_rows)} rows; Applications: {len(app_rows)} rows")


if __name__ == "__main__":
    main()
