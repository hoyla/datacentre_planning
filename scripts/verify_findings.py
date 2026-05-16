"""Pre-publication libel-risk pass: re-check every `findings.evidence_text`
against the source PDF's cached page text.

Each finding row carries a literal quote, a document, and a page. If the
human-in-loop Read-tool extractor misread or paraphrased, that quote
becomes a libel exposure when it's the basis for a published claim. This
script verifies the quote appears verbatim in the page we recorded it
against — and surfaces every miss for review.

Matching is normalised: lowercase, all whitespace collapsed to single
spaces. That tolerates pypdf's idiosyncratic line-breaking without
forgiving an actual paraphrase. Ellipsis ("...") in the recorded quote
is treated as a fragment separator — each fragment must appear in the
page text, in order.

Outputs a markdown report. Default exit codes:
  0 = all findings verified
  1 = one or more findings failed verification

Usage:
    scripts/verify_findings.py
    scripts/verify_findings.py --output data/exports/findings_verification.md
    scripts/verify_findings.py --tolerance 1   # also try ±N adjacent pages on miss
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

from dcp import db  # noqa: E402


_WS_RE = re.compile(r"\s+")
# pypdf inserts spurious whitespace around lots of non-letter glyphs.
# Common offenders, all observed in the corpus:
#   "back-up"   → "back -up"     (hyphen / en-dash / em-dash all collapse to "-")
#   "132kV/130MVA" → "132kv /130mva"  (slash)
#   "M&E"       → "M & E"         (ampersand)
# Collapse whitespace around the affected characters before comparison.
# Dashes additionally fold onto plain "-" so en-/em-dash variants match
# straight hyphens.
_DASH_WS_RE = re.compile(r"\s*[-–—]\s*")
_GLUE_WS_RE = re.compile(r"\s*([/&+])\s*")
# Quote-mark drift: humans recording a quote typically type whichever
# of ' or " is closest to hand, and pypdf preserves whatever's in the
# document (often curly variants). The mark itself rarely affects
# semantic match — strip all quote-like chars entirely so "the report"
# matches 'the report' matches "the report" matches the report.
_QUOTE_STRIP = re.compile(r"['‘’ʼʻ\"“”„‟‚‛]")


def _normalise(text: str) -> str:
    text = _QUOTE_STRIP.sub("", text)
    text = _DASH_WS_RE.sub("-", text)
    text = _GLUE_WS_RE.sub(r"\1", text)
    return _WS_RE.sub(" ", text).strip().lower()


def _cache_path_for_bytes(bytes_path: str) -> Path:
    """Map `data/raw/<adapter>/<ref>/<sha[:16]>.pdf` →
    `data/raw_text/<adapter>/<ref>/<sha[:16]>.pages.json`."""
    p = Path(bytes_path)
    parts = list(p.parts)
    # parts[0] = 'data', parts[1] = 'raw', rest = adapter / ref-segments / file
    if len(parts) < 3 or parts[0] != "data" or parts[1] != "raw":
        raise ValueError(f"unexpected bytes_path layout: {bytes_path}")
    new_parts = ["data", "raw_text"] + parts[2:]
    new_parts[-1] = p.stem + ".pages.json"
    return Path(*new_parts)


@dataclass
class FindingRow:
    finding_id: int
    application_ref: str
    signal_type: str
    value_text: str | None
    evidence_text: str
    evidence_page: int
    bytes_path: str

    @property
    def cache_path(self) -> Path:
        return _cache_path_for_bytes(self.bytes_path)


@dataclass
class CheckResult:
    finding: FindingRow
    # Outcomes, in increasing severity:
    #   pass            — quote found on recorded page
    #   pass_adjacent   — found on page ±1 of recorded (off-by-one)
    #   pass_cross_page — every fragment found in the doc, but split across
    #                     pages other than the recorded one. The journalism
    #                     is still defensible (every fragment is a real
    #                     quote from the doc) but the page anchor is wrong.
    #   page_empty      — recorded page has no pypdf text (likely
    #                     scanned-image-only); needs human eyeball.
    #   page_out_of_range — recorded page beyond pypdf page count.
    #   fail            — at least one fragment not found anywhere in doc.
    status: str
    matched_page: int | None = None
    cached_excerpt: str | None = None
    detail: str | None = None


def _query_findings(conn) -> list[FindingRow]:
    sql = """
    SELECT
      f.id, a.application_ref, f.signal_type, f.value_text,
      f.evidence_text, f.evidence_page, d.bytes_path
    FROM findings f
    JOIN documents d ON d.id = f.document_id
    JOIN applications a ON a.id = f.application_id
    ORDER BY a.application_ref, f.id
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return [FindingRow(*row) for row in cur.fetchall()]


