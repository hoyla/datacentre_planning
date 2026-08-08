#!/usr/bin/env python3
"""Fetch documents for the Salesforce public registers (Wiltshire, Reading).

The listing half of this adapter is browser-assisted and cached to
`data/priors/salesforce_documents.json` — see `dcp/sources/salesforce_pr.py`
for why replaying Salesforce's Aura protocol is not worth it. This script
is the other half: given a cached listing, pull the bytes over ordinary
HTTP, which the ContentVersion download endpoint serves with no session.

Applications with no cached listing are reported, not silently skipped:
a missing listing is a job for a browser, not a fetch failure.

    scripts/fetch_salesforce.py --dry-run    # what would be fetched
    scripts/fetch_salesforce.py
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
from dcp.sources import idox, salesforce_pr  # noqa: E402

log = logging.getLogger("fetch_salesforce")

COHORT_SQL = """
    SELECT a.id, a.application_ref, a.url
    FROM applications a
    -- Wildcards are doubled because psycopg reads a lone percent sign as
    -- the start of a parameter placeholder (including inside comments).
    WHERE (a.url ILIKE '%%/pr/s/planning-application/%%'
           OR a.url ILIKE '%%/pr/s/detail/%%'
           OR a.url ILIKE '%%/pr3/s/planning-application/%%')
      AND (%s OR NOT EXISTS (
            SELECT 1 FROM documents d WHERE d.application_id = a.id))
    ORDER BY a.application_ref
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--include-held", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-free-gb", type=float, default=15.0)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    listings = salesforce_pr.load_listings()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(COHORT_SQL, (args.include_held,))
        targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]

    have = [t for t in targets if t[1] in listings]
    missing = [t for t in targets if t[1] not in listings]
    log.info("%d applications: %d with a cached listing, %d needing one",
             len(targets), len(have), len(missing))
    for _, ref, _ in missing:
        log.warning("no listing yet (needs a browser pass): %s", ref)
    if args.dry_run:
        for _, ref, _ in have:
            log.info("would fetch %-28s %d documents", ref, len(listings[ref]))
        return 0
    if not have:
        return 0

    client = idox.IdoxClient(delay_seconds=args.delay)
    totals = {"apps": 0, "downloaded": 0, "existing": 0, "errors": 0, "empty": 0}
    started = time.monotonic()
    try:
        with db.connect() as conn:
            source_id = repo.ensure_source(
                conn, name=salesforce_pr.SOURCE_NAME, kind="council",
                base_url="(per-council Salesforce public register)")
            conn.commit()
            for i, (app_id, ref, url) in enumerate(have, 1):
                free_gb = shutil.disk_usage(args.data_dir).free / 1e9
                if free_gb < args.min_free_gb:
                    log.error("stopping at %d/%d: %.1fGB free below the "
                              "%.1fGB floor", i, len(have), free_gb,
                              args.min_free_gb)
                    totals["stopped_low_disk"] = True
                    break
                try:
                    s = salesforce_pr.fetch_documents_for_application(
                        conn, client=client, application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=source_id, data_dir=args.data_dir,
                        listings=listings)
                except Exception as exc:
                    log.error("[%d/%d] %s FAILED: %s", i, len(have), ref, exc)
                    totals["errors"] += 1
                    continue
                totals["apps"] += 1
                totals["downloaded"] += s["downloaded"]
                totals["existing"] += s["skipped_existing"]
                totals["errors"] += s["errors"]
                if s.get("error_class") == "no_documents":
                    totals["empty"] += 1
                log.info("[%d/%d] %-28s found=%d new=%d held=%d err=%d "
                         "| total new=%d in %.0fm",
                         i, len(have), ref, s["links_found"], s["downloaded"],
                         s["skipped_existing"], s["errors"],
                         totals["downloaded"], (time.monotonic() - started) / 60)
    finally:
        client.close()

    log.info("done: %(apps)d applications, %(downloaded)d new documents, "
             "%(existing)d already held, %(empty)d with none published, "
             "%(errors)d errors", totals)
    if totals.get("stopped_low_disk"):
        log.error("INCOMPLETE — stopped on low disk")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
