#!/usr/bin/env python3
"""Ingest documents harvested through the browser into the corpus.

`scripts/browser_receiver.py` writes whatever the page POSTs it into a
flat directory: `cov_<portal id>_<n>.bin` for the bytes and
`cov_<portal id>_manifest.json` for what each one is and where it came
from. This turns that into ordinary corpus rows — same storage layout,
same content-hash dedup, same provenance fields as any adapter — so a
document fetched by hand through a browser is indistinguishable
downstream from one fetched by an adapter, except in how it is labelled.

The manifest is the authority on what belongs to which application: the
portal's internal id maps to our application via the `id=` parameter in
the stored URL. A `.bin` with no manifest entry is left alone rather than
guessed at.

Idempotent. Re-running ingests nothing new: the documents table's
(application_id, content_sha256) constraint absorbs repeats, and files
already recorded are skipped by URL.

    scripts/ingest_browser_harvest.py --dry-run
    scripts/ingest_browser_harvest.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox as _idox  # noqa: E402

log = logging.getLogger("ingest_harvest")

# Magic numbers we expect from a planning portal. Anything else is
# reported rather than stored: an HTML error page saved as a PDF is how
# a corpus quietly fills with junk that only surfaces at read time.
MAGIC = {b"%PDF": "pdf", b"PK\x03\x04": "docx", b"\xd0\xcf\x11\xe0": "doc",
         b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"GIF8": "gif",
         b"{\\rt": "rtf"}


def sniff(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harvest", type=Path,
                   default=Path("data/raw/browser_harvest"))
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--source-name", default="browser_harvest")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")

    manifests = sorted(args.harvest.glob("*_manifest.json"))
    if not manifests:
        log.info("no manifests in %s", args.harvest)
        return 0
    log.info("%d manifests", len(manifests))

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, application_ref, url FROM applications
                       WHERE url ~ 'id=[0-9]+'""")
        by_portal_id: dict[str, tuple[int, str]] = {}
        for app_id, ref, url in cur.fetchall():
            m = re.search(r"[?&]id=(\d+)", url or "")
            if m:
                by_portal_id[m.group(1)] = (app_id, ref)

    totals = {"documents": 0, "stored": 0, "skipped": 0,
              "unmatched_app": 0, "bad_bytes": 0, "missing_file": 0}
    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=args.source_name, kind="council",
            base_url="(documents retrieved via browser where scripted "
                     "access is refused)")
        conn.commit()

        for mf in manifests:
            man = json.loads(mf.read_text())
            portal_id = str(man.get("app_internal_id"))
            match = by_portal_id.get(portal_id)
            if not match:
                log.warning("%s: portal id %s matches no application",
                            mf.name, portal_id)
                totals["unmatched_app"] += 1
                continue
            application_id, ref = match
            with conn.cursor() as cur:
                cur.execute("SELECT url FROM documents WHERE application_id = %s",
                            (application_id,))
                held = {u for (u,) in cur.fetchall()}

            app_dir = (args.data_dir / "raw" / "documents"
                       / _idox._sanitised_ref(ref))
            stored = skipped = 0
            for entry in man.get("documents", []):
                if entry.get("error") or not entry.get("file"):
                    continue
                totals["documents"] += 1
                if entry["url"] in held:
                    skipped += 1; totals["skipped"] += 1; continue
                src = args.harvest / entry["file"]
                if not src.exists():
                    totals["missing_file"] += 1; continue
                data = src.read_bytes()
                ext = sniff(data)
                if ext is None:
                    log.warning("%s: %s is not a recognised document (%r)",
                                ref, entry["file"], data[:8])
                    totals["bad_bytes"] += 1
                    continue
                if args.dry_run:
                    stored += 1; totals["stored"] += 1; continue
                sha = hashlib.sha256(data).hexdigest()
                target = app_dir / f"{sha[:16]}.{ext}"
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                repo.record_document(
                    conn, application_id=application_id, url=entry["url"],
                    kind=entry.get("type") or entry.get("desc"),
                    content_sha256=sha,
                    bytes_path=(str(target.relative_to(args.data_dir.parent))
                                if target.is_relative_to(args.data_dir.parent)
                                else str(target)))
                stored += 1; totals["stored"] += 1
            if not args.dry_run and stored:
                conn.commit()
                _idox._write_manifest(
                    conn, application_id=application_id, application_ref=ref,
                    app_dir=app_dir,
                    summary={"ref": ref, "links_found": len(man.get("documents", [])),
                             "downloaded": stored, "skipped_existing": skipped,
                             "errors": 0})
            log.info("%-30s %3d stored, %3d already held", ref, stored, skipped)

    log.info("done: %(stored)d documents stored, %(skipped)d already held, "
             "%(unmatched_app)d manifests unmatched, %(bad_bytes)d bad bytes, "
             "%(missing_file)d files missing", totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
