"""Fetch a Planning Inspectorate NSIP project's published document library.

Nationally significant projects are consented by PINS rather than by a
council, so their documents live outside every portal adapter this project
has. That leaves them invisible: SDC M40 Campus (EN0110030) is a 300MW IT
load data centre campus that reached us as a single register row with no
documents behind it.

PINS publishes no API for the library, but the document URLs are stable
and predictable —

    https://nsip-documents.planninginspectorate.gov.uk/published-documents/
        <PROJECT>-<SEQ>-<Title>.pdf

— so the library page is read once for the list, and the URLs are fetched
politely into the same canonical store as everything else: content-hashed,
deduplicated by (application_id, content_sha256), path recorded on the
document row. From there the deep-read, the verbatim gate and the exports
treat them exactly like council documents, which is the point.

The document list is passed in rather than scraped, because the library
page is JavaScript-rendered and a scraper would be the fragile part of an
otherwise simple job. Re-running with the same list is a no-op.

Usage:
    scripts/fetch_nsip_documents.py --ref EN0110030 --urls-file urls.txt
    scripts/fetch_nsip_documents.py --ref EN0110030 --url <one url>
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db, repo  # noqa: E402

USER_AGENT = ("datacentre-planning-research/1.0 "
              "(journalism; contact via github.com/hoyla)")
STORE = ROOT / "data" / "raw" / "documents"


def kind_from_url(url: str) -> str:
    """A readable document kind from the filename PINS publishes.

    The sequence prefix (EN0110030-000026-) is stripped: it identifies the
    document within the library but says nothing about what it is, and the
    deep-read's tiering reads this field.
    """
    name = unquote(url.rsplit("/", 1)[-1])
    name = name.rsplit(".", 1)[0]
    parts = name.split("-", 2)
    return (parts[2] if len(parts) == 3 else name).strip()


def fetch_one(client, conn, *, application_id: int, ref: str,
              url: str) -> tuple[str, str]:
    """Fetch and store one document. Returns (status, detail)."""
    r = client.get(url)
    if r.status_code != 200:
        return "error", f"HTTP {r.status_code}"
    body = r.content
    if not body:
        return "error", "empty body"
    sha = hashlib.sha256(body).hexdigest()

    out_dir = STORE / ref.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{sha[:16]}.pdf"
    if not path.exists():
        path.write_bytes(body)

    repo.record_document(
        conn, application_id=application_id, url=url,
        content_sha256=sha, bytes_path=str(path),
        kind=kind_from_url(url))
    conn.commit()
    return "ok", f"{len(body):,} bytes -> {path.name}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True,
                    help="NSIP project reference, e.g. EN0110030")
    ap.add_argument("--url", action="append", default=[],
                    help="Document URL; repeatable.")
    ap.add_argument("--urls-file", type=Path,
                    help="File of document URLs, one per line.")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="Seconds between requests. PINS is a public "
                         "service; there is no hurry.")
    args = ap.parse_args()

    urls = list(args.url)
    if args.urls_file:
        urls += [ln.strip() for ln in args.urls_file.read_text().splitlines()
                 if ln.strip() and not ln.startswith("#")]
    if not urls:
        sys.exit("no URLs given")

    import httpx
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM applications WHERE application_ref = %s",
                    (args.ref,))
        row = cur.fetchone()
        if row is None:
            sys.exit(f"no application row for {args.ref} — index the NSIP "
                     f"register first (dcp.cli index --source nsip)")
        application_id = row[0]

        ok = errors = 0
        with httpx.Client(headers={"User-Agent": USER_AGENT},
                          timeout=120.0, follow_redirects=True) as client:
            for i, url in enumerate(urls, 1):
                try:
                    status, detail = fetch_one(
                        client, conn, application_id=application_id,
                        ref=args.ref, url=url)
                except Exception as exc:
                    status, detail = "error", f"{type(exc).__name__}: {exc}"
                if status == "ok":
                    ok += 1
                else:
                    errors += 1
                print(f"  [{i}/{len(urls)}] {status:5} "
                      f"{kind_from_url(url)[:56]:56} {detail}")
                if i < len(urls):
                    time.sleep(args.delay)

    print(f"\n{ok} stored, {errors} failed")


if __name__ == "__main__":
    main()
