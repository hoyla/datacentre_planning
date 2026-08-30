"""Materialise the adjacent-power relationships into site_adjacent_power.

Adjacent power stands beside a data centre rather than belonging to one
(migration 032, issue #252). This records which sites each such record
relates to, and on what evidence, so that removing it from `site_members`
later does not remove it from the reader.

Nothing downstream reads the table yet, so running this changes no
output. It is safe to run at any point after `materialise_sites.py`,
and it must run after it: a relationship is to a live site, so a
clustering that has not been materialised yet gives relationships to
sites that no longer exist.

Idempotent: a relationship already live under the same site, application
and basis is left alone, and one that no longer holds is retired rather
than deleted.

Usage:
    .venv/bin/python scripts/materialise_adjacent_power.py [--dry-run]
    .venv/bin/python scripts/materialise_adjacent_power.py --radius-km 1.0
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from dcp import adjacent_power as ap  # noqa: E402
from dcp import db  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--radius-km", type=float, default=ap.PROXIMITY_KM,
                   help="how far a proximity row may reach (default 1.0, the "
                        "clustering radius)")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would be written, and write nothing")
    args = p.parse_args()

    with db.connect() as conn:
        found = ap.relations(conn, proximity_km=args.radius_km)
        by_basis = Counter(r.basis for r in found)
        apps = {r.application_id for r in found}
        print(f"{len(found)} relationships: "
              f"{by_basis.get('discovery', 0)} discovery, "
              f"{by_basis.get('cohort', 0)} cohort, "
              f"{by_basis.get('proximity', 0)} proximity")
        print(f"  across {len(apps)} adjacent-power records "
              f"and {len({r.site_id for r in found})} sites")

        # The records that relate to nothing are the point of the exercise
        # as much as the ones that do: an adjacent-power record with no
        # site is either a lead to a data centre this corpus does not
        # hold — a DRUPS "to support the Newton Data Centre" — or a
        # keyword sweep catching an energy scheme that is not about data
        # centres at all. Neither is served by being its own site, which
        # is what the model does today.
        with conn.cursor() as cur:
            cur.execute(ap.ADJACENT_SQL)
            unattached = [(ref, via) for aid, ref, via, _lat, _lon
                          in cur.fetchall() if aid not in apps]
        if unattached:
            print(f"  {len(unattached)} relate to no live site:")
            for ref, via in unattached:
                print(f"      {ref}  ({', '.join(via or []) or 'no provenance'})")

        if args.dry_run:
            print("\ndry run — nothing written")
            return 0
        print("\n" + str(ap.materialise(conn, proximity_km=args.radius_km)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
