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

from pathlib import Path

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


def test_a_dropped_comma_does_not_refuse_a_quote():
    """Every word and figure in order; punctuation between them is free."""
    r = _reading("The IT load is 168 MW.",
                 [_q("housed in acoustic enclosures The total IT load is 168 MW")])
    assert mr.gate(r, _inp()).ok


def test_a_space_inside_a_word_on_the_page_does_not_refuse_a_quote():
    """Ocean Estates, 2026-08-23: the page reads "general buildi ng
    services"; the quote reads the word. gate-1.1 refused it."""
    page = ("Of the supply, 3,600kW will be consumed by the IT servers and 60kW "
            "(13%) by the general buildi ng services. The power  infrastructure "
            "will achieve a minimum operational efficiency of 97%")
    inp = _inp()
    inp = mr.SiteInput("PTNO-1", "A Site", inp.panel,
                       pages=[mr.Page(41, "Hertsmere/25/1781/FUL", "Energy Statement", 7, page)],
                       cache={41: ["", "", "", "", "", "", page]})
    r = _reading("60kW goes to building services.",
                 [_q("and 60kW (13%) by the general building services. The power "
                     "infrastructure will achieve")])
    assert mr.gate(r, inp).ok
    # A changed word is still a changed word once the spaces are gone.
    r = _reading("60kW goes to building services.",
                 [_q("and 60kW (13%) by the landlord building services")])
    assert not mr.gate(r, inp).ok


def test_a_changed_word_still_refuses():
    r = _reading("The IT load is 168 MW.",
                 [_q("housed in quiet enclosures. The total IT load is 168 MW")])
    assert not mr.gate(r, _inp()).ok


def test_a_quote_under_the_wrong_citation_is_re_attributed_and_recorded():
    q = _q("a 120 MW grid connection", doc=41, page=7)
    r = _reading("A 120 MW grid connection is stated.", [q])
    inp = _inp()
    inp.cache[77] = ["unrelated", "The site benefits from a 120 MW grid connection."]
    del inp.cache[41][7]          # not in the cited document any more
    v = mr.gate(r, inp)
    assert v.ok, v.reason
    assert q["document_id"] == 77 and q["page"] == 2
    assert q["cited_document_id"] == 41


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


def test_a_quote_in_none_of_the_site_s_documents_is_refused():
    r = _reading("The IT load is 168 MW.", [_q("The IT load is 168 MW, said nobody",
                                               doc=41)])
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


def test_one_bad_paragraph_is_withheld_and_the_rest_stand():
    """gate-2.0: the paragraph is the unit. One slip in forty quotes no
    longer costs the thirty-nine verified ones around it."""
    r = {"sections": {"what_the_documents_say": [
            {"text": "The IT load is 168 MW.",
             "quotes": [_q("The total IT load is 168 MW")]},
            {"text": "The connection is 120 MW.",
             "quotes": [_q("a connection of one hundred and twenty megawatts, "
                           "words the page does not contain")]},
         ], "questions": [], "not_determined": []}}
    v = mr.gate(r, _inp())
    assert v.ok
    assert (v.paragraphs_passed, v.paragraphs_withheld) == (1, 1)
    paras = r["sections"]["what_the_documents_say"]
    assert "withheld" not in paras[0]
    assert "quote not found" in paras[1]["withheld"]


def test_a_reading_whose_every_paragraph_fails_is_refused():
    r = _reading("The load is 999 MW.", [_q("words the page does not contain")])
    v = mr.gate(r, _inp())
    assert not v.ok and v.paragraphs_withheld == 1
    assert "all 1 paragraphs withheld" in v.reason


def test_asking_about_intent_is_a_question_not_an_assertion():
    ask = "Does the applicant intend to run the engines at night? The energy "          "statement does not say."
    r = _reading(ask, [], section="questions")
    assert mr.gate(r, _inp()).ok
    r = _reading("The applicant intends to run the engines at night.", [],
                 section="what_the_documents_say")
    v = mr.gate(r, _inp())
    assert not v.ok


def test_a_quote_across_a_page_break_survives_the_running_header():
    """Watford's BREEAM refusal: the register document's header sat in
    the middle of the sentence where the page turned."""
    header = "REF LON02A-BWE-XX-XX-DN-N-960001 Date of issue 2025-11-04"
    pages = [f"Something else entirely.\n{header}",
             f"The aim is to achieve the same number of credits\n{header}",
             f"{header}\nthat would see the scheme achieving BREEAM Excellent.",
             f"More text.\n{header}"]
    inp = _inp()
    inp = mr.SiteInput("PTNO-1", "A Site", inp.panel,
                       pages=[mr.Page(41, "Hertsmere/25/1781/FUL", "Design note", 2, pages[1])],
                       cache={41: pages})
    r = _reading("The design note describes the BREEAM aim.",
                 [_q("The aim is to achieve the same number of credits that would "
                     "see the scheme achieving BREEAM Excellent.")])
    assert mr.gate(r, inp).ok


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


