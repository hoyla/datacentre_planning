"""The generation questions: the vocabulary, the span gate, the forty.

Unit tests, no database and no network. What they cannot check is
whether the model's answers are right — that is what the sample and a
person are for. What they can check is that the sheet a person fills in
and the schema the model answers under stay the same vocabulary, that
the span gate accepts a verbatim copy and nothing else, and that the
sample stays the sample: the named cases present, forty rows, and the
same forty whatever order the corpus arrives in.
"""

from __future__ import annotations

import csv
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
ag = _load("adjudicate_generation")


# ---------------------------------------------------------------------------
# The vocabulary, in two places that must not drift
# ---------------------------------------------------------------------------

def _enum(field: str) -> list[str]:
    props = ap.GENERATION_SCHEMA["properties"]["generation"]["items"]["properties"]
    return props[field]["enum"]


def test_sheet_offers_exactly_what_the_schema_accepts():
    """A person and the model answer the same closed question.

    The sheet prints its vocabulary in prose and validates what comes
    back against BASIS_VALUES/PLANT_VALUES; the model is constrained by
    the schema's enums. A value in one and not the other would score a
    hand-check as a disagreement when it is a typo in this file.
    """
    assert set(ag.BASIS_VALUES) == set(_enum("figure_basis"))
    assert set(ag.PLANT_VALUES) == set(_enum("plant_type"))


def test_the_sheet_prose_names_every_value():
    """Every value a person may write is explained in the sheet itself."""
    for value in ag.BASIS_VALUES + ag.PLANT_VALUES:
        assert f"`{value}`" in ag.HOW_TO_READ


def test_the_prompt_names_every_value():
    for value in ag.BASIS_VALUES + ag.PLANT_VALUES:
        assert f'"{value}"' in ap.GENERATION_PROMPT


def test_the_prompt_never_asks_for_a_multiplication():
    assert "Never multiply" in ap.GENERATION_PROMPT


def test_the_generation_version_is_its_own():
    """power-1.0's key is not to be shared or edited."""
    assert ap.GENERATION_PROMPT_VERSION.startswith("generation-")
    assert ap.GENERATION_PROMPT_VERSION != ap.PROMPT_VERSION


# ---------------------------------------------------------------------------
# The span gate
# ---------------------------------------------------------------------------

QUOTE = ("The proposal in cludes the installation of an energy centre,\n"
         "comprising 20  no. 2,499 kW natural gas  engines with a combined "
         "capacity of just under 50 MW electrical power.")


@pytest.mark.parametrize("span", [
    "20  no. 2,499 kW natural gas  engines",   # as it appears
    "20 no. 2,499 kW natural gas engines",     # rewrapped
    "just under 50 MW electrical power",
])
def test_a_verbatim_span_verifies(span):
    assert ap.verify_span(span, QUOTE)


@pytest.mark.parametrize("span", [
    "",
    "   ",
    "twenty 2,499 kW gas engines",             # paraphrase
    "20 no. 2499 kW natural gas engines",      # re-punctuated
    "up to 650 no. 2,480 kW back-up diesel",   # a different passage
])
def test_anything_else_does_not(span):
    assert not ap.verify_span(span, QUOTE)


def test_the_rendered_quote_is_what_a_span_must_match():
    """A span copied from what the model was shown verifies at home.

    The prompt normalises whitespace when it renders a quote; the gate
    checks against the raw evidence_text. If the two normalised
    differently, every span would fail and the batch would store
    nothing.
    """
    rendered = ap.render_generation_figures([{
        "finding_id": 1, "value_mw": 50.0, "value_number": 50,
        "value_unit": "MW", "signal_type": "gas_engine_capacity",
        "evidence_text": QUOTE}])
    span = "20 no. 2,499 kW natural gas engines"
    assert span in rendered
    assert ap.verify_span(span, QUOTE)


# ---------------------------------------------------------------------------
# Choosing the forty
# ---------------------------------------------------------------------------

def _row(site, fid, mw, quote, app=1):
    return {"site_key": site, "site": site, "application_id": app,
            "application_ref": f"REF-{app}", "description": "",
            "finding_id": fid, "document_id": 1, "signal_type": "gen",
            "value_mw": mw, "value_number": mw, "value_unit": "MW",
            "value_text": "", "evidence_text": quote}


def test_one_passage_and_one_figure_is_asked_once():
    rows = [_row("S", 1, 50.0, "the same words"),
            _row("S", 2, 50.0, "the  same   words"),
            _row("S", 3, 50.0, "THE SAME WORDS")]
    assert [r["finding_id"] for r in ag._select_rows(rows, 5)] == [1]


def test_one_passage_with_two_figures_is_asked_twice():
    """The 5,678 kW input and the 2,499 kW output share a sentence."""
    both = ("Each engine has an energy input of 5,678 kW, capable of "
            "delivering 2,499 kW electrical power.")
    rows = [_row("S", 1, 5.678, both), _row("S", 2, 2.499, both)]
    assert [r["finding_id"] for r in ag._select_rows(rows, 5)] == [1, 2]


def test_the_quota_spreads_across_a_site_s_figures():
    """Six rows of Elsham must not be six ways of saying 50 MW."""
    rows = ([_row("S", i, 50.0, f"fifty, said {i} ways") for i in range(1, 21)]
            + [_row("S", 100, 49.9, "the consented cap"),
               _row("S", 101, 5.678, "an energy input"),
               _row("S", 102, 2.499, "one engine")])
    picked = ag._select_rows(rows, 6)
    assert [r["value_mw"] for r in picked] == [50.0, 49.9, 5.678, 2.499,
                                               50.0, 50.0]


