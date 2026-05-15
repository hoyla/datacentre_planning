"""Retroactively write `_manifest.json` files for already-complete Idox app
directories — needed once after the inaugural top-N smoke run because the
adapter didn't yet write manifests during that run.

"Complete" here means: the count of PDFs on disk for an app matches the count
of `documents` rows in the DB for that app. If they match, the fetch loop for
that app finished cleanly (the DB row is inserted only after a successful
file write inside the orchestrator, and the commit happens immediately).

If they don't match (FS has more PDFs than DB), an earlier run was
interrupted between file-write and commit — those dirs are left without a
manifest so the operator notices.

Idempotent: existing manifests are not overwritten unless `--force` is set.

Usage:
    scripts/finalize_idox_manifests.py                 # dry run + summary
    scripts/finalize_idox_manifests.py --apply         # actually write
    scripts/finalize_idox_manifests.py --apply --force # rewrite existing too
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402
from dcp.sources import idox  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data",
                    help="Root for the bytes layout (default: data/).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write manifests. Default is dry-run.")
    ap.add_argument("--force", action="store_true",
                    help="Rewrite manifests even if one already exists.")
    args = ap.parse_args()

    raw_idox = args.data_dir / "raw" / "idox"
    if not raw_idox.exists():
        print(f"No {raw_idox} — nothing to manifest.")
        return 0

    # Count all document files, not just .pdf — Idox serves docx/rtf/xlsm/doc/etc.
    # too, and our `_ext_from_url` preserves the suffix verbatim. Exclude the
    # manifest file itself so re-runs don't inflate the count.
    doc_counts: dict[str, int] = {}
    for f in raw_idox.rglob("*"):
        if not f.is_file() or f.name == idox.MANIFEST_FILENAME:
            continue
        rel = f.relative_to(raw_idox).parent
        application_ref = str(rel)
        doc_counts[application_ref] = doc_counts.get(application_ref, 0) + 1

    print(f"Found {len(doc_counts)} app directories under {raw_idox}.")

    with db.connect() as conn:
        ready: list[tuple[str, int, int]] = []     # (ref, fs_count, db_count)
        skipped_mismatch: list[tuple[str, int, int]] = []
        skipped_existing: list[str] = []
        not_in_db: list[str] = []

        for application_ref, fs_count in sorted(doc_counts.items()):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.id, count(d.id)
                    FROM applications a
                    LEFT JOIN documents d ON d.application_id = a.id
                    WHERE a.application_ref = %s
                    GROUP BY a.id
                    """,
                    (application_ref,),
                )
                row = cur.fetchone()
            if row is None:
                not_in_db.append(application_ref)
                continue
            application_id, db_count = row
            if db_count != fs_count:
                skipped_mismatch.append((application_ref, fs_count, db_count))
                continue
            manifest_path = raw_idox / application_ref / idox.MANIFEST_FILENAME
            if manifest_path.exists() and not args.force:
                skipped_existing.append(application_ref)
                continue
            ready.append((application_ref, application_id, db_count))

        print(f"  ready to manifest: {len(ready)}")
        print(f"  skipped (existing manifest, no --force): {len(skipped_existing)}")
        print(f"  skipped (FS/DB count mismatch — fetch likely incomplete): {len(skipped_mismatch)}")
        print(f"  not in `applications` table: {len(not_in_db)}")
        if skipped_mismatch:
            print()
            print("Mismatch detail (FS != DB):")
            for ref, fs, db_n in skipped_mismatch:
                print(f"  - {ref}: fs={fs} db={db_n}")
        if not_in_db:
            print()
            print("Not in `applications` table (orphaned dirs):")
            for ref in not_in_db:
                print(f"  - {ref}")

        if not args.apply:
            print()
            print("(dry-run; pass --apply to write manifests)")
            return 0

        wrote = 0
        for application_ref, application_id, db_count in ready:
            app_dir = raw_idox / application_ref
            summary = {
                "links_found": db_count,
                "downloaded": 0,
                "skipped_existing": db_count,
                "errors": 0,
            }
            idox._write_manifest(
                conn,
                application_id=application_id,
                application_ref=application_ref,
                app_dir=app_dir,
                summary=summary,
            )
            wrote += 1
        print()
        print(f"Wrote {wrote} manifests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
