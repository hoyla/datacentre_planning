"""Smoke tests: confirm core modules import and FakeBackend works without external services."""

from dcp.llm import FakeBackend, LLMResponse


def test_fake_backend_returns_canned_response():
    backend = FakeBackend(responses={"hello": "world"})
    resp = backend.complete("hello, planet")
    assert isinstance(resp, LLMResponse)
    assert resp.text == "world"
    assert resp.model == "fake"


def test_fake_backend_records_calls():
    backend = FakeBackend()
    backend.complete("first", system="sys-a")
    backend.complete("second")
    assert backend.calls == [("first", "sys-a"), ("second", None)]


def test_fake_backend_falls_back_to_empty():
    backend = FakeBackend(responses={"known": "yes"})
    resp = backend.complete("unknown prompt")
    assert resp.text == ""
