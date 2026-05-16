"""Ingest manually-downloaded documents into the canonical bytes / manifest layout.

When the automated portal adapters miss documents (e.g. Idox's OMT-viewer
drawings that ship under `docKey=` links rather than direct PDFs, or
portals we don't have an adapter for yet), the operator can manually
download files from the council website and drop them under a `Manual/`
subdirectory of the application's data folder, then run this script to
fold them into the system.

The ingest is idempotent:
- Each file's SHA-256 is computed and matched against the
  `documents.(application_id, content_sha256)` UNIQUE constraint. If the
  identical bytes already exist for that application, the row is reused
  and the canonical copy isn't overwritten (the manual file stays where
  it was as a working copy).
- The kind label is derived from the filename per the convention the
  portals tend to use: strip the trailing `-<digits>.<ext>` source-id +
  extension, replace `_` with spaces, title-case. A reporter eyeballing
  the manifest gets readable labels (e.g. "Committee Report",
  "Ground Conditions Desk Top Study - Appendix") matching the
  automated-fetch shape.
- The `documents.url` records the manual file as a `file://` URI for
  provenance — distinguishes manual ingestion from adapter-fetched docs
  while preserving an audit trail of where the operator placed the file.
- After ingest, the per-app `_manifest.json` is rewritten so it lists
  every document for the app (manual + adapter-fetched together).

Run:
    .venv/bin/python -m scripts.ingest_manual_docs \\
        --source idox \\
        --application-ref EastRiding/16/02800/STPLF \\
        [--manual-dir <path>]

The default `--manual-dir` is `data/raw/<source>/<application_ref>/Manual/`.
Files anywhere inside that directory (recursing into subdirectories) are
picked up — the operator can mirror the council portal's folder structure
without flattening.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

from dcp import db, repo
from dcp.sources import idox, manual, ocella


# Map source name → adapter module (its `_app_dir`, `_bytes_path` and
# `_write_manifest` helpers we re-use). Keeps the script honest about
# source-specific bytes layout — same content from a different portal lands
# in a different subtree of `data/raw/`. `manual` is for apps whose entire
# bundle was sourced by hand (no adapter exists yet, e.g. NorthLincs); idox
# / ocella are for partial-manual additions to an adapter-covered app.
ADAPTERS = {
    "idox": idox,
    "ocella": ocella,
    "manual": manual,
}


def _kind_from_filename(filename: str) -> str:
    """Best-effort `documents.kind` label from a manual filename.

    Council portals tend to name files `<DOC_TYPE>-<source_id>.<ext>`
    (e.g. `COMMITTEE_REPORT-2472761.pdf`). We strip the trailing source_id
    + extension, normalise underscores to spaces, title-case for
    readability, and trim. If a filename doesn't match the convention the
    full stem is used verbatim.
    """
    stem = Path(filename).stem
    # Strip the trailing `-<digits>` source-id, if present.
    stem = re.sub(r"-\d+$", "", stem)
    # `_-_` separator that some portals use → single `-`
    label = stem.replace("_-_", " - ").replace("_", " ").strip()
    return label.title() if label.isupper() or "_" in stem else label or stem


def _ext_from_path(path: Path) -> str:
    """File extension without the leading dot, lower-cased; defaults to
    `bin` if there's no extension."""
    suffix = path.suffix.lstrip(".").lower()
    return suffix or "bin"


