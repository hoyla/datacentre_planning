#!/usr/bin/env python3
"""Rename the operator snapshots from `<slug>.txt` to `<slug>.<date>.txt`.

The one-off migration behind the append-only snapshot store
(ROADMAP, "The snapshot store is mutable"; WP-A of
docs/HANDOVER_SNAPSHOT_CHAIN.md). Every held snapshot already records
the day it was fetched in its own `# fetched:` header, so the new name
is read out of the file rather than invented — a file whose header
cannot be read is left alone and reported, never renamed to today.

`git mv`, not `mv`, so the rename is a rename in the history and the
diff stays reviewable at 81 files.

Idempotent: a store already migrated has nothing matching `<slug>.txt`
and the run is a no-op. Kept in the repository on the
`migrate_single_store.py` precedent — a migration that moved files is
worth being able to read afterwards.

Usage:
    scripts/migrate_snapshot_names.py --dry-run
    scripts/migrate_snapshot_names.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "external_sources" / "operator_snapshots"

_FETCHED_RE = re.compile(r"^# fetched: (\d{4}-\d{2}-\d{2})$", re.MULTILINE)


def fetched_day(path: Path) -> str | None:
    """The date the file says it was fetched on, from its own header."""
    m = _FETCHED_RE.search("\n".join(
        path.read_text(encoding="utf-8").splitlines()[:6]))
    return m.group(1) if m else None


def plan(out: Path = OUT) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Renames to make, and the files that state no fetch date."""
    moves, undated = [], []
    for src in sorted(out.glob("*.txt")):
        # A name already carrying a date is migrated; skip it rather
        # than nesting a second date inside it.
        if re.search(r"\.\d{4}-\d{2}-\d{2}(_\d+)?\.txt$", src.name):
            continue
        day = fetched_day(src)
        if day is None:
            undated.append(src)
            continue
        moves.append((src, out / f"{src.stem}.{day}.txt"))
    return moves, undated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    moves, undated = plan()
    for src in undated:
        print(f"  NO FETCH DATE, left alone: {src.name}", file=sys.stderr)
    for src, dest in moves:
        if dest.exists():
            print(f"  CLASH, left alone: {src.name} -> {dest.name}",
                  file=sys.stderr)
            continue
        print(f"  {src.name:<40} -> {dest.name}")
        if not args.dry_run:
            subprocess.run(["git", "mv", str(src), str(dest)],
                           cwd=ROOT, check=True)
    print(f"{len(moves)} to rename, {len(undated)} without a fetch date"
          f"{' (dry run)' if args.dry_run else ''}")
    return 1 if undated else 0


if __name__ == "__main__":
    sys.exit(main())
