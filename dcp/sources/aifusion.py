"""aifusion document adapter (Central Bedfordshire).

Central Bedfordshire's planning register is Acolnet, and Acolnet holds no
documents: the detail page links out to a separate viewer at
`cbc.aifusion.io/planning/publicViewer.html?caseID=CB/12/03613/OUT`, which
is a JavaScript shell. Reading its `publicViewer.js` gives the two things
that are not guessable from the page:

    base_url = window.location.protocol + '//api.' + window.location.host + '/planning'
    const caseIdTransformed = CaseID.replaceAll("/", "-")

— an `api.` host prefix, and hyphens where the case reference has slashes.
Get either wrong and the endpoint answers `200 OK` with the three bytes
"OK", which looks like a working request returning nothing. With both
right it returns a clean JSON document index.

The documents themselves live in the council's SharePoint tenant, and each
listed file arrives with two URLs that must not be confused:

- `url` — the stable SharePoint path. This is the provenance record and
  the dedup key.
- `downloadUrl` — the same file with a `tempauth=` token attached. It
  serves the bytes with no session, but the token is minted per listing
  and expires. Storing it would make every re-run look like a corpus of
  brand-new documents, breaking the idempotency contract the whole
  pipeline rests on.

So: list, then fetch each file promptly via `downloadUrl`, and record
`url`. A 403 mid-run means the token aged out, and the fix is to re-list
rather than to retry the dead URL.

Two smaller traps, both found by reading real responses rather than the
JS: the top-level `documentCount` is not the document count (it reported
2 for a case whose arrays held 6 — trust the arrays), and the per-group
`type` is sometimes an empty string.

Verified against 12 randomly-sampled Central Bedfordshire references:
12 hits, 0 misses, 442 documents. Only the Central Bedfordshire
deployment has been confirmed; `DEPLOYMENTS` is where another council
running the same product would be added, once someone has actually
checked it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote, urlparse

from dcp import repo
from dcp.sources import idox as _idox

log = logging.getLogger(__name__)

SOURCE_NAME = "aifusion"
USER_AGENT = _idox.USER_AGENT

# Register host -> aifusion API base. The council's own Acolnet host is
# the key because that is what the stored application URL contains; the
# viewer host is an implementation detail of the council's setup.
DEPLOYMENTS = {
    "plantech.centralbedfordshire.gov.uk": "https://api.cbc.aifusion.io/planning",
}

# Refs are stored council-prefixed ("CentralBedfordshire/CB/26/01149/DOC"),
# and the case reference is everything after that first segment. But the
# case reference opens with a letter code of its own ("CB/26/..."), so a
# rule that strips any leading alphabetic segment eats the "CB" from an
# unprefixed ref. Council names are spelled out and case codes are not, so
# strip only a digit-free segment longer than four characters.
_REF_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z\s]{4,}/")

_EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,5})$")


def _is_aifusion_url(url: str | None) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in DEPLOYMENTS


def api_base_for(url: str) -> str | None:
    return DEPLOYMENTS.get((urlparse(url).hostname or "").lower())


def case_id_for(application_ref: str) -> str:
    """`CentralBedfordshire/CB/26/01149/DOC` -> `CB-26-01149-DOC`.

    Mirrors publicViewer.js, which hyphenates both slash directions.
    """
    case = _REF_PREFIX_RE.sub("", application_ref.strip(), count=1)
    return case.replace("/", "-").replace("\\", "-")


def _flatten(payload: dict) -> list[dict]:
    """Documents from the grouped response, carrying their group type.

    `documentCount` is ignored deliberately — see the module docstring.
    """
    out: list[dict] = []
    for group in payload.get("documentsByType") or []:
        kind = (group.get("type") or "").strip() or None
        for doc in group.get("documents") or []:
            url = doc.get("url")
            download = doc.get("downloadUrl") or url
            if not url or not download:
                continue
            out.append({
                "url": url,
                "download_url": download,
                "filename": doc.get("filename") or "",
                "kind": kind,
                "item_id": doc.get("id"),
            })
    return out


def list_documents(client: _idox.IdoxClient, *, api_base: str,
                   case_id: str) -> list[dict] | None:
    """Document index for a case, or None if the register has no such case.

    None and `[]` are different answers: None means the endpoint did not
    recognise the reference (the bare "OK" body), `[]` means a real case
    holding no public documents.
    """
    url = f"{api_base}/docs?caseId={quote(case_id)}"
    r = client.get(url)
    body = r.text.strip()
    if not body.startswith("{"):
        log.info("aifusion: no case for %s (body %r)", case_id, body[:40])
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        log.warning("aifusion: unparseable index for %s", case_id)
        return None
    return _flatten(payload)


def _extension(filename: str, content_type: str) -> str:
    """Prefer the filename the register gives us; it is reliable here."""
    m = _EXT_RE.search(filename or "")
    if m:
        return m.group(1).lower()
    ct = (content_type or "").lower()
    return ("pdf" if "pdf" in ct else
            "rtf" if "rtf" in ct else
            "doc" if "msword" in ct else
            "png" if "png" in ct else
            "jpg" if "jpeg" in ct or "jpg" in ct else "bin")


def fetch_documents_for_application(
    conn,
    *,
    client: _idox.IdoxClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
    doc_client: _idox.IdoxClient | None = None,
) -> dict:
    """List a case's documents and download the ones we do not hold.

    `doc_client` fetches the bytes. It is a separate client because the
    two hosts are different infrastructure: the index comes from the
    council's API and deserves council spacing, while the files come from
    Microsoft's SharePoint. Passing one client for both works and is just
    slower.
    """
    summary = {"ref": application_ref, "links_found": 0, "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    api_base = api_base_for(application_url)
    if not api_base:
        summary["error_class"] = "not_aifusion"
        return summary
    docs = list_documents(client, api_base=api_base,
                          case_id=case_id_for(application_ref))
    if docs is None:
        summary["error_class"] = "case_not_found"
        return summary
    summary["links_found"] = len(docs)
    if not docs:
        summary["error_class"] = "no_documents"
        return summary

    fetcher = doc_client or client
    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id = %s",
                    (application_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}

    app_dir = data_dir / "raw" / "documents" / _idox._sanitised_ref(application_ref)
    relisted = False
    for doc in docs:
        bp = prior.get(doc["url"])
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            r = fetcher.get(doc["download_url"])
        except Exception as exc:
            # An expired tempauth token presents as 403/401. The listing is
            # cheap and mints fresh tokens, so re-list once and carry on;
            # retrying the dead URL would fail every time.
            if not relisted and _is_auth_failure(exc):
                relisted = True
                fresh = list_documents(client, api_base=api_base,
                                       case_id=case_id_for(application_ref)) or []
                by_url = {d["url"]: d["download_url"] for d in fresh}
                if doc["url"] in by_url:
                    doc["download_url"] = by_url[doc["url"]]
                    try:
                        r = fetcher.get(doc["download_url"])
                    except Exception as exc2:
                        log.warning("aifusion download failed after relist (%s): %s",
                                    application_ref, exc2)
                        summary["errors"] += 1
                        continue
                else:
                    summary["errors"] += 1
                    continue
            else:
                log.warning("aifusion download failed (%s, %s): %s",
                            application_ref, doc["filename"][:40], exc)
                summary["errors"] += 1
                continue
        body = r.content
        # See `repo.EmptyDocumentBody`: no bytes is a failed fetch.
        if not body:
            log.warning("zero-byte body (%s, %s) — recorded as a failed "
                        "fetch, nothing stored", application_ref, doc["url"])
            summary["errors"] += 1
            summary["zero_byte"] = summary.get("zero_byte", 0) + 1
            continue
        sha = hashlib.sha256(body).hexdigest()
        ext = _extension(doc["filename"], r.headers.get("content-type", ""))
        target = app_dir / f"{sha[:16]}.{ext}"
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn, application_id=application_id, url=doc["url"],
            kind=doc["kind"], content_sha256=sha,
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


def _is_auth_failure(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    return status in (401, 403)
