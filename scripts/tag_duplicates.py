"""Apply `duplicate_of:<primary>` tags to known-duplicate applications.

Reads `data/priors/duplicates.yaml` and stamps every `copy` ref with
`discovered_via=['duplicate_of:<primary_ref>']` via the idempotent
`repo.append_discovered_via` helper. Run after any DB rebuild to
restore the duplicate-tagging state.

Usage:
    .venv/bin/python -m scripts.tag_duplicates [--yaml <path>] [--dry-run]
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

DEFAULT_YAML = ROOT / "data" / "priors" / "duplicates.yaml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML,
                    help="Duplicates YAML (default: data/priors/duplicates.yaml).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be tagged without writing.")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.yaml.read_text())
    duplicates = cfg.get("duplicates", [])
    if not duplicates:
        print(f"No duplicates defined in {args.yaml}", file=sys.stderr)
        return 0

    with db.connect() as conn:
        total_tagged = 0
        for entry in duplicates:
            primary = entry["primary"]
            copies = entry.get("copies", [])
            tag = f"duplicate_of:{primary}"
            if args.dry_run:
                print(f"(dry-run) would tag {len(copies)} copies of {primary} with {tag!r}")
                for c in copies:
                    print(f"  - {c}")
                continue
            n = repo.append_discovered_via(
                conn, application_refs=copies, tag=tag,
            )
            print(f"Tagged {n} copies of {primary}")
            total_tagged += n
        if not args.dry_run:
            print(f"Total: {total_tagged} duplicate tags applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
