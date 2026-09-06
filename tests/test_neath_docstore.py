"""Neath Port Talbot's iDocs store is read on its own count.

The Idox documents tab refuses; the External Documents tab links to an
Oracle APEX results page — paged "1 - N of N" over rows with direct
`ShowDocument.aspx?id=` links. The parser trusts the page only when the
count is present and matches the rows; a maintenance page or a changed
template is an unrecognised listing, retryable, never "nothing published".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from dcp import acquisition_outcome

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "fetch_neath_docstore", ROOT / "scripts" / "fetch_neath_docstore.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["fetch_neath_docstore"] = mod
spec.loader.exec_module(mod)

FIXTURE = (ROOT / "tests" / "fixtures" / "neath" / "P2024_0791_results.html").read_text()


def test_the_captured_page_parses_to_its_own_count():
    docs = mod.parse_listing(FIXTURE)
    assert len(docs) == 2
    assert docs[0]["url"] == "https://maps.npt.gov.uk/iDocsPublic/ShowDocument.aspx?id=918206"
    assert docs[0]["kind"] == "Decision" and docs[0]["ext"] == "pdf"
    assert "EIA Screening Request" in docs[1]["description"]


def test_a_count_that_disagrees_with_the_rows_is_unrecognised():
    one_row_gone = FIXTURE.replace("ShowDocument.aspx?id=918206", "nowhere", 1)
    with pytest.raises(mod.UnrecognisedListing, match="of 2, page lists 1"):
        mod.parse_listing(one_row_gone)


def test_a_page_without_the_count_is_unrecognised():
    with pytest.raises(mod.UnrecognisedListing, match="no 'a - b of n'"):
        mod.parse_listing("<html><body><h1>APEX is unavailable</h1></body></html>")


def test_verdicts_come_from_the_shared_rule():
    empty = {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
             "errors": 0, "error_class": "no_documents"}
    assert acquisition_outcome.classify_outcome(empty)[0] == "none_published"
    strange = {"errors": 1, "links_found": 0, "error_class": "unrecognised_listing"}
    outcome, _ = acquisition_outcome.classify_outcome(strange)
    assert outcome == "error" and outcome not in acquisition_outcome.SETTLED
