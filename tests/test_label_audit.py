"""The label audit: what it asks, and what a flag does to a page.

READER_REDESIGN_PLAN §4.1e specified the audit and §7a depends on it.
Neither existed when 2.6 shipped, which is why a site's evidence can
still lead with landscape prose filed under a power family.

No database and no network. What these cannot check is whether a verdict
is right — that is what the sample and a person are for. What they can
check is that the vocabulary the model answers under is the vocabulary
the extractor used, that the span gate accepts only a verbatim copy,
and that a flag MOVES a finding rather than deleting it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ap = _load("adjudicate_power")
al = _load("audit_labels")


def _row(fid, family, label, text, number=None):
    return {"finding_id": fid, "site_key": "PTNO-1", "signal_family": family,
            "signal_type": label, "value_text": text, "value_number": number,
            "value_unit": None, "verdict": None}


# ---------------------------------------------------------------------------
# The question, and the vocabulary it is answered in
# ---------------------------------------------------------------------------

def test_the_audit_answers_in_the_families_the_extractor_used():
    """A suggested family the mapper has never heard of cannot be acted
    on; the prompt carries the same list dcp.signal_families defines."""
    from dcp import signal_families
    block = signal_families.prompt_vocabulary_block()
    for family in signal_families.PROMPT_FAMILY_ENUM:
        assert family in block, family


def test_the_verdicts_are_the_four_the_sheet_accepts():
    """The schema, the sheet's validator and the prompt offer one set.

    `not_a_finding` joined the three on 2026-08-25: marking the sample
    turned up rows that are not misfiled and are not findings — an
    extractor's own reasoning caught in a quote, an empty form field,
    two job descriptions — and the other three verdicts all assume the
    row belongs somewhere.
    """
    enum = ap.LABEL_AUDIT_SCHEMA["properties"]["labels"]["items"] \
             ["properties"]["verdict"]["enum"]
    assert set(enum) == set(al.VERDICTS) == {
        "fits", "does_not_fit", "unclear", "not_a_finding"}
    for verdict in al.VERDICTS:
        assert verdict in ap.LABEL_AUDIT_PROMPT, verdict


def test_only_does_not_fit_names_a_family():
    """`not_a_finding` means no family would hold the row, so naming one
    contradicts the verdict; the sheet's validator refuses both ways."""
    for verdict, sug in (("not_a_finding", "cooling"), ("fits", "cooling"),
                         ("unclear", "cooling"), ("does_not_fit", ""),
                         ("does_not_fit", "safety")):
        with pytest.raises(SystemExit):
            al._validate_rows([{"row": "1", "finding_id": "1",
                                "verdict": verdict, "suggested_family": sug}])
    # And the shapes that are fine.
    al._validate_rows([
        {"row": "1", "finding_id": "1", "verdict": "not_a_finding"},
        {"row": "2", "finding_id": "2", "verdict": "fits"},
        {"row": "3", "finding_id": "3", "verdict": "does_not_fit",
         "suggested_family": "cooling"},
        {"row": "4", "finding_id": "4", "verdict": ""}])


def test_the_prompt_tells_the_model_to_prefer_unclear_to_a_flag():
    """The asymmetry this task has: a flag moves a real quote, and a
    quote wrongly moved is worse than one under an imperfect heading."""
    assert "Reach for \"unclear\"" in ap.LABEL_AUDIT_PROMPT
    assert "removes this text" in ap.LABEL_AUDIT_PROMPT


def test_the_prompt_shows_the_family_the_label_and_the_text():
    rendered = ap.render_label_findings(
        [_row(1, "power_demand", "it_load", "Existing tree cover")])
    assert "family: power_demand" in rendered
    assert "label: it_load" in rendered
    assert "Existing tree cover" in rendered


def test_a_span_must_be_verbatim_in_the_finding_s_own_text():
    assert ap.verify_span("tree cover", "Existing tree cover, the enclosed")
    assert not ap.verify_span("landscape prose", "Existing tree cover")


# ---------------------------------------------------------------------------
# The sample
# ---------------------------------------------------------------------------

def test_the_sample_leads_with_the_class_the_review_found_by_hand():
    """A power family, no figure, and prose long enough to have been
    promoted by the length ranking. If the audit cannot catch those it
    is not worth running."""
    rows = [_row(1, "power_demand", "it_load", "x" * 200),
            _row(2, "cooling", "chiller", "a chiller", 3.0)]
    why = {r["finding_id"]: r["why_in_sample"] for r in al.choose_sample(rows)}
    assert why[1].startswith(("the power_demand family",
                             "power family, no figure"))


def test_the_sample_is_stable_whatever_order_the_rows_arrive_in():
    rows = [_row(i, "cooling", "chiller", "x" * (100 + i)) for i in range(1, 9)]
    a = [r["finding_id"] for r in al.choose_sample(rows, size=4)]
    b = [r["finding_id"] for r in al.choose_sample(list(reversed(rows)), size=4)]
    assert a == b


# ---------------------------------------------------------------------------
# What a flag does
# ---------------------------------------------------------------------------

def test_scoring_counts_a_wrong_flag_apart_from_a_missed_one():
    """A flag acts on the page; leaving a row is the status quo. The two
    disagreements are not one number (Luke, 2026-08-24)."""
    rows = [_row(1, "power_demand", "it_load", "tree cover"),
            _row(2, "cooling", "chiller", "a chiller")]
    hand = {"1": {"verdict": "fits"}, "2": {"verdict": "does_not_fit"}}
    run = {"answers": {
        "1": {"verdict": "does_not_fit", "span_verified": True, "reasoning": ""},
        "2": {"verdict": "fits", "span_verified": True, "reasoning": ""}}}
    report = "\n".join(al.score(rows, hand, run))
    assert "FLAGGED WRONGLY       1" in report
    assert "flag missed           1" in report
