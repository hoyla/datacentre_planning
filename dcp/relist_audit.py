"""Compare what a register offered with what we stored.

The manifests record what was stored. They do not record what was
offered, so a fetch that stopped short — a rate-limit cascade, a wedged
connection, a run killed mid-bundle — is indistinguishable from an
application that only ever had that many documents. `fetch_outstanding`
has caught this since the `partial` outcome landed, but only for fetches
run after it; the historical corpus is unmeasured. Per-site document
counts are on every reader site page, which is why the roadmap puts this
before anyone quotes one.

This module obtains a **listing only** and compares it to the `documents`
rows. It never downloads a document and never writes to `documents`. The
comparison lands in `document_listing_audit` (migration 026), append-only
and idempotent on the listing's content hash.

Three ways to get a listing, cheapest first:

*   `listing_from_snapshot` — the documents-tab HTML already in
    `source_snapshots`. The Idox adapter snapshots that page *before* it
    starts downloading, so for a short fetch this is the very page the
    run was working from. Costs no portal traffic.
*   `listing_from_harvest` — a browser-harvested Salesforce listing on
    disk (`data/priors/salesforce_documents.json`). Also free.
*   `listing_live` — re-list now, through the project's own adapters and
    their politeness contract (one client per host, adaptive spacing, no
    request the download path would not have made). The body is written
    to `source_snapshots` like any other fetch.

Parsing is the adapters' own code in every case. There is no second
scraper here: `dcp.sources.idox.parse_documents_page` and its siblings
are what decided which links the fetch would follow, so anything else
would be measuring a different question.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass, field

from psycopg2.extras import Json

from dcp import repo
from dcp.sources import agile, aifusion, arcus, idox, ocella, salesforce_pr

log = logging.getLogger(__name__)

TOOL = "dcp.relist_audit"

# Hosts we do not touch, and why. A skip is recorded rather than
# silently omitted: "nobody looked" must never be stored as "nothing
# there", and an application on this list has an unmeasured shortfall,
# not a measured zero.
SKIP_HOSTS: dict[str, str] = {
    # AWS WAF. Deliberately not scraped; the documents we hold for it came
    # through a browser with a human at the keyboard.
    "planandregulatory.coventry.gov.uk":
        "AWS WAF-protected; deliberately not scraped (ROADMAP, phase 2)",
}

# Portal families with a listing-only path in this module. Anything else
# is recorded `no_adapter` — an honest gap, and a cheap one to close
# later since only the listing half is needed.
SUPPORTED = ("idox", "ocella", "agile", "arcus", "aifusion", "salesforce_pr",
             "newport_docstore")

# Newport's Idox install serves an error page on its documents tab and
# publishes the documents from a separate store. Auditing it as Idox
# reads "the register offers nothing" over 42 applications that hold
# 700-odd documents — a measured zero where the truth is that the
# listing is somewhere else.
NEWPORT_HOST = "publicaccess.newport.gov.uk"


def _newport_module():
    """`fetch_doc_list` from the Newport docstore script.

    The listing parse lives in a script rather than a source module, and
    the audit must use the same parse the fetch used or it measures a
    different question. Loaded the way fetch_outstanding.py loads the
    campaign runner.
    """
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "scripts" \
        / "fetch_newport_docstore.py"
    spec = importlib.util.spec_from_file_location("newport_docstore", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Listing:
    """One register listing, whatever produced it."""

    offered: list[dict] = field(default_factory=list)  # [{url, filename, kind}]
    source: str = "none"          # snapshot | live | harvest | none
    url: str | None = None
    sha256: str | None = None
    captured_at: dt.datetime | None = None
    status: str = "audited"
    detail: str | None = None


def listing_family(url: str | None) -> str | None:
    """The adapter whose listing path fits this application URL, or None.

    Deliberately the adapters' own predicates rather than a hostname
    table: the fetch dispatched on these, so the audit must dispatch on
    the same ones or it audits a different application than the one that
    was fetched.
    """
    if not url:
        return None
    # Before the Idox test: Newport's URL is Idox-shaped and its
    # documents tab is not where its documents are.
    if NEWPORT_HOST in url:
        return "newport_docstore"
    if idox._is_idox_url(url):
        return "idox"
    if ocella._is_ocella_url(url):
        return "ocella"
    if agile._is_agile_url(url):
        return "agile"
    if aifusion._is_aifusion_url(url):
        return "aifusion"
    if salesforce_pr._is_salesforce_pr_url(url):
        return "salesforce_pr"
    if arcus._is_arcus_url(url):
        return "arcus"
    return None


def listing_key(url: str, family: str) -> str | None:
    """The `source_snapshots.key` a listing for this application is
    stored under, or None where the family does not snapshot listings."""
    if family == "idox":
        return idox._documents_tab_url(url)
    if family == "ocella":
        try:
            base, reference = ocella._parse_application_url(url)
        except ValueError:
            return None
        return ocella._show_documents_url(base, reference)
    if family == "arcus":
        return url
    return None


# --------------------------------------------------------------------
# Listings
# --------------------------------------------------------------------

def listing_from_snapshot(conn, *, url: str, family: str) -> Listing | None:
    """The newest stored listing body for this application, parsed.

    Returns None when nothing was ever snapshotted for it — which is a
    different answer from "the listing was empty" and must stay so.
    """
    key = listing_key(url, family)
    if key is None:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT raw_bytes_inline, content_sha256, fetched_at
            FROM source_snapshots
            WHERE key = %s AND status_code = 200
              AND raw_bytes_inline IS NOT NULL
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (key,),
        )
        row = cur.fetchone()
    if not row:
        return None
    raw, sha, fetched_at = row
    html = bytes(raw).decode("utf-8", "replace")
    return _parse_html_listing(
        html, key=key, family=family, source="snapshot",
        sha=sha, captured_at=fetched_at)


# A portal that refuses is not a portal that publishes nothing.
#
# Idox serves "Permission Denied" with HTTP 200 and the site's full
# chrome, so nothing upstream — not the status code, not the fetch, not
# this module until it learned these strings — could tell it from a
# documents tab. Parsed as a listing it yields zero links, and zero links
# read as a register that holds nothing. That is the substitution
# `dcp.acquisition_outcome` exists to refuse, arriving by the other door:
# not a failure miscounted, but a refusal page parsed as a fact.
#
# The markers are the pages' own words, taken from the bodies in
# `source_snapshots` rather than guessed.
REFUSAL_MARKERS = (
    "you do not have permission to view",
    "permission denied",
)

# Below this a body cannot be a listing page. The smallest listing in the
# corpus that offered even one document is 7,192 bytes (an Ocella
# showDocuments page); a real Idox documents tab carries 8-36KB of site
# chrome before it lists anything. Three Brighton snapshots are 212-byte
# bodies stored with a 200 — nothing at all, which parses to zero
# documents and reads as an empty register.
MIN_LISTING_BYTES = 1000


def _refusal(html: str) -> str | None:
    """Why this body is not a listing, or None if it may be one.

    The markers are checked before parsing; the length floor only after,
    and only when the parse found nothing. Length is weak evidence and
    must never overrule the strong kind: a body that yielded document
    links is a listing whatever its size.
    """
    low = html.lower()
    for marker in REFUSAL_MARKERS:
        if marker in low:
            return f"portal served a refusal page (HTTP 200): {marker!r}"
    return None


def _parse_html_listing(html: str, *, key: str, family: str, source: str,
                        sha: str, captured_at) -> Listing:
    if "no longer available for viewing" in html.lower():
        return Listing(source=source, url=key, sha256=sha,
                       captured_at=captured_at, status="withdrawn",
                       detail="portal reports the application is no longer "
                              "available for viewing")
    refusal = _refusal(html)
    if refusal:
        # `blocked`, not `empty_listing`: the register was not read. The
        # row keeps the body's hash as evidence, and `_content_key`
        # distinguishes it from any earlier row that read the same body
        # as a measured zero.
        return Listing(source=source, url=key, sha256=sha,
                       captured_at=captured_at, status="blocked",
                       detail=refusal)
    if family == "idox":
        links = idox.parse_documents_page(html, base_url=key)
        offered = [{"url": link.href, "filename": link.filename,
                    "kind": link.kind} for link in links]
    elif family == "ocella":
        links = ocella.parse_documents_page(html, base_url=key)
        offered = [{"url": link.href, "filename": link.filename,
                    "kind": link.kind} for link in links]
    elif family == "arcus":
        offered = [{"url": d["href"], "filename": d.get("filename"),
                    "kind": d.get("kind")}
                   for d in arcus.parse_documents_page(html, base_url=key)]
    else:
        raise ValueError(f"no HTML listing parser for {family!r}")
    if not offered and len(html) < MIN_LISTING_BYTES:
        # Nothing parsed out of a body too small to have been a listing
        # page. Three Brighton snapshots are 212 bytes, stored with a
        # 200: an empty response, which is not an empty register.
        return Listing(source=source, url=key, sha256=sha,
                       captured_at=captured_at, status="blocked",
                       detail=f"body is {len(html)} bytes and yielded no "
                              "links — too short to be a listing page (the "
                              "smallest real one in the corpus is 7,192)")
    return Listing(offered=offered, source=source, url=key, sha256=sha,
                   captured_at=captured_at,
                   status="audited" if offered else "empty_listing",
                   detail=None if offered
                   else "listing parsed and offered no documents")


def listing_from_harvest(application_ref: str,
                         listings: dict[str, list[dict]]) -> Listing:
    """A browser-harvested Salesforce listing. Absent is not empty."""
    docs = listings.get(application_ref)
    if docs is None:
        return Listing(source="none", status="no_listing",
                       detail="Salesforce register; no harvested listing held")
    offered = [{"url": d.get("url"), "filename": d.get("filename")
                or d.get("description"), "kind": d.get("description")}
               for d in docs if d.get("url")]
    blob = json.dumps(docs, sort_keys=True).encode()
    return Listing(offered=offered, source="harvest",
                   url=str(salesforce_pr.LIST_CACHE),
                   sha256=hashlib.sha256(blob).hexdigest(),
                   captured_at=None,
                   status="audited" if offered else "empty_listing")


def listing_live(conn, *, client, application_ref: str, url: str,
                 family: str, source_id: int | None = None) -> Listing:
    """Re-list one application through its own adapter. Listing only.

    The body is written to `source_snapshots` when we have a source id
    for it, so the evidence behind the audit row is preserved on the same
    append-only terms as every other fetch this project makes.
    """
    import httpx

    try:
        if family in ("idox", "ocella", "arcus"):
            key = listing_key(url, family)
            if key is None:
                return Listing(status="error",
                               detail="could not derive a listing URL")
            resp = client.get(key)
            body = resp.content
            sha = hashlib.sha256(body).hexdigest()
            if source_id is not None:
                repo.record_snapshot(conn, source_id=source_id, key=key,
                                     raw_bytes=body)
                conn.commit()
            return _parse_html_listing(
                body.decode("utf-8", "replace"), key=key, family=family,
                source="live", sha=sha,
                captured_at=dt.datetime.now(dt.timezone.utc))

        if family == "agile":
            parsed = agile.parse_portal_url(url)
            if parsed is None:
                return Listing(status="error", detail="not an Agile portal URL")
            slug, app_id = parsed
            docs = client.documents(slug, app_id)
            offered = [{"url": agile.document_url(d["documentHash"]),
                        "filename": d.get("fileName") or d.get("name"),
                        "kind": d.get("documentType") or d.get("type")}
                       for d in docs if d.get("documentHash")]
            return _api_listing(offered, url=f"agile:{slug}/{app_id}/document")

        if family == "newport_docstore":
            newport = _newport_module()
            folder_ref = application_ref.split("/", 1)[1]
            url_ = newport.search_url(folder_ref)
            body = client.get(url_).text
            docs = newport.parse_doc_list(body)
            if docs is None:
                # The docstore answered without its page model. The fetch
                # path reads that as nothing to download, which is right
                # for a downloader and wrong for a measurement: the store
                # was not read, so it must not be recorded as empty.
                return Listing(source="live", url=url_, status="blocked",
                               detail="docstore page carried no `var model`; "
                                      "the listing did not parse")
            offered = [{"url": f"{newport.VIEW_URL}?id={guid}",
                        "filename": None, "kind": kind}
                       for guid, kind in docs]
            return _api_listing(offered, url=url_)

        if family == "aifusion":
            api_base = aifusion.api_base_for(url)
            case_id = aifusion.case_id_for(application_ref)
            docs = aifusion.list_documents(client, api_base=api_base,
                                           case_id=case_id)
            if docs is None:
                return Listing(source="live",
                               url=f"{api_base}/docs?caseId={case_id}",
                               status="no_listing",
                               detail="register does not recognise this case "
                                      "reference")
            offered = [{"url": d["url"], "filename": d.get("filename"),
                        "kind": d.get("kind")} for d in docs]
            return _api_listing(offered,
                                url=f"{api_base}/docs?caseId={case_id}")
    except idox.PersistentHTTPError as exc:
        return Listing(
            status="rate_limited" if exc.status_code == 429 else "error",
            detail=str(exc)[:200])
    except httpx.HTTPStatusError as exc:
        return Listing(status="error",
                       detail=f"http {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
        return Listing(status="error", detail=f"{type(exc).__name__}: "
                                              f"{str(exc)[:180]}")

    if family == "salesforce_pr":
        # The Lightning register renders its listing in the browser and
        # refuses a scripted one; the listing has to be harvested by hand
        # (`--pass harvest` audits against what has been). Not an adapter
        # gap — a portal that will not answer this question to a script.
        return Listing(status="no_listing",
                       detail="Salesforce register serves no scripted "
                              "listing; harvest it via the browser and "
                              "re-run --pass harvest")
    return Listing(status="no_adapter", detail=f"no live listing for {family}")


def _api_listing(offered: list[dict], *, url: str) -> Listing:
    """A listing that came back as JSON rather than a page: hash the
    normalised document list so the idempotency key still means 'this
    listing has not changed'."""
    blob = json.dumps(sorted(d["url"] for d in offered)).encode()
    return Listing(offered=offered, source="live", url=url,
                   sha256=hashlib.sha256(blob).hexdigest(),
                   captured_at=dt.datetime.now(dt.timezone.utc),
                   status="audited" if offered else "empty_listing",
                   detail=None if offered
                   else "register listed no documents")


