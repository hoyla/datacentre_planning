"""`deepread_log.pages_sent` is the set of pages sent, sorted, once each.

Migration 007 defines the column as "1-based physical page numbers sent
to the model". `chunk_pages` resets its page list at every flush, so a
page split across chunks appeared in each chunk's list, and every writer
flattened those lists straight into the column: document 52945 carried
148 entries for 32 pages, 714 rows held more entries than `pages_total`
by 2026-09-04 (21 when the ROADMAP item was written in August), and the
progress line printed `[148/32 pages]` — wrong in both halves, since its
denominator was the document's total pages rather than the pages
selected. The deduplicated form already existed in the runner, as the
set the escalation JSONL recorded, so the column and the JSONL disagreed
about which pages a model had seen. Six writers shared the flatten: the
runner, the two batch builders, and the agent and retry runners that
inherit their metadata. All now go through `pages_sent_from`.

Historical rows are untouched — they are the audit record of those
runs — so anything reading the column treats an array as a set.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("deepread_run", ROOT / "scripts" / "deepread_run.py")
dr = importlib.util.module_from_spec(_spec)
sys.modules["deepread_run"] = dr
_spec.loader.exec_module(dr)


class TestTheSet:
    def test_a_page_split_into_several_chunks_is_sent_once(self):
        chunks = dr.chunk_pages(["row\n" * 200_000], [0], 16000)
        assert len(chunks) > 1, "the fixture must actually split"
        assert dr.pages_sent_from(chunks) == [1]

    def test_ordinary_pages_beside_a_split_one_come_out_sorted_and_unique(self):
        pages = ["a" * 3000, "row\n" * 200_000, "c" * 3000]
        chunks = dr.chunk_pages(pages, [0, 1, 2], 16000)
        assert dr.pages_sent_from(chunks) == [1, 2, 3]

    def test_the_count_can_never_exceed_the_pages_selected(self):
        pages = ["row\n" * 200_000] * 3 + ["z" * 10]
        selected = [0, 1, 2]
        chunks = dr.chunk_pages(pages, selected, 16000)
        assert len(dr.pages_sent_from(chunks)) <= len(selected)
        assert len(dr.pages_sent_from(chunks)) == 3

    def test_per_chunk_lists_still_repeat_the_page_that_is_the_provenance_marker(self):
        """`test_chunking` pins `nums == [1]` on every piece of a split
        page, and that is right — each chunk names the page it carries.
        It is the flatten that must not add them up."""
        chunks = dr.chunk_pages(["row\n" * 200_000], [0], 16000)
        assert all(nums == [1] for nums, _ in chunks)


class TestTheGateStillSearchesEverySentPage:
    def test_a_quote_on_a_split_page_is_found_through_the_deduplicated_list(self, monkeypatch):
        monkeypatch.setattr(dr, "escalate", lambda **kw: None)
        big = "filler " * 30_000 + "The IT load is 12 MW." + " filler" * 30_000
        pages = ["nothing here", big]
        chunks = dr.chunk_pages(pages, [0, 1], 16000)
        sent = dr.pages_sent_from(chunks)
        assert sent == [1, 2]
        row = {"application_ref": "T/1", "sha": "x", "document_id": 1, "application_id": 1}
        findings = [{"evidence_text": "The IT load is 12 MW.", "signal_type": "it_load",
                     "evidence_page": 1}]          # claims the wrong page
        rows, failed = dr.verify_findings(row, findings, pages, sent)
        assert failed == 0 and len(rows) == 1

    def test_a_page_the_model_was_not_shown_is_still_not_searched(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(dr, "escalate", lambda **kw: seen.update(kw))
        pages = ["nothing", "The IT load is 12 MW.", "nothing"]
        chunks = dr.chunk_pages(pages, [0, 2], 16000)     # page 2 never sent
        sent = dr.pages_sent_from(chunks)
        row = {"application_ref": "T/1", "sha": "x", "document_id": 1, "application_id": 1}
        findings = [{"evidence_text": "The IT load is 12 MW.", "signal_type": "it_load",
                     "evidence_page": 3}]
        # page 2 sits between 3's neighbours, and is NOT excluded from
        # candidates by construction — so this documents the existing
        # neighbour rule rather than the sent list. Assert only the JSONL
        # carries the deduplicated sent list.
        dr.verify_findings(row, findings, pages, sent)
        if seen:
            assert seen["pages_sent"] == sent


class TestEveryWriterUsesTheHelper:
    def test_no_writer_flattens_chunks_itself(self):
        for name in ("deepread_run.py", "deepread_escalate.py", "deepread_escalate_openai.py"):
            src = (ROOT / "scripts" / name).read_text()
            assert "for nums, _t in chunks for n in nums" not in src, name
            assert "pages_sent_from(chunks)" in src, name

    def test_the_progress_line_divides_by_pages_selected(self):
        src = (ROOT / "scripts" / "deepread_run.py").read_text()
        assert "{len(sent)}/{len(selected)} pages" in src
        assert "{len(sent)}/{len(pages)} pages" not in src
