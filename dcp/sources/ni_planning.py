"""Northern Ireland's planning register, via the API its own pages use.

The register at planningregister.planningsystemni.gov.uk is a Next.js
application: the page carries only an id, and every fact on it comes
from XHR calls to a TerraQuest backend. ROADMAP had this down as
"finding that endpoint needs a session with the network tab open" —
done on 2026-08-27, and the answer is better than the premise: the
backend is a clean, anonymous REST API, and no browser is needed at
all.

Three calls per application, all GET, all authenticated by nothing but
a tenant header whose value ships to every visitor in the page's own
``__ENV.js`` (``NEXT_APP_PP_TENANT_ID``):

1. ``/api/v1/application/{id}`` — the application's full metadata,
   including ``supportingDocuments``: one entry per document with
   ``documentId``, a guid filename, description, type and date. The
   ``{id}`` is the numeric tail of the register URL this project
   already stores (``/application/179744``), and ids minted by the
   previous register still resolve on this one.
2. ``/api/v1/application/{appId}/{docId}`` — answers JSON carrying
   ``documentUri``: a time-limited Azure blob SAS URL (about thirty
   minutes), which is why the URI is fetched per document at download
   time and never stored — the stored document URL is the *stable* API
   route above, which any future fetch can redeem for a fresh SAS.
3. The SAS URL itself — the bytes, from
   ``documentstore.tqinfra.co.uk``. Every document is a zip wrapping a
   single file (observed: a guid-named PDF); the adapter stores the
   inner file, because a zip in the canonical store is a document the
   extractors cannot read. A zip with more than one member is stored
   as-is and logged — none has been seen, and silently taking the
   first member of many would drop material.

Without the tenant header the API answers ``200`` with a JSON ``null``
body — which reads exactly like an application that does not exist,
and is worth knowing before concluding one doesn't.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import zipfile
from pathlib import Path

from dcp import repo
from dcp.sources import idox as _idox

log = logging.getLogger(__name__)

API_BASE = ("https://api-planningregister-planningportal"
            ".pr.tqinfra.co.uk/api/v1")

# Public by construction: served to every browser in the register's own
# __ENV.js as NEXT_APP_PP_TENANT_ID. Not a credential — the API is
# anonymous — but without it the API answers `null` to everything.
TQ_TENANT = "cfb86436-414d-4459-9545-93eec37615a2"

_HEADERS = {"Accept": "application/json", "TQ-Tenant": TQ_TENANT}

_APP_ID_RE = re.compile(r"/application/(\d+)(?:[/?#]|$)")


def _is_ni_url(url: str | None) -> bool:
    return bool(url) and "planningsystemni.gov.uk" in url.lower()


def app_id_from_url(url: str) -> int | None:
    m = _APP_ID_RE.search(url or "")
    return int(m.group(1)) if m else None


def _unwrap(body: bytes, guid_name: str) -> tuple[bytes, str]:
    """The inner file of a single-member zip, with its extension.

    Anything that is not a zip, or holds more than one member, is
    returned untouched — stored honestly as what the register served,
    and logged so a person can look.
    """
    if not body.startswith(b"PK"):
        return body, Path(guid_name).suffix.lstrip(".").lower() or "bin"
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            names = zf.namelist()
            if len(names) != 1:
                log.warning("ni_planning: %s holds %d members, stored as "
                            "zip", guid_name, len(names))
                return body, "zip"
            inner = zf.read(names[0])
            if not inner:
                return body, "zip"
            return inner, Path(names[0]).suffix.lstrip(".").lower() or "bin"
    except zipfile.BadZipFile:
        return body, Path(guid_name).suffix.lstrip(".").lower() or "bin"


def fetch_documents_for_application(
    conn,
    *,
    client: "_idox.IdoxClient",
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
) -> dict:
    """Fetch every document for one NI application. Summary shape
    matches the Idox adapter so campaign runners can treat them alike."""
    summary = {"ref": application_ref, "links_found": 0, "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    portal_id = app_id_from_url(application_url) if _is_ni_url(
        application_url) else None
    if portal_id is None:
        summary["error_class"] = "not_ni_planning_url"
        return summary

    meta_url = f"{API_BASE}/application/{portal_id}"
    try:
        resp = client.get(meta_url, headers=_HEADERS)
    except Exception as exc:
        summary["error_class"] = type(exc).__name__
        summary["errors"] += 1
        log.warning("ni_planning metadata fetch failed (%s): %s",
                    application_ref, exc)
        return summary

    # The whole listing is the metadata response; snapshot it verbatim,
    # as the documents-tab HTML is snapshotted elsewhere.
    repo.record_snapshot(conn, source_id=source_id, key=meta_url,
                         raw_bytes=resp.content)

    try:
        meta = resp.json()
    except json.JSONDecodeError:
        summary["error_class"] = "unparseable_api_response"
        summary["errors"] += 1
        return summary
    if meta is None:
        # What the API says when the id is unknown — or when the tenant
        # header is missing, which is why that distinction is in the
        # module docstring.
        summary["error_class"] = "application_not_in_register"
        return summary

    docs = meta.get("supportingDocuments") or []
    summary["links_found"] = len(docs)
    if not docs:
        summary["error_class"] = "no_documents_or_unparseable"
        return summary

    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents "
                    "WHERE application_id = %s", (application_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}

    app_dir = (data_dir / "raw" / "documents"
               / _idox._sanitised_ref(application_ref))
    for d in docs:
        doc_id = d.get("documentId")
        if not doc_id:
            summary["errors"] += 1
            continue
        stable_url = f"{API_BASE}/application/{portal_id}/{doc_id}"
        bp = prior.get(stable_url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            sas = client.get(stable_url, headers=_HEADERS).json()
            blob_url = (sas or {}).get("documentUri")
            if not blob_url:
                raise ValueError("no documentUri in response")
            # The SAS URL is a different host and needs no tenant
            # header; the client's pacing applies to it all the same.
            blob = client.get(blob_url)
        except Exception as exc:
            log.warning("ni_planning doc download failed (%s, doc %s): %s",
                        application_ref, doc_id, exc)
            summary["errors"] += 1
            continue
        body, ext = _unwrap(blob.content, d.get("name") or "")
        # See `repo.EmptyDocumentBody`: no bytes is a failed fetch.
        if not body:
            log.warning("zero-byte body (%s, doc %s) — recorded as a "
                        "failed fetch, nothing stored",
                        application_ref, doc_id)
            summary["errors"] += 1
            summary["zero_byte"] = summary.get("zero_byte", 0) + 1
            continue
        sha = hashlib.sha256(body).hexdigest()
        target = app_dir / f"{sha[:16]}.{ext}"
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn, application_id=application_id, url=stable_url,
            kind=d.get("documentType"), content_sha256=sha,
            bytes_path=(str(target.relative_to(data_dir.parent))
                        if target.is_relative_to(data_dir.parent)
                        else str(target)),
        )
        summary["downloaded"] += 1
        conn.commit()

    if summary["links_found"]:
        _idox._write_manifest(conn, application_id=application_id,
                              application_ref=application_ref,
                              app_dir=app_dir, summary=summary)
    return summary
