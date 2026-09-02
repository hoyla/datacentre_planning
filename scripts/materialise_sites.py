"""Materialise the site clustering into the sites/site_members tables.

Idempotent: stable site keys, membership replaced on each run, vanished
sites retired (never deleted). Run after anything that changes the
universe — new triage verdicts, new project links, coordinate priors.

Every run reports what it would change before changing it: the sites
that appear, the sites that retire, and — the one consequence a re-run
cannot undo on its own — any hand-adjudicated capacity claim that would
lose the site it was matched to. A claim whose site retires does not
error; it renders through a `retired_at IS NULL` join and simply stops
appearing. So an orphaned claim stops the run, and the fix is to
re-point the match in data/external_sources/*.yaml at the site the
members moved to (or to record that it no longer has one) and re-run
scripts/load_capacity_claims.py.

Usage:
    .venv/bin/python scripts/materialise_sites.py [--radius-km 1.0] [--dry-run]
    .venv/bin/python scripts/materialise_sites.py --allow-orphaned-claims
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, sites  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-orphaned-claims", action="store_true",
                    help="Proceed even though adjudicated capacity claims "
                         "would lose their site. Only with a plan to "
                         "re-point them in the same sitting.")
    ap.add_argument("--not-dc-veto", choices=sites.NOT_DC_VETO_MODES,
                    default="off",
                    help="whether a not_dc application may be admitted "
                         "through the family door (family) or through a "
                         "Barbour project link as well (family+project); "
                         "off is the behaviour to 2026-09-02. Dry-run each "
                         "before choosing — see ROADMAP, the not_dc item")
    args = ap.parse_args()

    with db.connect() as conn:
        clusters = sites.build_clusters(conn, radius_km=args.radius_km,
                                        not_dc_veto=args.not_dc_veto)
        by_class = Counter(c["classification"] for c in clusters)
        napps = sum(len(c["apps"]) for c in clusters)
        nproj = sum(len(c["projects"]) for c in clusters)
        print(f"Clusters: {len(clusters)} sites "
              f"({napps} applications, {nproj} Barbour projects)")
        for cls, n in by_class.most_common():
            print(f"  {cls:16} {n}")

        pre = sites.preflight(conn, clusters)
        print(f"\nWould add {len(pre['new'])} sites, "
              f"retire {len(pre['retiring'])}.")
        for key in pre["retiring"]:
            print(f"  retire  {key}")
        if pre["leaving"]:
            print(f"\n{len(pre['leaving'])} application(s) leave the "
                  f"universe — live members today, in no cluster after:")
            for ref, key in pre["leaving"][:25]:
                print(f"  leaves  {ref:44} from {key}")
            if len(pre["leaving"]) > 25:
                print(f"  ... and {len(pre['leaving']) - 25} more")
        if pre["stale_member_rows"]:
            print(f"\n{pre['stale_member_rows']} membership row(s) are still "
                  f"live on already-retired sites; this run retires them.")

        if pre["orphaned_claims"]:
            print(f"\n{len(pre['orphaned_claims'])} adjudicated capacity "
                  f"claim(s) would lose their site:")
            for o in pre["orphaned_claims"]:
                print(f"  {o['claim_name']} ({o['confidence']}, {o['method']})"
                      f"\n    site {o['site_key']} [id {o['site_id']}] retires; "
                      f"its members move to {', '.join(o['members_move_to'])}")
            if not (args.dry_run or args.allow_orphaned_claims):
                print("\nRefusing to materialise. A retired site does not "
                      "break the match — it silently empties it. Re-point "
                      "the matches in data/external_sources/ and re-run "
                      "scripts/load_capacity_claims.py, or pass "
                      "--allow-orphaned-claims deliberately.")
                return 1

        if args.dry_run:
            return 0
        summary = sites.materialise(conn, clusters, radius_km=args.radius_km)
        conn.commit()
        print(f"Materialised: {summary}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
