"""Tests for the dc_build rubric plumbing (taxonomy parsing, rubric registry,
backend dispatch). The prompt's classification *quality* is measured by
scripts/eval_triage.py against labelled ground truth, not unit-tested here."""

from __future__ import annotations

import json

from dcp import llm, triage
from dcp.llm import FakeBackend


def _resp(verdict, deep_read="maybe"):
    return json.dumps({
        "verdict": verdict, "worth_deep_read": deep_read,
        "signals": ["substation"], "why": "test", "confidence": "probable",
    })


def test_rubric_registry_has_both():
    assert set(triage.RUBRICS) == {"v1", "dc_build"}
    prompt, verdicts = triage.RUBRICS["dc_build"]
    assert "new_build" in verdicts and "adjacent_power" in verdicts
    assert "disguise" in prompt.lower()  # the B8-suspect rule is present


def test_parse_response_accepts_dc_build_classes():
    v = triage.parse_response(_resp("adjacent_power"), triage.DC_BUILD_VERDICTS)
    assert v.verdict == "adjacent_power"


def test_parse_response_normalises_spacing_and_case():
    v = triage.parse_response(_resp("New Build"), triage.DC_BUILD_VERDICTS)
    assert v.verdict == "new_build"


def test_parse_response_dc_build_skips_v1_coercion():
    # Under v1 coercion, anything containing "data" collapses to "DC" —
    # that must not happen for the dc_build taxonomy.
    v = triage.parse_response(_resp("data hall thing"), triage.DC_BUILD_VERDICTS)
    assert v.verdict == "data hall thing"  # left as-is for the caller to flag


def test_parse_response_default_still_v1():
    v = triage.parse_response(_resp("Data Centre"))
    assert v.verdict == "DC"


def test_triage_application_uses_selected_rubric():
    backend = FakeBackend(responses={"Application": _resp("pre_application")})
    out = triage.triage_application(
        {"ref": "X/1", "council": "X", "description": "scoping request"},
        backend, rubric="dc_build",
    )
    assert out.verdict == "pre_application"
    # The dc_build system prompt was the one sent
    _prompt, system = backend.calls[0]
    assert "PROJECT CLASS" in system


def test_make_backend_dispatch():
    b = llm.make_backend("granite4.1:30b")
    assert isinstance(b, llm.OllamaBackend)
    b2 = llm.make_backend("claude-sonnet-5")
    assert isinstance(b2, llm.ClaudeBackend)
    assert b2.model == "claude-sonnet-5"
