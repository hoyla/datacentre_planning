"""The verbatim quote gate: what it must forgive, and what it must not.

The gate is this project's hallucination protection — a model's quote has
to appear in the cached page text or the finding is rejected. Everything
here is a real pattern from the corpus, not a case invented to match the
implementation: pypdf breaks words mid-token when it reconstructs a line,
so a page reads "d ata centres" or "sust ainable" or "940 µ g/m 3" and a
correctly-copied quote fails against it.

Measured 2026-08-31 across every gate rejection with cached page text
(50,517 rows, matched against the claimed page): 68.8% were genuinely
absent — the gate working — and 29.8% appeared once whitespace was
ignored, rising to 36.4% among rejections carrying a numeric power unit.
The relaxation below recovers the second group. The guard keeps it from
recovering anything else.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "verify_findings", ROOT / "scripts" / "verify_findings.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_findings"] = mod
    spec.loader.exec_module(mod)
    return mod


VF = _load()


def _present(page: str, quote: str) -> bool:
    frags = [VF._normalise(f) for f in VF._quote_fragments(quote)]
    return bool(frags) and VF.fragments_present(VF._normalise(page), frags)


def _present_strict(page: str, quote: str) -> bool:
    frags = [VF._normalise(f) for f in VF._quote_fragments(quote)]
    return bool(frags) and VF._all_fragments_in_order(VF._normalise(page), frags)


# --- what the relaxation must recover ---------------------------------------

# Both sides of each pair are real: the quote as the model copied it, and
# the page as pypdf rendered it.
BROKEN_PAGES = [
    ("it is expected that the Data Centre will have a total ITE capacity of up to 30MW",
     "it is expected that the D ata Centre will have a total ITE capa city of up to 30MW"),
    ("a typical power consumption is defined as an average of 20-50 megawatts",
     "a typical power consum ption is defined as an aver age of 20-50 megaw atts"),
    ("Customer LV Switchroom RD Studios - 800kVA",
     "Customer LV Switchro om RD Studios - 800 kVA"),
    ("the annual mean concentration is 940 µg/m3 across the site",
     "the annual mean concentration is 940 µ g/m 3 acro ss the site"),
]


@pytest.mark.parametrize("quote,page", BROKEN_PAGES)
def test_a_correct_quote_survives_pypdf_breaking_a_word(quote, page):
    assert not _present_strict(page, quote), (
        "this case is only interesting if the old gate rejected it")
    assert _present(page, quote)


def test_the_split_repair_now_covers_letters_other_than_s():
    # The original repair handled a trailing "s" only, and its own comment
    # named these as cases it did not cover.
    assert _present("the energ y generation plant at the centr e of the site",
                    "the energy generation plant at the centre of the site")


def test_the_plural_case_it_always_handled_still_works():
    assert _present("two data centre s will be built",
                    "two data centres will be built")


# --- what it must still reject ----------------------------------------------

def test_a_paraphrase_is_still_rejected():
    assert not _present(
        "the site will require approximately 30MW of installed capacity",
        "the site needs about thirty megawatts of power")


def test_an_invented_figure_is_still_rejected():
    assert not _present(
        "the development will have a total capacity of up to 30MW",
        "the development will have a total capacity of up to 300MW")


def test_fragments_must_appear_in_order():
    page = "the grid connection is 40MW and the IT load is 25MW"
    assert _present(page, "the grid connection is 40MW ... the IT load is 25MW")
    assert not _present(page, "the IT load is 25MW ... the grid connection is 40MW")


# --- the guard --------------------------------------------------------------

def test_a_short_quote_is_not_admitted_by_the_whitespace_fallback():
    """The shortest recovery in the 2026-08-31 measurement was the quote
    "0 9", which whitespace-blind becomes "09" and matches almost any page
    carrying a number. That is a substring lottery, not verification."""
    page = "the substation at grid reference 5 09 8 was consented in 2019"
    assert not _present(page, "0 9")


def test_the_guard_is_set_where_the_distribution_says_it_should_be():
    """Not a magic number: median recovered length is 122 characters and
    the 1st percentile is 26, so 25 costs 107 of 15,042 recoveries
    (0.7%) — and what it costs is the 20-to-24 band, which is dominated
    by repeated single-word labels that verify almost nothing."""
    assert VF.MIN_WS_BLIND_CHARS == 25


def test_a_fragment_just_under_the_guard_is_refused_even_if_really_present():
    # 19 characters once whitespace is stripped: genuinely on the page,
    # and still refused, because the guard cannot depend on the answer.
    quote = "the capacity is 30 MW ok"
    stripped = "".join(quote.split())
    assert len(stripped) < VF.MIN_WS_BLIND_CHARS
    assert not _present("the total capa city is 30 M W ok for the scheme", quote)


def test_a_long_fragment_over_the_guard_is_admitted():
    quote = "the total installed generating capacity across the campus is 42MW"
    assert len("".join(quote.split())) >= VF.MIN_WS_BLIND_CHARS
    assert _present(
        "the total installed gener ating capacity across the cam pus is 42MW",
        quote)


def test_every_fragment_must_clear_the_guard_not_just_one():
    """A long fragment must not carry a short one past the guard."""
    page = "the total installed generating capacity across the campus is 42MW and 0 9"
    quote = "the total installed generating capacity across the campus is 42MW ... 09"
    assert not _present(page, quote)
