"""The legacy store's own words decide whether a null is settled.

`fetch_slough_legacy.py` searches a PHP store for documents the current
Agile register reports as absent. Until 2026-09-04 it took an empty PDF
list as "no documents in the legacy store", logged that, and wrote
nothing: the check left no trace, so eleven applications kept an
acquisition record showing only the Agile adapter's empty, and the fact
that the store had been searched independently survived in
`docs/PORTAL_NOTES.md` prose alone.

Two things had to be true before the check could be recorded. An empty
PDF list is also what a changed form, a dropped session or a maintenance
page looks like, and `no_documents` is settled-eligible — so the store
has to say it found nothing, in its own words, before we say so on its
behalf. And the verdict has to come from `classify_outcome`, so this
route cannot award one the adapters would not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "fetch_slough_legacy", ROOT / "scripts" / "fetch_slough_legacy.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["fetch_slough_legacy"] = mod
spec.loader.exec_module(mod)

from dcp import acquisition_outcome

# Trimmed from the real responses, captured 2026-09-04.
HIT = """<html><body>Searching Planning Applications for P/00072/096
<table><tr><td>P/00072/096</td><td>LAND AT FORMER AKZONOBEL SITE</td>
<td><a href="/sbcp/planapp/P72-96.pdf">View</a></td></tr></table>
<a href="/sbcp/scaling.pdf">scaling</a></body></html>"""

MISS = """<html><body>Searching Planning Applications for P/20054/000
<p>No results found (searching for P/20054/000 in Planning Number)</p>
<a href="/sbcp/scaling.pdf">scaling</a></body></html>"""

STRANGE = """<html><body><h1>Planning search is unavailable</h1>
<p>The service is down for maintenance.</p></body></html>"""


class _Response:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, text):
        self._text = text

    def post(self, url, data=None, headers=None):
        return _Response(self._text)


class TestSearchPage:
    def test_a_results_page_yields_its_documents(self):
        urls = mod.search_documents(_Client(HIT), "P/00072/096")
        assert urls == ["https://www.sbcplanning.co.uk/sbcp/planapp/P72-96.pdf"]

    def test_the_help_pdf_on_every_page_is_not_a_document(self):
        assert all("scaling" not in u
                   for u in mod.search_documents(_Client(HIT), "P/00072/096"))

    def test_a_stated_miss_is_an_empty_register(self):
        """The store's own "No results found" is what makes the null
        ours to record."""
        assert mod.search_documents(_Client(MISS), "P/20054/000") == []

    def test_a_page_that_is_neither_raises(self):
        """A maintenance page carries no document links either, and
        reading it as an empty register would settle the application."""
        with pytest.raises(mod.UnrecognisedSearchPage):
            mod.search_documents(_Client(STRANGE), "P/20054/000")

    def test_the_error_says_what_it_saw(self):
        with pytest.raises(mod.UnrecognisedSearchPage) as exc:
            mod.search_documents(_Client(STRANGE), "P/20054/000")
        assert "P/20054/000" in str(exc.value)


class TestWhatGetsRecorded:
    def test_a_stated_miss_settles_as_none_published(self):
        outcome, _detail = acquisition_outcome.classify_outcome(
            {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
             "errors": 0, "error_class": "no_documents"})
        assert outcome == "none_published"
        assert outcome in acquisition_outcome.SETTLED

    def test_an_unrecognised_page_does_not_settle(self):
        outcome, _ = acquisition_outcome.classify_outcome(
            {"links_found": 0, "errors": 1,
             "error_class": "unrecognised_search_page"})
        assert outcome == "error"
        assert outcome not in acquisition_outcome.SETTLED

    def test_documents_found_and_stored_read_as_fetched(self):
        outcome, _ = acquisition_outcome.classify_outcome(
            {"links_found": 3, "downloaded": 3, "skipped_existing": 0,
             "errors": 0})
        assert outcome == "fetched"

    def test_the_route_is_named_so_the_fold_shows_where_it_came_from(self):
        """Attributing this to the Agile register would credit the
        check to the source that reports these applications empty."""
        assert mod.ADAPTER == "slough_legacy"


class TestTheWriterIsShared:
    def test_the_scripts_import_the_writer_rather_than_copying_it(self):
        """It was copied verbatim into two scripts; a third copy is what
        prompted the move to `dcp.acquisition_outcome`."""
        assert callable(acquisition_outcome.record)
        for name in ("fetch_outstanding.py", "relist_refetch.py",
                     "fetch_slough_legacy.py"):
            src = (ROOT / "scripts" / name).read_text()
            assert "INSERT INTO acquisition_outcome" not in src, name
            assert "import" in src and "record" in src, name
