"""Re-filing a document is a move on Drive, not a second upload.

The ledger is keyed on local path, so when a site is re-partitioned and
whole application folders move between site folders, every moved
document reads as brand new. Uploading it again sends bytes Drive
already holds and leaves the original orphaned in a folder nothing links
to — 14.5 GB of it after the 2026-08-25 materialisation. These tests pin
the detection rule and, as much as the rule itself, the cases where it
must decline and upload instead.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "drive_sync", Path(__file__).parent.parent / "scripts" / "drive_sync.py")
drive_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drive_sync)


def _sync(state):
    s = drive_sync.Sync.__new__(drive_sync.Sync)
    s.svc = None
    s.state = state
    s._dirty = 0
    s._md5_cache = None
    return s


def test_moved_file_is_detected_when_its_old_path_has_gone(tmp_path):
    old = tmp_path / "old_site" / "app" / "doc.pdf"
    s = _sync({"folders": {}, "files": {
        str(old): {"md5": "abc123", "id": "file-1"}}})
    assert s._moved_source("abc123", "doc.pdf") == (str(old), "file-1")


def test_a_file_still_present_locally_is_a_copy_not_a_move(tmp_path):
    # Both paths exist: the tree genuinely holds the document twice, so
    # reparenting would strand the copy that stayed put.
    old = tmp_path / "old_site" / "doc.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    s = _sync({"folders": {}, "files": {
        str(old): {"md5": "abc123", "id": "file-1"}}})
    assert s._moved_source("abc123", "doc.pdf") is None


def test_two_candidates_are_declined_rather_than_guessed(tmp_path):
    a = tmp_path / "site_a" / "doc.pdf"
    b = tmp_path / "site_b" / "doc.pdf"
    s = _sync({"folders": {}, "files": {
        str(a): {"md5": "abc123", "id": "file-1"},
        str(b): {"md5": "abc123", "id": "file-2"}}})
    assert s._moved_source("abc123", "doc.pdf") is None


def test_same_bytes_under_a_different_name_is_not_a_move(tmp_path):
    # Identical bytes are common — a boilerplate consultation response
    # filed under two names is not the same document being re-filed.
    old = tmp_path / "old_site" / "090 - Report.pdf"
    s = _sync({"folders": {}, "files": {
        str(old): {"md5": "abc123", "id": "file-1"}}})
    assert s._moved_source("abc123", "Design and Access Statement.pdf") is None


def test_different_bytes_never_match(tmp_path):
    old = tmp_path / "old_site" / "doc.pdf"
    s = _sync({"folders": {}, "files": {
        str(old): {"md5": "abc123", "id": "file-1"}}})
    assert s._moved_source("different", "doc.pdf") is None


def test_ledger_entries_without_an_id_are_ignored(tmp_path):
    old = tmp_path / "old_site" / "doc.pdf"
    s = _sync({"folders": {}, "files": {
        str(old): {"md5": "abc123"}}})
    assert s._moved_source("abc123", "doc.pdf") is None


class _FakeFiles:
    def __init__(self, meta):
        self.meta = meta
        self.updates = []

    def get(self, fileId, fields):
        return _Exec(dict(self.meta[fileId]))

    def update(self, fileId, addParents, removeParents, fields):
        self.updates.append((fileId, addParents, removeParents))
        return _Exec({"id": fileId})


class _Exec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeService:
    def __init__(self, meta):
        self._files = _FakeFiles(meta)

    def files(self):
        return self._files


def test_upload_reparents_instead_of_sending_bytes(tmp_path, monkeypatch):
    old = tmp_path / "old_site" / "app" / "doc.pdf"
    new = tmp_path / "new_site" / "app" / "doc.pdf"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"hello")
    md5 = drive_sync.md5_of(new)

    s = _sync({"folders": {}, "files": {
        str(old): {"md5": md5, "id": "file-1"}}})
    s.svc = _FakeService({"file-1": {"parents": ["old-parent"],
                                     "trashed": False}})
    monkeypatch.setattr(drive_sync.Sync, "save", lambda self, force=False: None)

    assert s.upload(new, "new-parent") == "moved"
    assert s.svc.files().updates == [("file-1", "new-parent", "old-parent")]
    # The ledger follows the file: new path in, old path out, same id.
    assert s.state["files"][str(new)] == {"md5": md5, "id": "file-1"}
    assert str(old) not in s.state["files"]


def test_a_trashed_original_is_not_resurrected(tmp_path, monkeypatch):
    # Falls through to the normal upload path rather than un-binning a
    # file somebody deliberately removed.
    old = tmp_path / "old_site" / "doc.pdf"
    new = tmp_path / "new_site" / "doc.pdf"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"hello")
    md5 = drive_sync.md5_of(new)

    s = _sync({"folders": {}, "files": {
        str(old): {"md5": md5, "id": "file-1"}}})
    s.svc = _FakeService({"file-1": {"parents": ["old-parent"],
                                     "trashed": True}})
    monkeypatch.setattr(drive_sync.Sync, "save", lambda self, force=False: None)
    with pytest.raises(Exception):
        # No MediaFileUpload plumbing on the fake, so reaching the upload
        # path raises — which is the assertion: it did not return "moved".
        s.upload(new, "new-parent")
    assert s.svc.files().updates == []
