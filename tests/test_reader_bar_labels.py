"""The filter bar's menus as Luke relabelled them on 2026-09-03, and the
chip row's help paragraph folded into a "?".

A native select is as wide, closed, as its widest option, so the three
menus were 343, 279 and 201 px for labels of 47, 95 and 63 px. Shorter
options were his answer, one label per line, applied verbatim; the
class and origin labels are single-sourced in dcp, so the rename shows
wherever an origin or a class is named, not only in the menu.
"""

from __future__ import annotations

import re
from pathlib import Path

from dcp import origin, site_class as sclass

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "scripts" / "export_reader.py").read_text()


def _options(select_id: str) -> list[str]:
    m = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % select_id, SRC, re.S)
    assert m, select_id
    return re.findall(r"<option[^>]*>([^<]*)</option>", m.group(1))


def test_the_site_filter_menu_carries_lukes_labels():
    assert _options("f") == [
        "All sites", "Sites with power figure", "Fully read sites",
        "Incompletely acquired/read sites", "Sites whose figures may rise",
        "Sites near national energy projects"]


def test_the_class_menu_no_longer_says_only():
    assert [sclass.CLASS_FILTER_LABELS[k] for k in sclass.CLASS_ORDER] == [
        "Datacentres", "Disguise suspects", "Adjacent power", "Procedural only",
        "No planning record"]
    assert _options("sc")[0] == "Any kind of site"


def test_the_origin_labels_are_the_short_ones_everywhere_an_origin_is_named():
    assert origin.routes_for(["energy_national:PTNO-1"]) == ["Nearby energy search"]
    assert origin.routes_for(["operator:x"]) == ["Operator watchlist"]
    assert "watch-list" not in SRC.split("<script")[0], "the methodology still hyphenates it"


def test_the_chip_help_is_a_question_mark_not_a_paragraph():
    chips = SRC[SRC.index('<div class="chips" id="cohortchips"'):SRC.index('<section id="view-start"')]
    assert '<span class="help">' not in chips, "the two-line paragraph is back under the chips"
    assert 'class="tip"' in chips and "Each chip is a named rule" in chips
    assert "down-the-side .chips .tip .tiptext{left:-8px;right:auto" in SRC, (
        "on the map the box must open rightwards from the left edge")
