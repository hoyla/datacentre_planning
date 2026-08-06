"""Materialise the site clustering into the sites/site_members tables.

Idempotent: stable site keys, membership replaced on each run, vanished
sites retired (never deleted). Run after anything that changes the
universe — new triage verdicts, new project links, coordinate priors.

Usage:
    .venv/bin/python scripts/materialise_sites.py [--radius-km 1.0] [--dry-run]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with db.connect() as conn:
        clusters = sites.build_clusters(conn, radius_km=args.radius_km)
        by_class = Counter(c["classification"] for c in clusters)
        napps = sum(len(c["apps"]) for c in clusters)
        nproj = sum(len(c["projects"]) for c in clusters)
        print(f"Clusters: {len(clusters)} sites "
              f"({napps} applications, {nproj} Barbour projects)")
        for cls, n in by_class.most_common():
            print(f"  {cls:16} {n}")
        if args.dry_run:
            return
        summary = sites.materialise(conn, clusters, radius_km=args.radius_km)
        conn.commit()
        print(f"Materialised: {summary}")


if __name__ == "__main__":
    main()
