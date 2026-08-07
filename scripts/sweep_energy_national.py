"""Find energy applications near our sites — by national keyword sweep, not
per-site spatial queries.

The obvious design (search a 2.5 km radius around each of ~350 sites) was
built first and measured: **22 pages for a single urban site**, because a
spatial query returns *every* application in the catchment and the
filtering happens locally. PlanIt's quota then asked for a 38-minute wait.
Extrapolated, 347 sites would have taken about nine days of wall-clock and
several thousand requests against a free, donation-supported service.

Inverted, the same result costs ~1% of the requests:

1. **One national sweep** of the energy lexicon (~20-40 pages at 500/page).
   PlanIt does the filtering server-side; we pay for matches, not for
   catchments.
2. **Proximity computed locally** against site coordinates we already hold
   — free arithmetic, no requests at all, and re-runnable at any radius
   without touching the API.

The lexicon is deliberately broad: as a *discovery* filter "energy centre"
was too noisy (the v1 index pass excluded it for that reason), but as a
*candidate pool for a spatial join* noise is exactly what the local
proximity test removes.

Two passes:

    --fetch     national keyword sweep, snapshotting each page
    --process   read snapshots, compute proximity, report/ingest

Usage:
    .venv/bin/python -u scripts/sweep_energy_national.py --fetch
    .venv/bin/python -u scripts/sweep_energy_national.py --process --radius-km 2.5
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import planit  # noqa: E402

# Energy-infrastructure lexicon. Quoted phrases are matched as phrases by
# PlanIt's search; the union is OR'd.
ENERGY_KEYWORDS = (
    '"energy centre" OR "energy park" OR "gas engine" OR "gas turbine" OR '
    '"reciprocating engine" OR "peaking plant" OR "peaker" OR '
    '"battery energy storage" OR "battery storage" OR BESS OR '
    '"grid connection" OR "grid supply point" OR "electricity substation" OR '
    '"converter station" OR "private wire" OR "standby generation" OR '
    '"combined heat and power" OR CHP OR "open cycle gas turbine"'
)


# Generation and storage plant only — the terms that almost always mean a
# power scheme rather than an incidental mention. Drops "substation",
# "grid connection" and CHP, which appear in a large share of ordinary
# applications (every housing estate has a substation) and triple the
# page count. Sized 2026-08-06: 8,740 records from 2018, versus 29,455 for
# the full lexicon — the difference between one quota window and five.
ENERGY_KEYWORDS_TIGHT = (
    '"energy centre" OR "gas engine" OR "gas turbine" OR '
    '"reciprocating engine" OR "peaking plant" OR "peaker" OR '
    '"battery energy storage" OR BESS OR "converter station" OR '
    '"private wire" OR "open cycle gas turbine"'
)


# PlanIt caps a response at ~1000 kB, and the full APPS_SELECT (which
# includes the bulky `other_fields` blob) blows that at 500 records —
# the request 400s. This sweep only needs enough to identify an
# application and place it on a map; the full record is fetched later
# for anything that proves relevant. Measured: 500 records in 579 kB.
SLIM_SELECT = ("name,area_name,address,description,app_type,start_date,"
               "url,location_x,location_y")


def hav_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def do_fetch(delay: float, pg_sz: int, start_date: str | None,
             tight: bool = False) -> None:
    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=planit.SOURCE_NAME,
                                       kind="aggregator", base_url=planit.BASE)
        search = ENERGY_KEYWORDS_TIGHT if tight else ENERGY_KEYWORDS
        pages = new_snaps = records = 0
        print(f"national energy sweep ({'tight' if tight else 'full'} lexicon"
              + (f", from {start_date}" if start_date else "")
              + f") at {pg_sz}/page, {delay}s spacing")
        with planit.PlanItClient(delay_seconds=delay) as client:
            try:
                page = 1
                while True:
                    params = {"pg_sz": pg_sz, "page": page,
                              "sort": "-start_date", "select": SLIM_SELECT,
                              "search": search}
                    if start_date:
                        params["start_date"] = start_date
                    resp = client.get("/applics/json", params)
                    pages += 1
                    n = len(resp.data.get("records", []))
                    records += n
                    if repo.record_snapshot(conn, source_id=source_id,
                                            key=resp.url, raw_bytes=resp.raw):
                        new_snaps += 1
                    conn.commit()
                    print(f"  page {pages}: {n} records (total {records})")
                    if n < pg_sz:
                        break
                    page += 1
            except planit.RateLimited as exc:
                conn.commit()
                print(f"\nPlanIt quota spent — asked for {exc.retry_after:.0f}s "
                      f"({exc.retry_after/60:.0f} min).")
                print(f"Stopping cleanly after {pages} pages; re-run to resume "
                      f"(cached pages are not re-fetched).")
                return
        print(f"done: {pages} pages, {records} records, {new_snaps} new snapshots")


def do_process(radius_km: float, ingest: bool) -> None:
    """Join snapshotted energy applications against site coordinates."""
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT site_key, display_name, latitude, longitude
                       FROM sites
                       WHERE retired_at IS NULL AND latitude IS NOT NULL""")
        sites = cur.fetchall()
        cur.execute("""SELECT raw_bytes_inline FROM source_snapshots s
                       JOIN sources src ON src.id = s.source_id
                       WHERE src.name = %s AND s.key LIKE %s""",
                    (planit.SOURCE_NAME, "%search=%energy%"))
        snaps = cur.fetchall()
        cur.execute("SELECT application_ref FROM applications")
        known = {r[0] for r in cur.fetchall()}

    seen: dict[str, dict] = {}
    for (raw,) in snaps:
        try:
            data = json.loads(bytes(raw).decode("utf-8", errors="replace"))
        except Exception:
            continue
        for rec in data.get("records", []):
            name = rec.get("name")
            if name:
                seen[name] = rec
    print(f"{len(sites)} located sites; {len(seen)} distinct energy applications "
          f"in snapshots")

    near: dict[str, list] = defaultdict(list)
    for name, rec in seen.items():
        try:
            lat = float(rec.get("location_y")); lon = float(rec.get("location_x"))
        except (TypeError, ValueError):
            continue
        for site_key, site_name, slat, slon in sites:
            d = hav_km(lat, lon, float(slat), float(slon))
            if d <= radius_km:
                near[site_key].append((d, name, rec))

    total = sum(len(v) for v in near.values())
    fresh = sum(1 for v in near.values() for _d, n, _r in v if n not in known)
    print(f"{total} energy applications within {radius_km} km of a site "
          f"({len(near)} sites affected); {fresh} not already in the corpus\n")
    for site_key, hits in sorted(near.items(), key=lambda kv: -len(kv[1]))[:15]:
        print(f"{site_key}  ({len(hits)} nearby)")
        for d, name, rec in sorted(hits)[:4]:
            flag = "" if name in known else "  ** NEW **"
            print(f"    {d:4.1f} km  {name:32} "
                  f"{(rec.get('description') or '')[:56]}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--radius-km", type=float, default=2.5)
    ap.add_argument("--delay", type=float, default=10.0)
    ap.add_argument("--pg-sz", type=int, default=500)
    ap.add_argument("--tight", action="store_true",
                    help="Generation/storage terms only — one quota window "
                         "rather than five.")
    ap.add_argument("--start-date", default=None,
                    help="Restrict to applications on/after this date "
                         "(YYYY-MM-DD), shrinking the sweep.")
    ap.add_argument("--ingest", action="store_true",
                    help="(process) record new applications rather than "
                         "only reporting them.")
    args = ap.parse_args()
    if args.fetch:
        do_fetch(args.delay, args.pg_sz, args.start_date, args.tight)
    if args.process:
        do_process(args.radius_km, args.ingest)
    if not (args.fetch or args.process):
        print("nothing to do — pass --fetch and/or --process")


if __name__ == "__main__":
    main()
