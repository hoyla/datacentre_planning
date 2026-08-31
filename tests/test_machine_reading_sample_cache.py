"""The sample cache may not hand one model's answer to another.

`--sample` writes each raw answer to disk so a gate bug never costs a
second call. That cache is keyed, and what the key omits is what goes
wrong: `_sample_one` stores the reading under the model it was *asked*
for, so a hit across models would put a real reading under a false
author — the one failure this store exists to prevent (principle 7).

Found 2026-08-31, comparing gpt-5 against gpt-5.6-terra on one prompt.
Six sites already held terra answers at reading-1.4; the gpt-5 run over
the same prompt would have re-used every one and recorded gpt-5 as
their author, and the comparison would have shown the two models
agreeing perfectly on exactly those six.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "machine_reading_openai", ROOT / "scripts" / "machine_reading_openai.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["machine_reading_openai"] = mod
    spec.loader.exec_module(mod)
    return mod


MRO = _load()
PV = MRO.mr.PROMPT_VERSION


def _cached(**over):
    d = {"input_hash": "abc123", "prompt_version": PV,
         "model": "gpt-5", "reading": {"sections": {}}}
    d.update(over)
    return d


def test_same_input_prompt_and_model_is_reusable():
    assert MRO.cache_is_reusable(_cached(), "abc123", "gpt-5")


def test_a_different_model_is_not_reusable():
    """The 2026-08-31 case: same input, same prompt, different author."""
    assert not MRO.cache_is_reusable(
        _cached(model="gpt-5.6-terra"), "abc123", "gpt-5")
    assert not MRO.cache_is_reusable(
        _cached(model="gpt-5"), "abc123", "gpt-5.6-terra")


def test_a_different_prompt_is_not_reusable():
    assert not MRO.cache_is_reusable(
        _cached(prompt_version="reading-1.2"), "abc123", "gpt-5")


def test_a_different_input_is_not_reusable():
    assert not MRO.cache_is_reusable(_cached(), "different", "gpt-5")


def test_a_cache_with_no_model_recorded_is_not_reusable():
    """Files written before the model was recorded cannot prove their
    author, so they are re-read rather than trusted."""
    c = _cached()
    del c["model"]
    assert not MRO.cache_is_reusable(c, "abc123", "gpt-5")


def test_an_empty_cache_is_not_reusable():
    assert not MRO.cache_is_reusable({}, "abc123", "gpt-5")
    assert not MRO.cache_is_reusable(None, "abc123", "gpt-5")
