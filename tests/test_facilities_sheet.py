"""The workbook lists the facility roster, and the dictionary explains it.

The Facilities sheet is the list Luke asked for on 2026-09-02: every
facility a source names on a campus, where we currently believe it is,
and the figure it carries — read through the roster's loader so the
sheet cannot say what the file does not, with figures joined from the
claims store rather than copied.
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


def test_every_facility_column_has_a_dictionary_entry():
    hv = _load()
    documented = set()
    for sheet, cols, _ in hv.DICTIONARY:
        if sheet == "Facilities":
            documented |= {c.strip() for c in cols.split(";")}
    missing = [h for h in hv.FACILITY_HEADERS if h not in documented]
    assert not missing, f"columns with no dictionary entry: {missing}"
    stray = sorted(documented - set(hv.FACILITY_HEADERS))
    assert not stray, f"dictionary names columns the sheet lacks: {stray}"


def test_the_sheet_reads_the_roster_through_its_loader_and_copies_no_figure():
    src = (ROOT / "scripts" / "export_handover.py").read_text()
    block = src[src.index("# ---- Facilities"):src.index("# ---- Excluded applications")]
    assert "_sfac.load_facilities()" in block and "_sfac.facility_rows(" in block
    assert "FROM capacity_claims" in block, "figures come from the claims store by name"
    assert "yaml" not in block.lower(), "the sheet must not parse the roster file itself"


def test_the_dictionary_says_what_an_empty_location_means():
    hv = _load()
    text = " ".join(d for s, _c, d in hv.DICTIONARY if s == "Facilities")
    assert "not yet found" in text and "source" in text
