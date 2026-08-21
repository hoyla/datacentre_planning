"""Split the International Trading Estate campus out of the Union Park site.

One-off, targeted application of the site-partition prior
(data/priors/site_partitions.yaml, entry
international-trading-estate-southall): site PTNO-12511337 ("NORTH HYDE
GARDENS UNION PARK - DATA CENTRES") also held GTR's International
Trading Estate scheme at Trident Way, Southall — a distinct campus
0.28 km away by portal coordinates, merged by a direct spatial edge.

A full `scripts/materialise_sites.py` run would apply the same split,
but the sites tables were last materialised 2026-08-06 and ~1,500
applications have been ingested since; a full run today applies six
weeks of universe drift across hundreds of sites in the same action.
This script applies *only* the split, with the materialiser's own SQL
shapes and conventions: membership moves are a retire (never a delete)
plus an upsert-and-revive insert, the new site row is created exactly
as `sites.materialise` would create it, and re-runs are no-ops.

The member set is taken from `sites.build_clusters` under the partition
prior — not hardcoded — so what this script writes is exactly what the
next full materialisation will confirm.

Usage:
    .venv/bin/python scripts/split_union_park_ite.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, sites  # noqa: E402

OLD_KEY = "PTNO-12511337"   # Union Park / North Hyde Gardens
NEW_KEY = "PTNO-12842719"   # International Trading Estate, Trident Way


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with db.connect() as conn:
        clusters = sites.build_clusters(conn)
        cluster = next((c for c in clusters if c["site_key"] == NEW_KEY), None)
        if cluster is None:
            print(f"FAIL: clustering did not produce {NEW_KEY} — is "
                  "data/priors/site_partitions.yaml present?", file=sys.stderr)
            return 1
        app_ids = {a["id"]: a["joined_via"] for a in cluster["apps"]}
        proj_ids = {p["id"]: p["joined_via"] for p in cluster["projects"]}
        print(f"{NEW_KEY}: {len(app_ids)} applications, {len(proj_ids)} "
              f"Barbour projects — {cluster['display_name']!r}")

        with conn.cursor() as cur:
            cur.execute("SELECT id, retired_at FROM sites WHERE site_key = %s",
                        (OLD_KEY,))
            row = cur.fetchone()
            if row is None or row[1] is not None:
                print(f"FAIL: {OLD_KEY} missing or retired", file=sys.stderr)
                return 1
            old_site_id = row[0]

            # Every member this script moves must currently be live in the
            # Union Park site, unless the split has already been applied —
            # anything else means the corpus has changed under us.
            cur.execute("""
                SELECT coalesce(application_id, -project_id)
                FROM site_members WHERE site_id = %s AND retired_at IS NULL""",
                (old_site_id,))
            live_old = {r[0] for r in cur.fetchall()}
            moving = set(app_ids) | {-p for p in proj_ids}
            missing = moving - live_old
            cur.execute("SELECT id, retired_at FROM sites WHERE site_key = %s",
                        (NEW_KEY,))
            new_row = cur.fetchone()
            if missing and not (new_row and new_row[1] is None):
                print(f"FAIL: {len(missing)} members not live in {OLD_KEY} "
                      f"and {NEW_KEY} does not exist: {sorted(missing)}",
                      file=sys.stderr)
                return 1

            if args.dry_run:
                print("Dry run; nothing written.")
                return 0

            # New site row, exactly as sites.materialise writes it.
            if new_row is None:
                cur.execute("""
                    INSERT INTO sites (site_key, classification, display_name,
                                       latitude, longitude, coord_source, radius_km)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (NEW_KEY, cluster["classification"],
                     cluster["display_name"], cluster["lat"], cluster["lon"],
                     cluster["coord_source"], 1.0))
                new_site_id = cur.fetchone()[0]
                created = True
            else:
                new_site_id = new_row[0]
                cur.execute("""
                    UPDATE sites SET classification=%s, display_name=%s,
                        latitude=%s, longitude=%s, coord_source=%s,
                        materialised_at=now(), retired_at=NULL
                    WHERE id=%s""",
                    (cluster["classification"], cluster["display_name"],
                     cluster["lat"], cluster["lon"], cluster["coord_source"],
                     new_site_id))
                created = False

            for aid, via in app_ids.items():
                cur.execute("""
                    INSERT INTO site_members (site_id, application_id, joined_via)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (site_id, application_id) WHERE application_id IS NOT NULL
                    DO UPDATE SET joined_via=EXCLUDED.joined_via,
                                  materialised_at=now(), retired_at=NULL""",
                    (new_site_id, aid, via))
            for pid, via in proj_ids.items():
                cur.execute("""
                    INSERT INTO site_members (site_id, project_id, joined_via)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (site_id, project_id) WHERE project_id IS NOT NULL
                    DO UPDATE SET joined_via=EXCLUDED.joined_via,
                                  materialised_at=now(), retired_at=NULL""",
                    (new_site_id, pid, via))

            cur.execute("""
                UPDATE site_members SET retired_at=now()
                WHERE site_id = %s AND retired_at IS NULL
                  AND (application_id = ANY(%s) OR project_id = ANY(%s))""",
                (old_site_id, sorted(app_ids), sorted(proj_ids)))
            retired = cur.rowcount
            cur.execute("UPDATE sites SET materialised_at=now() WHERE id=%s",
                        (old_site_id,))
        conn.commit()
    print(f"OK. {NEW_KEY} {'created' if created else 'updated'} with "
          f"{len(app_ids) + len(proj_ids)} members; {retired} memberships "
          f"retired from {OLD_KEY}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
