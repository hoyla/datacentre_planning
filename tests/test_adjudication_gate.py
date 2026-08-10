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


class TestPromptsRender:
    """A prompt that cannot render is a batch that cannot run.

    scripts/adjudicate_power.py builds its prompt with %-formatting, so a
    literal percent sign anywhere in the text — "80% - 480W", which is one
    of the examples the prompt itself cites — raises ValueError at build
    time. That failed only when a submission was attempted, after the
    cohort had been queried and the JSONL half-built. Cheap to assert.
    """

    def _prompt_module(self):
        spec = importlib.util.spec_from_file_location(
            "adjudicate_power", ROOT / "scripts" / "adjudicate_power.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_adjudication_prompt_renders(self):
        ap = self._prompt_module()
        out = ap.PROMPT % {"ref": "Council/1/23", "desc": "d",
                           "figures": "- finding_id 1: 5 MW"}
        assert "Council/1/23" in out and "5 MW" in out

    def test_literal_percent_survives_as_one_sign(self):
        """%% in the source must reach the model as %, or the example the
        prompt gives is not the example the model sees."""
        ap = self._prompt_module()
        out = ap.PROMPT % {"ref": "r", "desc": "d", "figures": "f"}
        assert "80% - 480W" in out
        assert "80%% - 480W" not in out


class TestNoExportBypassesAdjudication:
    """No artefact may derive a site's capacity straight from `findings`.

    Power adjudication decides whose figure each number is, and a
    consumer that reads `findings.value_number` instead is asserting
    that every MW in a site's documents belongs to that site. Planning
    statements argue for approval by quoting the market, so it does not.

    This shipped. `export_handover.py` was fixed for it; the identical
    expression in `export_duckdb.py`'s `site_overview` view was not,
    because the fix was scoped to the file that had been named rather
    than to the pattern. The phase 1 release therefore reported West
    London Technology Park at 298,000 MW — about ten times the UK grid,
    from a European demand scenario the adjudicator had already marked
    `market_context` — while the workbook and reader said 155 MW.

    Retracting a claim means sweeping everywhere it was asserted.
    """

    EXPORTS = ("scripts/export_duckdb.py", "scripts/export_handover.py",
               "scripts/export_reader.py", "scripts/build_drive_staging.py")

    def test_no_max_over_unadjudicated_mw_findings(self):
        import pathlib
        import re
        # max(...value_number...) anywhere near a MW unit filter, which is
        # the shape of the bug in every form it has taken so far.
        pattern = re.compile(
            r"max\s*\(\s*[a-z]*\.?value_number[^)]*\)[^;]{0,160}?"
            r"value_unit[^;]{0,40}?MW", re.I | re.S)
        for name in self.EXPORTS:
            src = pathlib.Path(name).read_text()
            hit = pattern.search(src)
            assert hit is None, (
                f"{name} derives a capacity from findings.value_number "
                f"filtered on a MW unit, bypassing power_adjudication:\n"
                f"  {hit.group()[:180]}")

    def test_duckdb_site_overview_reads_the_adjudication(self):
        import pathlib
        src = pathlib.Path("scripts/export_duckdb.py").read_text()
        view = src[src.index('"site_overview"'):src.index('"latest_verdict"')]
        assert "power_adjudication" in view, (
            "site_overview no longer joins power_adjudication; its capacity "
            "columns would be unadjudicated")
        assert "site_capacity" in view, (
            "site_overview does not filter to verdict='site_capacity'")
