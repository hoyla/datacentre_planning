"""Arcus planning-register adapter.

Arcus registers (`*.planning-register.co.uk` and council-hosted
equivalents such as `planning.bcpcouncil.gov.uk`) serve a
`/Planning/Display/<ref>` page listing documents as ordinary links:

    /Document/Download?module=PLA&recordNumber=<n>&planId=<n>
        &imageId=<n>&isPlan=False&fileName=<name>.pdf

Each host gates access behind a disclaimer page (copyright, Ordnance
Survey licensing, data protection, and an indemnity clause) until
`/Disclaimer/Accept` sets an `AcceptedDisclaimer` cookie. Luke reviewed
West Northamptonshire's terms on 2026-08-06 and accepted them for the
project — the adapter performs that acceptance per host at session
start. The terms restrict *redistribution* of drawings and Ordnance
Survey mapping; they do not restrict reading documents or extracting
facts with provenance, which is what this corpus does.

Bytes are stored in the single document store,
`data/raw/documents/<application_ref>/<sha256[:16]>.<ext>`, with a
`_manifest.json` per application. The `fileName`
parameter carries the council's own filename, which is recorded as the
document kind where the table's Document Type column is unavailable.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.parse
from pathlib import Path

from selectolax.parser import HTMLParser

from dcp import repo
from dcp.sources import idox as _idox

log = logging.getLogger(__name__)

SOURCE_NAME = "arcus"
USER_AGENT = _idox.USER_AGENT


def _is_arcus_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return "planning-register.co.uk" in u or "/planning/display/" in u


class ArcusClient:
    """Polite client that accepts each host's disclaimer once per session."""

    def __init__(self, *, delay_seconds: float = 5.0, max_retries: int = 2,
                 user_agent: str = USER_AGENT):
        self._http = _idox.IdoxClient(
            delay_seconds=delay_seconds, max_retries=max_retries,
            user_agent=user_agent)
        self._accepted: set[str] = set()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ArcusClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def accept_disclaimer(self, url: str) -> None:
        """Accept the host's disclaimer, setting its cookie (once per host).

        Two variants are in the wild:

        - **older**: a GET to `/Disclaimer/Accept?returnUrl=<relative>`.
          The returnUrl must carry the *whole* relative URL including its
          query string — hosts on the newer URL pattern identify the
          application as `?applicationNumber=<ref>` rather than as a path
          segment, so a path-only returnUrl bounces back to an
          application-less page and the documents never appear.
        - **newer**: a form POST to `/Disclaimer/AcceptDisclaimer` with
          `returnURL` and an ASP.NET `__RequestVerificationToken` read
          from the disclaimer page.

        Luke reviewed the terms on 2026-08-06 and accepted them for the
        project; this method performs that acceptance per host.
        """
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        if host in self._accepted:
            return
        self._accepted.add(host)
        relative = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        origin = f"{parsed.scheme}://{host}"

        # Older variant first — a no-op on hosts that don't implement it.
        self._http.client.get(
            f"{origin}/Disclaimer/Accept?"
            f"returnUrl={urllib.parse.quote(relative, safe='')}",
            follow_redirects=True)

        resp = self._http.client.get(url)
        if "Disclaimer" not in resp.text or "AcceptDisclaimer" not in resp.text:
            return

        tree = HTMLParser(resp.text)
        form = next((f for f in tree.css("form")
                     if "AcceptDisclaimer" in (f.attributes.get("action") or "")), None)
        if form is None:
            return
        payload: dict[str, str] = {}
        for inp in form.css("input"):
            name = inp.attributes.get("name")
            if name:
                payload[name] = inp.attributes.get("value") or ""
        payload.setdefault("returnURL", relative)
        action = urllib.parse.urljoin(origin, form.attributes.get("action") or "")
        self._http.client.post(action, data=payload, follow_redirects=True)

    def get(self, url: str):
        self.accept_disclaimer(url)
        return self._http.get(url)


def _clean_id(value: str | None) -> str:
    """`"3312189.0000"` → `"3312189"` (the newer register renders its
    numeric ids as decimals in data attributes)."""
    v = (value or "").strip()
    return v.split(".")[0] if "." in v else v


