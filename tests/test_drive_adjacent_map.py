"""The adjacent-power folder map reads the ledger the way the site maps do.

`adjacent_power/` sits beside `sites/` on Drive (issue #252; the 2.11
staging build). The reader links each entry's own folder from the
"Adjacent power" box, so the map has to key on the folder-name form of
the application reference — `clean_ref`, the same function the staging
build's naming goes through — and has to say nothing for a folder the
sync has not created yet, rather than building a URL that may 404.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def hv():
    spec = importlib.util.spec_from_file_location(
        "export_handover_under_test", ROOT / "scripts" / "export_handover.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ledger(tmp_path: Path, folders: dict) -> Path:
    path = tmp_path / ".drive_sync_state.json"
    path.write_text(json.dumps({"folders": folders, "files": {}}))
    return path


def test_maps_each_adjacent_folder_by_its_cleaned_ref(hv, tmp_path, monkeypatch):
    root = "ROOT"
    monkeypatch.setattr(hv, "DRIVE_LEDGER", _ledger(tmp_path, {
        f"{root}/sites": "SITES",
        f"{root}/adjacent_power": "ADJ",
        f"{root}/operator_snapshots": "SNAP",
        # a site and one of its applications — must NOT appear in the map
        "SITES/PTNO-1 — Somewhere": "S1",
        "S1/Council_25_0001": "S1A",
        # two adjacent-power applications
        f"ADJ/{hv.clean_ref('Medway/MC/21/0979')}": "ADJ1",
        f"ADJ/{hv.clean_ref('Plymouth/20/01477/MOR')}": "ADJ2",
    }))
    out = hv._drive_adjacent_map()
    assert out == {
        hv.clean_ref("Medway/MC/21/0979"): hv._drive.folder_url("ADJ1"),
        hv.clean_ref("Plymouth/20/01477/MOR"): hv._drive.folder_url("ADJ2"),
    }
    # the key is what the reader looks up with
    assert hv.clean_ref("Medway/MC/21/0979") in out
    assert "Medway/MC/21/0979" not in out


def test_no_adjacent_root_means_an_empty_map_not_a_guess(hv, tmp_path, monkeypatch):
    monkeypatch.setattr(hv, "DRIVE_LEDGER", _ledger(tmp_path, {
        "ROOT/sites": "SITES", "SITES/PTNO-1 — Somewhere": "S1"}))
    assert hv._drive_adjacent_map() == {}


def test_a_missing_or_broken_ledger_is_an_empty_map(hv, tmp_path, monkeypatch):
    monkeypatch.setattr(hv, "DRIVE_LEDGER", tmp_path / "absent.json")
    assert hv._drive_adjacent_map() == {}
    broken = tmp_path / "broken.json"; broken.write_text("{not json")
    monkeypatch.setattr(hv, "DRIVE_LEDGER", broken)
    assert hv._drive_adjacent_map() == {}
