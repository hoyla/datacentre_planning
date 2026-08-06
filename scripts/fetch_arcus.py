"""Fetch documents for Arcus planning-register applications.

Companion runner for `dcp.sources.arcus`. Defaults to the campaign
cohort shape (DC-verdict applications without documents); `--all` walks
every Arcus application in the universe — prefer `--all`, since the
narrow cohort skips applications that hold *some* documents and would
leave partial bundles unfinished.

Includes the Vale of White Horse variant, whose URLs use
`/Planning/Display?applicationNumber=<ref>` rather than a path segment
but are the same register software.

Parallel across councils, serial within each: Arcus applications spread
over ~15 council hosts, so shards run concurrently (`--workers`) while
each host keeps one request in flight with its own delay and backoff —
politeness is a per-host property. Each worker holds its own client
(and therefore its own disclaimer cookie) and database connection.

Usage:
    .venv/bin/python -u scripts/fetch_arcus.py --all [--delay 5] [--workers 6]
"""

from __future__ import annotations

import argparse
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import arcus  # noqa: E402

COHORT_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (application_id) application_id, verdict
  FROM triage ORDER BY application_id, inserted_at DESC)
SELECT a.id, a.application_ref, a.url
FROM applications a
LEFT JOIN latest l ON l.application_id = a.id
WHERE (a.url ILIKE '%%planning-register.co.uk%%'
       OR a.url ILIKE '%%/Planning/Display%%')
  AND (%(all)s OR (coalesce(l.verdict,'') = 'DC'
                   AND NOT EXISTS (SELECT 1 FROM documents d
                                   WHERE d.application_id = a.id)))
ORDER BY a.application_ref
"""


def _run_shard(host: str, apps: list[tuple], *, args, source_id: int,
               totals: dict, lock: threading.Lock) -> None:
    """One council host's applications, strictly serially, with this
    worker's own client (and disclaimer cookie) and DB connection."""
    with db.connect() as conn, arcus.ArcusClient(delay_seconds=args.delay) as client:
        for app_id, ref, url in apps:
            s = arcus.fetch_documents_for_application(
                conn, client=client, application_id=app_id,
                application_ref=ref, application_url=url,
                source_id=source_id, data_dir=args.data_dir)
            cls = s.get("error_class")
            with lock:
                totals["apps"] += 1
                totals["downloaded"] += s["downloaded"]
                totals["errors"] += s["errors"]
                if cls:
                    totals["empty"] += 1
                    print(f"  {ref:44} SKIP[{cls}]")
                else:
                    print(f"  {ref:44} docs={s['links_found']:3d} "
                          f"new={s['downloaded']:3d}")
        conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=6,
                    help="Concurrent council hosts. Within a host, "
                         "fetching is always strictly serial.")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(COHORT_SQL, {"all": args.all})
            targets = cur.fetchall()
        source_id = repo.ensure_source(
            conn, name=arcus.SOURCE_NAME, kind="council",
            base_url="(per-council Arcus register)")
        conn.commit()

    shards: dict[str, list[tuple]] = {}
    for t in targets:
        shards.setdefault(urllib.parse.urlparse(t[2]).netloc, []).append(t)
    ordered = sorted(shards.items(), key=lambda kv: -len(kv[1]))
    print(f"{len(targets)} Arcus applications across {len(shards)} council "
          f"hosts; {args.workers} concurrent")

    totals = {"apps": 0, "downloaded": 0, "errors": 0, "empty": 0}
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_run_shard, host, apps, args=args,
                               source_id=source_id, totals=totals, lock=lock)
                   for host, apps in ordered]
        for f in futures:
            f.result()
    print(f"\nTotals: {totals}")


if __name__ == "__main__":
    main()
