"""Spatial sweep for energy applications around every materialised site.

Closes the ingestion gap behind the adjacency investigation. The universe
was built from data-centre keyword searches, operator expansions and
application-anchored spatial sweeps — so a gas peaker, BESS or private-wire
scheme a kilometre from a hyperscale campus that **never uses the words
"data centre"** may not be in the corpus at all. No prompt can classify an
application that was never ingested; the Yorkshire Energy Park gas reserve
is the canonical case of exactly this shape, and it was caught by luck of
another discovery path rather than by design.

This sweep anchors on the 391 materialised **sites** rather than on
individual applications, so each cluster is searched once from its
canonical coordinates, and applies the energy lexicon to what comes back.
Matches are upserted with `discovered_via = 'site_energy:<site_key>'`, so
their provenance states which site brought them in.

Two-phase, mirroring the existing colocated sweep: `--fetch` hits PlanIt
(polite, cached in source_snapshots) and `--process` applies the lexicon
to cached responses. Re-running `--process` after a lexicon change costs
no API calls.

Usage:
    .venv/bin/python -u scripts/sweep_site_energy.py --fetch [--radius-km 2.5]
    .venv/bin/python -u scripts/sweep_site_energy.py --process
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import planit  # noqa: E402


def sites_with_coords(conn) -> list[tuple[str, float, float]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT site_key, latitude, longitude FROM sites
            WHERE retired_at IS NULL
              AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY site_key""")
        return cur.fetchall()


def do_fetch(radius_km: float, delay: float, limit: int | None) -> None:
    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=planit.SOURCE_NAME,
                                       kind="aggregator", base_url=planit.BASE)
        sites = sites_with_coords(conn)
        if limit:
            sites = sites[:limit]
        print(f"{len(sites)} located sites; searching {radius_km} km around each")
        pages = cached = new_snaps = 0
        with planit.PlanItClient(delay_seconds=delay) as client:
            for i, (site_key, lat, lng) in enumerate(sites, 1):
                try:
                    for resp in client.iter_by_spatial(lat=lat, lng=lng, krad=radius_km):
                        pages += 1
                        if resp.cached:
                            cached += 1
                        elif repo.record_snapshot(conn, source_id=source_id,
                                                  key=resp.url, raw_bytes=resp.raw):
                            new_snaps += 1
                    conn.commit()
                except Exception as exc:
                    print(f"  {site_key}: fetch failed — {exc}")
                    conn.rollback()
                if i % 25 == 0:
                    print(f"  {i}/{len(sites)} sites, {pages} pages "
                          f"({cached} cached, {new_snaps} new snapshots)")
        print(f"done: {pages} pages, {new_snaps} new snapshots")


def do_process(radius_km: float) -> None:
    """Apply the energy lexicon to cached spatial responses and report what
    is genuinely new to the universe."""
    import json

    with db.connect() as conn:
        source_id = repo.ensure_source(conn, name=planit.SOURCE_NAME,
                                       kind="aggregator", base_url=planit.BASE)
        sites = sites_with_coords(conn)
        seen_refs: set[str] = set()
        new_rows = 0
        with conn.cursor() as cur:
            cur.execute("SELECT application_ref FROM applications")
            known = {r[0] for r in cur.fetchall()}

        for site_key, lat, lng in sites:
            like = f"%lat={lat}&lng={lng}&krad={radius_km}%"
            with conn.cursor() as cur:
                cur.execute("""SELECT raw_bytes_inline FROM source_snapshots
                               WHERE source_id=%s AND key LIKE %s""",
                            (source_id, like))
                snaps = cur.fetchall()
            for (raw,) in snaps:
                try:
                    payload = json.loads(bytes(raw).decode("utf-8", "replace"))
                except Exception:
                    continue
                for rec in payload.get("records", []):
                    desc = rec.get("description") or ""
                    hits = planit._keyword_hits(desc)
                    if not hits:
                        continue
                    ref = rec.get("name") or rec.get("uid")
                    if not ref or ref in seen_refs:
                        continue
                    seen_refs.add(ref)
                    if ref in known:
                        continue
                    app_id = repo.upsert_application(
                        conn, source_id=source_id, app=rec,
                        discovered_via=[f"site_energy:{site_key}"])
                    if app_id:
                        new_rows += 1
            conn.commit()
        print(f"energy-matching applications near sites: {len(seen_refs)}; "
              f"NEW to the universe: {new_rows}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--radius-km", type=float, default=2.5,
                    help="Review band from the spatial policy (1 km is "
                         "same-site clustering; 2.5 km catches adjacent "
                         "power; corridors need evidence-based linking).")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not (args.fetch or args.process):
        ap.error("choose --fetch and/or --process")
    if args.fetch:
        do_fetch(args.radius_km, args.delay, args.limit)
    if args.process:
        do_process(args.radius_km)


if __name__ == "__main__":
    main()
