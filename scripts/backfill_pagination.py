#!/usr/bin/env python3
"""Populate documents.pagination from the text caches.

The extractor records whose division `evidence_page` indexes — pages for
a PDF, sections for a Word file, sheets for a workbook, slides for a
deck — but it records it in the cache file, and every export is SQL. This
carries it into the column migration 020 adds, so a citation can say
"sheet 3" where "page 3" would send a reporter looking for something that
does not exist.

Two sources, in order of authority:

1. **The cache's own `pagination` field.** Written by dcp/extract.py from
   its loader table. Trusted absolutely where present.
2. **The file's magic bytes**, for the 34,329 caches written before the
   field existed. Only `%PDF` is inferred, and only to 'pages'. Anything
   else is left null rather than guessed: null means "not recorded", and
   a wrong provenance label is worse than an absent one.

Idempotent and safe to re-run: it writes only where the value differs,
and reports what it changed.

Usage:
    scripts/backfill_pagination.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, extract  # noqa: E402

VALID = {"pages", "sections", "sheets", "slides"}


def pagination_for(app_ref: str, sha: str, bytes_path: str | None) -> str | None:
    """The recorded pagination, or one inferred from the file's own bytes."""
    cache = extract.cache_path_for("documents", app_ref, sha)
    if cache.exists():
        try:
            recorded = json.loads(cache.read_text()).get("pagination")
        except Exception:
            recorded = None
        if recorded in VALID:
            return recorded
        # extract.py stores the format name itself for some loaders (see
        # its `pagination=fmt` branch); map anything it does not
        # recognise to nothing rather than inventing a category.
        if recorded:
            return None
    if bytes_path:
        p = Path(bytes_path)
        try:
            if p.exists() and p.read_bytes()[:4] == b"%PDF":
                return "pages"
        except OSError:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    counts: Counter[str] = Counter()
    updates: list[tuple[str, int]] = []

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, a.application_ref, d.content_sha256,
                       d.bytes_path, d.pagination
                FROM documents d
                JOIN applications a ON a.id = d.application_id
                WHERE d.content_sha256 IS NOT NULL
                ORDER BY d.id""")
            rows = cur.fetchall()
        if args.limit:
            rows = rows[:args.limit]

        for doc_id, app_ref, sha, bytes_path, existing in rows:
            found = pagination_for(app_ref, sha, bytes_path)
            counts[found or "<unrecorded>"] += 1
            if found and found != existing:
                updates.append((found, doc_id))

        print(f"{len(rows):,} documents inspected")
        for k, v in counts.most_common():
            print(f"  {k:<14} {v:,}")
        print(f"{len(updates):,} to update")

        if args.dry_run or not updates:
            return 0
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE documents SET pagination = %s WHERE id = %s", updates)
        conn.commit()
    print(f"{len(updates):,} rows written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
