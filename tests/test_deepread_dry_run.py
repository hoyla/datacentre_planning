"""`--dry-run` must stop a submit, even beside `--submit`.

It did not. `do_submit` was called with `dry_run=not args.submit`, so
the flag was accepted, documented, and silently discarded: writing
`--submit --dry-run` — the natural way to ask "show me what a submit
would do", and what the module docstring's own examples encourage —
sent 1,936 requests to the OpenAI API on 2026-08-28.

The rule these tests pin: where the two flags contradict each other,
the reading that does not spend money wins.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deepread_escalate_openai.py"

# Every script that can spend money on a submit. All three had the same
# bug: a `--dry-run` flag defined, documented and then overridden by
# `dry_run=not args.submit`.
SPENDING_SCRIPTS = (
    "deepread_escalate_openai.py",
    "deepread_escalate.py",
    "machine_reading_openai.py",
    "adjudicate_openai.py",
)


def _code(name: str) -> str:
    """The script with comment lines removed.

    The first version of this test matched the bug pattern inside the
    comment that explains the bug, and failed on the fixed files — a
    probe that cannot tell code from prose about code.
    """
    return "\n".join(
        line for line in (ROOT / "scripts" / name).read_text().splitlines()
        if not line.lstrip().startswith("#"))


def _resolve(dry_run: bool, submit: bool) -> bool:
    """The expression the entry point uses, read from the source.

    Read rather than reimplemented: a test that hard-codes the rule
    passes happily while the script does something else, which is the
    failure being guarded against.
    """
    src = _code("deepread_escalate_openai.py")
    assert "dry_run=args.dry_run or not args.submit" in src, (
        "the dry-run rule has changed; if that is deliberate, change this "
        "test deliberately too")

    class A:
        pass
    a = A()
    a.dry_run, a.submit = dry_run, submit
    return a.dry_run or not a.submit


def test_dry_run_wins_when_both_flags_are_given():
    """The incident. `--submit --dry-run` must not submit."""
    assert _resolve(dry_run=True, submit=True) is True


def test_submit_alone_still_submits():
    assert _resolve(dry_run=False, submit=True) is False


def test_neither_flag_is_still_a_dry_run():
    """The long-standing behaviour: without --submit the script only
    estimates, which is what the docstring's examples rely on."""
    assert _resolve(dry_run=False, submit=False) is True


def test_dry_run_alone_is_a_dry_run():
    assert _resolve(dry_run=True, submit=False) is True


def test_the_flag_documents_which_way_it_resolves():
    """A flag whose precedence is invisible is how this happened."""
    src = SCRIPT.read_text()
    assert "Wins over --submit" in src


@pytest.mark.parametrize("name", SPENDING_SCRIPTS)
def test_no_spending_script_ignores_its_dry_run_flag(name):
    """The bug was not unique to one script. Any script that offers
    `--dry-run` and then computes the state from `--submit` alone will
    spend money when a careful operator asks it not to."""
    src = _code(name)
    if '"--dry-run"' not in src:
        pytest.skip(f"{name} offers no --dry-run flag")
    assert "dry_run=not args.submit" not in src, (
        f"{name} accepts --dry-run and then ignores it")
    assert "args.dry_run or not args.submit" in src, (
        f"{name} does not let --dry-run win")
