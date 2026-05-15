"""Retroactively fill NULL `applications.council_gss` from the `area_name`
carried in `raw_metadata`. Two passes:

  1. Direct match against `councils.notes->area_name`.
  2. Alias match against `council_aliases.alias_name` (legacy district names
     mapped to current unitary GSS codes).

Run once after Migration 004 (`004_council_aliases.sql`) lands. Subsequent
ingest passes get the right `council_gss` at insert time via
`_load_area_gss_map`, which consults both councils and council_aliases.

Idempotent — already-non-NULL rows are skipped.

Usage:
    python scripts/backfill_council_gss.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, repo  # noqa: E402


def main() -> int:
    with db.connect() as conn:
        out = repo.backfill_council_gss(conn)
        for k, v in out.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
