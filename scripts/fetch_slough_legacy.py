#!/usr/bin/env python3
"""Fetch Slough documents from the legacy sbcplanning.co.uk system.

Slough's current register (Agile) reports zero documents for these
applications, and it is telling the truth: the documents never moved off
the council's previous system. The application page says so in passing —
"View the decision notice for this application at Planning Search
(sbcplanning.co.uk)" — which is the only pointer that the material exists
at all. Read as a portal problem, this looks like 37 applications a
council declined to publish.

The legacy system is a PHP search over a static PDF store. Its filenames
are a lossy transformation of the planning reference (`P/00072/096`
becomes `P72-96`, leading zeros stripped, extra documents suffixed
`(2)`, `(3)`), and the series differ enough — `P/`, `SMI/`, `T/`, some
with parenthetical suffixes of their own — that reconstructing them would
be guesswork. So this asks the site's own search to resolve each
reference and takes the links it returns.

No browser required, unlike the other blocked registers: a plain session
with a Referer works. An earlier attempt without one appeared to return
nothing, which is what sent this down the browser route in the first
place.

    scripts/fetch_slough_legacy.py --dry-run
    scripts/fetch_slough_legacy.py
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from dcp import db, repo  # noqa: E402
from dcp.sources import idox as _idox  # noqa: E402

log = logging.getLogger("slough_legacy")

BASE = "https://www.sbcplanning.co.uk"
SEARCH_PAGE = f"{BASE}/plansearch.php"
SEARCH = f"{BASE}/search.php"
UA = ("Mozilla/5.0 (compatible; datacentre_planning research; "
      "+mailto:luke.hoyland@gmail.com)")

COHORT = """
    SELECT a.id, a.application_ref
    FROM applications a
    WHERE a.url ILIKE '%%agileapplications.co.uk/slough%%'
      AND (%s OR NOT EXISTS (
            SELECT 1 FROM documents d WHERE d.application_id = a.id))
    ORDER BY a.application_ref
"""

PDF_RE = re.compile(r'/sbcp/[^"\']+?\.pdf', re.I)


def search_documents(client: httpx.Client, reference: str) -> list[str]:
    """Absolute PDF URLs the legacy search returns for a reference."""
    r = client.post(SEARCH, data={"st": reference, "DBName": "planapp",
                                  "Searchfield": "Number",
                                  "plannsearch": "Search for number"},
                    headers={"Referer": SEARCH_PAGE})
    r.raise_for_status()
    # 'scaling.pdf' is a help document linked on every results page.
    return sorted({urljoin(BASE, p) for p in PDF_RE.findall(r.text)
                   if "scaling" not in p.lower()})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--delay", type=float, default=2.5)
    p.add_argument("--include-held", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(COHORT, (args.include_held,))
        targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]
    log.info("%d Slough applications to try", len(targets))
    if not targets:
        return 0

    totals = {"apps": 0, "stored": 0, "existing": 0, "empty": 0, "errors": 0}
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True,
                      timeout=90) as client, db.connect() as conn:
        client.get(SEARCH_PAGE)           # establish the session
        source_id = repo.ensure_source(
            conn, name="slough_legacy", kind="council", base_url=BASE)
        conn.commit()

        for i, (app_id, ref) in enumerate(targets, 1):
            short = ref.split("/", 1)[1]
            try:
                urls = search_documents(client, short)
            except Exception as exc:
                log.error("[%d/%d] %s search failed: %s", i, len(targets), ref, exc)
                totals["errors"] += 1
                continue
            time.sleep(args.delay)
            if not urls:
                totals["empty"] += 1
                log.info("[%d/%d] %-22s no documents in the legacy store",
                         i, len(targets), short)
                continue
            if args.dry_run:
                log.info("[%d/%d] %-22s %d documents", i, len(targets), short, len(urls))
                totals["apps"] += 1
                continue

            with conn.cursor() as cur:
                cur.execute("SELECT url FROM documents WHERE application_id = %s",
                            (app_id,))
                held = {u for (u,) in cur.fetchall()}
            app_dir = (args.data_dir / "raw" / "documents"
                       / _idox._sanitised_ref(ref))
            stored = skipped = failed = 0
            for u in urls:
                if u in held:
                    skipped += 1; totals["existing"] += 1; continue
                try:
                    r = client.get(u)
                    r.raise_for_status()
                except Exception as exc:
                    log.warning("   %s: %s", u.split("/")[-1], str(exc)[:60])
                    failed += 1; totals["errors"] += 1; continue
                data = r.content
                if not data.startswith(b"%PDF"):
                    log.warning("   %s is not a PDF (%r)", u.split("/")[-1], data[:8])
                    failed += 1; totals["errors"] += 1; continue
                sha = hashlib.sha256(data).hexdigest()
                target = app_dir / f"{sha[:16]}.pdf"
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                repo.record_document(
                    conn, application_id=app_id, url=u, kind="legacy register",
                    content_sha256=sha,
                    bytes_path=(str(target.relative_to(args.data_dir.parent))
                                if target.is_relative_to(args.data_dir.parent)
                                else str(target)))
                stored += 1; totals["stored"] += 1
                time.sleep(args.delay)
            conn.commit()
            if stored:
                _idox._write_manifest(
                    conn, application_id=app_id, application_ref=ref,
                    app_dir=app_dir,
                    summary={"ref": ref, "links_found": len(urls),
                             "downloaded": stored, "skipped_existing": skipped,
                             "errors": failed})
            totals["apps"] += 1
            log.info("[%d/%d] %-22s found=%d new=%d held=%d err=%d | total %d",
                     i, len(targets), short, len(urls), stored, skipped, failed,
                     totals["stored"])

    log.info("done: %(apps)d applications with documents, %(stored)d stored, "
             "%(existing)d already held, %(empty)d with none in the legacy "
             "store, %(errors)d errors", totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
