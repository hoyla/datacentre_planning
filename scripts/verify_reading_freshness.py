#!/usr/bin/env python3
"""Check that each stored machine reading still describes its site.

The input-hash discipline exists at generation: `--collect` rebuilds a
site's input, compares the hash with the one the batch was submitted
under, and stores the reading withheld if it moved. Nothing checked it
again afterwards, so a reading written on Monday could still be rendered
on Friday against documents that arrived on Wednesday. This is the belt
to that generation-time braces (ROADMAP, the readings freshness item).

**Why it is a script and not a render-time guard.** Rebuilding one
site's input costs about 8 seconds — `select_pages` reads and scores
every cached page — so verifying the corpus's readings would add
roughly 35 minutes to a build that takes ten. Measured 2026-08-27. The
one check cheap enough for every build is liveness, and that is in
`machine_reading.load_latest`.

**What it records, and how.** Nothing is mutated: a site whose input has
moved gets a NEW row in `site_machine_readings` carrying the *current*
input hash, no reading, and a withheld reason. Because `load_latest`
takes the newest row per site, the reader then shows that site's panel
as withheld with its reason — the same path a gate refusal already
takes, so no rendering code changes. The stale marker is written under
the model tag `freshness-check` rather than the reading's own model, so
it can never occupy the unique key a genuine reading of that same input
would need.

Re-runs are no-ops: the row is keyed on the current input hash, so
checking twice without the corpus moving inserts nothing.

    scripts/verify_reading_freshness.py            # check and record
    scripts/verify_reading_freshness.py --dry-run  # report only
    scripts/verify_reading_freshness.py --site KEY [--site KEY ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from dcp import db, site_cohorts, site_profile  # noqa: E402
from dcp import machine_reading as mr  # noqa: E402

# The latest row per site that actually carries a reading, with the hash
# of what the model was shown. Rows already withheld are skipped: they
# render as withheld whatever their input does now.
CANDIDATES_SQL = """
SELECT DISTINCT ON (r.site_key)
       r.site_key, r.model, r.prompt_version, r.gate_version, r.input_hash
FROM site_machine_readings r
JOIN sites s ON s.site_key = r.site_key AND s.retired_at IS NULL
ORDER BY r.site_key, r.inserted_at DESC, r.id DESC
"""

MARK_SQL = """
INSERT INTO site_machine_readings
    (site_key, model, prompt_version, input_hash, gate_version,
     documents_read, pages_read, input_chars, reading, withheld_reason)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
ON CONFLICT (site_key, model, prompt_version, input_hash, gate_version)
DO NOTHING
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what has moved without recording it")
    ap.add_argument("--site", action="append", default=[],
                    help="check only this site key (repeatable)")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many sites (for a quick sample)")
    args = ap.parse_args()

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(CANDIDATES_SQL)
            rows = cur.fetchall()
        if args.site:
            wanted = set(args.site)
            rows = [r for r in rows if r[0] in wanted]
        if args.limit:
            rows = rows[:args.limit]
        if not rows:
            print("no readings to check")
            return 0

        # The three corpus-wide loads, once, exactly as the generator
        # and the reader do — a freshness check that built its inputs
        # differently would report drift it had caused itself.
        profiles = site_profile.load_site_profiles(conn)
        coverage = site_profile.load_coverage_detail(conn)
        cohorts = site_cohorts.compute_all(conn)

        moved, held, failed = [], 0, []
        for site_key, model, pv, gv, stored_hash in rows:
            try:
                inp = mr.load_site_input(
                    conn, site_key, profile=profiles.get(site_key, {}),
                    coverage=coverage.get(site_key, {}), cohorts=cohorts)
            except Exception as e:                    # noqa: BLE001
                # A site whose input cannot be built is reported, never
                # marked: "could not check" is not "has changed".
                failed.append((site_key, str(e)[:120]))
                continue
            if inp.input_hash == stored_hash:
                held += 1
                continue
            moved.append((site_key, model, pv, gv, inp))

        for site_key, model, pv, gv, inp in moved:
            print(f"  moved: {site_key} (read under {model} {pv})")
            if args.dry_run:
                continue
            with conn.cursor() as cur:
                cur.execute(MARK_SQL, (
                    site_key, mr.FRESHNESS_MODEL, pv, inp.input_hash, gv,
                    inp.documents_read, len(inp.pages),
                    sum(len(p.text) for p in inp.pages), mr.STALE_REASON))
            conn.commit()

        for site_key, why in failed:
            print(f"  could not check: {site_key} — {why}")
        verb = "would be marked" if args.dry_run else "marked"
        print(f"{len(rows)} readings checked: {held} still describe their "
              f"site, {len(moved)} {verb} stale"
              + (f", {len(failed)} could not be checked" if failed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
