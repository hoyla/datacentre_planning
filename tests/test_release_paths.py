"""The release chain finds `data/exports` from the package root.

Every tool in the chain reads that one location to decide what to
build — the newest release folder, the phase it stamps, the Drive sync
ledger, the staging tree, the release diff — and until 2026-09-02
`dcp/release.py` spelled it relative to the working directory. From
anywhere else `release_dirs()` was empty, `latest_release_dir()` was
None, and two consumers turned that into a wrong answer rather than an
error: the reader fell back to `phase1_build` and phase "1" — stamping
its title, header and database filename with a phase several releases
old — and the staging build took the same folder. Neither raised.

Behaviour is tested against an exports tree the test builds itself,
never the real one: `data/exports` is gitignored, so a clean checkout
holds no release folders at all.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from dcp import drive, release

ROOT = Path(__file__).resolve().parent.parent

# Every script the release chain runs, in the runbook's order, plus the
# one that verifies it. None may find the exports directory by a path
# relative to wherever the command happened to be run.
RELEASE_CHAIN = (
    "scripts/materialise_sites.py",
    "scripts/export_handover.py",
    "scripts/export_duckdb.py",
    "scripts/export_reader.py",
    "scripts/build_drive_staging.py",
    "scripts/drive_sync.py",
    "scripts/record_drive_ids.py",
    "scripts/sync_snapshots_drive.py",
    "scripts/sheet_sync.py",
    "scripts/verify_drive_sample.py",
    "scripts/release_diff.py",
)


def _exports(tmp_path, monkeypatch, *names):
    """A throwaway exports tree, written oldest-first so mtimes order it."""
    exports = tmp_path / "exports"
    exports.mkdir()
    made = []
    for i, name in enumerate(names):
        d = exports / name
        d.mkdir()
        stamp = time.time() - (len(names) - i) * 100
        os.utime(d, (stamp, stamp))
        made.append(d)
    monkeypatch.setattr(release, "EXPORTS", exports)
    return exports, made


def test_the_exports_location_is_absolute():
    """The mechanism, not a count of release folders (there may be none)."""
    assert release.EXPORTS.is_absolute()
    assert release.EXPORTS == ROOT / "data" / "exports"


def test_the_newest_release_is_found_from_another_working_directory(
        tmp_path, monkeypatch):
    """The failure this is for: the chain run from anywhere else."""
    _, (older, newer) = _exports(tmp_path, monkeypatch,
                                 "phase2.9_build", "phase2.10_build")
    from_here = release.latest_release_dir()
    monkeypatch.chdir(tmp_path / "somewhere-else"
                      if (tmp_path / "somewhere-else").mkdir() is None else tmp_path)
    assert release.latest_release_dir() == from_here == newer
    assert release.release_dirs() == [newer, older]


def test_an_explicit_release_folder_wins_and_must_exist(tmp_path, monkeypatch):
    _, (only,) = _exports(tmp_path, monkeypatch, "phase2.10_build")
    other = tmp_path / "phase3_build"
    other.mkdir()
    assert release.current_release_dir(other) == other
    with pytest.raises(SystemExit, match="not a directory"):
        release.current_release_dir(tmp_path / "missing_build")
    assert release.current_release_dir(None) == only


def test_no_release_folder_is_a_refusal_not_phase_one(tmp_path, monkeypatch):
    """A fresh checkout has no releases. The scripts used to answer
    `phase1_build` and "1" here, silently, and stamp the reader with it."""
    _exports(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="no release folder"):
        release.current_release_dir(None)
    with pytest.raises(SystemExit, match="pass --phase"):
        release.current_phase(None, None)


def test_the_phase_is_explicit_or_read_from_the_folder_never_guessed(
        tmp_path, monkeypatch):
    _, (d,) = _exports(tmp_path, monkeypatch, "phase2.11_build")
    assert release.current_phase(None, d) == "2.11"
    assert release.current_phase("3", d) == "3"
    # An unconventional folder name yields no phase, and no phase is a
    # refusal rather than "1".
    odd = tmp_path / "adhoc_build"
    odd.mkdir()
    with pytest.raises(SystemExit, match="pass --phase"):
        release.current_phase(None, odd)


def test_the_sync_ledger_is_one_absolute_path_under_exports():
    """Three scripts read it; one constant, resolved against the root.

    From another directory the sync found no ledger and would have
    started from nothing — every file uploaded again beside the copy
    already on Drive, the duplicate-archive mechanism by another door.
    """
    assert drive.SYNC_LEDGER.is_absolute()
    assert drive.SYNC_LEDGER.parent == release.EXPORTS
    assert drive.SYNC_LEDGER.name == ".drive_sync_state.json"


@pytest.mark.parametrize("script", RELEASE_CHAIN)
def test_no_release_chain_script_finds_exports_by_a_relative_path(script):
    """The sweep the fix was made under, kept as an assertion.

    A `Path("data/exports…")` literal in any of these is the same defect
    in a different place, and prose cannot stop one being reintroduced.
    Comments are exempt, so the historical mistake can still be cited.
    """
    src = (ROOT / script).read_text(encoding="utf-8")
    offenders = [
        (i, line.strip())
        for i, line in enumerate(src.splitlines(), 1)
        if 'Path("data/exports' in line and not line.strip().startswith("#")]
    assert not offenders, (
        f"{script} finds the exports directory relative to the working "
        f"directory:\n" + "\n".join(f"  line {i}: {l}" for i, l in offenders))
