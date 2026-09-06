"""Download documents from a council's "Public Access" document store.

Newport's Idox install serves an Error page on its documents tab; the
actual documents live at documents.newport.gov.uk ("Public Access"
document module). The document list is embedded in the search page as a
``var model = {...}`` JSON blob (no SignalR needed — that hub only
reports zip-download progress), and each document downloads directly
via ``ViewDocument?id=<guid>`` (plain HTTP, no session; verified
2026-08-06 on Newport/26/0191, 52/52).

Doncaster runs the same module (2026-09-06, Luke's finding): its Idox
documents tab refuses with an HTTP 200, and the register's *External
Documents* tab links to `necdm.doncaster.gov.uk` with `FileSystemId=DP`
— the same search page, the same page model, the same ViewDocument
URL. `STORES` names each council's host and file system; the
application reference's council prefix picks the store.

Bytes land in the standard idox layout for the application, recorded in
``documents`` with the ViewDocument URL as provenance, and a manifest is
written. Idempotent: URL-known documents with bytes on disk are skipped.
Run from here, the outcome is recorded through `classify_outcome` under
`<council>_docstore`; `relist_refetch.py` records its own.

Usage:
    .venv/bin/python scripts/fetch_newport_docstore.py --ref Newport/26/0191
    .venv/bin/python scripts/fetch_newport_docstore.py --all-missing --council Doncaster --dry-run
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
from dcp.acquisition_outcome import SETTLED, classify_outcome, record  # noqa: E402
from dcp.sources import idox  # noqa: E402

# council prefix -> (store host, FileSystemId). The prefix is the first
# segment of the application reference, which is how every other route
# in this repository names a council.
STORES = {
    "Newport": ("https://documents.newport.gov.uk", "PL"),
    "Doncaster": ("https://necdm.doncaster.gov.uk", "DP"),
}

STORE = STORES["Newport"][0]
VIEW_URL = f"{STORE}/PublicAccess_Live/Document/ViewDocument"
SEARCH_URL = f"{STORE}/PublicAccess_LIVE/SearchResult/RunThirdPartySearch"


def council_of(ref: str) -> str:
    """`Newport/26/0191` -> `Newport`; unknown councils are a ValueError,
    so a reference from a council whose store is not in `STORES` cannot
    be fetched from Newport's by accident."""
    council = ref.split("/", 1)[0]
    if council not in STORES:
        raise ValueError(f"no Public Access document store recorded for {council!r}")
    return council


def search_url(folder_ref: str, council: str = "Newport") -> str:
    base, fs = STORES[council]
    return (f"{base}/PublicAccess_LIVE/SearchResult/RunThirdPartySearch"
            f"?FileSystemId={fs}&FOLDER1_REF={folder_ref}")


def view_url(guid: str, council: str = "Newport") -> str:
    base, _fs = STORES[council]
    return f"{base}/PublicAccess_Live/Document/ViewDocument?id={guid}"


def parse_doc_list(text: str) -> list[tuple[str, str]] | None:
    """[(guid, doc_type)] from the embedded page model.

    **None means the page did not parse**, and an empty list means the
    store holds nothing for this folder. Collapsing the two is how "we
    could not read the page" becomes "the applicant published nothing":
    the docstore answers a session timeout or a refusal with a 200 and no
    model, which is indistinguishable from an empty result once both have
    become `[]`. `fetch_doc_list` keeps the old shape for the download
    path, which treats either as nothing to fetch; the listing audit
    needs them apart, because only one of them is a measurement.
    """
    marker = "var model ="
    i = text.find(marker)
    if i < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(text[i + len(marker):].lstrip())
    except ValueError:
        return None
    for v in obj.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "Guid" in v[0]:
            return [(row["Guid"], row.get("Doc_Type") or None) for row in v]
    # A model with no document array is a genuinely empty folder.
    return []


def fetch_doc_list(client: idox.IdoxClient, folder_ref: str,
                   council: str = "Newport") -> list[tuple[str, str]]:
    """Return [(guid, doc_type)] from the embedded page model."""
    r = client.get(search_url(folder_ref, council))
    return parse_doc_list(r.text) or []


def fetch_one(conn, client: idox.IdoxClient, *, ref: str,
              dry_run: bool = False) -> dict:
    council = council_of(ref)
    folder_ref = ref.split("/", 1)[1]
    docs = fetch_doc_list(client, folder_ref, council)
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
    if dry_run:
        for guid, kind in docs:
            print(f"  would fetch {kind or '?':<32} {guid}")
        return summary
    for guid, kind in docs:
        url = view_url(guid, council)
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
        # See `repo.EmptyDocumentBody`: no bytes is a failed fetch.
        if not body:
            print(f"  ZERO-BYTE {guid}: nothing stored, counted as a failure")
            summary["errors"] += 1
            summary["zero_byte"] = summary.get("zero_byte", 0) + 1
            continue
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
                   help="Every application of --council that is a live member "
                        "of a live site and holds zero documents.")
    ap.add_argument("--council", default="Newport", choices=sorted(STORES))
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="List what the store holds; fetch and record nothing.")
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
                    WHERE application_ref LIKE %s
                    AND EXISTS (SELECT 1 FROM site_members m
                                JOIN sites s ON s.id = m.site_id
                                WHERE m.application_id = a.id
                                  AND m.retired_at IS NULL AND s.retired_at IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM documents d
                                    WHERE d.application_id = a.id)
                    ORDER BY application_ref""", (args.council + "/%",))
                refs = [r[0] for r in cur.fetchall()]
        print(f"{len(refs)} {args.council} application(s) to fetch from the store")
        with idox.IdoxClient(delay_seconds=args.delay) as client:
            for ref in refs:
                s = fetch_one(conn, client, ref=ref, dry_run=args.dry_run)
                print(f"  {ref}: {s}")
                if args.dry_run:
                    continue
                # The verdict through the shared rule, under this route's
                # own name, so the fold shows the store was read rather
                # than attributing the check to the Idox tab that refused.
                # `no_documents_in_store` is deliberately not settled-
                # eligible (see acquisition_outcome): the download path
                # still folds "did not parse" into "empty".
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM applications WHERE application_ref=%s", (ref,))
                    app_id = cur.fetchone()[0]
                outcome, detail = classify_outcome(s)
                record(conn, app_id, outcome, f"{council_of(ref).lower()}_docstore",
                       detail, found=s.get("downloaded") or 0)
                conn.commit()


if __name__ == "__main__":
    main()
