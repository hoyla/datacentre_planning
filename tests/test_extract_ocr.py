"""Tests for the OCR fallback in dcp.extract.

The OCR engines themselves are exercised manually (they need the tesseract
binary / ONNX models); these tests cover the fallback *wiring*: when OCR
fires, how results merge into the page cache, the audit trail, and
backwards compatibility with pre-OCR cache files.
"""

from __future__ import annotations

import json
from pathlib import Path

from dcp import extract


def _fake_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-fake")
    return p


def _run(tmp_path, monkeypatch, *, pypdf_pages, ocr_result, **kwargs):
    monkeypatch.setattr(extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    monkeypatch.setattr(extract, "extract_pdf", lambda _p: list(pypdf_pages))
    calls: list[tuple] = []

    def fake_ocr(bytes_path, page_indices, engine="tesseract"):
        calls.append((tuple(page_indices), engine))
        return ocr_result

    monkeypatch.setattr(extract, "ocr_pdf_pages", fake_ocr)
    doc = extract.extract_document(
        source="idox", application_ref="Test/1", sha="a" * 16,
        bytes_path=_fake_pdf(tmp_path), force=True, **kwargs,
    )
    return doc, calls


def test_empty_pages_trigger_ocr_and_merge(tmp_path, monkeypatch):
    doc, calls = _run(
        tmp_path, monkeypatch,
        pypdf_pages=["", "This page has a perfectly good text layer, thanks."],
        ocr_result={0: "OCR text for page one"},
    )
    assert calls == [((0,), "tesseract")]
    assert doc.pages[0] == "OCR text for page one"
    assert doc.pages[1].startswith("This page has")
    assert doc.engine == "pypdf+tesseract"
    assert doc.ocr_pages == (1,)


def test_short_title_block_page_is_ocr_candidate(tmp_path, monkeypatch):
    # Drawings often yield a few chars of title-block text via pypdf — still
    # below OCR_MIN_CHARS, so OCR gets a shot at the rest.
    doc, calls = _run(
        tmp_path, monkeypatch,
        pypdf_pages=["A1 - 100", "x" * 200],
        ocr_result={0: "Site plan with Plant labels"},
    )
    assert calls == [((0,), "tesseract")]
    assert doc.ocr_pages == (1,)


def test_ocr_disabled_leaves_pages_empty(tmp_path, monkeypatch):
    doc, calls = _run(
        tmp_path, monkeypatch,
        pypdf_pages=["", "text " * 20],
        ocr_result={0: "should not be used"},
        ocr=False,
    )
    assert calls == []
    assert doc.pages[0] == ""
    assert doc.engine == "pypdf"
    assert doc.ocr_pages == ()


def test_ocr_returning_nothing_keeps_plain_engine(tmp_path, monkeypatch):
    doc, _ = _run(
        tmp_path, monkeypatch,
        pypdf_pages=["", "text " * 20],
        ocr_result={0: "   "},  # whitespace-only OCR output is not a merge
    )
    assert doc.pages[0] == ""
    assert doc.engine == "pypdf"
    assert doc.ocr_pages == ()


def test_cache_roundtrip_preserves_ocr_pages(tmp_path, monkeypatch):
    doc, _ = _run(
        tmp_path, monkeypatch,
        pypdf_pages=["", "text " * 20],
        ocr_result={0: "OCR text"},
    )
    cached = extract.extract_document(
        source="idox", application_ref="Test/1", sha="a" * 16,
        bytes_path=tmp_path / "doc.pdf",
    )
    assert cached.engine == "pypdf+tesseract"
    assert cached.ocr_pages == (1,)
    assert cached.pages[0] == "OCR text"


def test_legacy_cache_without_ocr_pages_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    cache = extract.cache_path_for("idox", "Test/2", "b" * 16)
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({
        "sha": "b" * 16, "bytes_path": "x.pdf", "pages": ["hello"],
        "engine": "pypdf", "extracted_at": "2026-05-16T00:00:00",
    }))
    doc = extract.extract_document(
        source="idox", application_ref="Test/2", sha="b" * 16,
        bytes_path=tmp_path / "x.pdf",
    )
    assert doc.pages == ["hello"]
    assert doc.ocr_pages == ()
