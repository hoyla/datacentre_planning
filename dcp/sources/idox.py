"""Idox Public Access adapter — fetches document bundles for triage matches.

Idox is the dominant UK council planning portal. The canonical install path is
`/online-applications/applicationDetails.do?keyVal=<KEY>&activeTab=summary` —
already captured in `applications.url` by the PlanIt index pass. Swapping
`activeTab=summary` for `activeTab=documents` gets the documents tab, which
carries a single HTML table of (Date Published, Document Type, …, filename, link).

Document links are relative paths of the form
`/online-applications/files/<HEX>/pdf/<filename>.pdf` and are served as direct
PDFs. A subset of plan documents (where the council uses Idox's OMT viewer)
have `docKey=` URLs that point to an interactive viewer rather than a direct
PDF — we currently skip those; deep-read can fall back to manual download.

Some councils' portals ship a misconfigured TLS chain (missing intermediate
cert; Sectigo OV R36 in particular). Callers can pass `verify=<path>` with a
custom CA bundle for those councils; the default uses certifi's bundle. The
data is public planning material and document content is hashed via SHA-256
on download, but TLS chain bypasses are NOT enabled by default — broken
councils log a warning and skip rather than silently bypassing verification.

Bytes are stored under `data/raw/idox/<application_ref>/<sha256[:16]>.pdf`,
recorded in `documents` table with `(application_id, content_sha256)` UNIQUE
so re-runs are no-ops.
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

SOURCE_NAME = "idox"
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"


@dataclass
class DocumentLink:
    """One row from an Idox documents-tab table."""
    href: str            # absolute URL
    filename: str        # the displayed filename in the table
    kind: str | None     # the "Document Type" column value
    date_published: str | None
    description: str | None  # the "Description" column value (often = filename)


def _is_idox_url(url: str) -> bool:
    """Heuristic: Idox URLs contain '/online-applications/' or
    '/newplanningaccess/' and the `applicationDetails.do` endpoint."""
    if not url:
        return False
    return (
        "applicationDetails.do" in url
        and ("/online-applications/" in url or "/newplanningaccess/" in url)
    )


def _documents_tab_url(application_url: str) -> str:
    """Translate the summary-tab URL we have on hand into the documents-tab URL.
    Idfdox accepts an `activeTab` query parameter; we replace it (or append it
    if missing). Any other params on the URL are preserved."""
    parsed = urllib.parse.urlparse(application_url)
    qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    qs["activeTab"] = "documents"
    new_q = urllib.parse.urlencode(qs)
    return urllib.parse.urlunparse(parsed._replace(query=new_q))


def parse_documents_page(html: str, base_url: str) -> list[DocumentLink]:
    """Extract document links from an Idox documents-tab HTML page.

    The page has a single top-level table; row 1 is the header, rows 2+ are
    documents. Relative `href`s are resolved against `base_url`. The OMT-viewer
    `docKey=` links are filtered out — they're not direct PDFs.
    """
    tree = HTMLParser(html)
    table = tree.css_first("table")
    if table is None:
        return []
    rows = table.css("tr")
    if not rows:
        return []
    # Header detection: first row should have <th> cells; fall back to "Document
    # Type" / "Date Published" string match if a council renders headers in <td>.
    header_cells = [c.text(strip=True).lower() for c in rows[0].css("th, td")]
    col_index = {name: i for i, name in enumerate(header_cells)}
    out: list[DocumentLink] = []
    for tr in rows[1:]:
        cells = tr.css("td")
        if not cells:
            continue
        a = tr.css_first("a")
        if a is None:
            continue
        href = a.attributes.get("href") or ""
        if not href or "docKey=" in href:
            # Skip OMT-viewer links; we want direct PDFs only in this pass.
            continue
        abs_href = urllib.parse.urljoin(base_url, href)
        def _cell(name: str) -> str | None:
            idx = col_index.get(name)
            if idx is None or idx >= len(cells):
                return None
            val = cells[idx].text(strip=True)
            return val or None
        out.append(DocumentLink(
            href=abs_href,
            filename=_cell("description") or _cell("filename") or "",
            kind=_cell("document type"),
            date_published=_cell("date published"),
            description=_cell("description"),
        ))
    return out


class IdoxClient:
    """Polite Idox HTTP client. Same shape as PlanItClient — inter-request
    delay, exponential backoff on 429s/5xx, identifying User-Agent. SSL
    verification follows httpx's default (certifi bundle) unless `verify` is
    supplied explicitly; misconfigured councils raise httpx.ConnectError which
    we surface as a logged skip rather than retrying-forever."""

    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        delay_seconds: float = 5.0,
        backoff_seconds: float = 60.0,
        max_retries: int = 4,
        verify: str | bool = True,
    ):
        self.delay = delay_seconds
        self.backoff = backoff_seconds
        self.max_retries = max_retries
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=90.0,
            follow_redirects=True,
            verify=verify,
        )
        self._next_request_at = 0.0

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "IdoxClient":
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


_SAFE_REF_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def _sanitised_ref(application_ref: str) -> str:
    """Filesystem-safe rendering of an application_ref. Slashes are preserved
    so each council gets its own subdirectory."""
    return _SAFE_REF_RE.sub("_", application_ref)


def _app_dir(data_dir: Path, application_ref: str) -> Path:
    """`<DATA_DIR>/raw/idox/<safe_ref>/` — the per-application directory."""
    return data_dir / "raw" / "idox" / _sanitised_ref(application_ref)


def _bytes_path(data_dir: Path, application_ref: str, content_sha256: str, ext: str) -> Path:
    """`<DATA_DIR>/raw/idox/<safe_ref>/<sha256[:16]>.<ext>` — the bytes layout
    documented in ARCHITECTURE.md."""
    return _app_dir(data_dir, application_ref) / f"{content_sha256[:16]}.{ext}"


def _ext_from_url(url: str) -> str:
    """Conservative extension guess — Idox direct-download URLs always end
    in `.pdf` in our observed sample. Anything else falls back to `bin`."""
    path = urllib.parse.urlparse(url).path
    if path.lower().endswith(".pdf"):
        return "pdf"
    # Idox can serve images under .png/.jpg/.tif; preserve those extensions.
    m = re.search(r"\.([a-zA-Z0-9]{2,4})$", path)
    return m.group(1).lower() if m else "bin"


def _write_manifest(
    conn,
    *,
    application_id: int,
    application_ref: str,
    app_dir: Path,
    summary: dict,
) -> None:
    """Drop a `_manifest.json` in the per-app directory once the fetch loop
    finishes. Presence of this file is the hand-over signal: an app dir
    without a manifest is either mid-fetch or interrupted before completion.

    The manifest lists every document recorded in the `documents` table for
    this application — both newly downloaded and previously-existing — so
    Aisha (or any downstream consumer) can see at a glance what's in the
    folder and whether it was a clean fetch.
    """
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
        "fetcher": f"dcp.sources.idox v{MANIFEST_VERSION}",
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
    client: IdoxClient,
    application_id: int,
    application_ref: str,
    application_url: str,
    source_id: int,
    data_dir: Path,
) -> dict:
    """Fetch every direct-download document for one Idox application and
    record metadata in the `documents` table. Returns a per-application
    summary dict."""
    summary = {
        "ref": application_ref,
        "links_found": 0,
        "downloaded": 0,
        "skipped_existing": 0,
        "errors": 0,
    }
    if not _is_idox_url(application_url):
        log.info("not an Idox URL, skipping: %s", application_url)
        summary["error_class"] = "not_idox_url"
        return summary

    docs_url = _documents_tab_url(application_url)
    try:
        resp = client.get(docs_url)
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

    # Idox returns 200 with a "Planning Application details not available"
    # body when an application has been withdrawn from public view. Flag these
    # so the operator can act on them rather than treating them as parse misses.
    if "no longer available for viewing" in resp.text.lower():
        summary["error_class"] = "withdrawn_from_view"
        log.info("withdrawn from view: %s", application_ref)
        return summary

    # Snapshot the documents-tab HTML so the parse can be re-run later if our
    # heuristics evolve.
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
        ext = _ext_from_url(link.href)
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

    # All links processed — write the per-app manifest so downstream consumers
    # (or a handoff to Aisha) can see at a glance that this directory is done.
    if summary["links_found"] > 0:
        _write_manifest(
            conn, application_id=application_id, application_ref=application_ref,
            app_dir=_app_dir(data_dir, application_ref), summary=summary,
        )
    return summary


def _worklist_apps(conn, *, model: str, top: int | None) -> list[tuple]:
    """Pull the ranked worklist apps that have a likely-Idox URL. Mirrors the
    filter `dcp.worklist.fetch` uses but trims to just the fields we need."""
    sql = """
    WITH latest_triage AS (
      SELECT DISTINCT ON (application_id) * FROM triage
      WHERE model = %s ORDER BY application_id, inserted_at DESC
    ),
    ranked AS (
      SELECT a.id, a.application_ref, a.url, a.discovered_via,
        (SELECT count(*) FROM unnest(t.signals) AS s WHERE lower(s) ~
           '(energy centre|gas turbine|chp|gas[- ]fired|hydrogen|biomass)') AS t1
      FROM applications a JOIN latest_triage t ON t.application_id = a.id
      WHERE ((t.verdict IN ('DC','adjacent') AND t.worth_deep_read IN ('yes','maybe'))
             OR 'foxglove_top10' = ANY(a.discovered_via))
        AND a.url IS NOT NULL
        AND (a.url LIKE '%%/online-applications/%%' OR a.url LIKE '%%/newplanningaccess/%%')
    )
    SELECT id, application_ref, url FROM ranked
    ORDER BY t1 DESC, application_ref
    """
    if top is not None:
        sql += " LIMIT %s"
        with conn.cursor() as cur:
            cur.execute(sql, (model, top))
            return cur.fetchall()
    with conn.cursor() as cur:
        cur.execute(sql, (model,))
        return cur.fetchall()


def fetch_worklist(
    *,
    model: str = "granite4.1:30b",
    top: int | None = None,
    delay_seconds: float = 5.0,
    data_dir: Path = Path("data"),
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Walk the top-N worklist apps with Idox-shaped URLs and fetch every
    direct-download document for each. Per-app summaries are streamed to
    `progress` and aggregated into the returned total."""
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
            base_url="(per-council Idox host)",
        )
        apps = _worklist_apps(conn, model=model, top=top)
        with IdoxClient(delay_seconds=delay_seconds) as client:
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
