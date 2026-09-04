"""An unrecognised body is not an empty register.

`none_published` is a settled verdict: it takes an application out of
`fetch_outstanding`'s queue for good and renders in the reader as
"checked, and the council publishes nothing" — a claim about a council,
made in our name. `dcp.acquisition_outcome` awards it only when nothing
was listed and nothing failed, so the whole weight rests on adapters
telling an empty listing apart from a body they could not read.

Three of them can reach that verdict, and until 2026-09-04 one could
reach it from a body that was never a listing: Agile's `documents()`
ended `data if isinstance(data, list) else []`, the same `or []` shape
that `acquisition_outcome`'s own docstring records as having cost 17
Newport applications. Twelve applications sit settled behind it, eleven
of them Slough's, two of those load-bearing for the VIRTUS Slough campus
review.

These tests pin the rule in both directions, because a fix that only
made the adapter stricter would settle nothing at all and look just as
green: an unrecognised body must not settle, and a genuinely empty
register must still settle.
"""

from __future__ import annotations

import json

import pytest

from dcp import acquisition_outcome
from dcp.sources import agile, aifusion


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    def json(self):
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload


class _Http:
    """Stands in for the client's httpx transport."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, url, headers=None):
        return _Response(self._payload)


def _client(payload):
    client = agile.AgileClient.__new__(agile.AgileClient)
    client._http = _Http(payload)
    client._headers = lambda slug: {}
    return client


class TestAgileListing:
    def test_a_real_list_passes_through(self):
        docs = [{"documentHash": "abc", "fileName": "statement.pdf"}]
        assert _client(docs).documents("slough", "1") == docs

    def test_an_empty_list_is_a_recognised_empty(self):
        """The register saying "none" is a real answer and must keep
        reaching the settled arm; otherwise the fix trades a false
        negative for an unclosable queue."""
        assert _client([]).documents("slough", "1") == []

    @pytest.mark.parametrize("body", [
        {"message": "Client has not beeing selected"},   # the 401 body, served 200
        {"error": "not found"},
        {},
        None,                                            # a literal JSON null
    ])
    def test_a_body_that_is_not_a_list_raises(self, body):
        with pytest.raises(agile.UnrecognisedListing):
            _client(body).documents("slough", "1")

    def test_a_body_that_is_not_json_at_all_was_already_safe(self):
        """Not this fix's route, pinned so the distinction stays visible:
        a non-JSON body fails in `r.json()`, and the adapter's own
        `except Exception` arm records it with `errors`, which keeps it
        out of the settled verdict. Only a body that parses and is not a
        list needed the new guard."""
        with pytest.raises(json.JSONDecodeError):
            _client("OK").documents("slough", "1")

    def test_the_error_names_the_body_it_could_not_read(self):
        """A detail that says only "failed" sends the next person back to
        the portal to find out what happened."""
        with pytest.raises(agile.UnrecognisedListing) as exc:
            _client({"message": "Client has not beeing selected"}).documents("s", "1")
        assert "Client has not beeing selected" in str(exc.value)


class TestWhatEachOutcomeSettles:
    """The adapter summary a body produces, put through the real
    classifier — which is where the damage would land."""

    def test_an_unrecognised_listing_is_retryable_not_settled(self):
        summary = {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
                   "errors": 1, "error_class": "unrecognised_listing"}
        outcome, _detail = acquisition_outcome.classify_outcome(summary)
        assert outcome == "error"
        assert outcome not in acquisition_outcome.SETTLED

    def test_a_recognised_empty_still_settles(self):
        summary = {"links_found": 0, "downloaded": 0, "skipped_existing": 0,
                   "errors": 0, "error_class": "no_documents"}
        outcome, detail = acquisition_outcome.classify_outcome(summary)
        assert outcome == "none_published"
        assert detail == "no_documents"
        assert outcome in acquisition_outcome.SETTLED


class TestAifusionIndex:
    def test_an_index_holding_no_documents_is_a_recognised_empty(self):
        assert aifusion._flatten({"documentsByType": []}) == []

    def test_a_json_object_without_the_index_key_is_not_an_empty_index(self):
        """`_flatten`'s `or []` reads a stray object as an empty index,
        and `no_documents` is settled-eligible. The guard is in
        `list_documents`, which is what the adapter calls."""
        class _C:
            def get(self, url):
                return _Response({"status": "error"})
        assert aifusion.list_documents(
            _C(), api_base="https://api.example/planning", case_id="CB-1") is None

    def test_the_bare_ok_body_is_still_not_a_case(self):
        class _C:
            def get(self, url):
                return _Response("OK")
        assert aifusion.list_documents(
            _C(), api_base="https://api.example/planning", case_id="CB-1") is None
