"""Download Neath Port Talbot documents from the council's iDocs store.

`planningonline.npt.gov.uk`'s Idox documents tab refuses with an HTTP
200; its External Documents tab links to an Oracle APEX page,

    http://appsportal2.npt.gov.uk/ords/idocs12/f?p=Planning:2:0::NO::P2_REFERENCE:<ref>

a server-rendered results table — paged "1 - N of N" — whose rows
carry a direct `https://maps.npt.gov.uk/iDocsPublic/ShowDocument.aspx?id=<n>`
link, served to a plain GET (verified 2026-09-06: `application/pdf`,
`%PDF`). Typed as the other stores are: the "Results" count must be
present and match the rows, or the page is unrecognised and the
outcome stays retryable; an empty list only on the store's own count.
Outcomes through `classify_outcome` under `neath_docstore`.

Usage:
    .venv/bin/python scripts/fetch_neath_docstore.py --dry-run
    .venv/bin/python scripts/fetch_neath_docstore.py --ref Neath/P2024/0791
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

log = logging.getLogger("neath_docstore")

ADAPTER = "neath_docstore"
STORE = "http://appsportal2.npt.gov.uk/ords/idocs12/f?p=Planning:2:0::NO::P2_REFERENCE:"
UA = ("Mozilla/5.0 (compatible; datacentre_planning research; "
      "+mailto:luke.hoyland@gmail.com)")

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
LINK_RE = re.compile(r'href="(https?://[^"]*ShowDocument\.aspx\?id=\d+)"')
# The "Results" heading sits in another element; the pager text is "1 - 2 of 2".
RESULTS_RE = re.compile(r"\b(\d+)\s*-\s*(\d+)\s*of\s*(\d+)\b")
NO_RESULTS_RE = re.compile(r"no data found|no documents", re.I)

COHORT = """
SELECT a.id, a.application_ref
FROM applications a
WHERE a.application_ref LIKE 'Neath/%%'
  AND EXISTS (SELECT 1 FROM site_members m JOIN sites s ON s.id = m.site_id
              WHERE m.application_id = a.id
                AND m.retired_at IS NULL AND s.retired_at IS NULL)
  AND (%s OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.application_id = a.id))
ORDER BY a.application_ref
"""


class UnrecognisedListing(RuntimeError):
    """Not the store's results page for this case: no "Results a - b of
    n" count, a count that disagrees with the rows, or a row without its
    document link. Retryable."""


def listing_url(short_ref: str) -> str:
    return f"{STORE}{short_ref}"


def parse_listing(html: str) -> list[dict]:
    """[{url, kind, group, description, date, ext}] from the APEX results
    page; empty only when the page says so."""
    m = RESULTS_RE.search(re.sub(r"<[^>]+>", " ", html))
    if not m:
        if NO_RESULTS_RE.search(html):
            return []
        raise UnrecognisedListing(
            f"results page of {len(html)} bytes carries no 'a - b of n' count")
    first, last, total = (int(x) for x in m.groups())
    docs = []
    for row in ROW_RE.findall(html):
        links = LINK_RE.findall(row)
        if not links:
            continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                 for c in CELL_RE.findall(row)]
        # View | Group | Item | Title | Superseded | Date | Size Kb | Ext
        if len(cells) < 8:
            raise UnrecognisedListing(f"document row of unexpected shape: {cells!r}"[:200])
        docs.append({"url": links[0], "group": cells[1], "kind": cells[2],
                     "description": cells[3], "date": cells[5], "ext": cells[7].lower()})
    if len(docs) != total or last != total:
        raise UnrecognisedListing(
            f"store says results {first} - {last} of {total}, page lists {len(docs)}")
    return docs


def _record(conn, app_id: int, summary: dict, *, dry_run: bool,
            note: str | None = None) -> None:
    outcome, detail = classify_outcome(summary)
    if note:
        detail = note if outcome in SETTLED else (f"{detail} — {note}" if detail else note)
    if dry_run:
        log.info("        would record %s (%s)", outcome, detail)
        return
    record(conn, app_id, outcome, ADAPTER, detail, found=summary.get("downloaded") or 0)


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
                note="iDocs store found the case and listed no documents")
        return summary
    if dry_run:
        for d in docs:
            log.info("        would fetch %-22s %s", d["kind"][:22], d["description"][:60])
        return summary
    for d in docs:
        url = d["url"]
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
            log.warning("  FAIL %s (%s): %s", url, d["description"][:50], exc)
            summary["errors"] += 1
            time.sleep(delay)
            continue
        sha = hashlib.sha256(body).hexdigest()
        ctype = resp.headers.get("content-type") or ""
        ext = ("pdf" if "pdf" in ctype or body[:4] == b"%PDF"
               else (d["ext"] if d["ext"].isalnum() and len(d["ext"]) <= 4 else "bin"))
        target = _idox._bytes_path(data_dir, ref, sha, ext)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        repo.record_document(conn, application_id=app_id, url=url,
                             kind=d["kind"], content_sha256=sha, bytes_path=str(target))
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
    p.add_argument("--ref")
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
    log.info("%d Neath application(s) to try at the iDocs store", len(targets))
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
            log.info("[%d/%d] %-20s listed=%d stored=%d existing=%d errors=%d",
                     i, len(targets), ref, s["links_found"], s["downloaded"],
                     s["skipped_existing"], s["errors"])
    log.info("done: %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