def parse_documents_page(html: str, base_url: str) -> list[dict]:
    """Extract document links from an Arcus application page.

    Two register generations are handled:

    - **anchor style** (West Northants, BCP, Glamorgan …): each row
      carries an `<a href="/Document/Download?module=…&fileName=…">`.
    - **data-attribute style** (Vale of White Horse, South Oxfordshire …):
      the row holds `data-module` / `data-recordNumber` / `data-planID` /
      `data-imageID` / `data-fileName` and a JavaScript "View" button,
      so the same `/Document/Download` URL is constructed from them.
      Numeric ids arrive as decimals ("163.0000") and are trimmed.

    Returns dicts with `href`, `filename` and `kind`.
    """
    tree = HTMLParser(html)
    out: list[dict] = []
    seen: set[str] = set()

    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if "Document/Download" not in href:
            continue
        abs_href = urllib.parse.urljoin(base_url, href)
        if abs_href in seen:
            continue
        seen.add(abs_href)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(abs_href).query)
        filename = (qs.get("fileName") or [""])[0]
        label = a.attributes.get("aria-label") or a.text(strip=True) or ""
        kind = label.replace("Link(Download)", "").strip() or None
        out.append({"href": abs_href, "filename": filename,
                    "kind": kind or filename or None})

    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(base_url))
    for tr in tree.css("tr.grid-dataRow"):
        at = tr.attributes
        plan_id, image_id = _clean_id(at.get("data-planid")), _clean_id(at.get("data-imageid"))
        record = _clean_id(at.get("data-recordnumber"))
        raw_name = at.get("data-filename") or ""
        if not (plan_id and image_id and record):
            continue
        # The stored path is a council file-server path; only its leaf is
        # meaningful to us (and to the download endpoint).
        filename = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
        qs = urllib.parse.urlencode({
            "module": at.get("data-module") or "PLA",
            "recordNumber": record, "planId": plan_id, "imageId": image_id,
            "isPlan": at.get("data-isplan") or "False", "fileName": filename,
        })
        abs_href = f"{origin}/Document/Download?{qs}"
        if abs_href in seen:
            continue
        seen.add(abs_href)
        cells = [c.text(strip=True) for c in tr.css("td")]
        kind = next((c for c in cells[1:3] if c and c != "-"), None)
        out.append({"href": abs_href, "filename": filename,
                    "kind": kind or filename or None})
    return out


def fetch_documents_for_application(
    conn,
    *,
    client: ArcusClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
) -> dict:
    """Fetch every document for one Arcus application. Summary shape
    matches the Idox adapter so campaign runners can treat them alike."""
    summary = {"ref": application_ref, "links_found": 0, "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    if not _is_arcus_url(application_url):
        summary["error_class"] = "not_arcus_url"
        return summary

    try:
        resp = client.get(application_url)
    except Exception as exc:
        summary["error_class"] = type(exc).__name__
        summary["errors"] += 1
        log.warning("arcus page fetch failed (%s): %s", application_ref, exc)
        return summary

    repo.record_snapshot(conn, source_id=source_id, key=application_url,
                         raw_bytes=resp.content)

    links = parse_documents_page(resp.text, base_url=application_url)
    summary["links_found"] = len(links)
    if not links:
        summary["error_class"] = "no_documents_or_unparseable"
        return summary

    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id = %s",
                    (application_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}

    app_dir = data_dir / "raw" / "documents" / _idox._sanitised_ref(application_ref)
    for link in links:
        bp = prior.get(link["href"])
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            blob = client.get(link["href"])
        except Exception as exc:
            log.warning("arcus doc download failed (%s, %s): %s",
                        application_ref, link["filename"][:40], exc)
            summary["errors"] += 1
            continue
        body = blob.content
        # See `repo.EmptyDocumentBody`: no bytes is a failed fetch.
        if not body:
            log.warning("zero-byte body (%s, %s) — recorded as a failed "
                        "fetch, nothing stored", application_ref, link["href"])
            summary["errors"] += 1
            summary["zero_byte"] = summary.get("zero_byte", 0) + 1
            continue
        sha = hashlib.sha256(body).hexdigest()
        ext = "pdf" if "pdf" in (blob.headers.get("content-type") or "") else \
            (Path(link["filename"]).suffix.lstrip(".").lower() or "bin")
        target = app_dir / f"{sha[:16]}.{ext}"
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn, application_id=application_id, url=link["href"],
            kind=link["kind"], content_sha256=sha,
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
