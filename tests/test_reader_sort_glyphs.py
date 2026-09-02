"""The sort indicator on every sortable table, and the Sites table's centred columns.

Source-level, so it runs without a database or a browser: the markup and
the CSS the reader ships are what this pins, per the conformance record's
two entries of 2026-09-02.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "scripts" / "export_reader.py").read_text()
TABLES = {"tbl-sites": 6, "tbl-apps": 9, "tbl-energy": 9}


def _head(table_id: str) -> str:
    start = SRC.index(f'<table id="{table_id}"><thead><tr>')
    return SRC[start:SRC.index("</tr></thead>", start)]


def test_every_heading_of_every_sortable_table_carries_aria_sort_and_the_chevron_pair():
    wired = re.search(r"wire\('#tbl-sites'\); wire\('#tbl-apps'\); wire\('#tbl-energy'\);", SRC)
    assert wired, "the three sortable tables are the ones wire() binds"
    for table_id, n in TABLES.items():
        head = _head(table_id)
        ths = re.findall(r"<th(?:\s[^>]*)?>", head)      # not <thead>
        assert len(ths) == n, (table_id, len(ths))
        assert all('aria-sort="none"' in t for t in ths), table_id
        assert head.count("{SORTGLYPH}") == n, table_id
    assert 'class="up"' in SRC and 'class="dn"' in SRC
    assert "M 0.9 7.549 L 7.015 2.542" in SRC          # ChevronUpSingleSmall's path
    assert "M 13.1 0 L 6.985 5.007" in SRC             # ChevronDownSingleSmall's path


def test_the_three_states_are_the_design_systems_and_the_handler_keeps_them():
    assert "opacity:.32" in SRC
    assert 'th[aria-sort="ascending"],th[aria-sort="descending"]{color:var(--brand)}' in SRC
    assert 'th[aria-sort="ascending"] .sortglyph .dn' in SRC
    assert "th.setAttribute('aria-sort', dir===1?'ascending':'descending')" in SRC
    assert "o.setAttribute('aria-sort','none')" in SRC
    # the old page-wide up-down arrow hint is gone, not scoped
    assert 'content:"\\\\00a0↕"' not in SRC


def test_the_sites_tables_four_columns_are_centred_and_the_site_cell_is_not():
    rule = re.search(r"#tbl-sites th:nth-child\(2\),#tbl-sites td:nth-child\(2\),\s*"
                     r"#tbl-sites th:nth-child\(3\),#tbl-sites td:nth-child\(3\),\s*"
                     r"#tbl-sites th:nth-child\(4\),#tbl-sites td:nth-child\(4\),\s*"
                     r"#tbl-sites th:nth-child\(5\),#tbl-sites td:nth-child\(5\)\{text-align:center\}", SRC)
    assert rule, "the centre rule for columns 2-5 is missing"
    assert "td:nth-child(1){text-align:center" not in SRC
    assert "td:nth-child(6){text-align:center" not in SRC
    # the other two tables keep their alignment: widths yes, centring no
    assert re.search(r"#tbl-(?:apps|energy)[^{}]*\{[^}]*text-align:center", SRC) is None


def test_the_dictionary_marker_is_a_circle_by_construction():
    """Equal fixed width and height, the glyph centred: an inline marker
    took its height from the heading's line box and drew as an oval."""
    rule = re.search(r"a\.dlink\{([^}]*)\}", SRC).group(1)
    w = re.search(r"(?<![a-z-])width:(\d+)px", rule).group(1)
    h = re.search(r"(?<![a-z-])height:(\d+)px", rule).group(1)
    assert w == h, (w, h)
    assert "display:inline-block" in rule and "text-align:center" in rule and "border-radius:50%" in rule
