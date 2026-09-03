"""Tests for format sniffing and the non-PDF loaders in dcp.extract.

Two things are being defended here.

**Sniffing, because the filename lies.** 255 corpus documents arrive as
`.bin` and are really Word documents, Outlook messages, workbooks and
scans; one `.doc` is really a `.docx`. Dispatch on the extension and every
one of those goes unread.

**The cache contract, because getting it wrong is silent.** An earlier
extractor wrote an empty cache for any format it could not load, so "we
have no loader for this" was stored as "this document contains no words" —
and because the deep-read cohort skips anything already settled, the miss
was permanent. A format with no loader must leave *no cache behind*.

The loaders themselves are exercised against real documents in the corpus
(which is local-only); these build the smallest real file of each format
that the library will accept.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from dcp import extract


# ---------------------------------------------------------------------------
# Builders — real files, small enough to write inline
# ---------------------------------------------------------------------------


def _docx(path: Path, paragraphs: list[str], table: list[list[str]] | None = None):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                t.cell(r, c).text = cell
    doc.save(str(path))
    return path


def _xlsx(path: Path, sheets: dict[str, list[list]]):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title=title)
        for row in rows:
            ws.append(row)
    wb.save(str(path))
    return path


def _zip(path: Path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


# ---------------------------------------------------------------------------
# Sniffing
# ---------------------------------------------------------------------------


def test_sniffs_by_content_not_by_extension(tmp_path):
    """The corpus's 255 `.bin` documents are the whole reason this exists."""
    disguised = _docx(tmp_path / "mystery.bin", ["Supporting statement."])
    assert extract.sniff_format(disguised) == "docx"


def test_pdf_named_as_something_else_is_still_a_pdf(tmp_path):
    p = tmp_path / "attachment.bin"
    p.write_bytes(b"%PDF-1.7\n% mock")
    assert extract.sniff_format(p) == "pdf"


@pytest.mark.parametrize("magic,expected", [
    (b"\xff\xd8\xff\xe0", "image"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"II*\x00", "image"),
    (b"MM\x00*", "image"),
    (b"{\\rtf1\\ansi", "rtf"),
])
def test_magic_bytes(tmp_path, magic, expected):
    p = tmp_path / "f.bin"
    p.write_bytes(magic + b"\x00" * 64)
    assert extract.sniff_format(p) == expected


def test_ooxml_containers_are_told_apart_by_their_members(tmp_path):
    assert extract.sniff_format(_docx(tmp_path / "a", ["x"])) == "docx"
    assert extract.sniff_format(_xlsx(tmp_path / "b", {"S": [[1]]})) == "xlsx"
    # .xlsb looks exactly like .xlsx from outside, and openpyxl cannot read it.
    xlsb = _zip(tmp_path / "c", {"[Content_Types].xml": b"<x/>",
                                 "xl/workbook.bin": b"\x00\x01"})
    assert extract.sniff_format(xlsb) == "xlsb"
    assert "xlsb" in extract.UNSUPPORTED_FORMATS


def test_opendocument_identified_by_its_mimetype_member(tmp_path):
    ods = _zip(tmp_path / "s.bin",
               {"mimetype": b"application/vnd.oasis.opendocument.spreadsheet",
                "content.xml": b"<office><text:p>Load 42 MW</text:p></office>"})
    assert extract.sniff_format(ods) == "ods"


def test_utf16_markup_is_text_not_binary(tmp_path):
    """Five Chorley documents are UTF-16LE HTML: full of NUL bytes, and not
    binary. Read as binary they sniff as unknown and go unread."""
    p = tmp_path / "page.html"
    p.write_bytes(b"\xff\xfe"
                  + "<html><body>Energy centre</body></html>".encode("utf-16-le"))
    assert extract.sniff_format(p) == "html"
    assert "Energy centre" in " ".join(extract.extract_html(p))


