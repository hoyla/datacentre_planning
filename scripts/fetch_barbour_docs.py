"""Targeted document fetch for the Barbour-round applications.

Walks the applications ingested in the 2026-08-02 Barbour round (the gap
ingest plus the parent backfill), routes each to the right portal adapter by
URL shape, and fetches every available document. Applications on portals we
have no adapter for are classified and reported, not silently skipped.

Deliberately worklist-independent: these applications have no (or fresh)
triage verdicts, and several are exactly the keyword-blind kind that triage
under-ranks — the fetch must not depend on the ranking.

Routing:
- Idox (any `applicationDetails.do` URL, incl. non-standard mount paths)
  → dcp.sources.idox.fetch_documents_for_application
- Ocella (`/OcellaWeb/planningDetails`)
  → dcp.sources.ocella.fetch_documents_for_application
- Everything else → counted per portal family in the "needs adapter/manual"
  report at the end.

Idempotent: content-hash dedup in the documents table and on-disk layout;
re-runs skip existing bytes.

Usage:
    .venv/bin/python -u scripts/fetch_barbour_docs.py [--delay 5] [--limit N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox, ocella  # noqa: E402


def portal_family(url: str | None) -> str:
    if not url:
        return "no_url"
    u = url.lower()
    if idox._is_idox_url(url):
        return "idox"
    if "/ocellaweb/planningdetails" in u:
        return "ocella"
    if "agileapplications.co.uk" in u:
        return "agile"
    if "planningregister." in u or "/planning/display/" in u:
        return "arcus_register"
    if "planningexplorer" in u or "stddetails.aspx" in u:
        return "northgate_planning_explorer"
    if "/s/detail/" in u:
        return "salesforce"
    if "lpassure" in u:
        return "nec_lpassure"
    return "other_bespoke"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT a.id, a.application_ref, a.url
                   FROM applications a
                   WHERE a.first_seen_at >= '2026-08-02'
                   ORDER BY a.application_ref""",
            )
            targets = cur.fetchall()
        if args.limit:
            targets = targets[: args.limit]

        idox_source = repo.ensure_source(
            conn, name="idox", kind="council", base_url="(per-council Idox host)")
        ocella_source = repo.ensure_source(
            conn, name="ocella", kind="council", base_url="(per-council Ocella host)")

        totals = {"apps": 0, "docs_downloaded": 0, "docs_existing": 0,
                  "errors": 0, "by_error_class": {}, "fully_successful": 0}
        unfetchable: dict[str, list[str]] = {}

        idox_client = idox.IdoxClient(delay_seconds=args.delay)
        ocella_client = ocella.OcellaClient(delay_seconds=args.delay)
        try:
            for app_id, ref, url in targets:
                totals["apps"] += 1
                family = portal_family(url)
                if family == "idox":
                    s = idox.fetch_documents_for_application(
                        conn, client=idox_client, application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=idox_source, data_dir=args.data_dir)
                elif family == "ocella":
                    s = ocella.fetch_documents_for_application(
                        conn, client=ocella_client, application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=ocella_source, data_dir=args.data_dir)
                else:
                    unfetchable.setdefault(family, []).append(ref)
                    print(f"  {ref:44} NEEDS[{family}]")
                    continue
                totals["docs_downloaded"] += s.get("downloaded", 0)
                totals["docs_existing"] += s.get("skipped_existing", 0)
                totals["errors"] += s.get("errors", 0)
                cls = s.get("error_class")
                if cls:
                    totals["by_error_class"][cls] = totals["by_error_class"].get(cls, 0) + 1
                    print(f"  {ref:44} SKIP[{cls}]")
                else:
                    totals["fully_successful"] += 1
                    print(f"  {ref:44} links={s.get('links_found',0):3d} "
                          f"new={s.get('downloaded',0):3d}")
        finally:
            idox_client.close()
            ocella_client.close()
        conn.commit()

    print(f"\nTotals: {totals}")
    if unfetchable:
        print("\nNo adapter for these portals (manual or new-adapter work):")
        for family, refs in sorted(unfetchable.items()):
            print(f"  {family} ({len(refs)}):")
            for r in refs:
                print(f"    {r}")


if __name__ == "__main__":
    main()
