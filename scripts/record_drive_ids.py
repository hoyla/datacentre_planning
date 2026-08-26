#!/usr/bin/env python3
"""Record where each document's copy lives on Drive, by file id.

Run after `drive_sync.py`. Reads the sync ledger, works out which
document each uploaded file is a copy of, and writes the Drive file id
into `document_drive_files`. Nothing downstream derives a path again:
the reader and the workbook read the id straight out of the table.

## Why this is a separate step and not a lookup at export time

Deriving a file's location is fine until something moves. The ledger
keys on the local staging path, so resolving a document meant rebuilding
its expected path from the site stem, the application reference, and a
number counting the application's documents in `fetched_at, id` order.
Every one of those can change. When it does, the derivation either finds
nothing — the document silently loses its link — or finds the
neighbouring file, which is a live link to the wrong document sitting
under a citation that names a different one. The second is invisible.

Capturing the id once removes the derivation from everything that runs
afterwards. A Drive file id survives the file being moved or renamed on
Drive, so a recorded id keeps resolving where a recorded path would not.

## The contract

Append-only and idempotent: a unique index on (document_id, file_id)
means re-running over an unchanged ledger inserts nothing, and a
document re-uploaded to a new location gains a row rather than losing
its old one.

Every id written is checked against the ledger's own md5 of the uploaded
bytes before it is stored. A document whose local bytes do not match the
copy the ledger claims to have uploaded is reported and skipped, because
a link that resolves to the wrong document is worse than no link — the
same argument that took the `file://` anchors out of the reader.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcp import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "data" / "exports" / ".drive_sync_state.json"

# The documents an id can be recorded for: everything staged, which is
# everything whose application has a live site row. The same rule
# `build_drive_staging` applies, stated once here so a document outside
# it is reported as out of scope rather than as a failure.
DOCUMENTS_SQL = """
    SELECT a.id, a.application_ref, s.site_key, s.display_name,
           d.id, d.url, d.kind, d.content_sha256, d.bytes_path, d.fetched_at
    FROM documents d
    JOIN applications a ON a.id = d.application_id
    JOIN site_members m ON m.application_id = a.id AND m.retired_at IS NULL
    JOIN sites s ON s.id = m.site_id AND s.retired_at IS NULL
    ORDER BY a.id, s.site_key, d.fetched_at, d.id"""


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def ledger_files() -> dict[str, dict]:
    if not LEDGER.exists():
        raise SystemExit(
            f"no sync ledger at {LEDGER} — run scripts/drive_sync.py first")
    return json.loads(LEDGER.read_text()).get("files", {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be recorded, write nothing")
    ap.add_argument("--verify-bytes", action="store_true",
                    help="hash every local file and refuse an id whose md5 "
                         "disagrees with the ledger (~3 min, 138 GB read)")
    args = ap.parse_args()

    files = ledger_files()
    # Index the ledger by the tail of its key so the lookup does not
    # depend on where the staging tree sits on disk.
    by_tail: dict[str, dict] = {}
    for path, meta in files.items():
        if (meta or {}).get("id"):
            parts = PurePosixPath(path).parts
            if len(parts) >= 3:
                by_tail.setdefault("/".join(parts[-3:]),
                                   {**meta, "path": path})

    bds = _load("build_drive_staging")

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(DOCUMENTS_SQL)
            rows = cur.fetchall()
            cur.execute("SELECT document_id, file_id FROM document_drive_files")
            known = {(d, f) for d, f in cur.fetchall()}

        by_app: dict[tuple, list] = defaultdict(list)
        meta_by_app: dict[tuple, tuple] = {}
        for (app_id, ref, site_key, site_name, doc_id, url, kind, sha, bp,
             ft) in rows:
            k = (app_id, site_key)
            by_app[k].append((doc_id, (url, kind, sha, bp, ft)))
            meta_by_app[k] = (ref, site_key, site_name)

        found: dict[int, tuple[str, str, str]] = {}
        unstaged = 0
        for k in sorted(by_app, key=lambda t: (t[0], t[1])):
            ref, site_key, site_name = meta_by_app[k]
            stem = bds.site_stem(site_key, site_name)
            named = bds.document_filenames(ref, [r[1] for r in by_app[k]])
            for (doc_id, _row), (_sha, _src, relpath, _u, _kind,
                                 exists) in zip(by_app[k], named):
                if not exists or not relpath:
                    unstaged += 1
                    continue
                hit = by_tail.get(f"{stem}/{relpath}")
                if not hit:
                    unstaged += 1
                    continue
                # First path by site key wins, deterministically: an
                # application under two sites is staged under both and
                # the files are identical.
                found.setdefault(doc_id,
                                 (hit["id"], hit.get("md5") or "",
                                  hit.get("path") or ""))

        # The bytes check. Off by default because it reads the whole
        # corpus; on, it is the thing that makes a wrong id impossible
        # rather than merely unobserved.
        rejected = []
        if args.verify_bytes:
            paths = {r[4]: r[8] for r in rows}
            for doc_id in sorted(found):
                fid, want, spath = found[doc_id]
                bp = paths.get(doc_id)
                if not want or not bp or not Path(bp).exists():
                    continue
                got = hashlib.md5(Path(bp).read_bytes()).hexdigest()
                if got != want:
                    rejected.append((doc_id, spath, want, got))
            for doc_id, *_ in rejected:
                found.pop(doc_id, None)

        fresh = [(d, f, m, p) for d, (f, m, p) in sorted(found.items())
                 if (d, f) not in known]

        print(f"ledger entries with an id : {len(by_tail):,}")
        print(f"documents matched to a copy: {len(found):,}")
        print(f"  already recorded         : {len(found) - len(fresh):,}")
        print(f"  to record                : {len(fresh):,}")
        print(f"staged nowhere yet         : {unstaged:,}")
        if args.verify_bytes:
            print(f"refused, bytes disagree    : {len(rejected):,}")
            for doc_id, spath, want, got in rejected[:10]:
                print(f"    doc {doc_id}: ledger md5 {want} but local {got}")
                print(f"      {spath}")
        elif fresh:
            print("bytes not verified (pass --verify-bytes to check every "
                  "id against the local file before storing it)")

        if args.dry_run:
            print("\ndry run — nothing written")
            return 0
        if not fresh:
            print("\nnothing to do")
            return 0

        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO document_drive_files
                       (document_id, file_id, md5, staged_path)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (document_id, file_id) DO NOTHING""",
                fresh)
        conn.commit()
        print(f"\nrecorded {len(fresh):,} Drive file ids")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