def test_email_needs_a_header_block_not_just_a_from_line(tmp_path):
    """Council letters open 'From: ...' too — one header line is not an email."""
    letter = tmp_path / "letter.txt"
    letter.write_bytes(b"From: the Planning Officer\n\nDear Sir or Madam,\n")
    assert extract.sniff_format(letter) == "text"

    mail = tmp_path / "mail.eml"
    mail.write_bytes(b"Return-Path: <a@b.uk>\nFrom: a@b.uk\nTo: c@d.gov.uk\n"
                     b"Date: Mon, 1 Jan 2024 00:00:00 +0000\n"
                     b"Subject: Objection\n\nI object.\n")
    assert extract.sniff_format(mail) == "eml"


def test_unreadable_and_empty_files_sniff_as_unknown(tmp_path):
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    assert extract.sniff_format(empty) == "unknown"
    assert extract.sniff_format(tmp_path / "does-not-exist.bin") == "unknown"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def test_docx_keeps_tables_in_document_order(tmp_path):
    """A capacity figure in a table must stay next to the heading above it —
    reading all prose then all tables separates the number from its meaning."""
    path = _docx(tmp_path / "statement.docx",
                 ["Section 4: Plant", "The schedule is set out below."],
                 table=[["Item", "Rating"], ["Standby generators", "12 x 3.3 MW"]])
    sections = extract.extract_docx(path)
    body = "\n".join(sections)
    assert "Standby generators | 12 x 3.3 MW" in body
    assert body.index("Section 4: Plant") < body.index("Standby generators")


def test_xlsx_gives_one_section_per_worksheet(tmp_path):
    path = _xlsx(tmp_path / "sched.xlsx", {
        "Loads": [["IT load", 40], ["Cooling", 12]],
        "Notes": [["Water cooled"]],
    })
    sections = extract.extract_xlsx(path)
    assert len(sections) == 2
    assert "[sheet: Loads]" in sections[0] and "IT load | 40" in sections[0]
    assert "Water cooled" in sections[1]


def test_xlsx_reads_a_workbook_that_arrived_as_bin(tmp_path):
    """openpyxl refuses by *filename*, so the path must not reach it."""
    path = _xlsx(tmp_path / "workbook.bin", {"S": [["Total demand", "96 MW"]]})
    assert "96 MW" in " ".join(extract.extract_xlsx(path))


def test_zip_reads_the_exported_email_bundle(tmp_path):
    """Every archive sampled is an exported email: header, body, images."""
    inner = tmp_path / "inner.pdf"
    inner.write_bytes(b"%PDF-fake")
    bundle = _zip(tmp_path / "bundle.bin", {
        "msg/header.txt": b"From: objector@example.org\nSubject: Objection\n",
        "msg/image001.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        "msg/message.pdf": b"%PDF-fake",
    })
    assert inner.exists()  # the nested-PDF path is exercised in test_extract_ocr
    sections = extract.extract_zip(bundle)
    assert any("objector@example.org" in s for s in sections)
    assert any(s.startswith("[header.txt]") for s in sections)


def test_zip_uses_its_own_names_for_scratch_files(tmp_path):
    """Nothing is written to a path the archive chooses."""
    bundle = _zip(tmp_path / "evil.zip",
                  {"../../escaped.txt": b"Subject: x\nFrom: y\nTo: z\n\nbody"})
    extract.extract_zip(bundle)
    assert not (tmp_path.parent.parent / "escaped.txt").exists()


def test_paginate_never_splits_a_block(tmp_path):
    """The quote-verification gate compares verbatim, so a section boundary
    mid-sentence would fail a quote that is genuinely in the document."""
    huge = "x" * (extract.SECTION_CHARS * 3)
    sections = extract.paginate(["short", huge, "also short"])
    assert huge in sections
    assert "".join(sections).count("x") == len(huge)


def test_paginate_drops_blank_blocks_and_groups_to_target():
    blocks = [f"paragraph {i} " + "y" * 900 for i in range(6)] + ["", "   "]
    sections = extract.paginate(blocks)
    assert len(sections) > 1
    assert all(s.strip() for s in sections)


# ---------------------------------------------------------------------------
# The cache contract
# ---------------------------------------------------------------------------