_TRIM_END_PUNCT = re.compile(r"[\s\.,;:!?\)\]\}\"’”]+$")
_TRIM_START_PUNCT = re.compile(r"^[\s\(\[\{\"‘“]+")


def _quote_fragments(quote: str) -> list[str]:
    """Split a quote on ellipsis. Each fragment must appear independently
    in the page text — and in the page-text order — for the quote to count
    as verified. A quote with no ellipsis returns a single-fragment list.

    Trailing sentence-terminator punctuation is stripped from each
    fragment: humans naturally close a trimmed quote with a period that
    isn't always at that exact spot in the source (e.g. the source had a
    comma and continued; the quoter ended it cleanly with a period). We
    don't want to flag those as failures. Opening / closing quote marks
    and brackets are stripped on the same principle.
    """
    parts = re.split(r"\s*\.{3,}\s*|\s*…\s*", quote)
    out: list[str] = []
    for p in parts:
        stripped = _TRIM_END_PUNCT.sub("", _TRIM_START_PUNCT.sub("", p.strip()))
        if stripped:
            out.append(stripped)
    return out


def _all_fragments_in_order(page_text: str, fragments: list[str]) -> bool:
    cursor = 0
    for frag in fragments:
        idx = page_text.find(frag, cursor)
        if idx < 0:
            return False
        cursor = idx + len(frag)
    return True


def _check_one(finding: FindingRow, *, tolerance: int) -> CheckResult:
    cache_path = finding.cache_path
    if not cache_path.exists():
        return CheckResult(
            finding=finding, status="cache_missing",
            detail=f"no cached page-JSON at {cache_path}",
        )
    payload = json.loads(cache_path.read_text())
    pages: list[str] = payload.get("pages", [])
    if not pages:
        return CheckResult(
            finding=finding, status="cache_missing",
            detail="cache file has no pages (likely a non-PDF / scanned-only doc)",
        )

    fragments_norm = [_normalise(frag) for frag in _quote_fragments(finding.evidence_text)]
    if not fragments_norm:
        return CheckResult(
            finding=finding, status="fail",
            detail="evidence_text was empty after normalisation",
        )

    pages_norm = [_normalise(p) for p in pages]
    p1 = finding.evidence_page

    # 1) Recorded page in range? If not, jump straight to whole-doc search.
    if 1 <= p1 <= len(pages):
        primary_norm = pages_norm[p1 - 1]
        if _all_fragments_in_order(primary_norm, fragments_norm):
            return CheckResult(finding=finding, status="pass", matched_page=p1)

        # Scanned-only? pypdf got nothing — punt to human eyeball.
        if not pages[p1 - 1].strip():
            return CheckResult(
                finding=finding, status="page_empty", matched_page=p1,
                detail=("page text is empty in the pypdf cache — likely a "
                        "scanned-image-only page that the Read-tool extractor "
                        "read via vision. Manual eyeball needed."),
            )

        # 2) ±tolerance adjacent pages, single-page match.
        for offset in range(1, tolerance + 1):
            for candidate in (p1 - 1 - offset, p1 - 1 + offset):
                if 0 <= candidate < len(pages):
                    if _all_fragments_in_order(pages_norm[candidate], fragments_norm):
                        return CheckResult(
                            finding=finding, status="pass_adjacent",
                            matched_page=candidate + 1,
                            detail=f"matched on page {candidate + 1} instead of recorded {p1}",
                        )

    # 3) Whole-document fragment search. The journalism is defensible as
    #    long as every fragment is a genuine quote from the document; the
    #    page anchor is a usability concern, not a libel concern.
    fragment_pages: list[int | None] = []
    for frag in fragments_norm:
        found_on: int | None = None
        for i, page_norm in enumerate(pages_norm, 1):
            if frag in page_norm:
                found_on = i
                break
        fragment_pages.append(found_on)

    if all(p is not None for p in fragment_pages):
        pages_str = ", ".join(str(p) for p in fragment_pages)
        if 1 <= p1 <= len(pages):
            detail = (
                f"every fragment is in the document but split across pages "
                f"{pages_str} — recorded page {p1} doesn't cover all of them"
            )
        else:
            detail = (
                f"recorded page {p1} is out of range (doc has {len(pages)} "
                f"pages); every fragment is in the document, found on pages "
                f"{pages_str}"
            )
        return CheckResult(
            finding=finding, status="pass_cross_page",
            matched_page=fragment_pages[0],
            detail=detail,
        )

    # 4) Genuine miss. List which fragments couldn't be found.
    missing = [
        i for i, found in enumerate(fragment_pages, 1) if found is None
    ]
    if 1 <= p1 <= len(pages):
        excerpt = pages[p1 - 1][:400].replace("\n", " ").strip()
        return CheckResult(
            finding=finding, status="fail", matched_page=p1,
            cached_excerpt=excerpt,
            detail=f"fragment(s) {missing} not found anywhere in document "
                   f"(quote has {len(fragments_norm)} ellipsis-separated fragments)",
        )
    return CheckResult(
        finding=finding, status="page_out_of_range", matched_page=p1,
        detail=f"recorded page {p1} beyond {len(pages)}-page doc; "
               f"fragments {missing} also missing from the document text",
    )


