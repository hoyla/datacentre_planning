"""A model's citation has to be in the text it cites.

One rule, in `dcp/spans`, because two callers apply it and they must not
drift: `scripts/adjudicate_power.py` before storing a verdict, and
`scripts/export_reader.py` again before acting on one. The second matters
because a stored `span_verified` records what the gate said when the row
was written, and the gate has changed since — the question a build has to
answer is whether the citation stands now.

Both cases here are ones the corpus actually produced.
"""

from __future__ import annotations

from dcp.spans import verify_span

TEXT = ("The assignment of significant, not significant and negligible to the "
        "sensitivity of receptors were defined according to the measure of "
        "susceptibility and vulnerability of the receptors to future "
        "projections of climate change")


def test_a_contiguous_run_verifies():
    assert verify_span("sensitivity of receptors", TEXT)
    assert verify_span("future projections of climate change", TEXT)


def test_whitespace_is_normalised_on_both_sides():
    """A PDF's line breaks are not the model's copy of them."""
    assert verify_span("sensitivity   of\nreceptors", TEXT)


def test_two_phrases_stitched_without_an_ellipsis_are_refused():
    """The one citation in 10,605 that the gate rejects, and rightly.

    The model wrote "sensitivity of receptors to future projections of
    climate change". Both halves are in the document; that sentence is
    not, because thirteen words sit between them.
    """
    assert not verify_span(
        "sensitivity of receptors to future projections of climate change", TEXT)


def test_an_ellipsis_joins_two_runs_that_are_both_there():
    """Every unverified flag in the first audit run was one of these —
    a citation form, not an invention, rejected by a gate that could
    only see one contiguous run."""
    assert verify_span(
        "sensitivity of receptors ... future projections of climate change", TEXT)
    assert verify_span(
        "sensitivity of receptors … future projections of climate change", TEXT)


def test_an_ellipsis_cannot_reorder_the_document():
    """Otherwise it would license quoting a document backwards."""
    assert not verify_span(
        "future projections of climate change ... sensitivity of receptors", TEXT)


def test_an_ellipsis_cannot_introduce_words_that_are_not_there():
    assert not verify_span("sensitivity of receptors ... entirely invented", TEXT)


def test_joined_fragments_must_carry_evidence():
    """"a ... the" would otherwise verify against almost any sentence."""
    assert not verify_span("to ... of", TEXT)


def test_a_short_span_on_its_own_is_fine():
    """The rule above applies only to joined fragments. Applied to single
    spans it threw away 22 correct verdicts whose finding text is the
    whole of "No" or "Yes" — a form field answered, which is exactly what
    `not_a_finding` is for.
    """
    assert verify_span("No", "No")
    assert verify_span("Yes", "Yes")
    assert not verify_span("No", TEXT)


def test_an_empty_span_verifies_against_nothing():
    assert not verify_span("", TEXT)
    assert not verify_span("   ", TEXT)
    assert not verify_span("anything", "")


def test_the_adjudicator_still_exports_the_name_its_callers_use():
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "ap", root / "scripts" / "adjudicate_power.py")
    ap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ap)
    assert ap.verify_span is verify_span