def test_selection_does_not_depend_on_arrival_order():
    rows = [_row("S", i, mw, f"quote {i}")
            for i, mw in enumerate([3.0, 9.0, 1.0, 9.0, 4.0], start=1)]
    assert (ag._select_rows(rows, 3)
            == ag._select_rows(list(reversed(rows)), 3))


def test_spread_takes_both_ends_and_the_middle():
    assert ag._spread(list(range(101)), 3) == [0, 50, 100]
    assert ag._spread([1, 2], 5) == [1, 2]
    assert ag._spread([], 3) == []


def _corpus():
    """A stand-in corpus: every named site, plus enough others to fill."""
    by_site: dict[str, list[dict]] = {}
    for app, (key, quota, _why) in enumerate(
            ag.NAMED_CASES + ag.PER_UNIT_SITES, start=1):
        by_site[key] = [_row(key, app * 1000 + i, 100.0 - i,
                             f"{key} passage {i}", app=app)
                        for i in range(quota + 2)]
    for n in range(30):
        key = f"SITE-filler-{n}"
        by_site[key] = [_row(key, 900000 + n, 40.0 - n,
                             "as stated in the documents", app=500 + n)]
    return by_site


def test_the_sample_is_forty_rows_of_distinct_findings():
    rows = ag.choose_sample(_corpus())
    assert len(rows) == ag.SAMPLE_SIZE
    assert len({r["finding_id"] for r in rows}) == ag.SAMPLE_SIZE


def test_every_named_case_is_in_it_at_its_quota():
    rows = ag.choose_sample(_corpus())
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["site_key"]] = counts.get(r["site_key"], 0) + 1
    for key, quota, why in ag.NAMED_CASES + ag.PER_UNIT_SITES:
        assert counts.get(key) == quota, key
        assert all(r["why_in_sample"] == why
                   for r in rows if r["site_key"] == key)


def test_the_named_cases_come_first_and_in_order():
    """A sheet groups its reasons rather than interleaving them."""
    rows = ag.choose_sample(_corpus())
    registry = [(k, q) for k, q, _w in ag.NAMED_CASES + ag.PER_UNIT_SITES]
    expected = [k for k, quota in registry for _ in range(quota)]
    assert [r["site_key"] for r in rows[:len(expected)]] == expected
    assert all(r["why_in_sample"] == "headline as stated"
               for r in rows[len(expected):])


def test_a_missing_named_site_does_not_shrink_the_sample():
    """A partition split can retire a site_key overnight.

    The sample is defined by a list of keys written by hand; if one of
    them stops existing the sheet must still be forty rows, so the loss
    shows up as a site that is absent rather than as four rows that
    quietly never got asked.
    """
    corpus = _corpus()
    del corpus[ag.NAMED_CASES[0][0]]
    rows = ag.choose_sample(corpus)
    assert len(rows) == ag.SAMPLE_SIZE
    assert all(r["site_key"] != ag.NAMED_CASES[0][0] for r in rows)


# ---------------------------------------------------------------------------
# Reading a filled sheet back
# ---------------------------------------------------------------------------

def _write_hand_sheet(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ag.SHEET_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in ag.SHEET_COLUMNS})


def test_a_blank_row_is_unchecked_not_agreement(tmp_path):
    path = tmp_path / "hand.csv"
    _write_hand_sheet(path, [
        {"row": 1, "finding_id": 11, "figure_basis": "per_unit",
         "plant_type": "standby_combustion"},
        {"row": 2, "finding_id": 22},
    ])
    hand = ag.read_hand_sheet(path)
    rows = [_row("S", 11, 3.2, "q"), _row("S", 22, 50.0, "q")]
    run = {"answers": {
        "11": {"figure_basis": "per_unit", "plant_type": "standby_combustion",
               "span_verified": True, "reasoning": ""},
        "22": {"figure_basis": "site_total", "plant_type": "unclear",
               "span_verified": True, "reasoning": ""}}}
    report = "\n".join(ag.score(rows, hand, run))
    assert "1 of 2 rows hand-checked" in report
    assert "figure_basis  1/1" in report


def test_a_value_outside_the_vocabulary_stops_the_scoring(tmp_path):
    path = tmp_path / "hand.csv"
    _write_hand_sheet(path, [
        {"row": 1, "finding_id": 11, "figure_basis": "per unit"}])
    with pytest.raises(SystemExit) as exc:
        ag.read_hand_sheet(path)
    assert "per unit" in str(exc.value)


def test_a_disagreement_is_reported_with_the_model_s_reason(tmp_path):
    path = tmp_path / "hand.csv"
    _write_hand_sheet(path, [
        {"row": 1, "finding_id": 11, "figure_basis": "site_fleet_total",
         "plant_type": "prime_combustion"}])
    hand = ag.read_hand_sheet(path)
    run = {"answers": {"11": {
        "figure_basis": "per_unit", "plant_type": "prime_combustion",
        "span_verified": True, "reasoning": "the quote says each"}}}
    report = "\n".join(ag.score([_row("S", 11, 50.0, "q")], hand, run))
    assert "basis per_unit vs site_fleet_total" in report
    assert "the quote says each" in report


def test_an_unverified_span_is_counted(tmp_path):
    run = {"answers": {"11": {
        "figure_basis": "per_unit", "plant_type": "unclear",
        "span_verified": False, "reasoning": ""}}}
    report = "\n".join(ag.score([_row("S", 11, 50.0, "q")], {}, run))
    assert "did not verify against their quote: 1" in report
