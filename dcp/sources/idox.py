"""Idox Public Access adapter — fetches document bundles for triage matches.

Idox is the dominant UK council planning portal. The canonical install path is
`/online-applications/applicationDetails.do?keyVal=<KEY>&activeTab=summary` —
already captured in `applications.url` by the PlanIt index pass. Swapping
`activeTab=summary` for `activeTab=documents` gets the documents tab, which
carries a single HTML table of (Date Published, Document Type, …, filename, link).

Document links are relative paths of the form
`/online-applications/files/<HEX>/pdf/<filename>.pdf` and are served as direct
PDFs. Where the council enables Idox's OMT measuring tool, drawing rows carry
an *additional* `omt-server/omt.html#docKey=` anchor ("Measure document")
ahead of the direct "View" link in the same row — the parser prefers the
first non-docKey anchor, so those rows resolve to their direct PDF. Across
every observed snapshot (14 councils) a docKey anchor is always accompanied
by a direct link; a row with only viewer anchors would be skipped.

Many UK council Idox installs ship a misconfigured TLS chain — the server
sends only the leaf cert and not the intermediate(s), so strict OpenSSL
validation fails (Tower Hamlets uses GoDaddy G2; Northumberland and Glasgow
use Sectigo OV R36; others vary). The `IdoxClient` defaults to an SSL
context built via the `truststore` package, which delegates to the OS native
TLS APIs (Keychain on macOS, schannel on Windows, system OpenSSL on Linux).
Those native APIs perform AIA chasing — downloading the missing intermediate
from the URL embedded in the leaf cert's Authority Information Access
extension — so chain reconstruction is automatic and we never bypass
verification.

Bytes are stored in the single document store,
`data/raw/documents/<application_ref>/<sha256[:16]>.<ext>`,
recorded in `documents` table with `(application_id, content_sha256)` UNIQUE
so re-runs are no-ops.

**Path-layout quirk worth knowing**: application refs use `/` as their
own segment separator, and the bytes-layout preserves slashes verbatim
so each council gets a tidy subtree on disk. The edge case is when one
ref is a *prefix* of another — `TowerHamlets/PA/15/00249` and the
Section 73 variation `TowerHamlets/PA/15/00249/S`. The variation's
directory naturally nests inside the parent's, so the parent dir
contains its own PDFs alongside a subdirectory holding the variation's.
Each app's `_manifest.json` still distinguishes their contents and the
apps are genuinely related, so this is editorially defensible. A
flat-path migration (`TowerHamlets/PA_15_00249/` etc.) would eliminate
the quirk but would orphan every already-fetched directory — deferred
until a clean-sheet rebuild. See ARCHITECTURE.md §Storage for details.
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

# Many UK council Idox installs serve TLS certs without including the full
# intermediate chain (Tower Hamlets, Northumberland, Glasgow, and others). The
# leaf cert is typically issued by a public CA whose root IS in certifi, but
# the intermediate that bridges the two is missing — so Python's strict chain
# validation fails. The proper fix is to use a trust store that performs AIA
# chasing (downloading the missing intermediate from the URL in the leaf
# cert's Authority Information Access extension). The `truststore` package
# delegates to the OS native TLS APIs (Keychain on macOS, schannel on Windows,
# OpenSSL with system roots on Linux), all of which support AIA chasing.
# We never bypass certificate verification — only fix the chain.


def _resolve_ssl_context():
    """Build an SSL context that uses the OS native trust store (so we get
    AIA chasing for free). Used as `verify=<context>` on the httpx.Client.
    Memoised so the context is built once per process."""
    import ssl
    import truststore
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

SOURCE_NAME = "idox"
USER_AGENT = "datacentre_planning research (luke.hoyland@gmail.com)"


class PersistentHTTPError(RuntimeError):
    """A request that kept returning the same retryable status (429/5xx)
    until the backoff ladder was exhausted. Carries the status code so
    callers can distinguish 'this portal is rate-limiting us right now'
    (429 — come back later) from 'this portal is broken' (5xx — probably
    stays broken). Subclasses RuntimeError so existing handling that
    treats ladder exhaustion generically keeps working."""

    def __init__(self, status_code: int, url: str, attempts: int):
        self.status_code = status_code
        self.url = url
        super().__init__(
            f"persistent {status_code}s after {attempts} retries: {url}")


@dataclass
class DocumentLink:
    """One row from an Idox documents-tab table."""
    href: str            # absolute URL
    filename: str        # the displayed filename in the table
    kind: str | None     # the "Document Type" column value
    date_published: str | None
    description: str | None  # the "Description" column value (often = filename)


def _is_idox_url(url: str) -> bool:
    """Heuristic: the `applicationDetails.do` endpoint is unique to Idox
    Public Access across observed UK portals (Ocella uses `planningDetails`,
    Northgate uses `StdDetails.aspx`), so the endpoint alone is the signal.
    Councils mount Idox under many path prefixes — `/online-applications/`
    and `/newplanningaccess/` are the common ones, but Fife uses `/online/`,
    Horsham `/public-access/`, Stockport `/PlanningData-live/`, Dacorum
    `/publicaccess/`, Midlothian `/OnlinePlanning/` — and the documents-tab
    `activeTab` swap works identically on all of them."""
    if not url:
        return False
    return "applicationDetails.do" in url


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
    documents. Relative `href`s are resolved against `base_url`. Drawing rows
    on OMT-enabled councils carry a "Measure document" viewer anchor
    (`docKey=`) *before* the direct "View" anchor — the row's document link is
    the first non-docKey anchor, and rows with only viewer anchors are skipped.
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
        href = ""
        for a in tr.css("a"):
            candidate = a.attributes.get("href") or ""
            if candidate and "docKey=" not in candidate:
                href = candidate
                break
        if not href:
            # Only OMT-viewer links (or none) in this row; no direct PDF.
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
        verify: str | bool | None = None,
        adaptive_delay: bool = True,
        max_delay_seconds: float = 45.0,
    ):
        self.delay = delay_seconds
        self.backoff = backoff_seconds
        self.max_retries = max_retries
        # A 429 says our chosen pace is faster than this council wants.
        # Backing off for the retry and then resuming the original pace
        # means asking again at a rate already refused — the campaign
        # logged 220 of them across eight councils at 5s spacing, each
        # handled correctly but each still an unwelcome request.
        #
        # So a 429 permanently slows THIS client, and clients are one per
        # host, which makes the adaptation per-council for the rest of the
        # run. Multiplicative increase converges quickly; the cap stops a
        # pathological host stalling its shard forever. 5xx does not
        # adapt: a server error is not a statement about our rate.
        self.adaptive_delay = adaptive_delay
        self.max_delay = max_delay_seconds
        self._base_delay = delay_seconds
        # Default: OS native trust store via `truststore`, which performs AIA
        # chasing to recover intermediate certs that misconfigured council
        # servers fail to send. Pass `verify=True` to get certifi's strict
        # bundle only (and accept failures on broken-chain councils); pass a
        # path to a bundle to use a specific trust file. `verify=False`
        # bypasses validation entirely — never do that for council portals.
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

    def __enter__(self) -> "IdoxClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next_request_at:
            time.sleep(self._next_request_at - now)

    def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        """GET with the politeness contract: inter-request delay, backoff
        on 429/5xx, ladder exhaustion raising PersistentHTTPError.
        `headers` are merged over the client defaults for this request —
        used by adapters whose API requires per-request identification."""
        for attempt in range(self.max_retries):
            self._wait()
            r = self.client.get(url, headers=headers)
            self._next_request_at = time.monotonic() + self.delay
            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = self.backoff * (2 ** attempt)
                if r.status_code == 429 and self.adaptive_delay:
                    was = self.delay
                    self.delay = min(self.delay * 1.5, self.max_delay)
                    if self.delay > was:
                        log.warning(
                            "429 from %s — this host's spacing raised "
                            "%.0fs -> %.0fs for the rest of the run",
                            _host_of(url), was, self.delay,
                        )
                log.warning(
                    "%d from %s (attempt %d/%d); backing off %.0fs",
                    r.status_code, url, attempt + 1, self.max_retries, wait,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise PersistentHTTPError(r.status_code, url, self.max_retries)


def _host_of(url: str) -> str:
    """Host for logging, so an adaptation names the council not the file."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url[:60]
    except Exception:
        return url[:60]


