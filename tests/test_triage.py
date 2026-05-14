"""Unit tests for triage prompt formatting + response parsing."""

from __future__ import annotations

import pytest

from dcp import triage
from dcp.llm import FakeBackend


def test_render_user_message_includes_metadata_and_description():
    app = {
        "ref": "Northumberland/24/04112/OUTES",
        "council": "Northumberland (County)",
        "app_type": "Outline",
        "date_received": "2024-11-28",
        "status": "Undecided",
        "address": "Land at Former Power Station Site, Cambois",
        "description": "Outline planning application for ten data centre buildings.",
    }
    msg = triage.render_user_message(app)
    assert "Northumberland/24/04112/OUTES" in msg
    assert "Northumberland (County)" in msg
    assert "Outline" in msg
    assert "Cambois" in msg
    assert "ten data centre buildings" in msg


def test_parse_response_strict_json():
    raw = '{"verdict": "DC", "worth_deep_read": "yes", "signals": ["generator", "substation"], "why": "Explicit DC build.", "confidence": "sure"}'
    v = triage.parse_response(raw)
    assert v.verdict == "DC"
    assert v.worth_deep_read == "yes"
    assert v.signals == ["generator", "substation"]
    assert v.why == "Explicit DC build."
    assert v.confidence == "sure"


def test_parse_response_handles_code_fences():
    raw = "```json\n{\"verdict\": \"adjacent\", \"worth_deep_read\": \"yes\", \"signals\": [\"substation\"], \"why\": \"...\", \"confidence\": \"probable\"}\n```"
    v = triage.parse_response(raw)
    assert v.verdict == "adjacent"
    assert v.confidence == "probable"


def test_parse_response_tolerates_lead_in_prose():
    raw = """Here's my assessment:

{
  "verdict": "DC",
  "worth_deep_read": "maybe",
  "signals": ["plant", "substation"],
  "why": "Borderline case.",
  "confidence": "guessing"
}
"""
    v = triage.parse_response(raw)
    assert v.verdict == "DC"
    assert v.worth_deep_read == "maybe"
    assert v.confidence == "guessing"


def test_parse_response_normalises_loose_values():
    """Small models often slip on exact spelling — normalise where intent is clear."""
    raw = '{"verdict": "Data Centre", "worth_deep_read": "Yes", "signals": [], "why": "x", "confidence": "Probable"}'
    v = triage.parse_response(raw)
    assert v.verdict == "DC"
    assert v.worth_deep_read == "yes"
    assert v.confidence == "probable"


def test_parse_response_handles_string_signals():
    raw = '{"verdict": "DC", "worth_deep_read": "yes", "signals": "generator, substation, fuel storage", "why": "x", "confidence": "sure"}'
    v = triage.parse_response(raw)
    assert v.signals == ["generator", "substation", "fuel storage"]


def test_parse_response_raises_on_no_json():
    with pytest.raises(ValueError):
        triage.parse_response("I don't know what to say.")


def test_triage_application_uses_fake_backend():
    canned = '{"verdict": "DC", "worth_deep_read": "yes", "signals": ["generator"], "why": "explicit DC.", "confidence": "sure"}'
    backend = FakeBackend(responses={"Application:": canned})
    app = {"ref": "X/1", "council": "Test", "description": "data centre"}
    v = triage.triage_application(app, backend)
    assert v.verdict == "DC"
    assert v.signals == ["generator"]
    # The fake backend should have received our rendered message
    assert len(backend.calls) == 1
    assert "X/1" in backend.calls[0][0]


class _GarbageThenJsonBackend:
    """Returns prose on first call, valid JSON on second. Simulates a model
    that needed a JSON-only reminder."""

    def __init__(self, second_response: str):
        self.second_response = second_response
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None):
        from dcp.llm import LLMResponse
        self.calls.append((prompt, system))
        if len(self.calls) == 1:
            return LLMResponse(text="Sure! Here's my view: it's a DC.", model="fake")
        return LLMResponse(text=self.second_response, model="fake")


def test_triage_application_retries_on_parse_error():
    json_ok = '{"verdict": "DC", "worth_deep_read": "yes", "signals": [], "why": "x", "confidence": "sure"}'
    backend = _GarbageThenJsonBackend(json_ok)
    app = {"ref": "X/1", "council": "Test", "description": "data centre"}
    v = triage.triage_application(app, backend)
    assert v.verdict == "DC"
    # Two calls — first failed parse, second succeeded
    assert len(backend.calls) == 2
    # The retry's prompt should contain the JSON-only reminder
    assert "Return ONLY the JSON" in backend.calls[1][0]


def test_triage_application_no_retry_raises():
    backend = _GarbageThenJsonBackend('{"verdict": "DC", "worth_deep_read": "yes", "signals": [], "why": "x", "confidence": "sure"}')
    app = {"ref": "X/1", "council": "Test", "description": "data centre"}
    with pytest.raises(ValueError):
        triage.triage_application(app, backend, retry_on_parse_error=False)
    assert len(backend.calls) == 1


def test_triage_application_double_failure_raises():
    """If both attempts return unparseable text, the second ValueError propagates."""
    class _AlwaysBad:
        def __init__(self):
            self.calls = []
        def complete(self, prompt, *, system=None):
            from dcp.llm import LLMResponse
            self.calls.append((prompt, system))
            return LLMResponse(text="not json at all", model="fake")
    backend = _AlwaysBad()
    app = {"ref": "X/1", "council": "Test", "description": "data centre"}
    with pytest.raises(ValueError):
        triage.triage_application(app, backend)
    assert len(backend.calls) == 2  # retried once
