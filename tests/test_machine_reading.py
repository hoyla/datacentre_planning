"""The prose gate: what a machine's reading may not do, checked.

Unit tests over dcp.machine_reading with hand-built inputs. The gate is
the only thing between a model's paragraph and a reporter's screen, so
its refusals are tested one by one: a figure with no quote; a quote
that is not in the document; a quote in the wrong document; a figure
in the text that its own paragraph's quotes do not contain; a sentence
that names another site, infers intent, ranks, or advises. And the
acceptances: a verbatim page quote, a quote of an adjudicated finding,
an ellipsis quote, whitespace that a PDF wrapped differently.
"""

from __future__ import annotations

import pytest

from dcp import machine_reading as mr

PAGE_7 = ("The proposed development comprises 112 No. standby generators "
          "(likely to be 3.2MWe Rolls Royce MTU DS4000 20V4000 G94LF) "
          "housed in acoustic enclosures. The total IT load is 168 MW.")
PAGE_8 = "The site benefits from a 120 MW grid connection from Letchmore Heath."


def _inp(**over):
    panel = {
        "site_key": "PTNO-1", "name": "A Site", "applications": [],
        "adjudicated_figures": [{
            "quantity": "total_site", "value_mw": 218.4, "is_maximum": False,
            "application_ref": "Hertsmere/25/1781/FUL", "document_id": 41,
            "page": 3, "quote": "total electricity demand at PUE 1.3 of 218.4 MW",
            "label": "power_demand_mw"}],
        "external_claims": [], "coverage": {},
        "generation": {"figure_basis": "", "figure_note": "",
                       "generator_count": None, "generator_fuel": "",
                       "generator_caveat": ""},
        "parties": {k: "" for k in ("end_user", "applicant_of_record",
                                    "operator_group", "advisers",
                                    "named_in_documents", "authority",
                                    "parties_source")},
        "cohorts": [],
    }
    panel.update(over)
    return mr.SiteInput("PTNO-1", "A Site", panel,
                        pages=[mr.Page(41, "Hertsmere/25/1781/FUL",
                                       "Planning Statement", 7, PAGE_7)],
                        cache={41: ["", "", "", "", "", "", PAGE_7, PAGE_8]})


def _reading(text, quotes, section="what_the_documents_say"):
    return {"sections": {"what_the_documents_say": [], "questions": [],
                         "not_determined": [],
                         section: [{"text": text, "quotes": quotes}]}}


def _q(quote, doc=41, page=7, ref=None):
    return {"quote": quote, "document_id": doc, "page": page,
            "application_ref": ref}


# ---------------------------------------------------------------------------
# Acceptances
# ---------------------------------------------------------------------------

def test_a_figure_with_a_verbatim_page_quote_passes():
    r = _reading("The documents describe 112 standby generators of 3.2 MWe.",
                 [_q("112 No. standby generators (likely to be 3.2MWe")])
    v = mr.gate(r, _inp())
    assert v.ok, v.reason
    assert v.figures_checked == 2 and v.quotes_checked == 1


def test_a_quote_wrapped_differently_by_the_pdf_still_verifies():
    r = _reading("The total IT load is stated as 168 MW.",
                 [_q("The total IT\nload is   168 MW")])
    assert mr.gate(r, _inp()).ok


def test_an_ellipsis_quote_verifies_in_order():
    r = _reading("The generators are 3.2 MWe units; IT load is 168 MW.",
                 [_q("112 No. standby generators … 3.2MWe … 168 MW")])
    assert mr.gate(r, _inp()).ok


def test_a_quote_from_the_wrong_page_is_found_on_the_right_one():
    """The page number is a hint, not a condition."""
    r = _reading("A 120 MW grid connection is stated.",
                 [_q("a 120 MW grid connection", page=2)])
    assert mr.gate(r, _inp()).ok


def test_a_quote_of_an_adjudicated_figure_passes_by_application_ref():
    r = _reading("The adjudicated total site demand is 218.4 MW.",
                 [_q("total electricity demand at PUE 1.3 of 218.4 MW",
                     doc=None, page=None, ref="Hertsmere/25/1781/FUL")])
    assert mr.gate(r, _inp()).ok


def test_a_paragraph_with_no_figures_needs_no_quote():
    r = _reading("The officer report recommends approval subject to conditions.",
                 [])
    assert mr.gate(r, _inp()).ok


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_a_figure_with_no_quote_is_refused():
    r = _reading("The IT load is 168 MW.", [])
    v = mr.gate(r, _inp())
    assert not v.ok and "168 MW" in v.reason


def test_a_figure_not_in_its_own_paragraph_s_quotes_is_refused():
    """The quote is real, but it does not contain the figure written."""
    r = _reading("The IT load is 168 MW and the connection 120 MW.",
                 [_q("The total IT load is 168 MW")])
    v = mr.gate(r, _inp())
    assert not v.ok and "120 MW" in v.reason


