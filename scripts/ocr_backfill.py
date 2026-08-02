"""Backfill OCR across existing text caches.

The v1 corpus was text-extracted before the OCR fallback existed, so any
scanned-only or image-only pages in those caches sit as empty strings —
invisible to the regex pre-pass and unusable as a quote-verification
substrate. This walks every `*.pages.json` cache, finds documents with
pages below the OCR threshold that haven't been OCR'd yet, and re-runs
`extract_document(force=True)` so the fallback fires.

The bytes on disk remain the canonical source; the cache is derived data,
and each rewrite records its engine ('pypdf+tesseract') and the OCR'd page
numbers, so provenance survives the rewrite.

Idempotent: re-runs skip documents whose cache already carries `ocr_pages`
or whose pages all clear the threshold.

Usage: .venv/bin/python -u scripts/ocr_backfill.py [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dcp import extract  # noqa: E402

# Per-document wall-clock budget. Pathological PDFs (corrupt compression
# streams) can stall pypdf's per-page retry loop for a very long time —
# observed on a Thurrock EIA document. SIGALRM aborts the document and the
# backfill moves on; the skipped doc is logged for manual attention.
DOC_TIMEOUT_S = 600


class _DocTimeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise _DocTimeout()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    caches = sorted(glob.glob("data/raw_text/**/*.pages.json", recursive=True))
    todo = []
    for c in caches:
        payload = json.loads(Path(c).read_text())
        if payload.get("ocr_pages"):
            continue
        if not payload["pages"]:
            continue  # never parsed (encrypted / non-PDF) — not an OCR case
        n_empty = sum(1 for t in payload["pages"]
                      if len(t.strip()) < extract.OCR_MIN_CHARS)
        if n_empty:
            todo.append((c, payload, n_empty))

    print(f"{len(todo)} cached documents need OCR ({sum(n for _, _, n in todo)} pages)")
    if args.limit:
        todo = todo[: args.limit]

    summary = {"docs_ocrd": 0, "pages_ocrd": 0, "docs_unchanged": 0, "missing_bytes": 0}
    t0 = time.time()
    for i, (cache_file, payload, n_empty) in enumerate(todo, 1):
        rel = Path(cache_file).relative_to("data/raw_text")
        source = rel.parts[0]
        application_ref = "/".join(rel.parts[1:-1])
        bytes_path = Path(payload["bytes_path"])
        if not bytes_path.exists():
            summary["missing_bytes"] += 1
            print(f"[{i}/{len(todo)}] MISSING BYTES {payload['bytes_path']}")
            continue
        if args.dry_run:
            print(f"[{i}/{len(todo)}] DRY {application_ref} ({n_empty} pages)")
            continue
        signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(DOC_TIMEOUT_S)
        try:
            doc = extract.extract_document(
                source=source, application_ref=application_ref,
                sha=payload["sha"], bytes_path=bytes_path, force=True,
            )
        except _DocTimeout:
            summary.setdefault("timed_out", 0)
            summary["timed_out"] += 1
            print(f"[{i}/{len(todo)}] TIMEOUT after {DOC_TIMEOUT_S}s: "
                  f"{application_ref} {bytes_path.name} — skipped, needs manual attention")
            continue
        finally:
            signal.alarm(0)
        if doc.ocr_pages:
            summary["docs_ocrd"] += 1
            summary["pages_ocrd"] += len(doc.ocr_pages)
            print(f"[{i}/{len(todo)}] {application_ref} "
                  f"{bytes_path.name}: OCR'd {len(doc.ocr_pages)}/{n_empty} pages "
                  f"({time.time()-t0:.0f}s elapsed)")
        else:
            summary["docs_unchanged"] += 1

    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()
