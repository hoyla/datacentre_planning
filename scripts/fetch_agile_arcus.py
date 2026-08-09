#!/usr/bin/env python3
"""Fetch documents for cohort applications on Agile and Arcus portals.

Both adapters exist and have run before — their portals sit at 71% and
77% document coverage. What they missed is the applications the dc_build
sweep newly brought into scope: the re-run campaign dispatches only Idox
and Ocella, so Agile and Arcus cohort members sat documentless while
their adapters sat idle. This runner points the existing adapters at
exactly that remainder, using the campaign's own cohort definition so
the two can never disagree about scope.

Runs alongside the campaign safely: different portal hosts, so no
rate-limit interaction, and resume is the usual contract (URL-level
skip plus content-hash dedup).

    scripts/fetch_agile_arcus.py --dry-run
    scripts/fetch_agile_arcus.py
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import agile, arcus  # noqa: E402

log = logging.getLogger("fetch_agile_arcus")


def _campaign():
    """The campaign module, for COHORT_SQL and portal_family.

    Imported rather than copied: scope drift between two cohort
    definitions is precisely the failure mode this weekend was spent
    repairing.
    """
    spec = importlib.util.spec_from_file_location(
        "dc_campaign", Path(__file__).parent / "fetch_dc_campaign.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=5.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-free-gb", type=float, default=15.0)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    camp = _campaign()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(camp.COHORT_SQL)
        rows = cur.fetchall()
    targets = [(app_id, ref, url, camp.portal_family(url))
               for app_id, ref, url in rows
               if camp.portal_family(url) in ("agile", "arcus")]
    if args.limit:
        targets = targets[:args.limit]
    log.info("%d cohort applications on Agile/Arcus without documents",
             len(targets))
    if args.dry_run:
        for _, ref, url, fam in targets:
            log.info("  would fetch [%s] %s", fam, ref)
        return 0
    if not targets:
        return 0

    clients = {"agile": agile.AgileClient(delay_seconds=args.delay),
               "arcus": arcus.ArcusClient(delay_seconds=args.delay)}
    mods = {"agile": agile, "arcus": arcus}
    totals = {"apps": 0, "downloaded": 0, "existing": 0, "errors": 0}
    started = time.monotonic()
    try:
        with db.connect() as conn:
            source_ids = {
                fam: repo.ensure_source(conn, name=fam, kind="council",
                                        base_url=f"(per-council {fam} host)")
                for fam in ("agile", "arcus")}
            conn.commit()
            for i, (app_id, ref, url, fam) in enumerate(targets, 1):
                free_gb = shutil.disk_usage(args.data_dir).free / 1e9
                if free_gb < args.min_free_gb:
                    log.error("stopping at %d/%d: %.1fGB free below the "
                              "%.1fGB floor", i, len(targets), free_gb,
                              args.min_free_gb)
                    totals["stopped_low_disk"] = True
                    break
                try:
                    s = mods[fam].fetch_documents_for_application(
                        conn, client=clients[fam], application_id=app_id,
                        application_ref=ref, application_url=url,
                        source_id=source_ids[fam], data_dir=args.data_dir)
                except Exception as exc:
                    log.error("[%d/%d] %s FAILED: %s", i, len(targets), ref, exc)
                    totals["errors"] += 1
                    continue
                totals["apps"] += 1
                totals["downloaded"] += s.get("downloaded", 0)
                totals["existing"] += s.get("skipped_existing", 0)
                totals["errors"] += s.get("errors", 0)
                log.info("[%d/%d] [%s] %-30s found=%d new=%d err=%d "
                         "| total new=%d in %.0fm",
                         i, len(targets), fam, ref, s.get("links_found", 0),
                         s.get("downloaded", 0), s.get("errors", 0),
                         totals["downloaded"], (time.monotonic() - started) / 60)
    finally:
        for c in clients.values():
            c.close()

    log.info("done: %(apps)d applications, %(downloaded)d new documents, "
             "%(existing)d already held, %(errors)d errors", totals)
    if totals.get("stopped_low_disk"):
        log.error("INCOMPLETE — stopped on low disk")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
