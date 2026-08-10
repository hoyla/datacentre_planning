"""Extract page-indexed text for the whole document corpus.

The prerequisite for deep-read, and independent of which model does the
reading: pypdf for the text layer, OCR fallback (tesseract by default)
for pages with none. Results are cached per document as
`data/raw_text/<source>/<application_ref>/<sha[:16]>.pages.json`, so this
is idempotent and resumable — an interrupted run re-reads nothing.

Deliberately CPU-only and offline: no model, no network, no API quota.
It also makes the deep-read's page-selection measurable, since pages
cannot be scored for relevance until they are text.

**Everything is extracted, including drawings.** An earlier version
skipped graphical documents on the grounds that they carry no prose,
which was wrong twice over: a proposed site plan often labels the energy
centre, an elevation may annotate a generator enclosure, and plant
layouts carry specifications that never appear in prose at all. It also
baked an analytical judgement into the cheapest and most reusable layer,
against the project's first principle — ingest broadly, analyse second.
Relevance is decided at deep-read time (dcp/deepread_select.py), where
it can be revisited without re-reading 70GB of PDFs. Pass
--skip-drawings if a fast partial pass is genuinely wanted.

Usage:
    .venv/bin/python -u scripts/extract_text_corpus.py [--workers 4]
    .venv/bin/python -u scripts/extract_text_corpus.py --stats
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from dcp import db, deepread_select as sel  # noqa: E402
from dcp import extract  # noqa: E402


def _one(args: tuple) -> tuple[str, int, bool, str | None]:
    """Extract one document. Runs in a worker process."""
    ref, sha, path_s, ocr, force = args
    try:
        doc = extract.extract_document(
            source="documents", application_ref=ref, sha=sha,
            bytes_path=Path(path_s), ocr=ocr, force=force)
        pages = doc.pages if isinstance(doc.pages, list) else []
        ocr_used = bool(getattr(doc, "ocr_pages", None))
        return sha, len(pages), ocr_used, None
    except Exception as exc:  # a corrupt PDF must not stop the corpus
        return sha, 0, False, f"{type(exc).__name__}: {exc}"[:160]


def load_documents(*, include_drawings: bool) -> list[tuple]:
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT a.application_ref, d.content_sha256, d.bytes_path, d.kind
            FROM documents d JOIN applications a ON a.id = d.application_id
            WHERE d.bytes_path IS NOT NULL
            ORDER BY a.application_ref, d.id""")
        rows = cur.fetchall()
    out = []
    skipped = 0
    for ref, sha, bp, kind in rows:
        tier, _reason = sel.classify_kind(kind)
        if tier == "skip" and not include_drawings:
            skipped += 1
            continue
        out.append((ref, sha, bp, kind))
    print(f"{len(rows)} documents; {skipped} graphical skipped; {len(out)} to extract")
    return out


def partition(docs: list[tuple]) -> tuple[list[tuple], set[str], list[tuple]]:
    """Split documents into (to-do, stale-shas, already-done).

    A cache is not enough on its own: an earlier extractor wrote an empty
    cache with `engine: "skipped"` for every format it could not load, so
    1,119 documents present as extracted-and-empty when nothing has read
    them. Those are re-read, with `force` so the stale cache is replaced.

    Only non-PDFs are checked for staleness. Reading the engine means
    parsing the cache payload, which holds the document's whole text, and
    a PDF cache never carries a stale engine.
    """
    todo: list[tuple] = []
    stale: set[str] = set()
    done: list[tuple] = []
    for d in docs:
        ref, sha, bytes_path = d[0], d[1], d[2]
        cache = extract.cache_path_for("documents", ref, sha)
        if not cache.exists():
            todo.append(d)
        elif (not str(bytes_path).lower().endswith(".pdf")
                and extract.is_stale_cache(cache)):
            stale.add(sha)
            todo.append(d)
        else:
            done.append(d)
    return todo, stale, done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-ocr", action="store_true",
                    help="Skip the OCR fallback (much faster; scanned pages "
                         "yield no text).")
    ap.add_argument("--skip-drawings", action="store_true",
                    help="Exclude graphical documents (faster, but their "
                         "annotations — plant labels, generator ratings — "
                         "are then never seen).")
    ap.add_argument("--stats", action="store_true",
                    help="Report cache coverage and exit.")
    args = ap.parse_args()

    docs = load_documents(include_drawings=not args.skip_drawings)

    todo, stale, cached = partition(docs)
    print(f"already extracted: {len(cached)}; to do: {len(todo)} "
          f"(of which {len(stale)} re-read after a stale cache)")
    if args.stats:
        return
    if args.limit:
        todo = todo[: args.limit]

    t0 = time.time()
    done = failed = ocr_docs = pages_total = 0
    tasks = [(ref, sha, bp, not args.no_ocr, sha in stale)
             for ref, sha, bp, _kind in todo]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_one, t): t for t in tasks}
        for fut in as_completed(futures):
            sha, npages, ocr_used, err = fut.result()
            done += 1
            if err:
                failed += 1
                if failed <= 12:
                    print(f"  failed {sha[:12]}: {err}")
            else:
                pages_total += npages
                ocr_docs += 1 if ocr_used else 0
            if done % 200 == 0:
                rate = done / (time.time() - t0)
                eta = (len(tasks) - done) / rate / 3600 if rate else 0
                print(f"  {done}/{len(tasks)}  {pages_total} pages  "
                      f"{failed} failed  {rate:.1f} docs/s  eta {eta:.1f}h")
    el = time.time() - t0
    print(f"\ndone: {done} documents in {el/60:.0f} min, {pages_total} pages, "
          f"{ocr_docs} needed OCR, {failed} failed")


if __name__ == "__main__":
    main()
