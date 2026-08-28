"""Turn a saved WebDrawer case-file page into a ranked download list.

Camden's planning register (and other councils running the same
Content Manager "WebDrawer" front end) sits behind a Cloudflare
challenge, so nothing here fetches: the case-file HTML is saved from a
browser by a person, and this reads it.

What it produces is a triage list, because the raw record count is
misleading. Camden's 2023/4648/P reports **201 records**, of which a
large share is consultation responses, tree surveys and drawing issue
sheets. For an investigation into power infrastructure, perhaps twenty
of the 201 matter.

So each record is scored against the vocabulary this project actually
turns on — energy centres, substations, generators, grid connections,
air quality, cooling — and the output is ordered with those first. The
full list is still written: **the ranking decides reading order, never
what exists.** Nothing is dropped, and the summary says what scored
zero and why.

Many titles end in a bracketed number (`… Statement(2)`). Whether that
marks a duplicate upload or a segment of a chopped-up file is not
settled — see `dedupe` — so nothing is collapsed unless `--dedupe` is
passed. The asymmetry decides the default: keeping a duplicate costs a
download, dropping a segment costs evidence.

Usage:
    scripts/parse_webdrawer_casefile.py data/raw/camden_html/ \\
        [--out data/exports/camden_documents.csv] [--top 25]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# A row is three cells: date created, a titled link, a document-type link.
# Both links point at the same record, so the href is taken once.
_ROW = re.compile(
    r'<tr>\s*'
    r'<td[^>]*>\s*([\d/]{8,10}\s+[\d:]{5,8})\s*</td>\s*'
    r'<td[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</td>\s*'
    r'<td[^>]*>\s*<a[^>]+href="[^"]+"[^>]*>(.*?)</a>\s*</td>',
    re.S | re.I)
_APPNO = re.compile(r"Application No:.*?<td[^>]*>\s*([^<\s][^<]*?)\s*</td>", re.S | re.I)
_RECORDS = re.compile(r"Records:.*?<td[^>]*>\s*(\d+)\s*</td>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")

# What this investigation turns on. Weighted so that a document naming
# an energy centre or a generator outranks one that merely mentions
# air quality, and so a superseded copy sinks below its replacement.
SIGNAL = {
    r"energy\s*centre|\bSWEC\b": 10,
    r"substation|\bISS\b|incoming\s*supply": 9,
    r"generator|standby|\bCHP\b|combined\s*heat": 9,
    r"grid|distribution|electrical|\bkVA?\b|\bMVA?\b|\bMW\b": 7,
    r"energy\s*(and|&)\s*sustainability|carbon|emission": 6,
    r"air\s*quality": 5,
    r"cooling|chiller|plant\s*room": 5,
    r"noise": 4,
    r"planning\s*statement|design\s*(and|&)\s*access": 3,
    r"decision\s*notice|committee\s*report|officer\s*report": 3,
    r"application\s*form|schedule\s*of\s*works": 2,
}
_PENALTY = re.compile(r"supersed|tree|arboricultur|ecolog|archaeolog|"
                      r"daylight|sunlight|heritage|travel\s*plan", re.I)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub("", fragment)).strip()


def score(title: str, doc_type: str) -> int:
    blob = f"{title} {doc_type}"
    total = sum(w for pat, w in SIGNAL.items() if re.search(pat, blob, re.I))
    if _PENALTY.search(blob):
        total -= 6
    return total


def parse(html: str, base: str) -> tuple[str, int | None, list[dict]]:
    """(application number, records the page claims, records found)."""
    app = (_APPNO.search(html) or [None, ""])[1].strip()
    claimed = _RECORDS.search(html)
    out = []
    for created, href, title, doc_type in _ROW.findall(html):
        t, dt = _text(title), _text(doc_type)
        if not t:
            continue
        rec = re.search(r"/Record/(\d+)/", href)
        out.append({
            "application": app,
            "record_id": rec.group(1) if rec else "",
            "created": created.strip(),
            "title": t,
            "doc_type": dt,
            "score": score(t, dt),
            "url": urljoin(base, href.replace("&amp;", "&")),
        })
    return app, int(claimed.group(1)) if claimed else None, out


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    """Collapse `Foo` and `Foo(2)` — OPT-IN ONLY, and off by default.

    What the `(N)` suffix means is not settled. It reads as a name
    collision from the bundle being uploaded twice: the same set appears
    at 11:39-11:45 all suffixed and at 11:45-11:52 unsuffixed, including
    single-file items that could not be segmented (`03. Covering
    Letter(2)`), and documents that ARE segmented say so separately
    (`_Part 1`, `_Part 2`), then appear again as `_Part 1(2)`.

    Luke reads it as segmentation — the file chopped into parts, the
    number naming the part (2026-08-28). If he is right, collapsing them
    deletes half of every large document, which is why this is opt-in:
    keeping a duplicate costs a download, dropping a segment costs
    evidence, and only one of those is recoverable. Settle it by
    downloading both `15. Energy and Sustainability Statement` (record
    10297390) and its `(2)` (10297329) and comparing the bytes.
    """
    def key(r):
        t = re.sub(r"\(\d+\)\s*$", "", r["title"]).strip().lower()
        return (r["application"], t)
    best: dict[tuple, dict] = {}
    for r in sorted(rows, key=lambda r: r["created"]):
        best[key(r)] = r
    return list(best.values()), len(rows) - len(best)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path,
                    help="A saved .html case file, or a folder of them.")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "exports" / "webdrawer_documents.csv")
    ap.add_argument("--base", default="https://planningrecords.camden.gov.uk",
                    help="Origin the relative hrefs hang off.")
    ap.add_argument("--top", type=int, default=25,
                    help="How many to print as the suggested shortlist.")
    ap.add_argument("--dedupe", action="store_true",
                    help="Collapse `Foo` and `Foo(2)` into one row. Off by "
                         "default: if the suffix is a segment number rather "
                         "than a duplicate, this drops real content.")
    args = ap.parse_args()

    files = ([args.source] if args.source.is_file()
             else sorted(args.source.glob("*.html")))
    if not files:
        print(f"no .html files in {args.source}", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for f in files:
        app, claimed, found = parse(f.read_text(errors="replace"), args.base)
        rows += found
        # The page states its own record count, so a parse that sees
        # fewer is reporting a gap in this script, not in the register.
        note = ""
        if claimed is not None and claimed != len(found):
            note = f"  ← page claims {claimed}, parsed {len(found)}"
        print(f"{f.name:<34} {app or '?':<16} {len(found):>4} records{note}")

    if args.dedupe:
        kept, dropped = dedupe(rows)
    else:
        kept, dropped = rows, 0
    kept.sort(key=lambda r: (-r["score"], r["application"], r["title"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["application", "score", "title",
                                           "doc_type", "created", "record_id", "url"])
        w.writeheader()
        for r in kept:
            w.writerow({k: r[k] for k in w.fieldnames})

    zero = sum(1 for r in kept if r["score"] <= 0)
    variants = sum(1 for r in kept if re.search(r"\(\d+\)\s*$", r["title"]))
    print(f"\n{len(rows)} records"
          + (f", {dropped} collapsed by --dedupe" if args.dedupe else "")
          + f" — {len(kept)} written to {args.out}")
    if variants and not args.dedupe:
        print(f"{variants} titles end in a bracketed number. Kept, because "
              f"whether that is a duplicate or a segment is unsettled — "
              f"pass --dedupe only once you have compared two of them.")
    print(f"{len(kept) - zero} score above zero; {zero} scored zero or less "
          f"(kept in the file, ranked last).")
    print(f"\nSuggested first {min(args.top, len(kept))} to download:\n")
    for r in kept[:args.top]:
        print(f"  {r['score']:>3}  {r['title'][:66]}")
        print(f"       {r['url']}")
    types = Counter(r["doc_type"] for r in kept if r["score"] <= 0)
    if types:
        print("\nScoring zero (nothing here matches the power vocabulary): "
              + ", ".join(f"{t or 'untyped'} ×{n}" for t, n in types.most_common(6)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
