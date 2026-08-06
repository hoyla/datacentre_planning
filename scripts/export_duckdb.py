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

from dcp import db, signals  # noqa: E402

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
    "findings": """
        SELECT a.application_ref, f.signal_type, f.value_text, f.value_number,
               f.value_unit, f.evidence_text, f.evidence_page, f.model,
               d.content_sha256 AS document_sha256, d.url AS document_url,
               f.inserted_at
        FROM findings f
        JOIN applications a ON a.id = f.application_id
        LEFT JOIN documents d ON d.id = f.document_id""",
    "barbour_projects": """
        SELECT p.external_ref AS ptno, p.title, p.stage_summary, p.dev_type,
               p.address, p.postcode, p.latitude, p.longitude,
               p.value_gbp, p.floor_area, p.site_area,
               p.authority_name, p.planning_ref, p.plan_date, p.decision_date,
               p.start_date, p.completion_date, p.url
        FROM projects p""",
}

VIEWS: dict[str, str] = {
    "site_overview": """
        SELECT s.site_key, s.classification, s.display_name AS site_name,
               s.latitude, s.longitude,
               count(DISTINCT m.application_ref) AS applications,
               count(DISTINCT d.content_sha256)  AS documents,
               count(DISTINCT f.rowid)           AS findings,
               max(f.value_number) FILTER (WHERE upper(coalesce(f.value_unit,'')) = 'MW')
                                                 AS max_disclosed_mw,
               max(b.value_gbp)                  AS barbour_value_gbp,
               string_agg(DISTINCT t.verdict, ', ') AS verdicts
        FROM sites s
        LEFT JOIN site_members m ON m.site_key = s.site_key
        LEFT JOIN documents d ON d.application_ref = m.application_ref
        LEFT JOIN findings f ON f.application_ref = m.application_ref
        LEFT JOIN triage_verdicts t ON t.application_ref = m.application_ref
        LEFT JOIN barbour_projects b ON b.ptno = m.barbour_ptno
        GROUP BY 1,2,3,4,5""",
    "latest_verdict": """
        SELECT application_ref, verdict, worth_deep_read, confidence, rubric,
               prompt_version, enriched, why, signals, inserted_at
        FROM (SELECT *, row_number() OVER (PARTITION BY application_ref, rubric
                                           ORDER BY inserted_at DESC) AS rn
              FROM triage_verdicts) WHERE rn = 1""",
}


def main() -> None:
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
