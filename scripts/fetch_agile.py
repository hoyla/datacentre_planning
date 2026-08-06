"""Fetch documents for every Agile Applications portal application.

Companion runner for `dcp.sources.agile`. Defaults to the campaign
cohort shape (DC-verdict applications without documents) but will walk
every Agile application in the universe with `--all`.

Also promotes the API's structured party fields (applicant/agent names,
no contact details) into `applications.raw_metadata.agile_parties` —
Agile is currently the only source giving us these reliably, and they
feed the parties/affiliations analysis.

Usage:
    .venv/bin/python -u scripts/fetch_agile.py [--all] [--delay 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import agile  # noqa: E402


COHORT_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (application_id) application_id, verdict
  FROM triage ORDER BY application_id, inserted_at DESC)
SELECT a.id, a.application_ref, a.url
FROM applications a
LEFT JOIN latest l ON l.application_id = a.id
WHERE a.url ILIKE '%%agileapplications%%'
  AND (%(all)s OR (coalesce(l.verdict,'') = 'DC'
                   AND NOT EXISTS (SELECT 1 FROM documents d
                                   WHERE d.application_id = a.id)))
ORDER BY a.application_ref
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="Every Agile application, not just document-less "
                         "DC-verdict ones.")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(COHORT_SQL, {"all": args.all})
            targets = cur.fetchall()
        source_id = repo.ensure_source(
            conn, name=agile.SOURCE_NAME, kind="council",
            base_url="planning.agileapplications.co.uk")
        print(f"{len(targets)} Agile applications to fetch")

        totals = {"apps": 0, "downloaded": 0, "errors": 0, "no_documents": 0}
        with agile.AgileClient(delay_seconds=args.delay) as client:
            for app_id, ref, url in targets:
                totals["apps"] += 1
                parsed = agile.parse_portal_url(url)
                if parsed is None:
                    print(f"  {ref:44} SKIP[unparseable_url]")
                    continue
                slug, portal_id = parsed
                # Promote party fields alongside the raw record.
                try:
                    record = client.application(slug, portal_id)
                    parties = agile.party_fields(record)
                    if parties:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE applications SET raw_metadata = "
                                "jsonb_set(coalesce(raw_metadata,'{}'::jsonb), "
                                "'{agile_parties}', %s::jsonb) WHERE id = %s",
                                (json.dumps(parties), app_id))
                        conn.commit()
                except Exception as exc:
                    print(f"  {ref:44} party fetch failed: {exc}")

                s = agile.fetch_documents_for_application(
                    conn, client=client, application_id=app_id,
                    application_ref=ref, application_url=url,
                    source_id=source_id, data_dir=args.data_dir)
                totals["downloaded"] += s["downloaded"]
                totals["errors"] += s["errors"]
                cls = s.get("error_class")
                if cls == "no_documents":
                    totals["no_documents"] += 1
                if cls:
                    print(f"  {ref:44} SKIP[{cls}]")
                else:
                    print(f"  {ref:44} docs={s['links_found']:3d} "
                          f"new={s['downloaded']:3d}")
    print(f"\nTotals: {totals}")


if __name__ == "__main__":
    main()
