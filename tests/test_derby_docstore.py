"""Derby's document server is read on its own word.

`eplanning.derby.gov.uk` refuses its Idox documents tab with an HTTP
200; the register's External Documents tab points at
`docs.derby.gov.uk/padocumentserver`, whose `MainTable.aspx` lists the
case's documents under a "Documents found N" count. The parser returns
an empty list only when that count is present, and cross-checks the
count against the rows, so a maintenance page, a login redirect or a
paginated template is an unrecognised listing — retryable — and never
"the applicant published nothing". Verdicts go through
`classify_outcome`, so this route cannot award one the adapters would not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from dcp import acquisition_outcome

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "fetch_derby_docstore", ROOT / "scripts" / "fetch_derby_docstore.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["fetch_derby_docstore"] = mod
spec.loader.exec_module(mod)

FIXTURE = (ROOT / "tests" / "fixtures" / "derby" / "19_01343_FUL_maintable.html").read_text()


def test_the_captured_listing_parses_to_its_own_count():
    rows = mod.parse_listing(FIXTURE)
    assert len(rows) == 12
    assert rows[0] == {"kind": "Decision Notice", "description": "Decision Notice",
                       "published": "24/10/2019", "docid": "141662628"}
    assert {r["kind"] for r in rows} >= {"Application Documents", "Decision Notice"}
    assert mod.download_url(rows[0]["docid"]).endswith("DownloadDocument.aspx?docid=141662628")


def test_an_empty_store_is_empty_only_on_its_own_word():
    empty = FIXTURE.replace("12", "0")
    empty = mod.ROW_RE.sub("", empty)
    assert mod.parse_listing(empty) == []


def test_a_page_without_the_count_is_unrecognised():
    with pytest.raises(mod.UnrecognisedListing):
        mod.parse_listing("<html><body><h1>Service unavailable</h1></body></html>")


def test_a_count_that_disagrees_with_the_rows_is_unrecognised():
    with pytest.raises(mod.UnrecognisedListing, match="says 12 documents, page lists 11"):
        mod.parse_listing(FIXTURE.replace(
            '<tr class="firstrow-data"><td>Decision Notice</td><td>Decision Notice</td>'
            '<td>24/10/2019</td><td class="doc-id">141662628</td></tr>', "", 1))


def test_verdicts_come_from_the_shared_rule():
    empty = {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
             "errors": 0, "error_class": "no_documents"}
    assert acquisition_outcome.classify_outcome(empty)[0] == "none_published"
    strange = {"errors": 1, "links_found": 0, "error_class": "unrecognised_listing"}
    outcome, _ = acquisition_outcome.classify_outcome(strange)
    assert outcome == "error" and outcome not in acquisition_outcome.SETTLED
