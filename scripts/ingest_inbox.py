"""Ingest hand-obtained documents from the manual inbox.

Reads `data/raw/manual/<application-ref>/`, writes each file into the
single document store, records it with provenance, regenerates the
application's manifest, and empties the inbox folder — so anything left
in the inbox always means "not yet ingested".

Folder names map to application references with any of `/`, `_` or `:`
as the separator (macOS renders `/` as `:` in filenames, so a zip named
after its reference unpacks tidily). A folder that cannot be resolved to
exactly one application is reported and left alone rather than guessed
at.

Provenance for hand-obtained documents is the application's portal page
plus the council's own filename — per-document portal URLs cannot be
recovered after a browser download, and a fabricated one would be worse
than an honest page-level reference.

Usage:
    .venv/bin/python scripts/ingest_inbox.py [--dry-run] [--keep]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox  # noqa: E402

INBOX = Path("data/raw/manual")
SKIP_NAMES = {".DS_Store", "README.md"}


def resolve_ref(conn, folder_name: str) -> tuple[int, str, str] | None:
    """Map an inbox folder name to (application_id, ref, url), or None."""
    candidate = folder_name.replace(":", "/").replace("_", "/")
    with conn.cursor() as cur:
        cur.execute("""SELECT id, application_ref, url FROM applications
                       WHERE application_ref = %s""", (candidate,))
        row = cur.fetchone()
        if row:
            return row
        # Fall back to a normalised comparison (separator-insensitive).
        norm = candidate.replace("/", "").upper()
        cur.execute("""SELECT id, application_ref, url FROM applications
                       WHERE replace(upper(application_ref), '/', '') = %s""",
                    (norm,))
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0]
        # A zip named after the council's own reference has no council
        # prefix ("21/00802/NMA" for "Wychavon/21/00802/NMA"), so match on
        # suffix — but only accept an unambiguous single hit, since bare
        # references repeat across councils.
        cur.execute("""SELECT id, application_ref, url FROM applications
                       WHERE replace(upper(application_ref), '/', '') LIKE %s""",
                    (f"%{norm}",))
        rows = cur.fetchall()
        return rows[0] if len(rows) == 1 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true",
                    help="Leave the inbox folder in place after ingest.")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    folders = [p for p in sorted(INBOX.iterdir())
               if p.is_dir() and p.name not in SKIP_NAMES] if INBOX.exists() else []
    if not folders:
        print("inbox empty — nothing to ingest")
        return

    with db.connect() as conn:
        repo.ensure_source(conn, name="idox", kind="council",
                           base_url="(per-council Idox host)")
        for folder in folders:
            resolved = resolve_ref(conn, folder.name)
            if resolved is None:
                print(f"  {folder.name}: UNRESOLVED — no single matching "
                      f"application; left in place")
                continue
            app_id, ref, page_url = resolved
            files = [f for f in sorted(folder.rglob("*"))
                     if f.is_file() and f.name not in SKIP_NAMES]
            print(f"  {folder.name} -> {ref}: {len(files)} files")
            if args.dry_run:
                continue

            summary = {"links_found": len(files), "downloaded": 0,
                       "skipped_existing": 0, "errors": 0}
            for f in files:
                body = f.read_bytes()
                sha = hashlib.sha256(body).hexdigest()
                ext = f.suffix.lstrip(".").lower() or "bin"
                target = idox._bytes_path(args.data_dir, ref, sha, ext)
                if target.exists():
                    summary["skipped_existing"] += 1
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(body)
                repo.record_document(
                    conn, application_id=app_id,
                    url=f"{page_url}#{urllib.parse.quote(f.name)}",
                    kind=f.stem[:120], content_sha256=sha,
                    bytes_path=str(target.relative_to(args.data_dir.parent)),
                )
                summary["downloaded"] += 1
                conn.commit()

            idox._write_manifest(conn, application_id=app_id,
                                 application_ref=ref,
                                 app_dir=idox._app_dir(args.data_dir, ref),
                                 summary=summary)
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM documents WHERE application_id=%s",
                            (app_id,))
                held = cur.fetchone()[0]
            print(f"     ingested {summary['downloaded']}, "
                  f"application now holds {held} distinct documents")
            if not args.keep:
                shutil.rmtree(folder)


if __name__ == "__main__":
    main()
