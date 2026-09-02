"""The inbox resolves the folder layouts people actually use.

No database: `folder_candidate` is the pure half of resolution, and it
is where the two accepted layouts and a stray annotation meet.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _mod(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("folder, ref", [
    ("Havering_P0384.15", "Havering/P0384.15"),
    ("Wychavon_21_00802_NMA", "Wychavon/21/00802/NMA"),
    ("Midlothian:07:00051:FUL", "Midlothian/07/00051/FUL"),
    # the council/ref layout, with the site key written down while downloading
    ("Havering/P0384.15 (PTNO-12106647)", "Havering/P0384.15"),
    ("Midlothian/07:00051:FUL (PTNO-12067176)", "Midlothian/07/00051/FUL"),
    ("Havering/P0384.15", "Havering/P0384.15"),
])
def test_both_layouts_and_an_annotation_reduce_to_the_reference(folder, ref):
    assert _mod("ingest_inbox").folder_candidate(folder) == ref


def test_a_hand_check_can_only_conclude_what_an_adapter_could():
    """`record_portal_check` offers the settled verdicts and `error`,
    never `fetched` or `partial` — a person did not fetch anything."""
    from dcp.acquisition_outcome import SETTLED
    m = _mod("record_portal_check")
    assert set(m.HAND_OUTCOMES) == set(SETTLED) | {"error"}
    assert m.ADAPTER == "browser_probe"


def test_a_page_capture_is_filed_beside_the_bundles_not_as_a_document(tmp_path):
    m = _mod("record_portal_check")
    dest = m.capture_destination("Midlothian/07/00051/FUL", Path("/x/page.pdf"),
                                 bundles=tmp_path)
    assert dest == tmp_path / "Midlothian:07:00051:FUL" / "page.pdf"


def test_an_inbox_ingest_earns_a_fetched_outcome_and_an_empty_one_earns_nothing():
    m = _mod("ingest_inbox")
    assert m.hand_outcome(0, "x") is None
    outcome, detail = m.hand_outcome(14, "Havering/P0384.15 (PTNO-12106647)")
    assert outcome == "fetched" and "14 file(s)" in detail and "by hand" in detail
    assert m.ADAPTER == "manual"
