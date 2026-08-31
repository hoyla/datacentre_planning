"""The re-gate's two judgements: which read produced a finding, and which
page its quote verifies on.

Both are places where a wrong answer would be invisible. Attributing a
recovered finding to the wrong model puts a false provenance in the
column reporters drill into; searching a page the model was never shown
would admit a quote on evidence the model could not have seen.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "regate_escalations", ROOT / "scripts" / "regate_escalations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regate_escalations"] = mod
    spec.loader.exec_module(mod)
    return mod


RG = _load()


# --- claimed_page comes in more than one shape -------------------------------

def test_claimed_page_accepts_an_integer():
    assert RG._page_of(7) == 7


def test_claimed_page_accepts_the_bracketed_form_the_log_also_holds():
    # Real: some escalations record '[PAGE 4]' rather than 4.
    assert RG._page_of("[PAGE 4]") == 4


def test_claimed_page_is_none_when_absent_rather_than_zero():
    # A zero would be read as a page number by the caller's range check.
    assert RG._page_of(None) is None
    assert RG._page_of("") is None
    assert RG._page_of("front matter") is None


# --- which read produced the finding -----------------------------------------

def _read(model, when=None, app=1):
    return {"model": model, "prompt_version": "1.0", "application_id": app,
            "completed_at": datetime.fromisoformat(when) if when else None}


def test_a_reader_family_with_one_model_resolves_without_a_timestamp():
    cands = [_read("claude-sonnet-5"), _read("mlx:Qwen3.6-35B-A3B-4bit")]
    assert RG.pick_read(cands, "claude-sonnet-5", None)["model"] == "claude-sonnet-5"


def test_an_ambiguous_family_is_decided_by_the_nearest_read():
    """`openai` matches both :minimal and :low, which is the 646-row case.
    The escalation's own timestamp settles it."""
    cands = [_read("openai:gpt-5:minimal", "2026-08-07T10:00:00"),
             _read("openai:gpt-5:low", "2026-08-20T10:00:00")]
    got = RG.pick_read(cands, "openai", "2026-08-20T10:05:00")
    assert got["model"] == "openai:gpt-5:low"
    got = RG.pick_read(cands, "openai", "2026-08-07T09:58:00")
    assert got["model"] == "openai:gpt-5:minimal"


def test_an_unresolvable_reader_returns_none_rather_than_guessing():
    """Nine escalations have no matching log row. A finding whose read
    cannot be identified is dropped, not attributed to whatever is
    nearest."""
    cands = [_read("claude-sonnet-5")]
    assert RG.pick_read(cands, "openai", "2026-08-20T10:00:00") is None
    assert RG.pick_read([], "mlx", None) is None


# --- which page the quote verifies on ----------------------------------------

PAGES = ["nothing here",
         "the total installed generating capacity across the campus is 42MW",
         "an unrelated page",
         "the grid connection is rated at 120MVA for the whole estate"]

QUOTE = "the total installed generating capacity across the campus is 42MW"


def test_the_claimed_page_is_tried_first():
    assert RG.passes(PAGES, QUOTE, 2, None) == 2


def test_a_neighbouring_page_is_tried_when_the_claim_is_off_by_one():
    assert RG.passes(PAGES, QUOTE, 3, None) == 2
    assert RG.passes(PAGES, QUOTE, 1, None) == 2


def test_a_page_the_model_was_never_shown_is_not_searched():
    """The runners only ever search pages_sent. A quote 'found' on a page
    the model did not see is not evidence that the model read it."""
    far = ["x"] * 20 + [QUOTE]
    assert RG.passes(far, QUOTE, 1, [1, 2]) is None
    assert RG.passes(far, QUOTE, 1, [1, 2, 21]) == 21


def test_an_absent_quote_stays_absent():
    assert RG.passes(PAGES, "a capacity of 999MW is proposed", 2, [1, 2, 3, 4]) is None


def test_the_whitespace_fallback_applies_here_too():
    """The whole point of the re-gate: a quote pypdf broke mid-word."""
    broken = ["", "the total installed gener ating capacity across the cam pus is 42MW"]
    assert RG.passes(broken, QUOTE, 2, None) == 2
