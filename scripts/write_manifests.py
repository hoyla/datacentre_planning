"""Write `_manifest.json` for every application in the single document store.

One manifest per application folder, generated from the database, so the
folder is self-describing wherever it ends up (Drive, a shared archive, a
reporter's laptop). Supersedes the per-adapter manifests that the old
split store produced, and the manual-only variant.

Each manifest records, per document: content hash, on-disk path, source
URL, document kind, when it was fetched, and how it was obtained
(portal fetch vs by hand) — plus application-level context: the portal
page, the status we hold, and any browser-observed status panel.

Usage:
    .venv/bin/python scripts/write_manifests.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db  # noqa: E402

MANIFEST_VERSION = 2
SAFE_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def safe_ref(ref: str) -> str:
    return SAFE_RE.sub("_", ref)


def _obtained(url: str | None) -> str:
    u = url or ""
    if u.startswith("file://"):
        return "by hand (operator download, pre-URL-recording)"
    if "#" in u and "plan.wychavon" in u:
        return "by hand via browser (portal blocks automated clients)"
    return "portal fetch"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    args = ap.parse_args()

    written = 0
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT a.id, a.application_ref, a.url, a.status, a.date_received,
                   a.date_decided, a.raw_metadata->'portal_status_observed'
            FROM applications a
            WHERE EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id)
            ORDER BY a.application_ref""")
        apps = cur.fetchall()
        print(f"{len(apps)} applications with documents")

        for app_id, ref, page_url, status, received, decided, observed in apps:
            cur.execute("""
                SELECT url, kind, content_sha256, bytes_path, fetched_at,
                       page_count, ocr_used
                FROM documents WHERE application_id = %s
                ORDER BY fetched_at, id""", (app_id,))
            rows = cur.fetchall()
            docs = [
                {
                    "kind": kind,
                    "content_sha256": sha,
                    "bytes_path": bp,
                    "source_url": url,
                    "obtained": _obtained(url),
                    "page_count": pc,
                    "ocr_used": ocr,
                    "fetched_at": ft.isoformat(timespec="seconds") if ft else None,
                }
                for url, kind, sha, bp, ft, pc, ocr in rows
            ]
            by_hand = sum(1 for d in docs if not d["obtained"].startswith("portal"))
            payload = {
                "manifest_version": MANIFEST_VERSION,
                "application_ref": ref,
                "application_url": page_url,
                "status_held": status,
                "date_received": str(received) if received else None,
                "date_decided": str(decided) if decided else None,
                "portal_status_observed": observed,
                "generated_at": dt.datetime.now(dt.timezone.utc)
                                  .isoformat(timespec="seconds"),
                "document_count": len(docs),
                "documents_obtained_by_hand": by_hand,
                "documents": docs,
            }
            out = args.data_dir / "raw" / "documents" / safe_ref(ref) / "_manifest.json"
            if args.dry_run:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            written += 1

    print(f"wrote {written} manifests" if not args.dry_run else "(dry run)")


if __name__ == "__main__":
    main()
