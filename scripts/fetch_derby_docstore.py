"""Download Derby documents from the council's own document server.

`eplanning.derby.gov.uk`'s Idox documents tab answers HTTP 200 with
"Permission Denied … restricted to specific users", and the 8 August
fetch settled five live applications as `none_published` on that page.
The register's *External Documents* tab (`activeTab=externalDocuments`,
Luke's pointer, 2026-09-06) links to the council's own store:

    https://docs.derby.gov.uk/padocumentserver/index.html?caseref=<ref>

whose page loads `MainTable.aspx?caseref=<ref>` — a table of type,
description, published date and a document id, headed "Documents found
N" — and each row opens `DownloadDocument.aspx?docid=<id>`, which serves
the PDF to a plain GET with no session (verified 2026-09-06 on
19/01343/FUL, 110 KB, `application/pdf`).

The listing is typed, the Newport docstore's lesson: a page carrying
"Documents found" with no rows is the store's own empty and settles
through `classify_outcome`; a page without that marker is unrecognised
and stays retryable. Bytes land in the standard per-application layout,
recorded in `documents` with the download URL as provenance; the
outcome is recorded under the adapter `derby_docstore` so the fold shows
which route made the check. Idempotent: URL-known documents with bytes
on disk are skipped.

Usage:
    .venv/bin/python scripts/fetch_derby_docstore.py --dry-run
    .venv/bin/python scripts/fetch_derby_docstore.py
    .venv/bin/python scripts/fetch_derby_docstore.py --ref Derby/19/01343/FUL
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.acquisition_outcome import SETTLED, classify_outcome, record  # noqa: E402
from dcp.sources import idox as _idox  # noqa: E402

log = logging.getLogger("derby_docstore")

ADAPTER = "derby_docstore"
STORE = "https://docs.derby.gov.uk/padocumentserver"
UA = ("Mozilla/5.0 (compatible; datacentre_planning research; "
      "+mailto:luke.hoyland@gmail.com)")

ROW_RE = re.compile(r"<tr[^>]*row-data[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
FOUND_RE = re.compile(r"Documents found\s*</td>\s*<td[^>]*>\s*(\d+)", re.S)

# Live members and the adjacent-power class, holding nothing — the
# fetch queue's scope, narrowed to Derby. `--include-held` widens it to
# every Derby application in scope, for a re-list.
COHORT = """
SELECT a.id, a.application_ref
FROM applications a
WHERE a.application_ref LIKE 'Derby/%%'
  AND EXISTS (SELECT 1 FROM site_members m JOIN sites s ON s.id = m.site_id
              WHERE m.application_id = a.id
                AND m.retired_at IS NULL AND s.retired_at IS NULL)
  AND (%s OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id))