def _extract(tmp_path, monkeypatch, path):
    monkeypatch.setattr(extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    doc = extract.extract_document(
        source="documents", application_ref="Test/1", sha="b" * 16,
        bytes_path=path, ocr=False)
    return doc, extract.cache_path_for("documents", "Test/1", "b" * 16)


def test_unsupported_format_writes_no_cache(tmp_path, monkeypatch):
    """The bug this branch exists to fix. A cache here records 'nobody could
    read this' as 'this contains no words', and the absence of the file is
    the only thing that makes a later run retry."""
    path = tmp_path / "legacy.bin"
    path.write_bytes(extract._OLE_SIG + b"\x00" * 512)  # OLE, no known streams
    doc, cache = _extract(tmp_path, monkeypatch, path)
    assert doc.engine == "unsupported"
    assert doc.pages == []
    assert not cache.exists(), "an unreadable format must leave no cache behind"


def test_a_loader_that_returns_nothing_writes_no_cache(tmp_path, monkeypatch):
    """Observed for real: a transient import failure inside the .msg loader
    made it return `[]`, which cached as an extracted-and-empty document and
    would never have been retried. Every loader swallows its own exceptions,
    so 'returned nothing' and 'failed' are the same signal."""
    monkeypatch.setitem(extract._LOADERS, "docx", (lambda _p: [], "sections"))
    path = _docx(tmp_path / "s.docx", ["Real content that the loader misses."])
    doc, cache = _extract(tmp_path, monkeypatch, path)
    assert doc.engine == "unsupported"
    assert not cache.exists()


def test_whitespace_only_load_is_also_treated_as_a_failure(tmp_path, monkeypatch):
    monkeypatch.setitem(extract._LOADERS, "docx", (lambda _p: ["", "  \n "], "sections"))
    path = _docx(tmp_path / "s.docx", ["x"])
    _doc, cache = _extract(tmp_path, monkeypatch, path)
    assert not cache.exists()


def test_empty_pdf_still_caches(tmp_path, monkeypatch):
    """PDFs keep the older contract — an image-only page genuinely is empty
    until OCR runs, and `no_text` is the honest state for it."""
    monkeypatch.setattr(extract, "extract_pdf", lambda _p: ["", ""])
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-fake")
    doc, cache = _extract(tmp_path, monkeypatch, path)
    assert doc.engine == "pypdf"
    assert cache.exists()


def test_supported_format_caches_with_its_pagination(tmp_path, monkeypatch):
    path = _docx(tmp_path / "s.docx", ["Gas-fired standby plant is proposed."])
    doc, cache = _extract(tmp_path, monkeypatch, path)
    assert doc.engine == "docx"
    assert doc.pagination == "sections"
    assert not doc.native_pagination, "a .docx index is not a page number"
    assert cache.exists()
    assert "Gas-fired" in " ".join(doc.pages)


def test_pdf_pagination_is_native_and_default(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "extract_pdf", lambda _p: ["page one text"])
    path = tmp_path / "d.pdf"
    path.write_bytes(b"%PDF-fake")
    doc, _cache = _extract(tmp_path, monkeypatch, path)
    assert doc.pagination == "pages"
    assert doc.native_pagination


def test_pre_pagination_caches_read_as_native(tmp_path, monkeypatch):
    """Every cache written before the field existed is a PDF."""
    monkeypatch.setattr(extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    cache = extract.cache_path_for("documents", "Test/1", "c" * 16)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text('{"sha": "c", "bytes_path": "x.pdf", "pages": ["t"],'
                     ' "engine": "pypdf", "extracted_at": "2026-01-01T00:00:00"}')
    doc = extract.extract_document(
        source="documents", application_ref="Test/1", sha="c" * 16,
        bytes_path=tmp_path / "x.pdf")
    assert doc.pagination == "pages"


def test_stale_cache_is_recognised(tmp_path):
    """1,119 of these exist in the corpus, written by the extractor that had
    no loaders. They must not read as extracted-and-empty."""
    for engine, stale in (("skipped", True), ("unsupported", True),
                          ("pypdf", False), ("docx", False)):
        cache = tmp_path / f"{engine}.pages.json"
        cache.write_text(f'{{"pages": [], "engine": "{engine}"}}')
        assert extract.is_stale_cache(cache) is stale
        assert extract.cached_engine(cache) == engine


def test_unreadable_cache_is_not_stale(tmp_path):
    """Corrupt or absent is a different fact from 'no loader ran'."""
    truncated = tmp_path / "half.pages.json"
    truncated.write_text('{"pages": [')
    assert extract.cached_engine(truncated) is None
    assert extract.is_stale_cache(truncated) is False
    assert extract.is_stale_cache(tmp_path / "absent.pages.json") is False


@pytest.mark.parametrize("raw", [
    b"\xff\xfe" + "Energy".encode("utf-16-le"),
    b"\xfe\xff" + "Energy".encode("utf-16-be"),
    b"\xef\xbb\xbfEnergy",
    b"Energy",
])
def test_decode_text_drops_the_byte_order_mark(raw):
    """A surviving U+FEFF ends up inside the first extracted quote and fails
    verbatim verification against the source document."""
    assert extract.decode_text(raw) == "Energy"


def test_bytesio_workbook_is_not_a_path_dependency():
    """Guards the fix directly: openpyxl must be handed bytes, not a name."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.active.append(["Total IT load", "96 MW"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    reopened = openpyxl.load_workbook(buf, read_only=True, data_only=True)
    assert [c.value for c in next(reopened.worksheets[0].rows)] == \
        ["Total IT load", "96 MW"]


# ---------------------------------------------------------------------------
# The cache write survives text it cannot encode (2026-09-03)
# ---------------------------------------------------------------------------

def test_a_lone_surrogate_is_dropped_rather_than_killing_the_write(tmp_path):
    """A PDF's font mapping can hand pypdf half of a character pair.

    Two 26MB appeal bundles for the West London Technology Park carried
    one at the same offset. `write_text` truncated the file, then the
    UTF-8 encode raised, and the zero-byte cache that was left read as an
    extracted document — so two prose documents held a 937-document site
    out of the machine readings until 2026-09-03.
    """
    cache = tmp_path / "doc.pages.json"
    extract.write_cache(cache, {"pages": ["fine", "half \ud835 a pair"],
                                "engine": "pypdf"})
    got = json.loads(cache.read_text())
    assert got["pages"] == ["fine", "half  a pair"]
    assert got["engine"] == "pypdf"


def test_the_cache_write_is_atomic_and_leaves_no_temporary_behind(tmp_path):
    """A write that dies must leave the previous cache standing."""
    cache = tmp_path / "doc.pages.json"
    extract.write_cache(cache, {"pages": ["first"], "engine": "pypdf"})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        extract.write_cache(cache, {"pages": [Unserialisable()]})
    assert json.loads(cache.read_text())["pages"] == ["first"]
    assert [p.name for p in tmp_path.iterdir()] == ["doc.pages.json"]


def test_a_zero_byte_cache_is_re_extracted_whatever_the_format(tmp_path, monkeypatch):
    """`partition` must not read a died write as an extracted document.

    Staleness by engine is checked only for non-PDFs, because reading the
    engine parses the whole payload; a zero-byte file is checked by size,
    which is cheap enough for every format. Four such files existed when
    this was found, two of them the West London Technology Park's.
    """
    import scripts.extract_text_corpus as etc

    monkeypatch.setattr(extract, "RAW_TEXT_ROOT", tmp_path)
    empty = extract.cache_path_for("documents", "Chiltern/PL/24", "a" * 40)
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("")
    full = extract.cache_path_for("documents", "Chiltern/PL/24", "b" * 40)
    full.write_text('{"pages": ["text"], "engine": "pypdf"}')

    docs = [("Chiltern/PL/24", "a" * 40, "/x/bundle.pdf", "Appeal"),
            ("Chiltern/PL/24", "b" * 40, "/x/other.pdf", "Appeal")]
    todo, stale, done = etc.partition(docs)
    assert [d[1] for d in todo] == ["a" * 40]
    assert stale == {"a" * 40}, "a re-extraction must force past the dead cache"
    assert [d[1] for d in done] == ["b" * 40]
