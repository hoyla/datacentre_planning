"""Apply editorial-cohort and exclusion tags to applications.

Reads `data/priors/cohorts.yaml` and stamps each listed application's
`discovered_via` array with:

- `cohort:<name>` for every cohort the app appears in. The FIRST cohort
  in the YAML's `cohorts` order that lists an app is its primary cohort
  for rendering purposes; subsequent cohorts get the app as a
  cross-reference. The loader doesn't enforce primacy — that's resolved
  at render time — it just records every membership.
- `exclude:<reason>` for every app listed in `exclusions` (currently
  `reason: not_a_data_centre` for the four confirmed worklist
  false-positives). Excluded apps are filtered from the primary worklist
  count in `dcp/worklist.py` and shown as a separate section at the
  bottom of the export.

Idempotent via `repo.append_discovered_via`'s ARRAY-distinct pattern —
re-running is a no-op.

Usage:
    .venv/bin/python -m scripts.tag_cohorts [--yaml <path>] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, repo  # noqa: E402

DEFAULT_YAML = ROOT / "data" / "priors" / "cohorts.yaml"


def _apply_cohort_tags(conn, cohorts: list[dict], dry_run: bool) -> int:
    total = 0
    for cohort in cohorts:
        name = cohort["name"]
        apps = cohort.get("apps", [])
        tag = f"cohort:{name}"
        if dry_run:
            print(f"(dry-run) would tag {len(apps)} apps with {tag!r}")
            continue
        n = repo.append_discovered_via(conn, application_refs=apps, tag=tag)
        print(f"  cohort:{name:32s}  tagged {n}/{len(apps)} apps")
        total += n
    return total


def _apply_exclusion_tags(conn, exclusions: list[dict], dry_run: bool) -> int:
    total = 0
    for entry in exclusions:
        app = entry["app"]
        reason = entry["reason"]
        tag = f"exclude:{reason}"
        if dry_run:
            print(f"(dry-run) would tag {app} with {tag!r}")
            continue
        n = repo.append_discovered_via(conn, application_refs=[app], tag=tag)
        print(f"  exclude:{reason:25s}  {app}  ({'tagged' if n else 'not found'})")
        total += n
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML,
                    help="Cohorts YAML (default: data/priors/cohorts.yaml).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be tagged without writing.")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.yaml.read_text())
    cohorts = cfg.get("cohorts", [])
    exclusions = cfg.get("exclusions", [])

    with db.connect() as conn:
        print("Cohort tags:")
        n_cohort = _apply_cohort_tags(conn, cohorts, args.dry_run)
        print()
        print("Exclusion tags:")
        n_exclude = _apply_exclusion_tags(conn, exclusions, args.dry_run)
        print()
        if not args.dry_run:
            print(f"Total: {n_cohort} cohort tags + {n_exclude} exclusion tags applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
