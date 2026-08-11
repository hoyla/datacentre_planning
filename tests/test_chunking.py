"""Chunking must not send a unit larger than the model can answer."""
from __future__ import annotations
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "deepread_run", Path("scripts/deepread_run.py"))
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
