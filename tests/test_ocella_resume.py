"""Ocella resumes from what it holds, and counts only what it wrote.

Until 2026-09-16 the Ocella adapter was the one of seven that never
consulted `repo.held_bytes`, so a re-walk of a completed application
re-downloaded every document; and every adapter counted a document
already on disk as both `skipped_existing` and `downloaded`, so `held`
(their sum, the outcome rule's input) could exceed `links_found`. On a
re-walk where one document failed, the held one was counted twice and
the application read as `fetched`. The Idox test in
tests/test_zero_byte_guard.py is the pattern; this is the same shape on
a two-document Ocella listing built from the committed Hillingdon page.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from dcp import repo
from dcp.acquisition_outcome import classify_outcome
from dcp.sources import ocella

BASE = "https://planning.hillingdon.gov.uk/OcellaWeb/"
APP_URL = BASE + "planningDetails?reference=73420/APP/2021/4569&module=pl"
FIXTURE = Path(__file__).parent / "fixtures" / "ocella" / "hillingdon_populated.html"


def _two_document_listing() -> str:
    """The committed one-document page, with its anchor duplicated for a
    second file — the same markup Ocella serves, twice."""
    html = FIXTURE.read_text(encoding="utf-8")
    anchor = next(line for line in html.splitlines() if "viewDocument?file=" in line)
    second = anchor.replace("pdecnfa-73420_APP_2021_4569-SBY-20220503-1610774608.pdf",
                            "second-document.pdf").replace("DECISION NOTICE", "PLANS")
    assert anchor != second
    return html.replace(anchor, anchor + "\n" + second)


@pytest.fixture
def setup(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(ocella.time, "sleep", lambda s: None)
    listing = _two_document_listing()
    state = {"fail_second": False, "gets": []}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "showDocuments" in url:
            return httpx.Response(200, content=listing.encode())
        assert "viewDocument" in url, url
        state["gets"].append(url)
        if "second-document" in url:
            if state["fail_second"]:
                return httpx.Response(500, content=b"")
            return httpx.Response(200, content=b"%PDF-1.4 second")
        return httpx.Response(200, content=b"%PDF-1.4 first")

    source_id = repo.ensure_source(db_conn, name="ocella", kind="council")
    app_id = repo.upsert_application(db_conn, source_id=source_id,
                                     app={"name": "Hillingdon/73420/APP/2021/4569",
                                          "url": APP_URL})

    def run() -> dict:
        client = ocella.OcellaClient(delay_seconds=0.0, backoff_seconds=0.0,
                                     verify=False)
        client.client = httpx.Client(transport=httpx.MockTransport(handler),
                                     timeout=30, headers={"User-Agent": "test"})
        return ocella.fetch_documents_for_application(
            db_conn, client=client, application_id=app_id,
            application_ref="Hillingdon/73420/APP/2021/4569",
            application_url=APP_URL, source_id=source_id,
            data_dir=tmp_path / "data")

    return run, state


@pytest.mark.integration
def test_a_second_walk_downloads_nothing(setup):
    run, state = setup
    first = run()
    assert (first["links_found"], first["downloaded"], first["skipped_existing"],
            first["errors"]) == (2, 2, 0, 0)
    assert classify_outcome(first)[0] == "fetched"

    gets_before = len(state["gets"])
    second = run()
    assert (second["downloaded"], second["skipped_existing"], second["errors"]) == (0, 2, 0)
    assert len(state["gets"]) == gets_before, "a held document was fetched again"
    assert classify_outcome(second)[0] == "fetched"


@pytest.mark.integration
def test_a_failure_on_a_re_walk_is_partial_not_fetched(setup, db_conn):
    """One document held from before, the other failing today. Before the
    fix the held one was re-downloaded and counted twice, so held (2)
    reached listed (2) and the failure vanished into `fetched`."""
    run, state = setup
    state["fail_second"] = True
    first = run()
    assert (first["downloaded"], first["errors"]) == (1, 1)
    assert classify_outcome(first)[0] == "partial"

    second = run()
    assert (second["downloaded"], second["skipped_existing"], second["errors"]) == (0, 1, 1)
    assert second["downloaded"] + second["skipped_existing"] < second["links_found"]
    assert classify_outcome(second)[0] == "partial"

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents")
        assert cur.fetchone()[0] == 1
