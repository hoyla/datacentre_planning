"""Agile Applications ("Citizen Portal") adapter.

Agile portals are Angular single-page applications: the HTML at
`planning.agileapplications.co.uk/<slug>/application-details/<id>` is an
empty shell, so there is nothing to parse. The data comes from a public
JSON API, which the adapter calls directly:

    GET https://planningapi.agileapplications.co.uk/api/application/<id>
    GET .../api/application/<id>/document          → document list
    GET .../api/application/document/<documentHash> → the bytes

Three headers identify the tenant — `x-client` (the council's code),
`x-service` ("PA" for planning) and `x-product` ("CITIZENPORTAL");
without them the API answers 401 "Client has not beeing selected"
[sic]. Client codes are resolved per council slug from the identity
service (`identity.agileapplications.co.uk/api/client/get?url=<slug>`),
so new councils need no code change.

Two things this adapter gets that Idox does not give us:

- **Structured party fields.** The application record carries
  `applicantName`, `agentName`, agent company and contact fields as
  first-class values, where PlanIt's Idox-derived metadata mostly says
  "See source". These feed the parties/affiliations analysis directly.
- **Document metadata** (description, media description, received date)
  arrives as JSON rather than table scraping.

Bytes are stored under `data/raw/agile/<application_ref>/<sha256[:16]>.<ext>`
with a `_manifest.json`, mirroring the Idox layout, and recorded in
`documents` with the API document URL as provenance.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.parse
from pathlib import Path

import httpx

from dcp import repo
from dcp.sources import idox as _idox

log = logging.getLogger(__name__)

SOURCE_NAME = "agile"
USER_AGENT = _idox.USER_AGENT

PLANNING_API = "https://planningapi.agileapplications.co.uk/api"
IDENTITY_API = "https://identity.agileapplications.co.uk/api"


def _is_agile_url(url: str | None) -> bool:
    return bool(url) and "agileapplications.co.uk" in url


def parse_portal_url(url: str) -> tuple[str, str] | None:
    """`(client_slug, application_id)` from a portal URL, or None."""
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    if len(parts) >= 3 and parts[1] == "application-details":
        return parts[0], parts[2]
    return None


class AgileClient:
    """Polite JSON-API client. Reuses the Idox client's delay/backoff
    behaviour (same politeness contract) and resolves per-council client
    codes once each."""

    def __init__(self, *, delay_seconds: float = 5.0, max_retries: int = 2,
                 user_agent: str = USER_AGENT):
        self._http = _idox.IdoxClient(
            delay_seconds=delay_seconds, max_retries=max_retries,
            user_agent=user_agent)
        self._client_codes: dict[str, str] = {}

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AgileClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def client_code(self, slug: str) -> str:
        """Council slug → API client code (`islington` → `IS`)."""
        if slug not in self._client_codes:
            r = self._http.get(f"{IDENTITY_API}/client/get?url={slug}")
            data = r.json()
            data = data[0] if isinstance(data, list) else data
            self._client_codes[slug] = data["code"]
        return self._client_codes[slug]

    def _headers(self, slug: str) -> dict[str, str]:
        return {"x-client": self.client_code(slug),
                "x-service": "PA",
                "x-product": "CITIZENPORTAL"}

    def application(self, slug: str, app_id: str) -> dict:
        r = self._http.get(f"{PLANNING_API}/application/{app_id}",
                           headers=self._headers(slug))
        data = r.json()
        return data[0] if isinstance(data, list) else data

    def documents(self, slug: str, app_id: str) -> list[dict]:
        r = self._http.get(f"{PLANNING_API}/application/{app_id}/document",
                           headers=self._headers(slug))
        data = r.json()
        return data if isinstance(data, list) else []

    def document_bytes(self, slug: str, doc_hash: str) -> httpx.Response:
        # The tenant headers are required on the download too — without
        # them the API answers 401 for every document.
        return self._http.get(f"{PLANNING_API}/application/document/{doc_hash}",
                              headers=self._headers(slug))


def document_url(doc_hash: str) -> str:
    return f"{PLANNING_API}/application/document/{doc_hash}"


def party_fields(record: dict) -> dict:
    """The party-related fields worth promoting out of the API record.
    Contact details (email, telephone) are deliberately not included."""
    keys = ("applicantName", "applicantForename", "applicantSurname",
            "agentName", "agentContactName", "agentForename", "agentSurname")
    return {k: record.get(k) for k in keys if record.get(k)}


def fetch_documents_for_application(
    conn,
    *,
    client: AgileClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
) -> dict:
    """Fetch every document for one Agile application. Same summary shape
    as the Idox adapter so campaign runners can treat them alike."""
    summary = {"ref": application_ref, "links_found": 0, "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    parsed = parse_portal_url(application_url)
    if parsed is None:
        summary["error_class"] = "not_agile_url"
        return summary
    slug, app_id = parsed

    try:
        docs = client.documents(slug, app_id)
    except httpx.HTTPStatusError as exc:
        summary["error_class"] = ("not_found" if exc.response.status_code == 404
                                  else f"http_{exc.response.status_code}")
        summary["errors"] += 1
        return summary
    except Exception as exc:
        summary["error_class"] = type(exc).__name__
        summary["errors"] += 1
        log.warning("agile document list failed (%s): %s", application_ref, exc)
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
        doc_hash = doc.get("documentHash")
        if not doc_hash:
            continue
        url = document_url(doc_hash)
        bp = prior.get(url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            r = client.document_bytes(slug, doc_hash)
        except Exception as exc:
            log.warning("agile doc download failed (%s, %s): %s",
                        application_ref, doc_hash[:16], exc)
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
        ext = "pdf" if "pdf" in (r.headers.get("content-type") or "") else "bin"
        target = app_dir / f"{sha[:16]}.{ext}"
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn, application_id=application_id, url=url,
            kind=doc.get("description") or doc.get("mediaDescription"),
            content_sha256=sha,
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
