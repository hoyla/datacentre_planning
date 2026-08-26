"""Salesforce public-register adapter (Reading, Wiltshire, Milton Keynes,
Bracknell Forest — Arcus's Salesforce Experience Cloud product).

These registers are Lightning/Aura applications: the served HTML is a
shell, and the file table renders client-side, so the *list* of
documents cannot be fetched with plain HTTP without replaying Salesforce's
Aura protocol (framework UID, session token, action descriptors — brittle
and version-bound).

The *bytes*, however, are public: each row links to

    /sfc/servlet.shepherd/version/download/<ContentVersionId>

which serves the file over ordinary HTTP with no session. So this adapter
splits the work the same way the Newport docstore one does:

1. **Listing** (browser-assisted, occasional): open the detail page with
   the Files tab selected — `?tabset-<id>=3` — and read the anchors.
   Collected lists are cached to `data/priors/salesforce_documents.json`
   keyed by application ref, so re-runs need no browser.
2. **Fetching** (plain HTTP, repeatable): download each ContentVersion,
   content-hash it, store it in the standard layout and record it with
   its Shepherd URL as provenance.

Listing entries are `{"url": ..., "description": ..., "date": ...}` as
read from the table row.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from dcp import repo
from dcp.sources import idox as _idox

log = logging.getLogger(__name__)

SOURCE_NAME = "salesforce_pr"
USER_AGENT = _idox.USER_AGENT
LIST_CACHE = Path("data/priors/salesforce_documents.json")


def _is_salesforce_pr_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return "/pr/s/detail/" in u or "/pr/s/planning-application/" in u


def load_listings() -> dict[str, list[dict]]:
    if LIST_CACHE.exists():
        return json.loads(LIST_CACHE.read_text())
    return {}


def save_listing(application_ref: str, docs: list[dict]) -> None:
    """Record a browser-harvested document list for an application."""
    data = load_listings()
    data[application_ref] = docs
    LIST_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LIST_CACHE.write_text(json.dumps(data, indent=1, ensure_ascii=False,
                                     sort_keys=True) + "\n")


def fetch_documents_for_application(
    conn,
    *,
    client: _idox.IdoxClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
    listings: dict[str, list[dict]] | None = None,
) -> dict:
    """Download the documents listed for this application. Requires a
    harvested listing (see module docstring); applications with no
    listing yet are reported as `needs_listing` rather than as empty."""
    summary = {"ref": application_ref, "links_found": 0, "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    listings = load_listings() if listings is None else listings
    docs = listings.get(application_ref)
    if docs is None:
        summary["error_class"] = "needs_listing"
        return summary
    summary["links_found"] = len(docs)
    if not docs:
        summary["error_class"] = "no_documents"
        return summary

    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id = %s",
                    (application_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}

    app_dir = data_dir / "raw" / "documents" / _idox._sanitised_ref(application_ref)
    for doc in docs:
        url = doc["url"]
        bp = prior.get(url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            r = client.get(url)
        except Exception as exc:
            log.warning("salesforce doc download failed (%s, %s): %s",
                        application_ref, url[-18:], exc)
            summary["errors"] += 1
            continue
        body = r.content
        # See `repo.EmptyDocumentBody`: no bytes is a failed fetch.
        if not body:
            log.warning("zero-byte body (%s, %s) — recorded as a failed "
                        "fetch, nothing stored", application_ref, url)
            summary["errors"] += 1
            summary["zero_byte"] = summary.get("zero_byte", 0) + 1
            continue
        sha = hashlib.sha256(body).hexdigest()
        ct = (r.headers.get("content-type") or "").lower()
        ext = ("pdf" if "pdf" in ct else
               "rtf" if "rtf" in ct else
               "doc" if "msword" in ct else "bin")
        target = app_dir / f"{sha[:16]}.{ext}"
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn, application_id=application_id, url=url,
            kind=doc.get("description"), content_sha256=sha,
            bytes_path=(str(target.relative_to(data_dir.parent))
                        if target.is_relative_to(data_dir.parent) else str(target)),
        )
        summary["downloaded"] += 1
        conn.commit()

    if summary["links_found"]:
        _idox._write_manifest(conn, application_id=application_id,
                              application_ref=application_ref,
                              app_dir=app_dir, summary=summary)
    return summary
