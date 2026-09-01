"""Chunking must not send a unit larger than the model can answer."""
from __future__ import annotations
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "deepread_run",
    Path(__file__).resolve().parent.parent / "scripts" / "deepread_run.py")
dr = importlib.util.module_from_spec(_spec)
import sys; sys.modules["deepread_run"] = dr
_spec.loader.exec_module(dr)


class TestOversizedUnits:
    def test_a_pdf_page_still_chunks_exactly_as_before(self):
        pages = ["a" * 3000, "b" * 3000, "c" * 3000]
        got = dr.chunk_pages(pages, [0, 1, 2], 16000)
        assert len(got) == 1
        assert got[0][0] == [1, 2, 3]

    def test_pages_still_group_up_to_the_limit(self):
        pages = ["a" * 3000] * 10
        got = dr.chunk_pages(pages, list(range(10)), 10000)
        assert len(got) > 1
        assert all(len(text) <= 10000 for _n, text in got)

    def test_one_enormous_sheet_is_split_rather_than_sent_whole(self):
        """The bug: 551,003 characters in a single chunk."""
        pages = ["row\n" * 200_000]          # 800,000 chars, one unit
        got = dr.chunk_pages(pages, [0], 16000)
        assert len(got) > 1, "an oversized unit went through whole"
        assert all(len(text) <= 16000 for _n, text in got)

    def test_every_piece_keeps_the_marker_so_provenance_survives(self):
        pages = ["row\n" * 200_000]
        got = dr.chunk_pages(pages, [0], 16000)
        for nums, text in got:
            assert nums == [1]
            assert text.startswith("[PAGE 1]\n")

    def test_splitting_happens_on_line_boundaries(self):
        """A quote cut mid-line is a quote the verbatim gate rejects."""
        pages = ["".join(f"line{i}\n" for i in range(5000))]
        got = dr.chunk_pages(pages, [0], 2000)
        for _n, text in got:
            body = text.split("\n", 1)[1]
            for line in body.splitlines():
                assert line == "" or line.startswith("line"), line

    def test_a_single_line_longer_than_the_limit_is_not_truncated(self):
        """Corrupting evidence is worse than one oversized request."""
        pages = ["x" * 50_000]
        got = dr.chunk_pages(pages, [0], 16000)
        assert "".join(t.replace("[PAGE 1]\n", "") for _n, t in got).strip() == "x" * 50_000

    def test_no_text_is_lost_or_duplicated(self):
        pages = ["".join(f"r{i}\n" for i in range(9000))]
        got = dr.chunk_pages(pages, [0], 5000)
        rebuilt = "".join(t[len("[PAGE 1]\n"):] for _n, t in got)
        assert rebuilt == pages[0] + "\n"


class TestParseFailedIsNotAReading:
    """A truncated answer is an absence of processing, not a verdict.

    `not_extracted` meant two opposite things once — nobody extracted it,
    and it contains no words — and the cohort excluded both, so the first
    kind was never revisited. `parse_failed` went the same way in a
    different costume: the model's JSON came back truncated, the row said
    so, and the document was never offered to that model again.
    """

    def test_the_cohort_exists_and_is_narrow(self):
        import pathlib
        src = pathlib.Path("scripts/deepread_escalate_openai.py").read_text()
        assert '"parse_failed"' in src
        # Only documents the failure cost us entirely: no findings banked,
        # and never successfully read by anyone. 442 of 456 parse-failed
        # documents kept their findings and must not be re-read.
        block = src[src.index('if which == "parse_failed":'):]
        block = block[:block.index('elif which == "power":')]
        assert "read_state = 'parse_failed'" in block
        assert "read_state = 'read'" in block
        assert "FROM findings f" in block

    def test_it_is_gated_like_the_bulk_cohort(self):
        """Every cohort that spends money waits for a validated model.

        Asserted as a rule over the cohort list rather than as the
        literal guard line: this test used to pin the exact string
        `cohort in ("remaining", "parse_failed")`, and it failed the day
        `first_read` was added to that same guard — a correct change,
        reported as a regression. A new spending cohort must now either
        appear in the guard or be named here as deliberately free.
        """
        import pathlib
        import re
        src = pathlib.Path("scripts/deepread_escalate_openai.py").read_text()
        flat = re.sub(r"\s+", " ", src)

        # `validation` is the cohort that establishes a model IS valid, so
        # gating it on a validated model would deadlock. `power` reuses
        # already-paid-for extractions rather than reading documents.
        FREE = {"validation", "power"}

        choices = re.search(r'"--cohort",\s*choices=\[([^\]]+)\]', src)
        assert choices, "cannot find the --cohort choices list"
        cohorts = set(re.findall(r'"([a-z_]+)"', choices.group(1)))
        assert cohorts, "no cohorts parsed"

        guard = re.search(r"if cohort in \(([^)]*)\) and not dry_run", flat)
        assert guard, "the validation guard is gone, not merely changed"
        gated = set(re.findall(r'"([a-z_]+)"', guard.group(1)))

        ungated = cohorts - gated - FREE
        assert not ungated, (
            f"cohorts {sorted(ungated)} spend money but do not wait for a "
            f"validated model. Add them to the guard, or to FREE here with "
            f"the reason they cost nothing.")
