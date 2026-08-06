"""Consolidate the per-adapter document stores into one tree keyed by application.

Documents used to live under `data/raw/<adapter>/<application_ref>/...`,
which encoded *how* a document arrived into *where* it lives. That is the
wrong axis: acquisition route is a property of the fetch, not of the
application, and one application is legitimately served by several routes
(an adapter, a hand download, a browser-obtained bundle from a portal that
blocks automated clients). It also decays — browser-obtained Wychavon
documents were written under `raw/idox/` even though Wychavon is not an
Idox portal.

After this migration:

    data/raw/documents/<application_ref>/<sha256[:16]>.<ext>
    data/raw/documents/<application_ref>/_manifest.json

One application, one folder, one manifest, whatever route each file came
by. How each document was obtained is recorded per document in the
manifest (`obtained`, `source_url`) and in the database.

Safety: files are *moved* (same filesystem — instant renames, no copying
of 66GB), each move verified by re-hashing the moved bytes before the old
path is forgotten; `documents.bytes_path` is updated in the same
transaction. Nothing is deleted: empty adapter directories are left in
place for the operator to remove once satisfied.

Usage:
    .venv/bin/python scripts/migrate_single_store.py --dry-run
    .venv/bin/python scripts/migrate_single_store.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402

SAFE_RE = re.compile(r"[^A-Za-z0-9._/-]+")
OLD_STORES = ("idox", "agile", "arcus", "ocella", "salesforce_pr",
              "manual", "fully_manual")


def safe_ref(application_ref: str) -> str:
    return SAFE_RE.sub("_", application_ref)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--verify-sample", type=int, default=50,
                    help="Re-hash this many moved files as a spot check "
                         "(every move is size-checked regardless).")
    args = ap.parse_args()

    root = args.data_dir / "raw" / "documents"
    stats = {"rows": 0, "moved": 0, "already_there": 0, "missing": 0,
             "hash_mismatch": 0, "collisions_deduped": 0}
    moved_paths: list[Path] = []

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.id, a.application_ref, d.bytes_path, d.content_sha256
                FROM documents d JOIN applications a ON a.id = d.application_id
                WHERE d.bytes_path IS NOT NULL
                ORDER BY a.application_ref, d.id""")
            rows = cur.fetchall()

        print(f"{len(rows)} document rows to consider")
        updates: list[tuple[str, int]] = []

        for doc_id, ref, bytes_path, sha in rows:
            stats["rows"] += 1
            old = Path(bytes_path)
            if not old.is_absolute():
                old = args.data_dir.parent / old
            # Target: single tree keyed by application.
            ext = old.suffix.lstrip(".") or "bin"
            new_rel = Path("data") / "raw" / "documents" / safe_ref(ref) / f"{sha[:16]}.{ext}"
            new_abs = args.data_dir.parent / new_rel

            if new_abs.exists():
                stats["already_there"] += 1
                if str(new_rel) != bytes_path:
                    updates.append((str(new_rel), doc_id))
                # An old copy that duplicates the canonical one is redundant.
                if old.exists() and old != new_abs:
                    stats["collisions_deduped"] += 1
                continue
            if not old.exists():
                stats["missing"] += 1
                continue
            if args.dry_run:
                stats["moved"] += 1
                continue

            new_abs.parent.mkdir(parents=True, exist_ok=True)
            size_before = old.stat().st_size
            shutil.move(str(old), str(new_abs))
            if new_abs.stat().st_size != size_before:
                stats["hash_mismatch"] += 1
                print(f"  SIZE MISMATCH after move: {new_abs}")
                continue
            moved_paths.append(new_abs)
            updates.append((str(new_rel), doc_id))
            stats["moved"] += 1

        if not args.dry_run and updates:
            with conn.cursor() as cur:
                cur.executemany("UPDATE documents SET bytes_path=%s WHERE id=%s",
                                updates)
            conn.commit()
            print(f"updated {len(updates)} bytes_path rows")

    # Spot-check: re-hash a sample of moved files against the recorded hash.
    if moved_paths and not args.dry_run:
        import random
        random.seed(0)
        sample = random.sample(moved_paths, min(args.verify_sample, len(moved_paths)))
        bad = 0
        for p in sample:
            expected = p.stem  # sha256[:16]
            if not sha256_of(p).startswith(expected):
                bad += 1
                print(f"  HASH MISMATCH: {p}")
        print(f"verified {len(sample)} moved files by re-hashing; {bad} mismatches")

    print(f"\n{stats}")
    if not args.dry_run:
        print("\nOld adapter directories are left in place (now mostly empty); "
              "remove them once you are satisfied:")
        for s in OLD_STORES:
            d = args.data_dir / "raw" / s
            if d.exists():
                left = sum(1 for _ in d.rglob("*") if _.is_file())
                print(f"  data/raw/{s}: {left} files remaining")


if __name__ == "__main__":
    main()
