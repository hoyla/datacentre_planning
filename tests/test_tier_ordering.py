"""Every kind TIER_A_KINDS names must actually reach tier A.

`classify_kind` tests DRAWING_KINDS first, so a phrase listed in
TIER_A_KINDS can be unreachable — matched by the drawing rule and
returned as `skip` before the tier-A rule is consulted. The rule is
then written, correct, and dead.

That is exactly what happened to planning obligations. DRAWING_KINDS
contains `section\\b` for architectural sections; TIER_A_KINDS lists
`section 106` explicitly. "Section 106 Agreement" matched the drawing
rule, so 58 documents recording planning obligations — where community
payments and infrastructure commitments are written down — were
classified as drawings and never read. "S106 Agreement" took the
intended path, so whether an obligation was read turned on how the
council abbreviated it.

The suite could not have caught it: nothing asserted that a rule which
is written is a rule that can fire. This is the same shape as
tests/test_adjudication_gate.py asserting that the corrector and the
gate agree while nothing asserts either is right.
"""

from __future__ import annotations

import re

import pytest

from dcp import deepread_select as sel


def _probes(pattern: str) -> list[str]:
    """Literal strings, one per top-level alternative of a kind regex.

    Splits on `|` outside groups, then turns each branch into something a
    council might actually write: `(a|b)` becomes `a`, `\\b` and `?` go,
    `.{0,30}` becomes a space. A branch that cannot be reduced to a
    literal is skipped rather than guessed at.
    """
    branches, depth, cur = [], 0, ""
    for ch in pattern:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "|" and depth == 0:
            branches.append(cur)
            cur = ""
        else:
            cur += ch
    branches.append(cur)

    out = []
    for b in branches:
        s = re.sub(r"\(([^()|]+)\|[^()]*\)", r"\1", b)   # (a|b) -> a
        s = s.replace(r"\y", "").replace(r"\b", "")
        s = re.sub(r"\.\{0,\d+\}", " ", s)
        s = re.sub(r"\(\?[^)]*\)", "", s)
        s = s.replace("?", "").strip()
        if s and not re.search(r"[\\\[\]{}()*+^$]", s):
            out.append(s)
    return out


TIER_A_PROBES = _probes(sel.TIER_A_KINDS.pattern)
TIER_C_PROBES = _probes(sel.TIER_C_KINDS.pattern)


def test_the_probe_extraction_found_a_sensible_number():
    """If this collapses to nothing the parametrised tests pass vacuously."""
    assert len(TIER_A_PROBES) > 15, TIER_A_PROBES
    assert "section 106" in TIER_A_PROBES
    assert "planning statement" in TIER_A_PROBES


@pytest.mark.parametrize("phrase", TIER_A_PROBES)
def test_every_tier_a_phrase_reaches_tier_a(phrase):
    tier, why = sel.classify_kind(phrase)
    assert tier == "A", (
        f"TIER_A_KINDS lists {phrase!r} but classify_kind returns "
        f"{tier!r} ({why}) — an earlier rule matches it first, so the "
        f"tier-A entry is dead")


@pytest.mark.parametrize("phrase", TIER_C_PROBES)
def test_every_tier_c_phrase_reaches_tier_c(phrase):
    tier, why = sel.classify_kind(phrase)
    assert tier == "C", (
        f"TIER_C_KINDS lists {phrase!r} but classify_kind returns "
        f"{tier!r} ({why})")


def test_architectural_sections_are_still_drawings():
    """The fix must not cost what the drawing rule was for."""
    for kind in ("Cross Section", "Section AA", "Proposed Section",
                 "Site Section", "Sectional Elevation"):
        assert sel.classify_kind(kind)[0] == "skip", kind


def test_a_numbered_section_is_a_legal_instrument_not_a_drawing():
    """Nobody titles a drawing "Section 106"."""
    for kind in ("Section 106 Agreement", "Section 106", "Section 73",
                 "Section 106 Redacted", "Draft Section 106 agreement"):
        assert sel.classify_kind(kind)[0] != "skip", kind


