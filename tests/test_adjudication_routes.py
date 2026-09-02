"""Power adjudication is split by consequence, and both routes read one rule.

No database: the split itself is a pure function, and the guard's
behaviour is what the tests pin — the long tail must never quietly
absorb a figure that can set a site's headline number.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from dcp.adjudication_routes import PROMPT_VERSION, split_by_consequence

ROOT = Path(__file__).resolve().parent.parent


def _apps():
    return [
        {"ref": "Havering/P0384.15", "figures": [{"finding_id": 1}, {"finding_id": 2}]},
        {"ref": "Slough/T/138", "figures": [{"finding_id": 3}]},
        {"ref": "Hackney/2020/1287", "figures": [{"finding_id": 4}, {"finding_id": 5}]},
    ]


def test_an_application_with_any_consequential_figure_is_held_whole():
    tail, held = split_by_consequence(_apps(), {2, 5})
    assert [a["ref"] for a in held] == ["Havering/P0384.15", "Hackney/2020/1287"]
    assert [a["ref"] for a in tail] == ["Slough/T/138"]
    # nothing lost, nothing duplicated
    assert sorted(f["finding_id"] for a in tail + held for f in a["figures"]) == [1, 2, 3, 4, 5]


def test_nothing_consequential_means_nothing_held():
    tail, held = split_by_consequence(_apps(), set())
    assert held == [] and len(tail) == 3


def test_both_routes_share_the_rule_and_the_rubric_version():
    for name in ("adjudicate_openai", "adjudicate_subagent"):
        src = (ROOT / "scripts" / f"{name}.py").read_text()
        assert "from dcp.adjudication_routes import" in src, name
        assert "WITH capped AS" not in src, f"{name} carries its own copy of the rule"
    spec = importlib.util.spec_from_file_location(
        "adjudicate_subagent", ROOT / "scripts" / "adjudicate_subagent.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.PROMPT_VERSION == PROMPT_VERSION == "power-1.0"


def test_the_long_tail_holds_the_consequential_set_unless_told_otherwise():
    src = (ROOT / "scripts" / "adjudicate_openai.py").read_text()
    assert "--include-consequential" in src
    assert "split_by_consequence(apps, consequential)" in src