def test_a_quote_not_in_the_document_is_refused():
    r = _reading("The IT load is 168 MW.", [_q("The total IT load is 168 MW",
                                               doc=99)])
    v = mr.gate(r, _inp())
    assert not v.ok and "quote not found" in v.reason


def test_a_paraphrased_quote_is_refused():
    r = _reading("There are 112 generators.",
                 [_q("one hundred and twelve standby generators")])
    assert not mr.gate(r, _inp()).ok


def test_a_figure_from_outside_the_documents_is_refused():
    """The model knew something; the documents did not say it."""
    r = _reading("The operator runs 40 MW elsewhere and 168 MW here.",
                 [_q("The total IT load is 168 MW")])
    v = mr.gate(r, _inp())
    assert not v.ok and "40 MW" in v.reason


@pytest.mark.parametrize("text", [
    "This is one of the largest schemes in the county.",
    "Compared with other sites, the connection is small.",
    "The applicant intends to run the engines continuously.",
    "Reporters should ask the council about the discharge.",
    "This is a red flag.",
    "The applicant really wants a gas plant.",
])
def test_ranking_intent_and_advice_are_refused(text):
    v = mr.gate(_reading(text, []), _inp())
    assert not v.ok and "forbid" in v.reason


def test_naming_another_site_is_refused():
    v = mr.gate(_reading("As at PTNO-12849818, the fleet is diesel.", []), _inp())
    assert not v.ok and "another site" in v.reason


def test_naming_this_site_s_own_key_is_fine():
    v = mr.gate(_reading("The record for PTNO-1 holds one application.", []),
                _inp())
    assert v.ok


def test_an_empty_reading_is_refused():
    v = mr.gate({"sections": {"what_the_documents_say": [], "questions": [],
                              "not_determined": []}}, _inp())
    assert not v.ok and "empty" in v.reason


def test_every_section_is_gated():
    r = _reading("Who could say whether 500 MW is the figure? The grid operator.",
                 [], section="questions")
    assert not mr.gate(r, _inp()).ok


# ---------------------------------------------------------------------------
# Inputs and the hash
# ---------------------------------------------------------------------------

def test_the_input_hash_moves_with_the_text_and_the_facts():
    a = _inp()
    b = _inp()
    assert a.input_hash == b.input_hash
    c = _inp()
    c.pages[0].text += " Amended."
    assert c.input_hash != a.input_hash
    d = _inp(parties={**a.panel["parties"], "end_user": "Someone"})
    assert d.input_hash != a.input_hash


def test_page_selection_never_sends_objections_or_drawings(tmp_path, monkeypatch):
    import json
    root = tmp_path / "raw_text" / "documents" / "REF"
    root.mkdir(parents=True)
    for sha, pages in (("a" * 16, ["planning statement 10 MW"]),
                       ("b" * 16, ["objection letter 10 MW"]),
                       ("c" * 16, ["elevation 10 MW"])):
        (root / f"{sha}.pages.json").write_text(json.dumps({"pages": pages}))
    monkeypatch.setattr(mr.extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    docs = [(1, "REF", "Planning Statement", "a" * 16, 1, ""),
            (2, "REF", "Objection", "b" * 16, 1, ""),
            (3, "REF", "Proposed Elevations", "c" * 16, 1, "")]
    pages, cache, considered = mr.select_pages(docs)
    assert [p.document_id for p in pages] == [1]
    assert considered == 1
    # Every document's text is still in the cache for the gate: a quote
    # from an objection is still a verbatim quote from the file.
    assert set(cache) == {1, 2, 3}


def test_page_selection_respects_the_budget_and_kind_order(tmp_path, monkeypatch):
    import json
    root = tmp_path / "raw_text" / "documents" / "REF"
    root.mkdir(parents=True)
    big = "grid connection 50 MW " * 200     # ~4,400 chars, relevant
    (root / ("a" * 16 + ".pages.json")).write_text(json.dumps({"pages": [big, big]}))
    (root / ("b" * 16 + ".pages.json")).write_text(json.dumps({"pages": [big]}))
    monkeypatch.setattr(mr.extract, "RAW_TEXT_ROOT", tmp_path / "raw_text")
    docs = [(1, "REF", "Planning Statement", "a" * 16, 2, ""),
            (2, "REF", "Environment Agency response", "b" * 16, 1, "")]
    pages, _, _ = mr.select_pages(docs, budget=len(big) + 10)
    assert [(p.document_id, p.page) for p in pages] == [(2, 1)], \
        "the consultee letter outranks the applicant's statement"


def test_the_prompt_carries_the_rules_the_gate_enforces():
    for phrase in ("verbatim", "Do not compare", "Do not infer intent",
                   "Do not advise", "Do not add knowledge"):
        assert phrase in mr.PROMPT, phrase
