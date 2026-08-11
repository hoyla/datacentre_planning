"""No document is dropped for being large.

A ceiling was tried at 120,000 characters after one 32-sheet xlsx
emissions tracker became 172 sequential model calls. Classifying every
document it bound on is what killed it: 1,183 documents, 1,029 of them
PDFs, 186.4 million characters dropped from PDFs against 50 million from
the spreadsheets it was aimed at — including 35 Environmental Statements
losing about half their selected pages. The threshold sat below the
median selection for a large document. It was a haircut on the corpus
dressed as an outlier guard.

Two narrower rules were tried and rejected for deleting evidence:
collapsing near-identical pages (which calls 118 of 208 pages of a soil
analytical report duplicates, when the differences are the sample ids and
the measurements) and dropping all-zero rows (a zero in an emissions log
says the generator did not run, and dropping it also erases the
difference between nothing-recorded and zero-recorded).

These tests hold that line: size may be reported, never acted on.
"""

from __future__ import annotations

from dcp import deepread_select as sel


def _page(text: str, size: int) -> str:
    """A page of roughly `size` characters that scores as a hit."""
    unit = f"{text} 12 MW generator NOx emissions load. "
    return (unit * (size // len(unit) + 1))[:size]


def test_nothing_is_truncated_by_default():
    """The property the corpus depends on: a big document is read.

    An Environmental Statement runs to thousands of pages, and it is the
    document class where disclosures live. Selection must be identical
    whether or not a ceiling is available.
    """
    pages = [_page(f"sheet {i}", 70_000) for i in range(48)]
    assert sel.MAX_SELECTED_CHARS is None
    assert (sel.select_pages(pages, tier="A")
            == sel.select_pages(pages, tier="A", max_chars=None))
    assert sum(len(pages[i]) for i in sel.select_pages(pages, tier="A")) \
        > 3_000_000


def test_a_caller_may_still_ask_for_a_bounded_read():
    """The parameter survives for anything that genuinely wants a bound —
    a smoke test, a preview — but nothing in the pipeline passes it."""
    pages = [_page(f"sheet {i}", 70_000) for i in range(48)]
    bounded = sel.select_pages(pages, tier="A", max_chars=500_000)
    assert sum(len(pages[i]) for i in bounded) <= 500_000 + 2 * 70_000


def test_large_documents_are_reported_not_trimmed():
    """Reporting is the whole mechanism now.

    What went wrong was never the cost: it was that a 172-call document
    was indistinguishable from a hung process. Saying so in advance is
    the fix; deleting pages was not.
    """
    big = [_page(f"sheet {i}", 70_000) for i in range(48)]
    selected = sel.select_pages(big, tier="A")
    assert sel.selection_is_large(big, selected)

    small = [_page(f"p{i}", 1_000) for i in range(10)]
    assert not sel.selection_is_large(small, sel.select_pages(small, tier="A"))


def test_reporting_does_not_change_what_is_selected():
    pages = [_page(f"sheet {i}", 70_000) for i in range(48)]
    before = sel.select_pages(pages, tier="A")
    sel.selection_is_large(pages, before)
    assert sel.select_pages(pages, tier="A") == before


def test_ordinary_documents_are_unaffected():
    pages = [_page(f"para {i}", 1_800) for i in range(48)]
    assert (sel.select_pages(pages, tier="A")
            == sel.select_pages(pages, tier="A", max_chars=None))