# --------------------------------------------------------------------
# Comparison and recording
# --------------------------------------------------------------------

def stored_urls(conn, application_id: int) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT url FROM documents WHERE application_id = %s",
                    (application_id,))
        return {r[0] for r in cur.fetchall() if r[0]}


def compare(listing: Listing, held: set[str]) -> dict:
    """Offered against stored. Counts plus the missing set."""
    offered_urls = [d["url"] for d in listing.offered if d.get("url")]
    offered_set = set(offered_urls)
    matched = offered_set & held
    missing = [d for d in listing.offered
               if d.get("url") and d["url"] not in held]
    return {
        "offered_count": len(offered_urls),
        "stored_count": len(held),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "unmatched_stored_count": len(held - offered_set),
        "missing": missing,
    }


# --------------------------------------------------------------------
# Reading the audit back
# --------------------------------------------------------------------

# Why an offered document is not stored against this application. Only
# the last of these means anything is missing from the corpus.
FILED_ELSEWHERE = "filed_elsewhere"
DUPLICATE_LISTING = "duplicate_listing"
ABSENT = "absent"


def classify_missing(offered: list[dict], missing: list[dict],
                     held_here: set[str], held_anywhere: set[str]
                     ) -> dict[str, list[dict]]:
    """Split a shortfall into the three things it can actually be.

    A raw offered-minus-stored difference over-counts in two known ways,
    both of them structural rather than accidental:

    *   **Filed elsewhere.** Seventeen portal URLs each serve two
        application references for the same case (Cambridge/SouthCambs, a
        Reading reference in two spellings). One listing describes both,
        and the fetch attached each document to whichever row it reached
        first. The document is held; it is filed next door.

    *   **Duplicate listing.** `documents` is unique on
        `(application_id, content_sha256)`, so a register that offers the
        same file under two URLs — a Salesforce re-upload, a re-published
        plan — stores one row and leaves the second URL looking
        un-fetched. Detected by the register's own displayed name: an
        offered document whose name matches another offered document we
        do hold is the same document.

    What survives both tests is absent from the corpus, and that is the
    number a refetch pass exists to fix.
    """
    by_label: dict[str, list[str]] = {}
    for d in offered:
        label = (d.get("filename") or d.get("kind") or "").strip().lower()
        if label and d.get("url"):
            by_label.setdefault(label, []).append(d["url"])

    out: dict[str, list[dict]] = {FILED_ELSEWHERE: [], DUPLICATE_LISTING: [],
                                  ABSENT: []}
    for d in missing:
        url = d.get("url")
        if not url:
            continue
        if url in held_anywhere:
            out[FILED_ELSEWHERE].append(d)
            continue
        label = (d.get("filename") or d.get("kind") or "").strip().lower()
        if label and any(u in held_here for u in by_label.get(label, ())):
            out[DUPLICATE_LISTING].append(d)
            continue
        out[ABSENT].append(d)
    return out