def _existing_document_id(conn, *, application_id: int, content_sha256: str) -> int | None:
    """Return the existing `documents.id` for this (app, sha) tuple, or None.
    Used to decide whether the manual ingest should leave the row alone (it
    matches adapter-fetched bytes — the adapter URL is more authoritative)
    or insert a fresh row with the file:// provenance."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM documents WHERE application_id = %s AND content_sha256 = %s",
            (application_id, content_sha256),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _ingest_one_file(
    conn,
    *,
    adapter,
    application_id: int,
    application_ref: str,
    source_path: Path,
    data_dir: Path,
) -> dict:
    """Hash a manual file, copy to the canonical SHA path if not already
    present, and record a `documents` row only when the bytes are net-new.

    Per principle 3 (never mutate original source material): if the same
    bytes already exist for this application — typically because the
    adapter fetched them earlier with a proper http URL — leave the row
    alone. The manual working copy is still kept in `Manual/` and the
    canonical SHA path on disk is correct, so downstream consumers see
    everything they need. Only the DB metadata is preserved as-was.
    """
    body = source_path.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    ext = _ext_from_path(source_path)
    target = adapter._bytes_path(data_dir, application_ref, sha, ext)
    if target.exists():
        copy_outcome = "skipped_existing"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Prefer a hard link to the operator's working copy — same inode,
        # zero additional disk usage, both paths see the same bytes. Falls
        # back to a real copy on EXDEV (cross-device, e.g. when the source
        # is on an external volume) so the script works on the awkward
        # cases too.
        try:
            os.link(source_path, target)
            copy_outcome = "linked"
        except OSError:
            shutil.copyfile(source_path, target)
            copy_outcome = "copied"

    existing_id = _existing_document_id(
        conn, application_id=application_id, content_sha256=sha,
    )
    if existing_id is not None:
        record_outcome = "row_preserved"
    else:
        repo.record_document(
            conn,
            application_id=application_id,
            url=source_path.resolve().as_uri(),
            kind=_kind_from_filename(source_path.name),
            content_sha256=sha,
            bytes_path=(
                str(target.relative_to(data_dir.parent))
                if target.is_relative_to(data_dir.parent) else str(target)
            ),
        )
        record_outcome = "row_inserted"
    return {"path": source_path, "sha": sha,
            "copy_outcome": copy_outcome, "record_outcome": record_outcome}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source", required=True, choices=sorted(ADAPTERS.keys()))
    parser.add_argument("--application-ref", required=True,
                        help="e.g. 'EastRiding/16/02800/STPLF'")
    parser.add_argument("--manual-dir", default=None,
                        help="Defaults to data/raw/<source>/<application_ref>/Manual/")
    parser.add_argument("--data-dir", default="data",
                        help="Root for the bytes layout (default: data).")
    args = parser.parse_args()

    adapter = ADAPTERS[args.source]
    data_dir = Path(args.data_dir)
    app_dir = adapter._app_dir(data_dir, args.application_ref)
    manual_dir = Path(args.manual_dir) if args.manual_dir else app_dir / "Manual"
    if not manual_dir.exists():
        print(f"manual-dir does not exist: {manual_dir}", file=sys.stderr)
        sys.exit(1)

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM applications WHERE application_ref = %s",
                (args.application_ref,),
            )
            row = cur.fetchone()
            if row is None:
                print(f"application not found: {args.application_ref}", file=sys.stderr)
                sys.exit(2)
            application_id = row[0]

        files = sorted(p for p in manual_dir.rglob("*") if p.is_file() and not p.name.startswith("."))
        print(f"Ingesting {len(files)} manual files from {manual_dir}")
        bytes_outcomes: dict[str, int] = {}
        rows_inserted = 0
        rows_preserved = 0
        for src in files:
            res = _ingest_one_file(
                conn, adapter=adapter,
                application_id=application_id,
                application_ref=args.application_ref,
                source_path=src, data_dir=data_dir,
            )
            kind = _kind_from_filename(src.name)
            print(f"  [bytes:{res['copy_outcome']:16s} row:{res['record_outcome']:14s}] "
                  f"{res['sha'][:16]}  {kind[:50]:50s}  {src.name}")
            bytes_outcomes[res["copy_outcome"]] = bytes_outcomes.get(res["copy_outcome"], 0) + 1
            if res["record_outcome"] == "row_inserted":
                rows_inserted += 1
            else:
                rows_preserved += 1
        # Refresh the per-app manifest so it reflects the combined set.
        # We re-use the adapter's existing manifest writer; it pulls every
        # `documents` row for the application_id, so manual + adapter-fetched
        # docs both appear.
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM documents WHERE application_id = %s
                """,
                (application_id,),
            )
            total_docs = cur.fetchone()[0]
        adapter._write_manifest(
            conn,
            application_id=application_id,
            application_ref=args.application_ref,
            app_dir=app_dir,
            summary={
                "links_found": total_docs,
                "downloaded": rows_inserted,
                "skipped_existing": rows_preserved,
                "errors": 0,
            },
        )
    print()
    bytes_summary = ", ".join(
        f"{k}={v}" for k, v in sorted(bytes_outcomes.items())
    ) or "(no files)"
    print(f"Done: bytes [{bytes_summary}]; "
          f"new rows={rows_inserted}, existing rows preserved={rows_preserved}.")
    print(f"Total documents recorded for this app now: {total_docs}")


if __name__ == "__main__":
    main()