_SAFE_REF_RE = re.compile(r"[^A-Za-z0-9._/-]+")


def _sanitised_ref(application_ref: str) -> str:
    """Filesystem-safe rendering of an application_ref. Slashes are preserved
    so each council gets its own subdirectory."""
    return _SAFE_REF_RE.sub("_", application_ref)


def _app_dir(data_dir: Path, application_ref: str) -> Path:
    """`<DATA_DIR>/raw/idox/<safe_ref>/` — the per-application directory."""
    return data_dir / "raw" / "documents" / _sanitised_ref(application_ref)


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


def _network_up() -> bool:
    """Cheap connectivity probe: DNS resolution of a stable public host,
    no HTTP round-trip. Distinguishes 'the laptop is offline' from 'this
    portal is down' so the document loop can pause rather than burn the
    remaining links of a bundle as errors."""
    import socket
    try:
        socket.getaddrinfo("www.gov.uk", 443)
        return True
    except OSError:
        return False


def _wait_for_network() -> None:
    """Block until connectivity returns, with a five-minutely heartbeat."""
    waited = 0
    while not _network_up():
        if waited % 300 == 0:
            log.warning("offline; pausing document fetch (%d min so far)",
                        waited // 60)
        time.sleep(60)
        waited += 60
    if waited:
        log.warning("back online after %d min; resuming document fetch",
                    waited // 60)


def _fetch_document(client: IdoxClient, href: str, docs_url: str) -> httpx.Response:
    """Download one document, recovering from session expiry.

    Some Idox installs sit behind a load balancer whose affinity cookies
    (JSESSIONID + NSC_*) gate file downloads — Bexley serves 404 for a
    document a browser fetches fine until the documents tab has been
    visited in the same session. Our session is established by the tab
    fetch, but a long 429/5xx backoff ladder can outlive it, after which
    every download 404s. On a 404, re-fetch the tab (re-establishing the
    session) and retry the document once; a 404 that survives a fresh
    session is genuinely missing."""
    try:
        return client.get(href)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        log.info("404 for %s — refreshing portal session, retrying once", href)
        client.get(docs_url)
        return client.get(href)


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
    except PersistentHTTPError as exc:
        # Tab-level ladder exhaustion: a 429 means the portal is throttling
        # us tonight (retryable later); a 5xx means the page itself is
        # broken (probably stays that way). Callers treat these differently.
        summary["error_class"] = (
            "rate_limited" if exc.status_code == 429 else "persistent_5xx")
        summary["error"] = str(exc)[:200]
        summary["errors"] += 1
        log.warning("documents page fetch failed (%s): %s", application_ref, exc)
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

    # Resume support: a document URL already recorded for this application
    # with its bytes still on disk doesn't need re-downloading. Idox file
    # URLs embed a unique per-revision document id, so bytes at a given URL
    # are immutable in practice — revised documents appear as new URLs.
    # Without this, re-walking a completed app re-downloads its whole bundle
    # just to rediscover every hash matches.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT url, bytes_path FROM documents WHERE application_id = %s",
            (application_id,),
        )
        prior_bytes = {url: bp for url, bp in cur.fetchall() if bp}

    # A portal that 429s persistently makes each failing document cost a
    # full backoff ladder (~15 min). Three consecutive ladder-exhausted
    # failures abandon the rest of this application's documents — the app
    # keeps errors > 0, stays out of any completed set, and the retry pass
    # picks it up later. Instant failures (404s on purged documents) don't
    # count: they're cheap, and a run of them shouldn't doom the bundle.
    ladder_failures_in_row = 0
    for link in links:
        prior_path = prior_bytes.get(link.href)
        if prior_path:
            p = Path(prior_path)
            if not p.is_absolute():
                p = data_dir.parent / p
            if p.exists():
                summary["skipped_existing"] += 1
                continue
        # Connectivity loss mid-bundle pauses the loop (retrying the same
        # document once the network returns) instead of failing the rest
        # of the bundle one link at a time.
        blob = None
        failure: Exception | None = None
        while True:
            try:
                blob = _fetch_document(client, link.href, docs_url)
                break
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if not _network_up():
                    _wait_for_network()
                    continue
                failure = exc
                break
            except Exception as exc:
                failure = exc
                break
        if blob is None:
            log.warning("doc download failed (%s, %s): %s",
                        application_ref, link.href, failure)
            summary["errors"] += 1
            if isinstance(failure, RuntimeError):
                ladder_failures_in_row += 1
                if ladder_failures_in_row >= 3:
                    summary["error_class"] = "rate_limit_cascade"
                    log.warning(
                        "abandoning %s after %d consecutive exhausted "
                        "backoff ladders (%d links unattempted)",
                        application_ref, ladder_failures_in_row,
                        len(links) - links.index(link) - 1,
                    )
                    break
            else:
                ladder_failures_in_row = 0
            continue
        ladder_failures_in_row = 0
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
    """Pull worklist apps that have a likely-Idox URL, in worklist-rank order
    (head-of-list first). Defers ranking to `dcp.worklist.fetch` so the fetch
    order matches the order Aisha sees in the export — earlier ranks are the
    highest-priority cases."""
    from dcp import worklist as worklist_mod
    data = worklist_mod.fetch(conn, model=model, limit=None)
    out: list[tuple] = []
    for row in data.rows:
        url = row.get("url")
        if not url or not _is_idox_url(url):
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
