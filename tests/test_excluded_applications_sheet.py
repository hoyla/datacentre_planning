"""The workbook names what it leaves out, and the dictionary explains every column.

A dash meaning four things was the reader's worst failure; an exclusion
"by decision" with no list is the same shape. The Excluded applications
sheet lists every application whose documents this project holds and
shows nowhere else — triaged not_dc, in no live site, not adjacent power
or its paperwork — with why we hold it. These tests pin that the sheet's
columns and the dictionary agree, and that the sheet reads the adjacent
class from the same rule as the staging build rather than re-deriving it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "export_handover_under_test", ROOT / "scripts" / "export_handover.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_excluded_column_has_a_dictionary_entry():
    hv = _load()
    documented = set()
    for sheet, cols, _desc in hv.DICTIONARY:
        if sheet == "Excluded applications":
            documented |= {c.strip() for c in cols.split(";")}
    missing = [h for h in hv.EXCLUDED_HEADERS if h not in documented]
    assert not missing, f"columns with no dictionary entry: {missing}"
    stray = sorted(documented - set(hv.EXCLUDED_HEADERS))
    assert not stray, f"dictionary names columns the sheet does not have: {stray}"


def test_the_sheet_reads_the_adjacent_class_from_the_shared_rule():
    src = (ROOT / "scripts" / "export_handover.py").read_text()
    block = src[src.index("# ---- Excluded applications"):src.index("# ---- Provenance")]
    assert "_adj.staged_applications(" in block, \
        "the sheet must exclude adjacent power by the rule the staging build uses"
    assert "l.verdict = 'adjacent_power'" not in block, \
        "and must not re-derive that class from the verdict"
    assert "s.retired_at IS NULL" in block and "m.retired_at IS NULL" in block, \
        "a membership row on a retired site is not a membership"


def test_the_dictionary_says_what_the_exclusion_is():
    hv = _load()
    text = " ".join(d for s, _c, d in hv.DICTIONARY if s == "Excluded applications")
    for phrase in ("not_dc", "no live site", "adjacent", "decision", "re-triage"):
        assert phrase in text, phrase