ORDER BY a.application_ref
"""


class UnrecognisedListing(RuntimeError):
    """The store answered with a page that is not its listing — no
    "Documents found" marker. A maintenance page, a redirect to a login
    or a changed template all look like this, and none is a measurement
    of what the store holds; the outcome stays retryable."""


def listing_url(short_ref: str) -> str:
    return f"{STORE}/MainTable.aspx?caseref={short_ref}"


def download_url(docid: str) -> str:
    return f"{STORE}/DownloadDocument.aspx?docid={docid}"


def parse_listing(html: str) -> list[dict]:
    """[{docid, kind, description, published}] from `MainTable.aspx`.

    Raises `UnrecognisedListing` when the page carries no "Documents
    found" count: an empty list is returned only on the store's own
    word. The count and the rows are cross-checked, because a template
    that renders the header but paginates or hides rows would otherwise
    read as a smaller register than the store holds.
    """
    m = FOUND_RE.search(html)
    if not m:
        raise UnrecognisedListing(
            f"listing page of {len(html)} bytes carries no 'Documents found' count")
    rows = []
    for row in ROW_RE.findall(html):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                 for c in CELL_RE.findall(row)]
        if len(cells) != 4 or not cells[3].isdigit():
            raise UnrecognisedListing(f"listing row of unexpected shape: {cells!r}")
        rows.append({"kind": cells[0], "description": cells[1],
                     "published": cells[2], "docid": cells[3]})
    if len(rows) != int(m.group(1)):
        raise UnrecognisedListing(
            f"store says {m.group(1)} documents, page lists {len(rows)}")
    return rows


def _record(conn, app_id: int, summary: dict, *, dry_run: bool,
            note: str | None = None) -> None:
    """Write this application's verdict, through the shared rule —
    `classify_outcome` decides it, so this route cannot invent a verdict
    the adapters would not award."""
    outcome, detail = classify_outcome(summary)
    if note:
        detail = note if outcome in SETTLED else (f"{detail} — {note}" if detail else note)
    if dry_run:
        log.info("        would record %s (%s)", outcome, detail)
        return
    record(conn, app_id, outcome, ADAPTER, detail,
           found=summary.get("downloaded") or 0)


def fetch_one(conn, client: httpx.Client, *, app_id: int, ref: str,
              data_dir: Path, delay: float, dry_run: bool) -> dict:
    short = ref.split("/", 1)[1]
    r = client.get(listing_url(short))
    r.raise_for_status()
    docs = parse_listing(r.text)
    time.sleep(delay)
    with conn.cursor() as cur:
        cur.execute("SELECT url, bytes_path FROM documents WHERE application_id=%s", (app_id,))
        prior = {u: bp for u, bp in cur.fetchall() if bp}
    summary = {"links_found": len(docs), "downloaded": 0,
               "skipped_existing": 0, "errors": 0}
    if not docs:
        summary["error_class"] = "no_documents"
        _record(conn, app_id, summary, dry_run=dry_run,
                note="council document server listed the case and answered "
                     "'Documents found 0'")
        return summary
    if dry_run:
        for d in docs:
            log.info("        would fetch %-28s %s", d["kind"], d["description"][:60])
        return summary
    for d in docs:
        url = download_url(d["docid"])
        bp = prior.get(url)
        if bp and Path(bp).exists():
            summary["skipped_existing"] += 1
            continue
        try:
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.content
            repo.check_document_body(body, url=url)
        except Exception as exc:
            log.warning("  FAIL %s (%s): %s", d["docid"], d["description"][:50], exc)
            summary["errors"] += 1
            time.sleep(delay)
            continue
        sha = hashlib.sha256(body).hexdigest()
        ctype = resp.headers.get("content-type") or ""
        ext = "pdf" if "pdf" in ctype or body[:4] == b"%PDF" else "bin"
        target = _idox._bytes_path(data_dir, ref, sha, ext)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(conn, application_id=app_id, url=url,
                             kind=d["kind"], content_sha256=sha,
                             bytes_path=str(target))
        conn.commit()
        summary["downloaded"] += 1
        time.sleep(delay)
    _idox._write_manifest(conn, application_id=app_id, application_ref=ref,
                          app_dir=_idox._app_dir(data_dir, ref), summary=summary)
    _record(conn, app_id, summary, dry_run=dry_run)
    conn.commit()
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ref", help="one application, e.g. Derby/19/01343/FUL")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=5.0)
    p.add_argument("--include-held", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn, conn.cursor() as cur:
        if args.ref:
            cur.execute("SELECT id, application_ref FROM applications WHERE application_ref=%s",
                        (args.ref,))
        else:
            cur.execute(COHORT, (args.include_held,))
        targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]
    log.info("%d Derby applications to try at the council's document server", len(targets))
    if not targets:
        return 0

    totals = {"apps": 0, "stored": 0, "existing": 0, "empty": 0, "errors": 0}
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=90) as client, db.connect() as conn:
        repo.ensure_source(conn, name=ADAPTER, kind="council", base_url=STORE)
        conn.commit()
        for i, (app_id, ref) in enumerate(targets, 1):
            totals["apps"] += 1
            try:
                s = fetch_one(conn, client, app_id=app_id, ref=ref,
                              data_dir=args.data_dir, delay=args.delay,
                              dry_run=args.dry_run)
            except UnrecognisedListing as exc:
                log.error("[%d/%d] %s unrecognised listing: %s", i, len(targets), ref, exc)
                totals["errors"] += 1
                _record(conn, app_id, {"errors": 1, "links_found": 0,
                                       "error_class": "unrecognised_listing"},
                        dry_run=args.dry_run, note=str(exc)[:120])
                continue
            except Exception as exc:
                log.error("[%d/%d] %s failed: %s", i, len(targets), ref, exc)
                totals["errors"] += 1
                _record(conn, app_id, {"errors": 1, "links_found": 0,
                                       "error_class": type(exc).__name__},
                        dry_run=args.dry_run, note=str(exc)[:120])
                continue
            if not s["links_found"]:
                totals["empty"] += 1
            totals["stored"] += s["downloaded"]
            totals["existing"] += s["skipped_existing"]
            totals["errors"] += s["errors"]
            log.info("[%d/%d] %-22s listed=%d stored=%d existing=%d errors=%d",
                     i, len(targets), ref, s["links_found"], s["downloaded"],
                     s["skipped_existing"], s["errors"])
    log.info("done: %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