def test_the_sample_markdown_shows_a_withheld_paragraph_as_its_reason():
    """The checkpoint is read on the markdown, so the markdown has to
    show what the reader will show: a withheld paragraph's reason
    standing where the paragraph would have been, and not its text."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "machine_reading_openai",
        Path(__file__).resolve().parent.parent / "scripts"
        / "machine_reading_openai.py")
    mro = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mro)

    inp = _inp()
    r = {"sections": {"what_the_documents_say": [
            {"text": "The IT load is 168 MW.",
             "quotes": [_q("The total IT load is 168 MW")]},
            {"text": "The connection is 120 MW.",
             "quotes": [_q("a connection of one hundred and twenty megawatts, "
                           "words the page does not contain")]},
         ], "questions": [], "not_determined": []}}
    verdict = mr.gate(r, inp)
    md = mro._markdown(inp, r, verdict, "gpt-5")

    assert "The IT load is 168 MW." in md
    assert "The connection is 120 MW." not in md
    assert "One paragraph withheld:" in md
    # The reason names the quote that failed, as the reader's does; what
    # must not survive is the paragraph's own assertion.
    assert "> The total IT load is 168 MW" in md   # the passing quote stands


# ---------------------------------------------------------------------------
# What a refusal may say on a page
# ---------------------------------------------------------------------------
# Luke, 2026-08-24, reading the withheld line in the built page: the
# commonest failure is a quote that is in none of the site's documents,
# so the model's words are a misquote or an invention — and the reason
# was printing them. One of the eight withheld paragraphs in the sample
# rendered "29.9 L/s" inside the sentence saying it could not be
# verified. A reader scanning that takes away a number, not a caveat.

def test_a_quote_that_verified_against_nothing_is_not_repeated():
    full = ('quote not found in document 5294 or any other the site holds: '
            '"The total surface water discharge of 29.9 L/s from the site '
            'will be controlled u"')
    public = mr.public_reason(full)
    assert "29.9" not in public and "surface water" not in public
    assert "document 5294" in public          # still checkable
    assert "not in" in public


def test_an_unevidenced_figure_is_not_reprinted():
    public = mr.public_reason("the figure '3.3 MWt' is not in any quote "
                              "attached to it")
    assert "3.3" not in public and "MWt" not in public
    assert "figure" in public and "quotes" in public


@pytest.mark.parametrize("reason", [
    "uses 'plans to', which the rules forbid",
    "names another site (SITE-Slough/P/00437/093)",
])
def test_a_reason_that_repeats_nothing_unverified_stands(reason):
    """These two quote the model's own vocabulary or a site key, neither
    of which is a claim about the world."""
    assert mr.public_reason(reason) == reason


def test_the_stored_reason_keeps_everything():
    """The redaction is for the page. The row is the audit trail, and the
    markdown a person checks against shows the quote that failed."""
    r = {"sections": {"what_the_documents_say": [
            {"text": "The connection is 120 MW.",
             "quotes": [_q("a connection of one hundred and twenty megawatts, "
                           "words the page does not contain")]},
         ], "questions": [], "not_determined": []}}
    mr.gate(r, _inp())
    stored = r["sections"]["what_the_documents_say"][0]["withheld"]
    assert "one hundred and twenty megawatts" in stored
    assert "one hundred and twenty megawatts" not in mr.public_reason(stored)


def test_a_nul_anywhere_in_a_reading_is_stripped_at_the_database_boundary():
    """Postgres refuses JSON carrying an escaped \\u0000, and a model can
    emit a NUL the source never contained: one arrived nested inside a
    quote in the 2026-08-27 batch and stopped a 250-site collect at
    site 157. The strip is recursive because a reading is nested — the
    flat per-field version in the deep-read path cannot reach it.
    """
    import json
    from scripts.machine_reading_openai import _no_nul

    reading = {"sections": {"what_the_documents_say": [
        {"text": "Generator rooms\x00 are shown.",
         "quotes": [{"quote": "Building 1 Generator rooms\x00",
                     "document_id": 7}]},
    ]}}
    clean = _no_nul(reading)
    assert "\x00" not in json.dumps(clean)
    assert "\\u0000" not in json.dumps(clean)
    quote = clean["sections"]["what_the_documents_say"][0]["quotes"][0]
    assert quote["quote"] == "Building 1 Generator rooms"
    assert quote["document_id"] == 7, "non-strings pass through untouched"
    assert reading["sections"]["what_the_documents_say"][0]["quotes"][0][
        "quote"].endswith("\x00"), "the input is not mutated"
