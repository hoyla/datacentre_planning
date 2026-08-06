"""Download Newport documents from the council's external document store.

Newport's Idox install serves an Error page on its documents tab; the
actual documents live at documents.newport.gov.uk ("Public Access"
document module). The document list is embedded in the search page as a
``var model = {...}`` JSON blob (no SignalR needed — that hub only
reports zip-download progress), and each document downloads directly
via ``ViewDocument?id=<guid>`` (plain HTTP, no session; verified
2026-08-06 on Newport/26/0191, 52/52).

Bytes land in the standard idox layout for the application, recorded in
``documents`` with the ViewDocument URL as provenance, and a manifest is
written. Idempotent: URL-known documents with bytes on disk are skipped.

Usage:
    .venv/bin/python scripts/fetch_newport_docstore.py --ref Newport/26/0191
    .venv/bin/python scripts/fetch_newport_docstore.py --all-missing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox  # noqa: E402

STORE = "https://documents.newport.gov.uk"
VIEW_URL = f"{STORE}/PublicAccess_Live/Document/ViewDocument"
SEARCH_URL = f"{STORE}/PublicAccess_LIVE/SearchResult/RunThirdPartySearch"


def fetch_doc_list(client: idox.IdoxClient, folder_ref: str) -> list[tuple[str, str]]:
    """Return [(guid, doc_type)] from the embedded page model."""
    r = client.get(f"{SEARCH_URL}?FileSystemId=PL&FOLDER1_REF={folder_ref}")
    marker = "var model ="
    i = r.text.find(marker)
    if i < 0:
        return []
    obj, _end = json.JSONDecoder().raw_decode(r.text[i + len(marker):].lstrip())
    rows = None
    for v in obj.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "Guid" in v[0]:
            rows = v
            break
    if rows is None:
        return []
    return [(row["Guid"], row.get("Doc_Type") or None) for row in rows]


def fetch_one(conn, client: idox.IdoxClient, *, ref: str) -> dict:
    folder_ref = ref.split("/", 1)[1]
    docs = fetch_doc_list(client, folder_ref)
    data_dir = Path("data")
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM applications WHERE application_ref=%s", (ref,))
        app_id = cur.fetchone()[0]
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id=%s",
                    (app_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}
    summary = {"links_found": len(docs), "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    if not docs:
        summary["error_class"] = "no_documents_in_store"
        return summary
    for guid, kind in docs:
        url = f"{VIEW_URL}?id={guid}"
        bp = prior.get(url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            r = c_get(client, url)
        except Exception as e:
            print(f"  FAIL {guid}: {e}")
            summary["errors"] += 1
            continue
        body = r.content
        sha = hashlib.sha256(body).hexdigest()
        ext = "pdf" if "pdf" in (r.headers.get("content-type") or "") else "bin"
        target = idox._bytes_path(data_dir, ref, sha, ext)
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(conn, application_id=app_id, url=url,
                             kind=kind, content_sha256=sha,
                             bytes_path=str(target))
        summary["downloaded"] += 1
        conn.commit()
    idox._write_manifest(conn, application_id=app_id, application_ref=ref,
                         app_dir=idox._app_dir(data_dir, ref), summary=summary)
    conn.commit()
    return summary


def c_get(client, url):
    return client.get(url)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ref")
    g.add_argument("--all-missing", action="store_true",
                   help="Every Newport application with zero documents.")
    ap.add_argument("--delay", type=float, default=5.0)
    args = ap.parse_args()

    with db.connect() as conn:
        repo.ensure_source(conn, name="idox", kind="council",
                           base_url="(per-council Idox host)")
        if args.ref:
            refs = [args.ref]
        else:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT application_ref FROM applications a
                    WHERE application_ref LIKE 'Newport/%%'
                    AND NOT EXISTS (SELECT 1 FROM documents d
                                    WHERE d.application_id = a.id)
                    ORDER BY application_ref""")
                refs = [r[0] for r in cur.fetchall()]
        print(f"{len(refs)} Newport application(s) to fetch from the store")
        with idox.IdoxClient(delay_seconds=args.delay) as client:
            for ref in refs:
                s = fetch_one(conn, client, ref=ref)
                print(f"  {ref}: {s}")


if __name__ == "__main__":
    main()
