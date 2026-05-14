"""Apply a `discovered_via` tag to a set of application_refs sourced from a
YAML prior-list. Idempotent: re-running on the same refs is a no-op.

Operates on the production DB (`DATABASE_URL` from `.env`).

Usage:
    scripts/tag_priors.py data/priors/foxglove_top10.yaml
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml_path", type=Path,
                    help="Prior-list YAML (top-level `tag` + `families: [{refs:[...]}]`).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be tagged without writing.")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.yaml_path.read_text())
    tag = cfg["tag"]
    refs: list[str] = []
    for family in cfg.get("families", []):
        refs.extend(family.get("refs", []))
    refs = sorted(set(refs))

    print(f"Tag: {tag!r}")
    print(f"Refs from {args.yaml_path.name}: {len(refs)}")

    with db.connect() as conn:
        # Audit which refs aren't in the universe — those are silent no-ops.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT application_ref FROM applications WHERE application_ref = ANY(%s)",
                (refs,),
            )
            present = {row[0] for row in cur.fetchall()}
        missing = sorted(set(refs) - present)
        if missing:
            print(f"WARNING: {len(missing)} ref(s) not in universe — these will be skipped:")
            for ref in missing:
                print(f"  - {ref}")

        if args.dry_run:
            print(f"(dry-run) would tag {len(present)} present refs with {tag!r}")
            return 0

        touched = repo.append_discovered_via(
            conn, application_refs=refs, tag=tag,
        )
        conn.commit()
        print(f"Tagged {touched} applications with {tag!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
