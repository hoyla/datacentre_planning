"""Ingest the Barbour-gap applications from cached PlanIt lookups.

Zero new API calls: replays the id_match snapshots recorded by
scripts/barbour_gap_postmortem.py, and upserts every record that belongs to
Barbour's stated authority into `applications`, tagged
`discovered_via=['barbour:<Ptno>']`. Covers the pre-2018 window artefacts
(now in scope per the 2026-08-02 decision), the keyword-blind descriptions,
the sweep escape, and the manually-accepted authority quirks (MidKent is the
Maidstone/Swale/Tunbridge Wells shared service; Runnymede RU.22/0393 is a
Barbour authority-field error).

After this, run:
    dcp index --source barbour --file <xlsx>     # links the new exact refs
    dcp backfill-parents --source planit --delay 10   # fetches missing parents
    .venv/bin/python scripts/link_barbour_families.py # family-level links

Usage: .venv/bin/python scripts/ingest_barbour_gap_apps.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources.planit import _load_area_gss_map  # noqa: E402

import importlib.util  # noqa: E402

for _mod in ("barbour_gap_postmortem", "barbour_gap_dossier"):
    _spec = importlib.util.spec_from_file_location(
        _mod, Path(__file__).parent / f"{_mod}.py")
    globals()[_mod] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(globals()[_mod])
pm = globals()["barbour_gap_postmortem"]
dossier = globals()["barbour_gap_dossier"]

# MidKent serves Maidstone, Swale and Tunbridge Wells — PlanIt files under
# the shared service, Barbour under the constituent council.
SHARED_SERVICES = {"midkent": {"maidstone", "swale", "tunbridgewells"}}

# Manually-accepted collision: Barbour's authority field says RBWM but
# RU.22/0393 is Runnymede's ref format and the record is correct.
ACCEPT_PTNOS = {"12256124"}


def record_belongs(rec: dict, authority: str | None, ptno: str) -> bool:
    if ptno in ACCEPT_PTNOS:
        return True
    if pm._authority_matches(authority, rec.get("area_name")):
        return True
    area = pm._norm_authority(rec.get("area_name") or "")
    auth = pm._norm_authority(authority or "")
    return auth in SHARED_SERVICES.get(area, set())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    summary = {"considered": 0, "ingested": 0, "skipped_no_record": 0,
               "skipped_wrong_authority": 0, "skipped_tender": 0}

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE name = 'planit'")
            planit_source_id = cur.fetchone()[0]
            cur.execute(
                """SELECT p.external_ref, p.planning_ref, p.authority_name
                   FROM projects p
                   WHERE p.planning_ref IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM project_applications pa
                                     WHERE pa.project_id = p.id)
                   ORDER BY p.external_ref""",
            )
            targets = cur.fetchall()

        gss_map = _load_area_gss_map(conn)

        for ptno, ref, authority in targets:
            summary["considered"] += 1
            if ref.upper().startswith("FIND A TENDER"):
                summary["skipped_tender"] += 1
                continue
            records = dossier.cached_lookup(conn, planit_source_id, ref)
            accepted = [r for r in records if record_belongs(r, authority, ptno)]
            if not accepted:
                summary["skipped_no_record" if not records
                        else "skipped_wrong_authority"] += 1
                continue
            # Multiple in-authority records for one bare ref would need a human;
            # take them all only if identical name, else first (most recent).
            rec = accepted[0]
            print(f"  {'DRY ' if args.dry_run else ''}ingest {rec.get('name'):42} "
                  f"start={rec.get('start_date')}  barbour:{ptno}")
            if not args.dry_run:
                repo.upsert_application(
                    conn, source_id=planit_source_id, app=rec,
                    council_gss=gss_map.get(rec.get("area_name")),
                    discovered_via=[f"barbour:{ptno}"],
                )
            summary["ingested"] += 1

        if not args.dry_run:
            backfill = repo.backfill_council_gss(conn)
            print(f"\ncouncil_gss backfill: {backfill}")
            conn.commit()

    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()
