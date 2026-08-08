#!/usr/bin/env python3
"""Read the Planning Inspectorate project page for each NSIP energy project.

Deliberately fetches no documents. A single DCO document set runs to
thousands of files; the project page carries the name, the description
and — often — the capacity, which is what the energy layer actually needs.
One request per project, no downloads.

Every page is snapshotted to `source_snapshots` before parsing, so a
later re-parse with better rules costs no further requests to the
Inspectorate, and any figure that reaches the handover can be traced to
the bytes it came from.

Parsed values are written to `raw_metadata['pins_page']` alongside the
PlanIt fields, never over them.

    scripts/fetch_nsip_project_info.py --limit 5
    scripts/fetch_nsip_project_info.py
    scripts/fetch_nsip_project_info.py --reparse   # no network at all
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox, nsip_project  # noqa: E402

log = logging.getLogger("nsip_project_info")

COHORT = """
    SELECT id, application_ref,
           raw_metadata->'other_fields'->>'applicant_name'
    FROM applications
    WHERE discovered_via @> ARRAY['nsip_energy']
      AND (%s OR NOT (raw_metadata ? 'pins_page'))
    ORDER BY application_ref
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--refresh", action="store_true",
                   help="re-read projects already carrying pins_page")
    p.add_argument("--reparse", action="store_true",
                   help="re-parse stored snapshots without any network access")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(COHORT, (args.refresh or args.reparse,))
        targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        log.info("nothing to do")
        return 0
    log.info("%d projects (%s)", len(targets),
             "re-parsing snapshots" if args.reparse else "fetching pages")

    client = None if args.reparse else idox.IdoxClient(delay_seconds=args.delay)
    got = {"name": 0, "description": 0, "description_raw": 0,
           "capacity_mentions": 0, "stage": 0, "developer_site": 0}
    done = errors = 0
    started = time.monotonic()
    try:
        with db.connect() as conn:
            source_id = repo.ensure_source(
                conn, name="pins_project_page", kind="national",
                base_url=nsip_project.BASE)
            conn.commit()

            for i, (app_id, ref, planit_applicant) in enumerate(targets, 1):
                url = nsip_project.project_url(ref)
                try:
                    if args.reparse:
                        raw = repo.find_cached_response(
                            conn, source_id=source_id, key=ref)
                        if raw is None:
                            log.warning("[%d/%d] %s no snapshot held", i, len(targets), ref)
                            continue
                        html = bytes(raw).decode("utf-8", "replace")
                    else:
                        r = client.get(url)
                        html = r.text
                        repo.record_snapshot(conn, source_id=source_id, key=ref,
                                             raw_bytes=r.content,
                                             status_code=r.status_code)
                    parsed = nsip_project.parse_project(html, applicant_hint=planit_applicant)
                except Exception as exc:
                    log.error("[%d/%d] %s FAILED: %s", i, len(targets), ref, exc)
                    errors += 1
                    continue

                for k in got:
                    if parsed.get(k):
                        got[k] += 1
                payload = dict(parsed)
                payload["source_url"] = url
                # Stored beside the PlanIt fields, never over them: the raw
                # record stays canonical and this is an interpretation of a
                # page read at a known moment.
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE applications
                           SET raw_metadata = jsonb_set(
                                 coalesce(raw_metadata, '{}'::jsonb),
                                 '{pins_page}', %s::jsonb, true),
                               title = coalesce(nullif(title, ''), %s)
                           WHERE id = %s""",
                        (json.dumps(payload), parsed.get("name"), app_id))
                conn.commit()
                done += 1
                if i % 20 == 0 or i == len(targets):
                    log.info("[%d/%d] %s — named %d, described %d, capacity %d, %.0fm",
                             i, len(targets), ref, got["name"], got["description"],
                             got["capacity_mentions"], (time.monotonic() - started) / 60)
    finally:
        if client:
            client.close()

    log.info("done: %d projects, %d errors", done, errors)
    for k, v in got.items():
        log.info("   %-18s %d/%d", k, v, done or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