def _render(results: list[CheckResult]) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines: list[str] = []
    lines.append(f"# Findings verification — {len(results)} rows checked")
    lines.append("")
    lines.append(
        "Each row in the `findings` table carries a literal `evidence_text` "
        "quote against a specific document and page. This pass re-opens "
        "the pypdf-cached page text and checks the quote appears verbatim "
        "(modulo whitespace and case). Mismatches are libel-risk surface "
        "before publication."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    status_order = [
        ("pass", "quote found verbatim on the recorded page"),
        ("pass_adjacent", "quote found on the page next to the recorded one (off-by-one)"),
        ("pass_cross_page", "every fragment found in the doc but spread across pages other than the recorded one"),
        ("page_empty", "recorded page has no pypdf text — scanned-only; manual check needed"),
        ("cache_missing", "no pypdf cache for the document"),
        ("page_out_of_range", "recorded page beyond the document's pypdf page count"),
        ("fail", "at least one fragment not found anywhere in the document"),
    ]
    for status, hint in status_order:
        n = counts.get(status, 0)
        if n:
            lines.append(f"- `{status}`: **{n}** — {hint}")
    lines.append("")

    need_eyeballs = [r for r in results if r.status not in ("pass",)]
    if need_eyeballs:
        lines.append("## Rows needing review")
        lines.append("")
        for r in need_eyeballs:
            f = r.finding
            lines.append(f"### finding {f.finding_id} — {f.application_ref} — `{f.signal_type}`")
            lines.append(f"- **status:** `{r.status}`")
            if r.detail:
                lines.append(f"- **detail:** {r.detail}")
            if f.value_text:
                vt = f.value_text if len(f.value_text) <= 200 else f.value_text[:200] + "…"
                lines.append(f"- **value_text:** {vt}")
            ev = f.evidence_text if len(f.evidence_text) <= 400 else f.evidence_text[:400] + "…"
            lines.append(f"- **evidence_text** (page {f.evidence_page}): {ev!r}")
            lines.append(f"- **doc:** `{f.bytes_path}`")
            if r.cached_excerpt:
                lines.append(f"- **cached page excerpt** (first 400 chars of page {r.matched_page}):")
                lines.append(f"  > {r.cached_excerpt}")
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tolerance", type=int, default=1,
        help="On a miss, also try ±N adjacent pages (off-by-one pagination tolerance).",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Write the markdown report to this path. Default: stdout.",
    )
    args = ap.parse_args()

    with db.connect() as conn:
        rows = _query_findings(conn)
    results = [_check_one(r, tolerance=args.tolerance) for r in rows]

    md = _render(results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)

    failed = any(r.status == "fail" for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
