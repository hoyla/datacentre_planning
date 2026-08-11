"""One document must not be able to cost a night.

A 32-sheet xlsx emissions tracker scored every sheet as a hit — each
mentions NOx, emissions and load — and offered 2,075,466 characters to a
runner that turns 12,000 characters into one model call. That is 204
sequential calls and about half an hour, on a workbook whose year sheets
are the same blank compliance template repeated to 2055.

Collapsing near-identical pages was the first idea and is deliberately
absent. Line-level similarity does find the duplicate year sheets, but on
a soil analytical report it calls 118 of 208 pages duplicates too: same
laboratory letterhead, same determinand rows, differing only in sample
ids and measured values. Those numbers are the evidence. These tests
therefore assert a cap, and assert that it leaves ordinary documents
exactly as they were.
"""

from __future__ import annotations

from dcp import deepread_select as sel


def _page(text: str, size: int) -> str:
    """A page of roughly `size` characters that scores as a hit."""
    unit = f"{text} 12 MW generator NOx emissions load. "
    return (unit * (size // len(unit) + 1))[:size]


def test_cap_binds_on_a_pathological_document():
    pages = [_page(f"sheet {i}", 70_000) for i in range(32)]
    uncapped = sel.select_pages(pages, tier="A", max_chars=None)
    capped = sel.select_pages(pages, tier="A")

    assert sum(len(pages[i]) for i in uncapped) > 2_000_000
    assert len(capped) < len(uncapped)
    # Bounded by the cap plus the opening pages, which are never dropped.
    # What actually matters is the number of sequential model calls: 32
    # pages of this size is 204 of them, and this must be a handful.
    assert len(capped) <= 4


def test_the_floor_may_exceed_the_cap_and_that_is_the_contract():
    """Two opening pages of 70,000 characters are 140,000, over the
    ceiling, and they are still sent.

    Stated rather than fixed. The alternative is a document whose first
    pages are enormous being reduced to nothing, and the opening pages
    are where the description of development and the applicant live. The
    cost stays bounded because the floor is a fixed number of pages, not
    a fixed number of characters — two model calls, not two hundred.
    """
    pages = [_page(f"sheet {i}", 70_000) for i in range(32)]
    capped = sel.select_pages(pages, tier="A")
    assert {0, 1} <= set(capped)
    assert sum(len(pages[i]) for i in capped) > sel.MAX_SELECTED_CHARS


def test_ordinary_documents_are_untouched():
    """The cap must be invisible to everything that is not pathological.

    A 48-page report of normal pages sits far under the ceiling, and
    selection must be byte-identical with the cap on and off — otherwise
    this is a change to what gets read, not a guard against runaway cost.
    """
    pages = [_page(f"para {i}", 1_800) for i in range(48)]
    assert (sel.select_pages(pages, tier="A")
            == sel.select_pages(pages, tier="A", max_chars=None))


def test_opening_pages_always_survive_the_cap():
    """They carry the description of development and the applicant.

    A document reduced to nothing is worse than one reduced to its
    summary, so the floor is not negotiable even when the first pages are
    themselves enormous.
    """
    pages = [_page("opening", 200_000)] + [_page(f"body {i}", 90_000)
                                           for i in range(20)]
    capped = sel.select_pages(pages, tier="A")
    assert 0 in capped, "the first page must be sent whatever it costs"


def test_pages_are_dropped_whole_never_truncated():
    """Half a page produces quotes that fail the verbatim gate against
    the whole one, which would look like the model inventing evidence."""
    pages = [_page(f"sheet {i}", 70_000) for i in range(32)]
    capped = sel.select_pages(pages, tier="A")
    assert all(isinstance(i, int) and 0 <= i < len(pages) for i in capped)
    assert len(set(capped)) == len(capped)


def test_highest_scoring_pages_are_the_ones_kept():
    """When the budget binds, what survives should be what mentions most.

    A page naming generators, megawatts and water outscores one naming a
    single term, and the scarce budget should go to the former.
    """
    dull = "planning history and consultation responses follow. " * 1200
    rich = ("12 MW gas turbine generator, grid connection, water cooling, "
            "diesel fuel storage, battery. ") * 700
    pages = [_page("opening", 500), _page("opening two", 500)] \
        + [dull] * 6 + [rich]
    capped = sel.select_pages(pages, tier="A")
    assert len(pages) - 1 in capped, "the information-dense page must survive"


def test_selection_was_capped_reports_honestly():
    small = [_page(f"p{i}", 1_000) for i in range(10)]
    assert not sel.selection_was_capped(
        small, sel.select_pages(small, tier="A"))

    huge = [_page(f"sheet {i}", 70_000) for i in range(32)]
    assert sel.selection_was_capped(huge, sel.select_pages(huge, tier="A"))


def test_cap_can_be_disabled():
    """The batch readers and any re-read of a capped document need the
    whole thing, so `None` must genuinely mean no ceiling."""
    pages = [_page(f"sheet {i}", 70_000) for i in range(32)]
    assert sum(len(pages[i]) for i in
               sel.select_pages(pages, tier="A", max_chars=None)) > 2_000_000
