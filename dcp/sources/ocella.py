"""Ocella Public Access adapter — fetches document bundles for triage matches.

Ocella is a planning portal product deployed by a handful of UK councils,
prominently including Hillingdon (a major DC corridor) and Havering. The
canonical URL shape is
`<host>/OcellaWeb/planningDetails?from=planningSearch&reference=<ref>` —
already captured in `applications.url` by the PlanIt index pass.

The summary page itself carries no direct document links. Instead, it
contains a POST form `<form method="post" action="showDocuments?reference=
<ref>&module=pl">` whose submission renders the documents list. The
documents list HTML contains anchors like:

    <a href ="viewDocument?file=dv_pl_files%5C<ref-with-underscores>%5C<filename>&module=pl"
       target="showdocument">KIND</a>

where `%5C` is the URL-encoded backslash separating internal storage
paths. The anchor's text is the document `kind` (e.g. "APPLICATION FORM",
"SITE LAYOUT - PROPOSED", "DELEGATED REPORT"). Note the **stray space**
in `href =` — Ocella's template emits it consistently; the parser tolerates
both forms.

Each `viewDocument` link returns the PDF (or occasionally .docx) directly
with `Content-Type: application/pdf`. No iframes, no inline viewers, no
auth, no JS required.

Bytes are stored under `data/raw/ocella/<application_ref>/<sha256[:16]>.<ext>`,
recorded in `documents` table with `(application_id, content_sha256)` UNIQUE
so re-runs are no-ops. Mirrors the Idox storage shape exactly.

Tested deployments: Hillingdon (`planning.hillingdon.gov.uk`),
Havering (`development.havering.gov.uk`). The PathOuter assumes the
showDocuments endpoint is always at `<base>/OcellaWeb/showDocuments` —
adjust if a council mounts it elsewhere.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import re
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

from dcp import db, repo

log = logging.getLogger(__name__)

MANIFEST_FILENAME = "_manifest.json"
MANIFEST_VERSION = 1


def _resolve_ssl_context():
    """OS native trust store — same shape as the Idox adapter so the same
    AIA-chasing fallback is in place when a council eventually ships a
    broken chain on an Ocella host. Memoised at module-import-time isn't
    needed; httpx caches contexts internally."""
    import ssl
    import truststore
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


SOURCE_NAME = "ocella"
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"


@dataclass
class DocumentLink:
    """One row from an Ocella documents listing."""
    href: str            # absolute URL
    filename: str        # the file=... param value, URL-decoded
    kind: str | None     # the anchor text (uppercased category label)


def _is_ocella_url(url: str) -> bool:
    """Heuristic: an Ocella URL contains `/OcellaWeb/planningDetails`."""
    if not url:
        return False
    return "/OcellaWeb/planningDetails" in url


def _parse_application_url(application_url: str) -> tuple[str, str]:
    """Decompose an Ocella planningDetails URL into `(base, reference)`.

    `base` is the `<scheme>://<host>/OcellaWeb/` prefix that every
    subsequent endpoint (showDocuments, viewDocument) is mounted under.
    `reference` is the URL-decoded `reference` query parameter — Ocella
    sends it back as a plain path-style string (e.g. `75111/APP/2025/2237`).
    """
    parsed = urllib.parse.urlparse(application_url)
    # `/OcellaWeb/planningDetails` → keep everything up to and including
    # `/OcellaWeb/`, drop the rest.
    idx = parsed.path.find("/OcellaWeb/")
    if idx < 0:
        raise ValueError(f"not an Ocella URL: {application_url}")
    base_path = parsed.path[:idx + len("/OcellaWeb/")]
    base = f"{parsed.scheme}://{parsed.netloc}{base_path}"
    qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    reference = qs.get("reference") or ""
    if not reference:
        raise ValueError(f"missing reference= param: {application_url}")
    return base, reference


def _show_documents_url(base: str, reference: str) -> str:
    """Build the showDocuments POST URL for a given Ocella base + reference."""
    # `reference` is sent as a query param. Ocella expects it as a path-style
    # string (slashes preserved); `quote(safe="/")` matches what the form
    # submission sends in the browser.
    qs = urllib.parse.urlencode(
        {"reference": reference, "module": "pl"}, safe="/",
    )
    return f"{base}showDocuments?{qs}"


# Ocella's documents listing emits anchors as `<a href ="viewDocument?...">`
# with a literal space before `=`. Tolerate both `href=` and `href =` so the
# parser doesn't break if a future template change removes the quirk.
_ANCHOR_RE = re.compile(
    r'<a\s+href\s*=\s*"([^"]*viewDocument[^"]+)"\s*'
    r'(?:target="[^"]*"\s*)?>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def parse_documents_page(html: str, base_url: str) -> list[DocumentLink]:
    """Extract document links from an Ocella documents-list HTML page.

    Unlike Idox, Ocella renders the listing as multiple per-category tables
    rather than one master table — but every anchor we care about has the
    form `<a href="viewDocument?file=...&module=pl">KIND</a>`. We grep them
    out directly and decode the `file=` param to recover the displayed
    filename. The anchor's text gives the document kind / type label.
    """
    out: list[DocumentLink] = []
    for m in _ANCHOR_RE.finditer(html):
        href, label = m.group(1), m.group(2).strip()
        # `file=` value is the only thing we need for filename display.
        parsed = urllib.parse.urlparse(href)
        qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        file_param = qs.get("file") or ""
        # Internal Ocella paths look like `dv_pl_files\<ref>\<filename>`.
        # The displayed filename is the last segment (after the final `\`).
        filename = file_param.replace("\\", "/").rsplit("/", 1)[-1] or file_param
        abs_href = urllib.parse.urljoin(base_url, href)
        # Strip any embedded HTML tags from the anchor body (Ocella
        # occasionally wraps the label in spans).
        label_text = re.sub(r"<[^>]+>", "", label).strip()
        out.append(DocumentLink(
            href=abs_href,
            filename=filename,
            kind=label_text or None,
        ))
    return out


class OcellaClient:
    """Polite Ocella HTTP client. Same shape as IdoxClient — inter-request
    delay, exponential backoff on 429s/5xx, identifying User-Agent. Ocella
    deployments observed so far have served clean TLS chains; we still
    default to the truststore-backed SSL context for safety if a council
    eventually ships a broken chain (matching the Idox safeguard)."""

    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        delay_seconds: float = 5.0,
        backoff_seconds: float = 60.0,
        max_retries: int = 4,
        verify: str | bool | None = None,
    ):
        self.delay = delay_seconds
        self.backoff = backoff_seconds
        self.max_retries = max_retries
        resolved_verify = _resolve_ssl_context() if verify is None else verify
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=90.0,
            follow_redirects=True,
            verify=resolved_verify,
        )
        self._next_request_at = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "OcellaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next_request_at:
            time.sleep(self._next_request_at - now)

    def get(self, url: str) -> httpx.Response:
        for attempt in range(self.max_retries):
            self._wait()
            r = self.client.get(url)
            self._next_request_at = time.monotonic() + self.delay
            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = self.backoff * (2 ** attempt)
                log.warning(
                    "%d from %s (attempt %d/%d); backing off %.0fs",
                    r.status_code, url, attempt + 1, self.max_retries, wait,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"persistent {r.status_code}s after {self.max_retries} retries: {url}")

    def post(self, url: str, data: dict | None = None) -> httpx.Response:
        """POST equivalent of `get`. Ocella's showDocuments expects a POST
        with the `ViewDocuments` button name in the form; an empty form
        body also works in practice but we send the explicit name to match
        what the browser would submit."""
        body = data if data is not None else {"ViewDocuments": "View Documents"}
        for attempt in range(self.max_retries):
            self._wait()
            r = self.client.post(url, data=body)
            self._next_request_at = time.monotonic() + self.delay
            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = self.backoff * (2 ** attempt)
                log.warning(
                    "%d from %s (attempt %d/%d); backing off %.0fs",
                    r.status_code, url, attempt + 1, self.max_retries, wait,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"persistent {r.status_code}s after {self.max_retries} retries: {url}")


_SAFE_REF_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def _sanitised_ref(application_ref: str) -> str:
    """Filesystem-safe rendering of an application_ref. Slashes preserved
    so each council gets a tidy subdirectory."""
    return _SAFE_REF_RE.sub("_", application_ref)


def _app_dir(data_dir: Path, application_ref: str) -> Path:
    """`<DATA_DIR>/raw/ocella/<safe_ref>/`."""
    return data_dir / "raw" / "ocella" / _sanitised_ref(application_ref)


def _bytes_path(data_dir: Path, application_ref: str, content_sha256: str, ext: str) -> Path:
    return _app_dir(data_dir, application_ref) / f"{content_sha256[:16]}.{ext}"


def _ext_from_filename(filename: str) -> str:
    """Extension from the `file=` param's last path segment. Falls back to
    `pdf` since Ocella overwhelmingly serves PDFs."""
    m = re.search(r"\.([a-zA-Z0-9]{2,4})$", filename)
    return m.group(1).lower() if m else "pdf"


def _write_manifest(
    conn,
    *,
    application_id: int,
    application_ref: str,
    app_dir: Path,
    summary: dict,
) -> None:
    """Manifest file mirrors the Idox shape — same JSON keys, same
    completion-signal semantic, just with `ocella` as the fetcher name."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT url, kind, content_sha256, bytes_path, fetched_at
            FROM documents WHERE application_id = %s
            ORDER BY fetched_at, id
            """,
            (application_id,),
        )
        rows = cur.fetchall()

    payload = {
        "manifest_version": MANIFEST_VERSION,
        "application_ref": application_ref,
        "fetcher": f"dcp.sources.ocella v{MANIFEST_VERSION}",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "links_found": summary.get("links_found", 0),
        "downloaded": summary.get("downloaded", 0),
        "skipped_existing": summary.get("skipped_existing", 0),
        "errors": summary.get("errors", 0),
        "complete": summary.get("errors", 0) == 0,
        "documents": [
            {
                "kind": kind,
                "content_sha256": sha,
                "bytes_path": bytes_path,
                "source_url": url,
                "fetched_at": fetched_at.isoformat(timespec="seconds")
                              if fetched_at else None,
            }
            for url, kind, sha, bytes_path, fetched_at in rows
        ],
    }
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / MANIFEST_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )


def fetch_documents_for_application(
    conn,
    *,
    client: OcellaClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
) -> dict:
    """Fetch every direct-download document for one Ocella application and
    record metadata in the `documents` table. Returns a per-application
    summary dict (same keys as the Idox version, for symmetry with the CLI
    progress callback)."""
    summary = {
        "ref": application_ref,
        "links_found": 0,
        "downloaded": 0,
        "skipped_existing": 0,
        "errors": 0,
    }
    if not _is_ocella_url(application_url):
        log.info("not an Ocella URL, skipping: %s", application_url)
        summary["error_class"] = "not_ocella_url"
        return summary

    try:
        base, reference = _parse_application_url(application_url)
    except ValueError as exc:
        summary["error_class"] = "url_parse_failure"
        summary["error"] = str(exc)[:200]
        summary["errors"] += 1
        return summary

    docs_url = _show_documents_url(base, reference)
    try:
        resp = client.post(docs_url)
    except httpx.ConnectError as exc:
        msg = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "SSL" in msg:
            summary["error_class"] = "ssl_chain_failure"
        elif "nodename nor servname" in msg or "Name or service not known" in msg \
             or "getaddrinfo" in msg:
            summary["error_class"] = "dns_failure"
        else:
            summary["error_class"] = "connect_failure"
        summary["error"] = msg[:200]
        summary["errors"] += 1
        log.warning("%s: %s — %s", summary["error_class"], application_ref, msg)
        return summary
    except httpx.TimeoutException as exc:
        summary["error_class"] = "timeout"
        summary["error"] = str(exc)[:200]
        summary["errors"] += 1
        log.warning("timeout: %s — %s", application_ref, exc)
        return summary
    except Exception as exc:
        summary["error_class"] = f"{type(exc).__name__}"
        summary["error"] = str(exc)[:200]
        summary["errors"] += 1
        log.warning("documents page fetch failed (%s): %s", application_ref, exc)
        return summary

    # Snapshot the documents-list HTML for future re-parsing.
    repo.record_snapshot(
        conn, source_id=source_id, key=docs_url, raw_bytes=resp.content,
    )

    links = parse_documents_page(resp.text, base_url=docs_url)
    summary["links_found"] = len(links)
    if len(links) == 0:
        summary["error_class"] = "no_documents_or_unparseable"
    for link in links:
        try:
            blob = client.get(link.href)
        except Exception as exc:
            log.warning("doc download failed (%s, %s): %s",
                        application_ref, link.href, exc)
            summary["errors"] += 1
            continue
        body = blob.content
        sha = hashlib.sha256(body).hexdigest()
        ext = _ext_from_filename(link.filename)
        target = _bytes_path(data_dir, application_ref, sha, ext)
        if target.exists():
            summary["skipped_existing"] += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(
            conn,
            application_id=application_id,
            url=link.href,
            kind=link.kind,
            content_sha256=sha,
            bytes_path=str(target.relative_to(data_dir.parent))
                if target.is_relative_to(data_dir.parent) else str(target),
        )
        summary["downloaded"] += 1
        conn.commit()

    if summary["links_found"] > 0:
        _write_manifest(
            conn, application_id=application_id, application_ref=application_ref,
            app_dir=_app_dir(data_dir, application_ref), summary=summary,
        )
    return summary


def _worklist_apps(conn, *, model: str, top: int | None) -> list[tuple]:
    """Worklist apps with Ocella-shaped URLs, in worklist-rank order."""
    from dcp import worklist as worklist_mod
    data = worklist_mod.fetch(conn, model=model, limit=None)
    out: list[tuple] = []
    for row in data.rows:
        url = row.get("url")
        if not url or not _is_ocella_url(url):
            continue
        out.append((row["id"], row["application_ref"], url))
        if top is not None and len(out) >= top:
            break
    return out


def fetch_worklist(
    *,
    model: str = "granite4.1:30b",
    top: int | None = None,
    delay_seconds: float = 5.0,
    data_dir: Path = Path("data"),
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Walk the top-N worklist apps with Ocella-shaped URLs and fetch every
    document for each. Per-app summaries are streamed to `progress` and
    aggregated into the returned total."""
    total: dict = {
        "apps_attempted": 0,
        "apps_done": 0,
        "links_found": 0,
        "downloaded": 0,
        "skipped_existing": 0,
        "errors": 0,
        "by_error_class": {},
        "fully_successful": 0,
    }
    with db.connect() as conn:
        source_id = repo.ensure_source(
            conn, name=SOURCE_NAME, kind="council",
            base_url="(per-council Ocella host)",
        )
        apps = _worklist_apps(conn, model=model, top=top)
        with OcellaClient(delay_seconds=delay_seconds) as client:
            for app_id, application_ref, application_url in apps:
                total["apps_attempted"] += 1
                summary = fetch_documents_for_application(
                    conn, client=client, application_id=app_id,
                    application_ref=application_ref,
                    application_url=application_url,
                    source_id=source_id, data_dir=data_dir,
                )
                total["apps_done"] += 1
                total["links_found"] += summary["links_found"]
                total["downloaded"] += summary["downloaded"]
                total["skipped_existing"] += summary["skipped_existing"]
                total["errors"] += summary["errors"]
                cls = summary.get("error_class")
                if cls:
                    total["by_error_class"][cls] = total["by_error_class"].get(cls, 0) + 1
                elif summary["downloaded"] > 0 or summary["skipped_existing"] > 0:
                    total["fully_successful"] += 1
                if progress is not None:
                    progress(summary)
    return total
