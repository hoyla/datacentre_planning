"""Build the queryable handover database (DuckDB).

The workbook is the interface; this is for the data journalists who want
to run their own queries. Single file, no server, opens in DuckDB CLI,
Python, R, or the DuckDB web shell — and readable by pandas/polars
directly.

Design notes:

- **Denormalised where it helps, joined where it matters.** `sites`,
  `applications`, `documents`, `findings` and `triage_verdicts` keep
  their real grain; `site_overview` is a convenience view answering the
  questions people actually open the file to ask.
- **Provenance travels.** Every triage verdict carries its rubric, prompt
  version, enrichment flag and the exact rendered input the model saw —
  so a reader can adjudicate a classification without our infrastructure,
  which the data team may well do themselves.
- **Documents carry their acquisition route** (portal fetch, by hand)
  and their source URL, so any number can be walked back to a file.
- **No PII beyond what councils published.** Barbour contact/role fields
  are not exported; consultation responses inside documents are as the
  councils published them.

Usage:
    .venv/bin/python scripts/export_duckdb.py
        [--out data/exports/dc_build_<date>.duckdb]
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

from dcp import adjudication_gate  # noqa: E402
from dcp import db, signals  # noqa: E402
from dcp import operator_disclosure  # noqa: E402

TABLES: dict[str, str] = {
    "sites": """
        SELECT s.site_key, s.classification, s.display_name,
               s.latitude, s.longitude, s.coord_source, s.radius_km,
               s.materialised_at
        FROM sites s WHERE s.retired_at IS NULL""",
    "site_members": """
        SELECT s.site_key, a.application_ref, p.external_ref AS barbour_ptno,
               m.joined_via
        FROM site_members m
        JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
        LEFT JOIN applications a ON a.id = m.application_id
        LEFT JOIN projects p ON p.id = m.project_id
        WHERE m.retired_at IS NULL""",
    # External capacity claims and their site matches, exported keyed by
    # site_key like everything else. The claim rows stay unjoined to the
    # sites table's own columns — the match is the only bridge, and it
    # carries its confidence, method and evidence so a query can decide
    # which tiers to trust.
    "capacity_claims": """
        SELECT cl.id AS claim_id, cl.source_key, cl.claim_name,
               cl.quantity_type, cl.value_original, cl.unit_original,
               cl.value_mw, cl.stage, cl.as_at,
               cl.attrs->>'connection_point' AS connection_point,
               cl.attrs->>'existing_connection_date' AS connection_date,
               -- Who published it, what they called it, and the span it
               -- was read from. The reader's Operators view and the
               -- workbook's two operator sheets are both built from
               -- these four; without them the same analysis cannot be
               -- reproduced here, which would make this file a narrower
               -- view of the store than the artefacts built on it.
               coalesce(cl.attrs->>'operator',
                        cl.attrs->>'company_name') AS published_by,
               cl.attrs->>'company_number' AS company_number,
               cl.attrs->>'operator_term' AS published_as,
               cl.attrs->>'quote' AS source_quote,
               cl.source_url, cl.source_locator, cl.inserted_at
        FROM capacity_claims cl""",
    "capacity_claim_matches": """
        SELECT m.claim_id, s.site_key, m.method, m.confidence, m.evidence,
               m.matched_by, m.inserted_at, m.retired_at, m.retired_reason
        FROM capacity_claim_matches m
        JOIN sites s ON s.id = m.site_id""",
    "applications": """
        SELECT a.application_ref,
               split_part(a.application_ref,'/',1) AS council,
               a.council_gss, a.title, a.description, a.address, a.postcode,
               a.date_received, a.date_decided, a.status, a.url AS portal_url,
               a.raw_metadata->>'app_type' AS application_type,
               (a.raw_metadata->>'location_y')::float AS latitude,
               (a.raw_metadata->>'location_x')::float AS longitude,
               array_to_string(a.discovered_via, ', ') AS discovered_via,
               a.raw_metadata->'agile_parties' ->> 'applicantName' AS applicant_name,
               a.raw_metadata->'agile_parties' ->> 'agentName' AS agent_name,
               a.raw_metadata->'portal_status_observed' ->> 'applicant' AS applicant_observed,
               a.raw_metadata->'portal_status_observed' ->> 'agent' AS agent_observed,
               a.first_seen_at
        FROM applications a""",
    "triage_verdicts": """
        SELECT a.application_ref, t.model, t.verdict, t.worth_deep_read,
               array_to_string(t.signals, ', ') AS signals, t.why, t.confidence,
               t.raw_response->>'rubric' AS rubric,
               t.raw_response->>'prompt_version' AS prompt_version,
               (t.raw_response->>'enriched')::boolean AS enriched,
               t.raw_response->>'rendered_input' AS model_input,
               t.inserted_at
        FROM triage t JOIN applications a ON a.id = t.application_id""",
    "documents": """
        SELECT a.application_ref, d.kind, d.content_sha256, d.bytes_path,
               d.url AS source_url,
               CASE WHEN d.url LIKE 'file://%' THEN 'by hand'
                    WHEN d.url LIKE '%#%' THEN 'by hand via browser'
                    ELSE 'portal fetch' END AS obtained,
               d.page_count, d.ocr_used, d.fetched_at
        FROM documents d JOIN applications a ON a.id = d.application_id""",
    # The adjudication columns matter more here than anywhere else. This
    # file exists for the question that is not in a column, which means
    # somebody will write `WHERE value_unit = 'MW' ORDER BY value_number
    # DESC` -- and the largest megawatt figures in this corpus are a 30 GW
    # national storage target and a 22,700 MW market forecast. Without a
    # verdict beside each figure the file invites exactly the mistake the
    # adjudication layer exists to prevent.
    "findings": """
        WITH adj AS (
          SELECT DISTINCT ON (finding_id)
                 finding_id, verdict, quantity_type, value_mw, unit_note
          FROM power_adjudication
          ORDER BY finding_id, (verdict = 'unclear'), inserted_at DESC)
        SELECT a.application_ref, f.signal_type, f.value_text, f.value_number,
               f.value_unit, f.evidence_text, f.evidence_page,
               -- Whose division evidence_page indexes. Only a PDF has
               -- pages; a Word file's index is a section, a workbook's a
               -- sheet. Kept beside the number rather than folded into
               -- it so the number stays sortable.
               d.pagination AS evidence_page_is_a, f.model,
               d.content_sha256 AS document_sha256, d.url AS document_url,
               adj.verdict        AS whose_figure,
               adj.quantity_type  AS quantity_type,
               adj.value_mw       AS adjudicated_mw,
               adj.unit_note      AS quantity_note,
               f.inserted_at
        FROM findings f
        JOIN applications a ON a.id = f.application_id
        LEFT JOIN documents d ON d.id = f.document_id
        LEFT JOIN adj ON adj.finding_id = f.id""",
    # The adjudications in full, so the reasoning is inspectable and not
    # only its conclusion. Every verdict carries the sentence that decided
    # it.
    "power_adjudication": """
        SELECT a.application_ref, pa.verdict, pa.quantity_type,
               pa.value_mw, pa.value_original, pa.unit_original,
               pa.unit_note, pa.is_maximum, pa.reasoning,
               f.signal_type, f.evidence_text, f.evidence_page,
               d.pagination AS evidence_page_is_a,
               pa.model, pa.prompt_version, pa.inserted_at
        FROM power_adjudication pa
        JOIN findings f ON f.id = pa.finding_id
        LEFT JOIN documents d ON d.id = f.document_id
        JOIN applications a ON a.id = pa.application_id""",
    "barbour_projects": """
        SELECT p.external_ref AS ptno, p.title, p.stage_summary, p.dev_type,
               p.address, p.postcode, p.latitude, p.longitude,
               p.value_gbp, p.floor_area, p.site_area,
               p.authority_name, p.planning_ref, p.plan_date, p.decision_date,
               p.start_date, p.completion_date, p.url
        FROM projects p""",
}

VIEWS: dict[str, str] = {
    # One CTE per contributing table, each already grouped to the site,
    # then joined one-to-one. The previous shape LEFT JOINed documents,
    # findings, verdicts and Barbour into a single GROUP BY, so a site
    # with 200 documents and 40,000 findings materialised eight million
    # rows to count DISTINCT its way back out of. It survived that;
    # adding power_adjudication to the same join multiplied it again and
    # a single-site lookup stopped returning. `count(DISTINCT ...)` hid
    # the fan-out from the answers but not from the cost, and a database
    # a reporter is invited to query has to answer quickly.
    #
    # Pre-aggregating also makes `power_figures_excluded` expressible at
    # all: a plain sum over the fanned-out join counts each excluded
    # figure once per document in the application.
    "site_overview": """
        WITH apps AS (
          SELECT site_key, count(DISTINCT application_ref) AS n
          FROM site_members GROUP BY 1),
        docs AS (
          SELECT m.site_key, count(DISTINCT d.content_sha256) AS n
          FROM site_members m
          JOIN documents d ON d.application_ref = m.application_ref
          GROUP BY 1),
        finds AS (
          SELECT m.site_key, count(*) AS n
          FROM site_members m
          JOIN findings f ON f.application_ref = m.application_ref
          GROUP BY 1),
        -- Adjudicated capacity only. This was `max(value_number) WHERE
        -- unit = 'MW'` over every finding, which is the power-attribution
        -- error the adjudication layer exists to correct: planning
        -- statements argue for approval by quoting the market, so the
        -- largest MW figure in a site's documents is usually not about
        -- that site. It reported West London Technology Park at 298,000
        -- MW — about ten times the UK grid, from a European demand
        -- scenario — and Amazon Didcot at 22,700, a Savills forecast.
        -- Both had already been adjudicated `market_context` correctly;
        -- this view simply never asked. `export_handover.py` was fixed
        -- for the identical expression and this one was missed, so a
        -- single release stated 298,000 MW and 155 MW for one site
        -- depending on which artefact you opened.
        --
        -- Four columns rather than one, matching the workbook: IT load,
        -- total site demand, grid connection and standby generation are
        -- different quantities for the same site (corpus medians 44, 84,
        -- 99 and 3.3 MW), and a single "site MW" column mixes them.
        pwr AS (
          SELECT m.site_key,
                 max(pa.value_mw) FILTER (WHERE pa.verdict = 'site_capacity'
                     AND pa.quantity_type = 'it_load')           AS it_load_mw,
                 max(pa.value_mw) FILTER (WHERE pa.verdict = 'site_capacity'
                     AND pa.quantity_type = 'total_site')        AS total_site_mw,
                 max(pa.value_mw) FILTER (WHERE pa.verdict = 'site_capacity'
                     AND pa.quantity_type = 'grid_connection')   AS grid_connection_mw,
                 max(pa.value_mw) FILTER (WHERE pa.verdict = 'site_capacity'
                     AND pa.quantity_type = 'onsite_generation') AS onsite_generation_mw,
                 -- Figures considered and set aside, so their absence
                 -- reads as a decision rather than as a gap.
                 count(*) FILTER (WHERE pa.verdict <> 'site_capacity')
                                                                 AS excluded
          FROM site_members m
          JOIN power_adjudication pa ON pa.application_ref = m.application_ref
          GROUP BY 1),
        verd AS (
          SELECT m.site_key, string_agg(DISTINCT t.verdict, ', ') AS v
          FROM site_members m
          JOIN triage_verdicts t ON t.application_ref = m.application_ref
          GROUP BY 1),
        barb AS (
          SELECT m.site_key, max(b.value_gbp) AS v
          FROM site_members m
          JOIN barbour_projects b ON b.ptno = m.barbour_ptno
          GROUP BY 1)
        SELECT s.site_key, s.classification, s.display_name AS site_name,
               s.latitude, s.longitude,
               coalesce(apps.n, 0)  AS applications,
               coalesce(docs.n, 0)  AS documents,
               coalesce(finds.n, 0) AS findings,
               pwr.it_load_mw, pwr.total_site_mw,
               pwr.grid_connection_mw, pwr.onsite_generation_mw,
               coalesce(pwr.excluded, 0) AS power_figures_excluded,
               barb.v AS barbour_value_gbp,
               verd.v AS verdicts
        FROM sites s
        LEFT JOIN apps  ON apps.site_key  = s.site_key
        LEFT JOIN docs  ON docs.site_key  = s.site_key
        LEFT JOIN finds ON finds.site_key = s.site_key
        LEFT JOIN pwr   ON pwr.site_key   = s.site_key
        LEFT JOIN verd  ON verd.site_key  = s.site_key
        LEFT JOIN barb  ON barb.site_key  = s.site_key""",
    "latest_verdict": """
        SELECT application_ref, verdict, worth_deep_read, confidence, rubric,
               prompt_version, enriched, why, signals, inserted_at
        FROM (SELECT *, row_number() OVER (PARTITION BY application_ref, rubric
                                           ORDER BY inserted_at DESC) AS rn
              FROM triage_verdicts) WHERE rn = 1""",
}


def main() -> None:
    # Nothing is written from adjudications nobody has
    # corrected. See dcp/adjudication_gate.py.
    adjudication_gate.require_corrected()
    import duckdb

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(
        f"data/exports/dc_build_{dt.date.today().isoformat()}.duckdb"))
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()

    con = duckdb.connect(str(args.out))
    counts: dict[str, int] = {}
    with db.connect() as pg:
        for name, sql in TABLES.items():
            with pg.cursor() as cur:
                cur.execute(sql)
                cols = [c.name for c in cur.description]
                rows = cur.fetchall()
            con.execute(f"DROP TABLE IF EXISTS {name}")
            placeholders = ", ".join("?" for _ in cols)
            col_defs = ", ".join(f'"{c}"' for c in cols)
            # Infer types by letting DuckDB take the first non-null per column.
            con.execute(f"CREATE TABLE {name} ({', '.join(_types(cols, rows))})")
            if rows:
                con.executemany(
                    f"INSERT INTO {name} ({col_defs}) VALUES ({placeholders})",
                    [tuple(_coerce(v) for v in r) for r in rows])
            counts[name] = len(rows)

    # The canonical operator, beside the name the source printed rather
    # than over it. Filed accounts name a legal entity and a website
    # names a brand, so grouping capacity_claims by published_by splits
    # Ark into "ARK DATA CENTRES LIMITED" and "Ark Data Centres" — two
    # rows here for the one row the reader and the workbook show. The
    # mapping is this project's inference, hand-checked and small, and
    # it belongs with the data rather than only inside the module that
    # renders it. published_by is untouched.
    con.execute("ALTER TABLE capacity_claims ADD COLUMN operator VARCHAR")
    con.execute("UPDATE capacity_claims SET operator = published_by")
    for legal, brand in operator_disclosure.COMPANY_TO_OPERATOR.items():
        con.execute("UPDATE capacity_claims SET operator = ? "
                    "WHERE published_by = ?", [brand, legal])

    # Environmental signals: derived deterministically, same lexicon as the
    # workbook, so the two artefacts agree.
    con.execute("""CREATE TABLE environmental_signals
                   (application_ref VARCHAR, subject VARCHAR, term VARCHAR)""")
    rows = con.execute("SELECT application_ref, description FROM applications").fetchall()
    env_rows = [(ref, group, term)
                for ref, desc in rows
                for group, terms in signals.environmental_signals(desc).items()
                for term in terms]
    if env_rows:
        con.executemany("INSERT INTO environmental_signals VALUES (?, ?, ?)", env_rows)
    counts["environmental_signals"] = len(env_rows)

    for name, sql in VIEWS.items():
        con.execute(f"CREATE VIEW {name} AS {sql}")

    con.execute("""CREATE TABLE _provenance (key VARCHAR, value VARCHAR)""")
    con.executemany("INSERT INTO _provenance VALUES (?, ?)", [
        ("generated_at_utc", dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
        ("pipeline_commit", _commit()),
        ("barbour_note", "Barbour ABI data licensed for this use; attribution "
                         "required in published output. Contact and role fields "
                         "deliberately not exported."),
        ("documents_note", "bytes_path is relative to the pipeline's data store; "
                           "source_url and obtained record how each file was got."),
        ("verdict_note", "triage_verdicts is append-only and multi-rubric; use the "
                         "latest_verdict view for one row per application per rubric. "
                         "model_input is exactly what the model saw."),
        ("capacity_claims_note", "External figures as their source states "
                         "them, from three sources with different standing: "
                         "NESO's Existing Agreements Register (contracted "
                         "grid connection capacity), accounts filed at "
                         "Companies House (built capacity and metered "
                         "consumption, audited), and operators' own websites "
                         "(marketing material, the weakest of the three). "
                         "source_key says which. quantity_type says what a "
                         "figure measures and is never elided: a contracted "
                         "connection, an IT load, a built capacity and an "
                         "observed draw are four different quantities and "
                         "must not be compared as one. published_by, "
                         "published_as and source_quote carry who published "
                         "the figure, the term or data key they published it "
                         "under, and the verbatim span it was read from — "
                         "everything needed to rebuild the operator "
                         "disclosure comparison the reader and the workbook "
                         "show. Group by operator, not published_by: the "
                         "latter is the name the source printed, and one "
                         "company's filed accounts and website print two "
                         "different ones. Never join value_mw onto a site's own power "
                         "columns; the bridge is capacity_claim_matches, "
                         "whose confidence tier ('tentative' is a lead, not "
                         "an attribution) and written evidence travel with "
                         "every match. Matches with retired_at set are "
                         "withdrawn assertions kept as history."),
    ])
    con.close()

    size_mb = args.out.stat().st_size / 1e6
    print(f"wrote {args.out} ({size_mb:.1f} MB)")
    for k, v in counts.items():
        print(f"  {k:24} {v:7d} rows")
    print(f"  views: {', '.join(VIEWS)}")


def _types(cols: list[str], rows: list) -> list[str]:
    """Column definitions, inferring numeric/bool/timestamp from the first
    non-null value; everything else is VARCHAR (safe for a handover file)."""
    import datetime as _dt
    from decimal import Decimal
    out = []
    for i, c in enumerate(cols):
        val = next((r[i] for r in rows if r[i] is not None), None)
        if isinstance(val, bool):
            t = "BOOLEAN"
        elif isinstance(val, int):
            t = "BIGINT"
        elif isinstance(val, (float, Decimal)):
            t = "DOUBLE"
        elif isinstance(val, _dt.datetime):
            t = "TIMESTAMP"
        elif isinstance(val, _dt.date):
            t = "DATE"
        else:
            t = "VARCHAR"
        out.append(f'"{c}" {t}')
    return out


def _coerce(v):
    from decimal import Decimal
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (list, dict)):
        import json
        return json.dumps(v, ensure_ascii=False)
    return v


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              cwd=Path(__file__).parent.parent).stdout.strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
