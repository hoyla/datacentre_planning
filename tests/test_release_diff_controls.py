"""The release diff compares a filter control's identity, not its count.

"Only datacentres (428)" became "Only datacentres (427)" when a site
retired into another in 2.12, and the diff reported the control REMOVED
and then added. A guard that cries wolf gets read past, so the count is
stripped before comparison and the test pins that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rd():
    spec = importlib.util.spec_from_file_location("release_diff", ROOT / "scripts" / "release_diff.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["release_diff"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_a_trailing_count_is_not_part_of_a_controls_identity():
    rd = _rd()
    assert rd.control_label("Only datacentres (428)") == rd.control_label("Only datacentres (427)") == "Only datacentres"
    assert rd.control_label("At least 100 MW (1,204)") == "At least 100 MW"
    assert rd.control_label("All 456 sites") == "All 456 sites"      # a count inside the label is the label
    assert rd.control_label("  Exclude unknown MW consumption ") == "Exclude unknown MW consumption"
    assert rd.control_label("Signals &amp; cohorts") == "Signals & cohorts"


def test_reader_shape_uses_the_stripped_label(tmp_path):
    rd = _rd()
    page = ('<div id="filterbar"><div class="controls"><select><option value="">All 500 sites</option>'
            '<option value="dc">Only datacentres (427)</option></select>'
            '<label><input type="checkbox" checked> Show energy projects (197)</label></div>\n</div>'
            '<div id="filterbar-home" hidden></div>')
    f = tmp_path / "reader.html"
    f.write_text(page)
    shape = rd.reader_shape(f)
    assert "Only datacentres" in shape.controls
    assert not any("(427)" in c or "(197)" in c for c in shape.controls)


def test_the_bars_text_inputs_are_controls_named_by_id(tmp_path):
    rd = _rd()
    page = ('<div id="filterbar"><div class="controls">'
            '<input type="search" id="q" placeholder="Search…">'
            '<input type="search" id="near" placeholder="Near a postcode">'
            '<select><option value="">All sites</option></select></div>\n</div>'
            '<div id="filterbar-home" hidden></div>')
    f = tmp_path / "reader.html"; f.write_text(page)
    shape = rd.reader_shape(f)
    assert "input#q" in shape.controls and "input#near" in shape.controls