def _content_key(listing: Listing) -> str:
    """The listing body's hash where there is one; otherwise the status
    and detail, so a repeated refusal does not accumulate copies.

    A `blocked` row carries the body's hash *and* its status, because the
    same body was once read as `empty_listing` and the correction has to
    be able to land beside that row rather than being deduplicated away
    by it. Only statuses that did not exist when those rows were written
    are qualified this way; the measuring statuses keep the bare hash, so
    re-auditing an unchanged page stays the no-op principle 5 requires.
    """
    if listing.sha256:
        if listing.status == "blocked":
            return f"blocked:{listing.sha256}"
        return listing.sha256
    payload = f"{listing.status}\n{listing.detail or ''}"
    return "s:" + hashlib.sha256(payload.encode()).hexdigest()


def record(conn, *, application_id: int, adapter: str, listing: Listing,
           comparison: dict | None, tool: str = TOOL) -> bool:
    """Append one audit row. Returns False when an identical row already
    stands — a re-list of an unchanged page is a no-op, per principle 5.
    """
    c = comparison or {}
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_listing_audit (
                application_id, adapter, listing_source, listing_url,
                listing_sha256, listing_captured_at, status, detail,
                offered_count, stored_count, matched_count, missing_count,
                unmatched_stored_count, offered, missing, content_key, tool)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (application_id, listing_source, content_key)
            DO NOTHING
            RETURNING id
            """,
            (application_id, adapter, listing.source, listing.url,
             listing.sha256, listing.captured_at, listing.status,
             listing.detail,
             c.get("offered_count"), c.get("stored_count"),
             c.get("matched_count"), c.get("missing_count"),
             c.get("unmatched_stored_count"),
             Json(listing.offered) if listing.offered else None,
             Json(c["missing"]) if c.get("missing") else None,
             _content_key(listing), tool),
        )
        inserted = cur.fetchone() is not None
    conn.commit()
    return inserted


def audit_from_snapshot(conn, *, application_id: int, application_ref: str,
                        url: str) -> tuple[Listing, dict | None] | None:
    """Audit one application against its stored listing, or None if it
    has no stored listing to audit against."""
    family = listing_family(url)
    if family is None:
        return None
    listing = listing_from_snapshot(conn, url=url, family=family)
    if listing is None:
        return None
    comparison = (compare(listing, stored_urls(conn, application_id))
                  if listing.status in ("audited", "empty_listing") else None)
    return listing, comparison


def skip_reason(url: str | None) -> str | None:
    """Why this host is not to be touched, or None."""
    from urllib.parse import urlparse
    host = (urlparse(url or "").hostname or "").lower()
    return SKIP_HOSTS.get(host)
