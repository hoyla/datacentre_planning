"""Phase 4 — per-document text extraction and regex candidate-surfacing.

Two responsibilities, in service of the deep-read findings extractor:

1. **Text extraction with per-page caching.** Run pypdf once per document
   and cache the per-page text under `data/raw_text/<source>/<application_ref>/
   <sha[:16]>.pages.json`. The cache is the contract between the parsing
   stage and the LLM stage — either can be re-run independently. Re-running
   the parser is a no-op when the cache is present and matches the source
   SHA.

2. **Regex pre-pass over the per-page text.** Surface candidate sentences
   for the high-signal patterns the rubric calls out — `\\d+\\s*MW`,
   generator counts, fuel storage in hours/litres/tonnes. The output is
   `(document_sha, page_number, sentence)` tuples; the LLM (or the
   human-in-the-loop reading via Claude Code's Read tool) decides which
   are real findings and what structured shape they take.

Some PDFs are scanned-image-only (no text layer); pypdf returns empty
strings for those pages. Those pages fall back to **RapidOCR** (ONNX
PaddleOCR — non-generative CTC decoding, pinned weights), chosen over a
VLM deliberately: the OCR text is the substrate the verbatim-quote
verification gate checks against, and it must fail *noisily* on
illegible input (garbage characters) rather than *fluently* (a
generative model's plausible hallucination would let an invented quote
verify). Measured on the 2026-08 Barbour-round fetch: ~5% of documents
are scanned-only, mostly clean typed council forms. Per-page OCR use is
recorded in the cache payload (`ocr_pages`) for the audit trail. If
rapidocr isn't installed, behaviour degrades to the old contract
(empty pages, vision-capable reader handles the doc whole).

`.docx` / `.msg` / `.xlsx` loaders land in follow-ups (the YEP
calibration set is PDF-dominated; `.docx` support arrives when the
top-100 sweep needs it).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# Single cache root for parsed text. Mirrors the bytes layout under data/raw/
# so the (source, application_ref) prefix points to the same logical doc set.
RAW_TEXT_ROOT = Path("data/raw_text")


# ---------------------------------------------------------------------------
# Per-page text extraction + cache
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ExtractedDoc:
    """Per-page text for one document, plus extraction metadata."""

    sha: str
    bytes_path: Path
    pages: list[str]  # index = 0-based page; pages[i] is the page's text
    engine: str
    extracted_at: str
    ocr_pages: tuple[int, ...] = ()  # 1-based pages whose text came from OCR

    @property
    def page_count(self) -> int:
        return len(self.pages)


def cache_path_for(source: str, application_ref: str, sha: str) -> Path:
    """Cache file location for a given document SHA.

    `application_ref` keeps its slashes (matches the `data/raw/` layout); the
    file ends in `.pages.json` to make it obvious the payload is structured,
    not a flat dump.
    """
    return RAW_TEXT_ROOT / source / application_ref / f"{sha[:16]}.pages.json"


def extract_pdf(bytes_path: Path) -> list[str]:
    """Pull text out of a PDF, one entry per page (empty string for image-only pages).

    Uses pypdf — already a project dep, fast enough for the top-100 corpus.
    Returns an empty list if the PDF can't be opened at all (encrypted, etc.).
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(bytes_path))
    except Exception as exc:
        log.warning("pypdf failed to open %s: %s", bytes_path, exc)
        return []
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:
            log.warning("pypdf failed on a page of %s: %s", bytes_path, exc)
            pages.append("")
    return pages


# A page whose stripped pypdf text is shorter than this is treated as
# image-only and sent to OCR. Drawings often carry a few characters of
# title-block text that pypdf does recover; the threshold keeps those in
# scope for OCR without re-processing genuinely text-layered pages.
OCR_MIN_CHARS = 25

