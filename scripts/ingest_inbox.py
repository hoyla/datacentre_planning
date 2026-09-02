"""Ingest hand-obtained documents from the manual inbox.

Reads `data/raw/manual/<application-ref>/`, writes each file into the
single document store, records it with provenance, regenerates the
application's manifest, and empties the inbox folder — so anything left
in the inbox always means "not yet ingested".

Folder names map to application references with any of `/`, `_` or `:`
as the separator (macOS renders `/` as `:` in filenames, so a zip named
after its reference unpacks tidily). Two shapes are accepted, because
both have been used: one folder per application at the top of the inbox
(`Havering_P0384.15`), or a council folder holding one folder per
reference (`Havering/P0384.15`). A trailing annotation in parentheses —
`P0384.15 (PTNO-12106647)`, the site key someone wrote down while
downloading — is ignored for resolution and kept as the folder's name.
A folder that cannot be resolved to exactly one application is reported
and left alone rather than guessed at.

**A page capture is not a document.** A portal page printed to PDF for
an application that lists *no* documents is evidence of absence, and
dropping it here would file it as the application's one document —
inverting the finding. Record that check with
`scripts/record_portal_check.py` instead, which files the capture beside
the other hand-obtained bundles and appends the acquisition outcome. A
capture of a page that *does* list documents may be ingested with them,
under a filename that says what it is.

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
import re
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
# The route name on the outcome row. `manual` is what the single-store
# migration used for bundles sourced entirely by hand, so the fold and
# the exporters see one route for hand-obtained documents.
ADAPTER = "manual"


def hand_outcome(n_files: int, shown: str) -> tuple[str, str] | None:
    """The acquisition outcome an inbox ingest earns, or None for none.

    Without this row the fold kept saying what the adapter last
    concluded — Creek Way's `none_published` from an Ocella page the
    adapter could not parse — while the application held fourteen
    documents obtained by hand. A fetch by a person is still a fetch.
    """
    if n_files <= 0:
        return None
    return ("fetched", f"{n_files} file(s) obtained by hand and ingested from "
                       f"the manual inbox ({shown})")


# "P0384.15 (PTNO-12106647)" -> "P0384.15": an annotation someone added
# while downloading is not part of the reference.
_ANNOTATION = re.compile(r"\s*\([^()]*\)\s*$")


def folder_candidate(folder_name: str) -> str:
    """The application reference an inbox folder name stands for.

    `folder_name` may be one level deep (`Havering/P0384.15 (...)`): each
    part loses any trailing parenthetical, then `:` and `_` become the
    reference separator, so the two accepted layouts and the macOS
    rendering of `/` all reduce to the same candidate.
    """
    parts = [_ANNOTATION.sub("", part) for part in folder_name.split("/")]
    return "/".join(p.replace(":", "/").replace("_", "/") for p in parts if p)


def resolve_ref(conn, folder_name: str) -> tuple[int, str, str] | None:
    """Map an inbox folder name to (application_id, ref, url), or None."""
    candidate = folder_candidate(folder_name)
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

    top = [p for p in sorted(INBOX.iterdir())
           if p.is_dir() and p.name not in SKIP_NAMES] if INBOX.exists() else []
    if not top:
        print("inbox empty — nothing to ingest")
        return

    with db.connect() as conn:
        repo.ensure_source(conn, name="idox", kind="council",
                           base_url="(per-council Idox host)")
        # A top-level folder is an application folder if its name
        # resolves; otherwise it is read as a council folder and each
        # child is tried as `council/ref`. Either way the folder that
        # resolves is the one ingested and removed.
        work: list[tuple[Path, str, tuple | None]] = []
        for folder in top:
            resolved = resolve_ref(conn, folder.name)
            children = [c for c in sorted(folder.iterdir())
                        if c.is_dir() and c.name not in SKIP_NAMES]
            if resolved is None and children:
                for child in children:
                    rel = f"{folder.name}/{child.name}"
                    work.append((child, rel, resolve_ref(conn, rel)))
            else:
                work.append((folder, folder.name, resolved))
        for folder, shown, resolved in work:
            if resolved is None:
                print(f"  {shown}: UNRESOLVED — no single matching "
                      f"application; left in place")
                continue
            app_id, ref, page_url = resolved
            files = [f for f in sorted(folder.rglob("*"))
                     if f.is_file() and f.name not in SKIP_NAMES]
            print(f"  {shown} -> {ref}: {len(files)} files")
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
                earned = hand_outcome(summary["downloaded"], shown)
                if earned:
                    cur.execute("""INSERT INTO acquisition_outcome
                                     (application_id, outcome, adapter, detail,
                                      documents_found, checked_at)
                                   VALUES (%s, %s, %s, %s, %s, now())""",
                                (app_id, earned[0], ADAPTER, earned[1],
                                 summary["downloaded"]))
            conn.commit()
            print(f"     ingested {summary['downloaded']}, "
                  f"application now holds {held} distinct documents")
            if not args.keep:
                shutil.rmtree(folder)
                # A council folder emptied of its last reference goes too,
                # so a non-empty inbox keeps meaning "work outstanding".
                parent = folder.parent
                if parent != INBOX and not any(
                        c.name not in SKIP_NAMES for c in parent.iterdir()):
                    shutil.rmtree(parent)


if __name__ == "__main__":
    main()