def test_a_drawing_that_mentions_a_tier_a_subject_is_still_a_drawing():
    """Why the fix is not "test tier A first".

    TIER_A_KINDS contains `drainage`, `noise`, `water` and `decision`,
    because a drainage *strategy* is prose worth reading. A drainage
    *drawing* is not. Reordering the two rules wholesale moves 68
    documents, and 10 are these — genuine drawings pulled into the read
    tier by an incidental word. Measured over the corpus, 2026-08-11.

    Note what is NOT in this list: "Flood Risk Plan" already classifies
    as A, because DRAWING_KINDS has no bare `plan`. An earlier draft of
    this test asserted it was `skip` and failed — the assumption was
    wrong, not the code.
    """
    for kind in ("Drainage Layout Drawing", "Energy Centre Elevation",
                 "Water Treatment Plans, Sections and Elevations",
                 "Drawing - Decision",
                 "NOISE SENSITIVE RECEPTOR LOCATION PLAN"):
        assert sel.classify_kind(kind)[0] == "skip", kind


def test_a_numbered_architectural_section_is_still_a_drawing():
    r"""Why the fix is not a lookahead on `section\b(?!\s*\d)` either.

    That un-skips these nine, which are numbered drawing sheets, not
    statutes. The distinction is the instrument's name, not the presence
    of a number.
    """
    for kind in ("Section 1", "Section 01", "Section 03"):
        assert sel.classify_kind(kind)[0] == "skip", kind


def test_a_statutory_instrument_is_read_however_it_is_abbreviated():
    """The bug in one line: the council's abbreviation decided it."""
    for kind in ("Section 106 Agreement", "S106 Agreement", "s.106",
                 "Section 106", "Unilateral Undertaking",
                 "Planning Obligation", "Section 73 Application"):
        assert sel.classify_kind(kind)[0] == "A", kind


def test_a_section_35_direction_is_a_legal_instrument_not_a_drawing():
    """The same defect, found on the Section 35 bundles (2026-08-26).

    These are the kinds the manual ingest actually produced from the
    cached gov.uk filenames. Both came back `skip` — a drawing —
    because DRAWING_KINDS tests `section\\b` first, so the request
    document stating a 300MW campus was classified graphical while
    "260615 Questpit ... s35 Direction" was read.
    """
    for kind in ("Section 35 Direction",
                 "Request Document - Sdc M40 Campus - Section 35 Direction",
                 "S35 Decision Letter New Barn Rd",
                 "s.35 Direction", "s 35 Direction", "Section35 Direction",
                 "Data Centre Campus Section 35 Direction Planning Act 2008"):
        assert sel.classify_kind(kind)[0] == "A", kind


def test_the_instrument_name_wins_even_when_the_title_says_plan():
    """The accepted cost, stated as a test rather than left implicit.

    "Appendix 1 Ebbsfleet DCC Section 35 Plan" is genuinely a location
    plan and will now be read. That is the rule working, not failing: a
    named statutory instrument is never a drawing whatever else its
    title says, and one wasted page beats a 54-page prose skip.
    """
    assert sel.classify_kind("Appendix 1 Ebbsfleet Dcc Section 35 Plan") == (
        "A", "statutory instrument")


def test_a_numbered_architectural_section_near_35_is_still_a_drawing():
    """The new alternatives must not eat the drawing sheets around them.

    `Section 35` is an instrument; `Section 3`, `Section 5` and
    `Section 350` are sheet numbers, and `Drawings 35` is not an
    abbreviation of anything.
    """
    for kind in ("Section 3", "Section 5", "Section 350", "Section 35A Plan",
                 "Cross Section 35B", "Drawings 35 Elevation"):
        assert sel.classify_kind(kind)[0] == "skip", kind
