"""Civica's document store is read on its own word, and only for the case asked.

Gateshead, Chelmsford, Reigate & Banstead and Southend refuse their
Idox documents tab and publish from a Civica portal whose page fills
itself by API. The search endpoint answers a search it does not
understand with the whole register, so the parser trusts a result only
when exactly one case names the reference back; the document list is
trusted only when its rows match its own `RowCount`. Anything else is
an unrecognised listing — retryable — and never "nothing published".
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from dcp import acquisition_outcome

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "fetch_civica_docstore", ROOT / "scripts" / "fetch_civica_docstore.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["fetch_civica_docstore"] = mod
spec.loader.exec_module(mod)

FIX = ROOT / "tests" / "fixtures" / "civica"
SEARCH = (FIX / "gateshead_23_00495_DOC4_search.json").read_text()
DOCLIST = (FIX / "gateshead_23_00495_DOC4_doclist.json").read_text()


def test_the_captured_search_names_the_case_once():
    assert mod.parse_search(SEARCH, "Gateshead/23/00495/DOC4") == ("105380", "Subject")


def test_a_search_answered_with_the_wrong_case_is_unrecognised():
    # The unfiltered answer: a real case, not the one asked for.
    with pytest.raises(mod.UnrecognisedListing, match="0 naming the reference"):
        mod.parse_search(SEARCH, "Gateshead/26/0141/HPE")
    two = json.dumps(json.loads(SEARCH) * 2)
    with pytest.raises(mod.UnrecognisedListing, match="2 naming the reference"):
        mod.parse_search(two, "Gateshead/23/00495/DOC4")
    with pytest.raises(mod.UnrecognisedListing, match="not JSON"):
        mod.parse_search("<html>maintenance</html>", "Gateshead/23/00495/DOC4")


def test_the_captured_list_parses_to_its_own_count():
    docs = mod.parse_doclist(DOCLIST)
    assert len(docs) == 4
    assert docs[-1]["docno"] == "24867237" and docs[-1]["kind"] == "Application Form"
    assert docs[-1]["filename"] == "ApplicationForm - Redacted.pdf"
    assert mod.document_url("Gateshead", "24867237") == (
        "https://myserviceplanning.gateshead.gov.uk/w2webparts/Resource/Civica/"
        "Handler.ashx/Doc/pagestream?cd=download&pdf=false&docno=24867237")


def test_an_empty_list_is_empty_only_on_the_stores_word():
    assert mod.parse_doclist('{"CompleteDocument": [], "RowCount": "0"}') == []
    with pytest.raises(mod.UnrecognisedListing, match="RowCount"):
        mod.parse_doclist('{"CompleteDocument": []}')
    with pytest.raises(mod.UnrecognisedListing, match="RowCount 4, list carries 3"):
        obj = json.loads(DOCLIST); obj["CompleteDocument"].pop()
        mod.parse_doclist(json.dumps(obj))


def test_a_council_without_a_store_is_refused():
    with pytest.raises(ValueError, match="Derby"):
        mod.council_of("Derby/19/01343/FUL")


def test_verdicts_come_from_the_shared_rule():
    empty = {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
             "errors": 0, "error_class": "no_documents"}
    assert acquisition_outcome.classify_outcome(empty)[0] == "none_published"
    strange = {"errors": 1, "links_found": 0, "error_class": "unrecognised_listing"}
    outcome, _ = acquisition_outcome.classify_outcome(strange)
    assert outcome == "error" and outcome not in acquisition_outcome.SETTLED