_OCR_ENGINE = None  # lazy singleton; RapidOCR loads ~3 ONNX models on init


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _ocr_image_tesseract(pil_image) -> str:
    """OCR one PIL image via the tesseract binary (no pytesseract dep).

    Default engine: on clean typed English council documents it preserves
    inter-word spacing and reading order noticeably better than RapidOCR's
    English model (which concatenates words and emits full-width CJK
    punctuation — measured on the 2026-08 Fife/Enfield scanned samples).
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        pil_image.save(tmp.name, format="PNG")
        proc = subprocess.run(
            ["tesseract", tmp.name, "stdout", "--psm", "3", "-l", "eng"],
            capture_output=True, text=True, timeout=120,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed: {proc.stderr[:200]}")
    return proc.stdout


def _ocr_image_rapidocr(pil_image) -> str:
    """OCR one PIL image via RapidOCR (ONNX PaddleOCR). Alternative engine —
    stronger on low-quality scans and complex layouts, but weaker spacing on
    clean English text."""
    import numpy as np

    engine = _get_ocr_engine()
    result, _elapse = engine(np.asarray(pil_image.convert("RGB")))
    return "\n".join(item[1] for item in (result or []))


_OCR_BACKENDS = {"tesseract": _ocr_image_tesseract, "rapidocr": _ocr_image_rapidocr}


def ocr_pdf_pages(
    bytes_path: Path, page_indices: list[int], engine: str = "tesseract",
) -> dict[int, str]:
    """OCR specific (0-based) pages of a PDF via pypdfium2 + a non-generative
    OCR engine.

    Returns {page_index: text}. Both engines are deliberately non-generative
    (see module docstring): misreads surface as noisy characters, never as
    fluent invented prose, so the quote-verification substrate stays honest.
    Rendering at ~300 DPI (scale 300/72) — the sweet spot for typed council
    forms. Returns {} if the renderer or engine is unavailable.
    """
    ocr_image = _OCR_BACKENDS[engine]
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        log.warning("OCR unavailable (%s); leaving image-only pages empty", exc)
        return {}

    out: dict[int, str] = {}
    try:
        pdf = pdfium.PdfDocument(str(bytes_path))
    except Exception as exc:
        log.warning("pypdfium2 failed to open %s: %s", bytes_path, exc)
        return {}
    try:
        for idx in page_indices:
            try:
                page = pdf[idx]
                # 300 DPI for ordinary pages, but cap the rendered long edge
                # at ~4000 px: A0/A1 site plans at full 300 DPI produce
                # 100-megapixel bitmaps that stall tesseract for minutes and
                # add nothing for text recovery.
                long_edge_pts = max(page.get_size())
                scale = min(300 / 72, 4000 / long_edge_pts)
                bitmap = page.render(scale=scale)
                out[idx] = ocr_image(bitmap.to_pil())
            except Exception as exc:
                log.warning("OCR failed on page %d of %s: %s", idx + 1, bytes_path, exc)
    finally:
        pdf.close()
    return out


def extract_document(
    *,
    source: str,
    application_ref: str,
    sha: str,
    bytes_path: Path,
    force: bool = False,
    ocr: bool = True,
    ocr_engine: str = "tesseract",
) -> ExtractedDoc:
    """Return parsed per-page text for a document, using cache when present.

    Set `force=True` to bypass the cache (e.g. after upgrading the extraction
    engine). Pages with no usable text layer are OCR'd unless `ocr=False`;
    OCR'd page numbers are recorded in the cache for audit and the engine
    string becomes e.g. 'pypdf+tesseract'.
    """
    cache = cache_path_for(source, application_ref, sha)
    if cache.exists() and not force:
        payload = json.loads(cache.read_text())
        return ExtractedDoc(
            sha=payload["sha"],
            bytes_path=Path(payload["bytes_path"]),
            pages=payload["pages"],
            engine=payload["engine"],
            extracted_at=payload["extracted_at"],
            ocr_pages=tuple(payload.get("ocr_pages", [])),
        )

    ocr_pages: tuple[int, ...] = ()
    suffix = bytes_path.suffix.lower()
    if suffix == ".pdf":
        pages = extract_pdf(bytes_path)
        engine = "pypdf"
        if ocr:
            needs_ocr = [i for i, t in enumerate(pages)
                         if len(t.strip()) < OCR_MIN_CHARS]
            if needs_ocr:
                ocr_out = ocr_pdf_pages(bytes_path, needs_ocr, engine=ocr_engine)
                merged = {i: t for i, t in ocr_out.items() if t.strip()}
                for i, text in merged.items():
                    pages[i] = text
                if merged:
                    engine = f"pypdf+{ocr_engine}"
                    ocr_pages = tuple(sorted(i + 1 for i in merged))
    else:
        # docx/msg/xlsx loaders land later; for now, leave non-PDFs uncached
        # so a future re-run picks them up. Returning an empty pages list
        # signals "regex pre-pass had nothing to work with, send the doc
        # whole to the LLM".
        log.info("No loader yet for %s (suffix=%s); skipping cache.", bytes_path, suffix)
        pages = []
        engine = "skipped"

    doc = ExtractedDoc(
        sha=sha,
        bytes_path=bytes_path,
        pages=pages,
        engine=engine,
        extracted_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        ocr_pages=ocr_pages,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "sha": doc.sha,
        "bytes_path": str(doc.bytes_path),
        "pages": doc.pages,
        "engine": doc.engine,
        "extracted_at": doc.extracted_at,
        "ocr_pages": list(doc.ocr_pages),
    }, ensure_ascii=False))
    return doc


# ---------------------------------------------------------------------------
# Regex pre-pass — high-signal patterns
# ---------------------------------------------------------------------------


# Capacity expressions. Captures the numeric magnitude and unit; tolerates a
# space or hyphen between number and unit, and optional decimals. The leading
# (?<![\w.]) and trailing (?![\w]) guards keep us from matching inside larger
# identifiers (e.g. "100MWh" still matches because the suffix may include 'h',
# but we don't want "FOO1MW1" to trigger).
CAPACITY_REGEX = re.compile(
    r"(?<![\w.])(\d{1,4}(?:\.\d+)?)\s*-?\s*(MW|kVA|kW|MVA)\b",
    re.IGNORECASE,
)

# Generator counts: "14 generators", "12 × diesel generators", "twenty-five
# gas reciprocating engines". We catch the digit form here; the LLM step
# handles spelled-out numbers if they show up.
GENERATOR_COUNT_REGEX = re.compile(
    r"(?<![\w.])(\d{1,3})\s*(?:×|x|\*)?\s*"
    r"(?:new\s+|proposed\s+|standby\s+|emergency\s+|backup\s+|back-up\s+|diesel\s+|gas\s+)*"
    r"(?:reciprocating\s+)?(?:engine\s+)?generators?\b",
    re.IGNORECASE,
)

# Fuel storage expressions — hours of run-time, litres, tonnes.
FUEL_STORAGE_REGEX = re.compile(
    r"(?<![\w.])(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(hour|hours|hr|hrs|litres?|l|tonnes?|t)\s+"
    r"(?:of\s+)?(?:diesel|gas|fuel|LPG|propane)\b",
    re.IGNORECASE,
)

# Sentence splitter — naive but sufficient for surfacing candidates. We
# don't need perfect sentence boundaries; just enough context for a human
# (or LLM) to read the candidate phrase and assess it.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\n{2,}")


@dataclasses.dataclass(frozen=True)
class Candidate:
    """One regex hit, with enough context to feed the LLM."""

    doc_sha: str
    page: int  # 1-based for display
    pattern: str  # 'capacity' | 'generator_count' | 'fuel_storage'
    match_text: str  # the regex match itself (e.g. "21MW", "14 gas reciprocating engine generators")
    sentence: str  # surrounding sentence

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


PATTERNS: dict[str, re.Pattern[str]] = {
    "capacity": CAPACITY_REGEX,
    "generator_count": GENERATOR_COUNT_REGEX,
    "fuel_storage": FUEL_STORAGE_REGEX,
}


def find_candidates(doc: ExtractedDoc) -> list[Candidate]:
    """Run every pattern against every page; return candidate hits with context.

    Each match yields one candidate with the enclosing sentence preserved.
    Duplicate sentences (same page, same pattern, same sentence text) are
    de-duplicated so the LLM-feed isn't padded with repeats.
    """
    seen: set[tuple[int, str, str]] = set()
    hits: list[Candidate] = []
    for page_idx, page_text in enumerate(doc.pages):
        if not page_text:
            continue
        sentences = _SENT_SPLIT.split(page_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            for label, pattern in PATTERNS.items():
                for m in pattern.finditer(sentence):
                    key = (page_idx + 1, label, sentence)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(Candidate(
                        doc_sha=doc.sha,
                        page=page_idx + 1,
                        pattern=label,
                        match_text=m.group(0),
                        sentence=sentence,
                    ))
    return hits


def candidates_for_application(
    *,
    source: str,
    application_ref: str,
    documents: Iterable[tuple[str, Path]],
    force_extract: bool = False,
) -> list[Candidate]:
    """End-to-end pre-pass for one application: extract every doc, run regex.

    `documents` is an iterable of `(sha, bytes_path)` pairs (typically from
    the `documents` table or a manifest file). Returns the flat list of
    candidates across all docs, ordered first by doc-of-appearance then by
    page number.
    """
    out: list[Candidate] = []
    for sha, bytes_path in documents:
        doc = extract_document(
            source=source, application_ref=application_ref,
            sha=sha, bytes_path=bytes_path, force=force_extract,
        )
        out.extend(find_candidates(doc))
    return out
