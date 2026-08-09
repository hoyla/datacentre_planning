"""Tests for the in-place Google Sheet refresh.

The point of writing values in place is to preserve formatting somebody
did by hand. So the failure that matters is not an exception — it is a
successful run that leaves the column widths describing the wrong data,
or that evaluates a council's description as a formula.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "sheet_sync", Path(__file__).parent.parent / "scripts" / "sheet_sync.py")
sheet_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet_sync)


def apply(have, edits):
    """Replay the edits the way the Sheets API would, to check the result."""
    cur = list(have)
    for e in edits:
        if "delete" in e:
            cur.pop(e["delete"])
        else:
            cur.insert(e["insert"], e["name"])
    return cur


class TestReconcileColumns:
    def test_unchanged_headers_need_no_edits(self):
        cols = ["Site key", "Site name", "Councils"]
        assert sheet_sync.reconcile_columns(cols, cols) == []

    def test_inserting_columns_mid_sheet(self):
        """The real case: Proposal and its flag arrived at D and E.

        They must be *inserted*, so the widths set on everything to their
        right travel with the columns instead of staying put while the
        data slides underneath them.
        """
        have = ["Site key", "Classification", "Site name", "Latitude"]
        want = ["Site key", "Classification", "Site name", "Proposal",
                "Proposal describes a development?", "Latitude"]
        edits = sheet_sync.reconcile_columns(have, want)
        assert all("insert" in e for e in edits)
        assert apply(have, edits) == want

    def test_removing_a_column(self):
        have = ["Site key", "Obsolete", "Site name"]
        want = ["Site key", "Site name"]
        edits = sheet_sync.reconcile_columns(have, want)
        assert apply(have, edits) == want

    def test_insert_and_delete_together(self):
        have = ["A", "gone", "B", "C"]
        want = ["A", "B", "new", "C"]
        assert apply(have, sheet_sync.reconcile_columns(have, want)) == want

    def test_deletions_run_right_to_left(self):
        """Deleting left-first invalidates every index after it."""
        have = ["A", "x", "B", "y", "C"]
        edits = sheet_sync.reconcile_columns(have, ["A", "B", "C"])
        deletes = [e["delete"] for e in edits if "delete" in e]
        assert deletes == sorted(deletes, reverse=True)
        assert apply(have, edits) == ["A", "B", "C"]

    def test_a_reordering_is_not_treated_as_delete_plus_insert(self):
        """Moving a column would discard the formatting of the one moved.

        Reordering is left for a human rather than silently rebuilt, so
        the edits must not delete a column that still exists in the
        target.
        """
        have = ["A", "B", "C"]
        want = ["A", "C", "B"]
        edits = sheet_sync.reconcile_columns(have, want)
        assert not any(e.get("delete") is not None for e in edits), edits

    def test_an_empty_sheet_header_asks_for_nothing(self):
        assert sheet_sync.reconcile_columns([], ["A", "B"]) == []


class TestCellCoercion:
    def test_deliberate_hyperlinks_stay_live(self):
        v = sheet_sync.cell('=HYPERLINK("https://example.org", "Open")')
        assert v.startswith("=HYPERLINK")

    @pytest.mark.parametrize("text", [
        "+/- 40 dwellings",
        "-5m below ground level",
        "=not a formula, a description",
        "@the corner of Bath Road",
    ])
    def test_text_that_looks_like_a_formula_is_not_evaluated(self, text):
        """Planning descriptions start with all sorts of punctuation."""
        assert sheet_sync.cell(text).startswith("'")

    def test_ordinary_values_pass_through(self):
        assert sheet_sync.cell("Erection of a data centre") == \
            "Erection of a data centre"
        assert sheet_sync.cell(77.0) == 77.0
        assert sheet_sync.cell(None) == ""


class TestSpreadsheetId:
    def test_reads_the_id_from_a_pasted_url(self):
        assert sheet_sync.spreadsheet_id(
            "https://docs.google.com/spreadsheets/d/174dkicvGxfjWgbD7Sw/"
            "edit?gid=1246662960#gid=1246662960") == "174dkicvGxfjWgbD7Sw"

    def test_refuses_a_url_it_cannot_parse(self):
        with pytest.raises(SystemExit):
            sheet_sync.spreadsheet_id("https://example.org/not-a-sheet")
