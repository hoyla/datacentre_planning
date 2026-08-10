"""The gate must agree with the correction it guards.

dcp/adjudication_gate.py carries its own copy of the six correction
predicates, deliberately: an export must be able to import it without
dragging in a script's argparse machinery. Two copies of one rule drift —
that is the whole reason migration 017 demoted 261 rows instead of 116 —
so these tests assert the copies stay in step, structurally and by name.

They are unit tests: no database, no network. What they cannot check is
whether a predicate is *right*; that is what the reports and a person are
for. What they can check is that nobody adds a rule to one file and
forgets the other, which is the failure that would let a build proceed
over exactly the errors the gate exists to stop.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from dcp import adjudication_gate

ROOT = Path(__file__).resolve().parent.parent


def _load_corrector():
    spec = importlib.util.spec_from_file_location(
        "correct_adjudications", ROOT / "scripts" / "correct_adjudications.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGateMatchesCorrector:
    def test_every_rule_is_named_in_the_gate(self):
        """A rule the corrector applies but the gate cannot see is a rule
        a build can sail past."""
        corrector = _load_corrector()
        names = {name for name, _set, _pred, _note in corrector.RULES}
        missing = [n for n in names
                   if f"[{n}]" not in adjudication_gate.UNCORRECTED_SQL]
        assert not missing, (
            f"rules in correct_adjudications.py with no clause in "
            f"adjudication_gate.UNCORRECTED_SQL: {missing}")

    def test_gate_names_no_rule_the_corrector_lacks(self):
        """The reverse: a gate clause with no corrector rule blocks every
        build forever with no way to clear it."""
        corrector = _load_corrector()
        names = {name for name, _set, _pred, _note in corrector.RULES}
        gate_names = set(re.findall(r"\[([a-z_]+)\]",
                                    adjudication_gate.UNCORRECTED_SQL))
        orphans = gate_names - names
        assert not orphans, (
            f"gate blocks on rules the corrector cannot fix: {orphans}")

    def test_gate_uses_postgres_word_boundaries(self):
        r"""\b is a backspace in PostgreSQL; \y is the word boundary.

        Written with \b these predicates match nothing, the gate passes
        everything, and the build proceeds over uncorrected rows — the
        silent-success direction, which is worse than a false alarm.
        """
        sql = adjudication_gate.UNCORRECTED_SQL
        assert "\\b" not in sql, (
            r"adjudication_gate uses \b, which PostgreSQL reads as a "
            r"backspace; use \y for a word boundary")

    def test_corrector_uses_postgres_word_boundaries(self):
        corrector = _load_corrector()
        for name, _set, pred, _note in corrector.RULES:
            assert "\\b" not in pred, (
                rf"rule {name} uses \b, which PostgreSQL reads as a "
                rf"backspace; use \y")

    def test_no_literal_space_before_a_number_in_predicates(self):
        r"""PDF text reads "Substation       25.4m²".

        A predicate written with one literal space between a word and a
        number misses every row lifted out of a PDF, which is most of
        them. \s+ or nothing.
        """
        corrector = _load_corrector()
        bad = [name for name, _s, pred, _n in corrector.RULES
               if re.search(r"[a-z] \[0-9", pred)]
        assert not bad, (
            f"rules matching a single literal space before a digit "
            f"(PDF text has runs of whitespace): {bad}")


class TestGateBehaviour:
    def test_override_flag_is_awkward_on_purpose(self):
        """The escape hatch should be hard to type by accident and easy
        to spot in a shell history."""
        flag = "--i-know-the-adjudications-are-uncorrected"
        src = (ROOT / "dcp" / "adjudication_gate.py").read_text()
        assert flag in src
        assert len(flag) > 30

    def test_message_tells_the_operator_what_to_run(self):
        """A refusal that does not say how to clear it trains people to
        reach for the override."""
        msg = adjudication_gate.MESSAGE
        assert "correct_adjudications.py" in msg
        assert "--dry-run" in msg
        assert "consumption_integrity.py" in msg
