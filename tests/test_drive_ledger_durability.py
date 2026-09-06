"""The ledger is the only record of what the sync created, and it is
written to be lost.

Under `drive.file` the API cannot list the archive, so
`data/exports/.drive_sync_state.json` is the whole memory of what is on
Drive: it drives move detection and pruning, and the id recorder and the
sample verifier read it. Until 2026-09-06 `Sync.save()` serialised the
state under its lock, released the lock, then `write_text`ed the file in
place. Two hazards, neither observed yet, both real: a kill mid-write
left truncated JSON, which the next run died on; and two workers could
pass the fifty-change gate in one order and finish their writes in the
other, so an older snapshot overwrote a newer one and the ledger on
disk fell up to fifty entries behind the state in memory until the next
checkpoint. That one is bounded: it cost anything only if the run then
died inside that window, since the final forced save writes the whole
state — the torn write is the hazard any kill hits, and the entries a
death inside the window would lose are files re-uploaded beside their
Drive copies next run, the duplicate-archive mechanism `dcp/drive.py`
exists to prevent. And nothing at all stopped two `drive_sync.py`
processes loading one snapshot into two memories.

The existing concurrent test could see none of it: it asserts after a
final uncontended save, when the last write is always whole. These
tests reach the mechanism directly.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path

import pytest

from dcp import drive as _drive

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "drive_sync", ROOT / "scripts" / "drive_sync.py")
drive_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drive_sync)


def _sync(state):
    s = drive_sync.Sync.__new__(drive_sync.Sync)
    s._tls = drive_sync.threading.local()
    s._lock = drive_sync.threading.RLock()
    s._creds = None
    s.svc = None
    s.state = state
    s._dirty = 0
    s._md5_cache = None
    return s


class TestAtomicWrite:
    def test_an_interrupted_write_leaves_the_previous_ledger_intact(self, tmp_path, monkeypatch):
        """Kill the process between serialising and replacing: the file on
        disk must still be the ledger that was there before, byte for
        byte, and still parse."""
        ledger = tmp_path / "state.json"
        before = {"folders": {}, "files": {"a": {"md5": "1", "id": "x"}}}
        ledger.write_text(json.dumps(before))
        monkeypatch.setattr(drive_sync, "STATE_PATH", ledger)

        def die(*a, **k):
            raise KeyboardInterrupt
        monkeypatch.setattr(_drive.os, "replace", die)

        s = _sync({"folders": {}, "files": {"a": {"md5": "1", "id": "x"},
                                             "b": {"md5": "2", "id": "y"}}})
        with pytest.raises(KeyboardInterrupt):
            s.save(force=True)
        assert json.loads(ledger.read_text()) == before

    def test_the_write_is_one_replace_never_a_truncate_in_place(self, tmp_path, monkeypatch):
        ledger = tmp_path / "state.json"
        monkeypatch.setattr(drive_sync, "STATE_PATH", ledger)
        seen = []
        real = _drive.os.replace

        def spy(src, dst):
            seen.append((Path(src).name, Path(dst).name))
            return real(src, dst)
        monkeypatch.setattr(_drive.os, "replace", spy)
        _sync({"folders": {}, "files": {"a": {"md5": "1", "id": "x"}}}).save(force=True)
        assert seen == [("state.json.tmp", "state.json")]
        assert not ledger.with_name("state.json.tmp").exists()
        assert json.loads(ledger.read_text())["files"]["a"]["id"] == "x"


class TestTheWriteIsUnderTheLock:
    def test_no_other_thread_can_take_the_lock_while_the_file_is_written(self, tmp_path, monkeypatch):
        """This is the reverse-order hazard closed: if the lock is held
        across the write, two saves cannot interleave, so a newer
        snapshot cannot be overwritten by an older one."""
        monkeypatch.setattr(drive_sync, "STATE_PATH", tmp_path / "state.json")
        s = _sync({"folders": {}, "files": {}})
        acquired_during_write = []
        real = _drive.write_ledger

        def observing(path, payload):
            got = s._lock.acquire(blocking=False)
            # RLock is re-entrant for THIS thread, so ask another one.
            result = []
            t = threading.Thread(target=lambda: result.append(s._lock.acquire(blocking=False)))
            t.start(); t.join()
            if got:
                s._lock.release()
            acquired_during_write.append(result[0])
            return real(path, payload)
        monkeypatch.setattr(_drive, "write_ledger", observing)
        s.save(force=True)
        assert acquired_during_write == [False]

    def test_a_checkpoint_below_the_threshold_writes_nothing(self, tmp_path, monkeypatch):
        ledger = tmp_path / "state.json"
        monkeypatch.setattr(drive_sync, "STATE_PATH", ledger)
        s = _sync({"folders": {}, "files": {}})
        for _ in range(49):
            s.save()
        assert not ledger.exists()
        s.save()
        assert ledger.exists()


class TestOneProcess:
    def test_a_second_holder_is_refused_before_anything_else(self, tmp_path):
        first = _drive.acquire_ledger_lock(tmp_path / "state.json")
        try:
            with pytest.raises(_drive.LedgerLocked, match="another sync holds"):
                _drive.acquire_ledger_lock(tmp_path / "state.json")
        finally:
            first.release()

    def test_the_refusal_names_the_holder(self, tmp_path):
        first = _drive.acquire_ledger_lock(tmp_path / "state.json")
        try:
            with pytest.raises(_drive.LedgerLocked, match=str(os.getpid())):
                _drive.acquire_ledger_lock(tmp_path / "state.json")
        finally:
            first.release()

    def test_releasing_lets_the_next_in(self, tmp_path):
        first = _drive.acquire_ledger_lock(tmp_path / "state.json")
        first.release()
        second = _drive.acquire_ledger_lock(tmp_path / "state.json")
        second.release()

    def test_the_sync_takes_the_lock_before_it_loads_the_ledger_or_calls_the_api(self):
        """Read from the source: the lock is taken after the argument
        checks and before `Sync(...)`, whose __init__ loads the ledger
        and after which the first `files().list` happens."""
        src = (ROOT / "scripts" / "drive_sync.py").read_text()
        main = src[src.index("def main("):]
        lock_at = main.index("_drive.acquire_ledger_lock(STATE_PATH)")
        sync_at = main.index("sync = Sync(svc, credentials=creds)")
        assert lock_at < sync_at


class TestTheReader:
    def test_an_absent_ledger_is_the_empty_ledger(self, tmp_path):
        assert _drive.read_ledger(tmp_path / "none.json") == {"folders": {}, "files": {}}

    def test_a_corrupt_ledger_is_refused_not_replaced(self, tmp_path, monkeypatch):
        """Starting from nothing beside a corrupt ledger would re-upload
        the whole archive beside itself. The message says what to do."""
        ledger = tmp_path / "state.json"
        ledger.write_text('{"folders": {}, "files": {"a": ')   # torn
        monkeypatch.setattr(drive_sync, "STATE_PATH", ledger)
        with pytest.raises(SystemExit, match="rebuild_drive_ledger"):
            drive_sync.Sync(None, None)
        assert ledger.read_text().startswith('{"folders"'), "untouched"


class TestOneConstantOneWriter:
    def test_every_script_that_touches_the_ledger_imports_the_constant(self):
        """Two still spelled the path themselves after the 2026-09-02
        fold, outside `tests/test_release_paths.py`'s reach."""
        for name in ("drive_sync.py", "export_handover.py", "verify_drive_sample.py",
                     "record_drive_ids.py", "rebuild_drive_ledger.py"):
            src = (ROOT / "scripts" / name).read_text()
            assert "SYNC_LEDGER" in src, name
            assert '"data" / "exports" / ".drive_sync_state.json"' not in src, name

    def test_the_two_writers_use_the_one_writer(self):
        for name in ("drive_sync.py", "rebuild_drive_ledger.py"):
            src = (ROOT / "scripts" / name).read_text()
            assert "_drive.write_ledger(" in src, name
            assert ".write_text(" not in src.split("def ")[-1] or name == "drive_sync.py"
        rebuild = (ROOT / "scripts" / "rebuild_drive_ledger.py").read_text()
        assert "_drive.acquire_ledger_lock(" in rebuild
