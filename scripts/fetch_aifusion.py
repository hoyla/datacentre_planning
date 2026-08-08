#!/usr/bin/env python3
"""Fetch documents for the aifusion-backed registers (Central Bedfordshire).

These 165 applications sat at zero documents through every campaign run,
not because the council withholds them but because Acolnet does not serve
them — see `dcp/sources/aifusion.py` for how the real endpoint was found.

Runs standalone rather than inside `fetch_dc_campaign.py` so it can be
started while a campaign is already in flight. Resume is free: documents
already held are skipped by URL, and the content-hash unique constraint
catches anything that slips past.

    scripts/fetch_aifusion.py --limit 3        # try a few
    scripts/fetch_aifusion.py                  # the lot
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import aifusion, idox  # noqa: E402

log = logging.getLogger("fetch_aifusion")

COHORT_SQL = """
    SELECT a.id, a.application_ref, a.url
    FROM applications a
    WHERE a.url ILIKE ANY(%s)
      AND (%s OR NOT EXISTS (
            SELECT 1 FROM documents d WHERE d.application_id = a.id))
    ORDER BY a.application_ref
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None,
                   help="stop after N applications")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--api-delay", type=float, default=5.0,
                   help="spacing for the council's API host")
    p.add_argument("--doc-delay", type=float, default=1.0,
                   help="spacing for SharePoint document downloads")
    p.add_argument("--include-held", action="store_true",
                   help="revisit applications that already have documents")
    p.add_argument("--dry-run", action="store_true",
                   help="list each case's document count, download nothing")
    # Postgres lives on the same volume as the document store, so filling
    # the disk would take the database down with the fetch. One of these
    # applications is 1.1GB on its own; stopping early costs nothing
    # because re-runs skip what is already held.
    p.add_argument("--min-free-gb", type=float, default=15.0,
                   help="stop cleanly when free disk falls below this")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S")
    # httpx logs every request line at INFO. Here that means the whole
    # SharePoint download URL, tempauth token and all — kilobytes of noise
    # per document, and a bearer credential written to a log file we keep.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    patterns = [f"%{h}%" for h in aifusion.DEPLOYMENTS]
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(COHORT_SQL, (patterns, args.include_held))
        targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        log.info("nothing to do")
        return 0
    log.info("%d applications to fetch", len(targets))

    api = idox.IdoxClient(delay_seconds=args.api_delay)
    docs = idox.IdoxClient(delay_seconds=args.doc_delay)
    totals = {"apps": 0, "downloaded": 0, "existing": 0,
              "errors": 0, "empty": 0, "missing": 0}
    started = time.monotonic()
    try:
        with db.connect() as conn:
            source_id = repo.ensure_source(
                conn, name=aifusion.SOURCE_NAME, kind="council",
                base_url="(per-council aifusion API host)")
            conn.commit()

            for i, (app_id, ref, url) in enumerate(targets, 1):
                free_gb = shutil.disk_usage(args.data_dir).free / 1e9
                if not args.dry_run and free_gb < args.min_free_gb:
                    log.error("stopping at %d/%d: %.1fGB free is below the "
                              "%.1fGB floor. Re-run after clearing space; "
                              "documents already held are skipped.",
                              i, len(targets), free_gb, args.min_free_gb)
                    totals["stopped_low_disk"] = True
                    break
                if args.dry_run:
                    base = aifusion.api_base_for(url)
                    listed = aifusion.list_documents(
                        api, api_base=base,
                        case_id=aifusion.case_id_for(ref))
                    n = "no case" if listed is None else f"{len(listed)} docs"
                    log.info("[%d/%d] %s -> %s", i, len(targets), ref, n)
                    continue
                try:
                    s = aifusion.fetch_documents_for_application(
                        conn, client=api, application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=source_id, data_dir=args.data_dir,
                        doc_client=docs)
                except Exception as exc:
                    log.error("[%d/%d] %s FAILED: %s", i, len(targets), ref, exc)
                    totals["errors"] += 1
                    continue
                totals["apps"] += 1
                totals["downloaded"] += s["downloaded"]
                totals["existing"] += s["skipped_existing"]
                totals["errors"] += s["errors"]
                if s.get("error_class") == "no_documents":
                    totals["empty"] += 1
                if s.get("error_class") == "case_not_found":
                    totals["missing"] += 1
                mins = (time.monotonic() - started) / 60
                log.info(
                    "[%d/%d] %s  found=%d new=%d held=%d err=%d "
                    "| total new=%d in %.0fm",
                    i, len(targets), ref, s["links_found"], s["downloaded"],
                    s["skipped_existing"], s["errors"],
                    totals["downloaded"], mins)
    finally:
        api.close()
        docs.close()

    log.info("done: %(apps)d applications, %(downloaded)d new documents, "
             "%(existing)d already held, %(empty)d with none published, "
             "%(missing)d not in the register, %(errors)d errors", totals)
    if totals.get("stopped_low_disk"):
        log.error("INCOMPLETE — stopped on low disk, not finished")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
