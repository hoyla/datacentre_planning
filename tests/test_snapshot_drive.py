"""The snapshots' Drive ids: recorded, verified, never derived.

WP-B of docs/HANDOVER_SNAPSHOT_CHAIN.md. What these pin is the pair of
rules the document tree learned the hard way — a location is recorded at
upload and read back by key, never rebuilt from a path; and a folder is
addressed by id, never resolved by name, because under the `drive.file`
scope a name query that finds nothing silently creates a duplicate.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from datetime import date as dt_date

from dcp import drive
from dcp import snapshot_drive as sd

ROOT = Path(__file__).resolve().parent.parent


def _script():
    spec = importlib.util.spec_from_file_location(
        "sync_snapshots_drive", ROOT / "scripts" / "sync_snapshots_drive.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ledger(tmp_path, body):
    p = tmp_path / "ledger.yaml"
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Reading the ledger

def test_an_absent_ledger_is_empty_not_an_error(tmp_path):
    """Before the first sync there are no ids, and that is a state to
    render around rather than a fault."""
    assert sd.load_ledger(tmp_path / "nothing.yaml") == {}


def test_a_recorded_id_resolves_to_a_drive_url(tmp_path):
    led = sd.load_ledger(_ledger(tmp_path, f"""
folder_id: {drive.SNAPSHOTS_FOLDER_ID or 'FOLDER'}
files:
  op-site.2026-08-30.txt:
    file_id: FILE1
    md5: abc
    uploaded: 2026-09-01
"""))
    assert sd.url_for("op-site.2026-08-30.txt", led) == drive.file_url("FILE1")


def test_a_snapshot_with_no_id_gets_no_link_rather_than_a_guess(tmp_path):
    """The whole point of recording ids: nothing derives a location. A
    snapshot fetched since the last sync renders its source URL alone."""
    led = sd.load_ledger(_ledger(tmp_path, "files:\n  a.2026-08-30.txt:\n    file_id: F\n"))
    assert sd.url_for("op-site.2026-09-01.txt", led) == ""


def test_an_entry_without_a_file_id_fails_loudly(tmp_path):
    with pytest.raises(sd.SnapshotDriveError, match="no file_id"):
        sd.load_ledger(_ledger(tmp_path, "files:\n  a.2026-08-30.txt:\n    md5: abc\n"))


def test_a_ledger_naming_a_different_folder_is_refused(tmp_path, monkeypatch):
    """Ids recorded against one folder and read while the repository
    addresses another would resolve into a folder nobody is looking at —
    the duplicate-archive failure wearing a link's clothes."""
    monkeypatch.setattr(drive, "SNAPSHOTS_FOLDER_ID", "THE-REAL-ONE")
    with pytest.raises(sd.SnapshotDriveError, match="stale"):
        sd.load_ledger(_ledger(
            tmp_path, "folder_id: SOMEWHERE-ELSE\nfiles:\n  a.txt:\n    file_id: F\n"))


def test_unsynced_lists_only_snapshots_with_no_id(tmp_path):
    for n in ("a.2026-08-30.txt", "b.2026-08-30.txt", "c.2026-09-01.txt"):
        (tmp_path / n).write_text("x")
    pending = sd.unsynced(tmp_path, {"b.2026-08-30.txt": {"file_id": "F"}})
    assert [p.name for p in pending] == ["a.2026-08-30.txt", "c.2026-09-01.txt"]


# ---------------------------------------------------------------------------
# The upload's own verification

class _Exec:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeFiles:
    def __init__(self, created_id="FILE1", meta=None):
        self.created_id, self.meta = created_id, meta or {}
        self.creates = []

    def create(self, body, fields, media_body=None):
        self.creates.append(body)
        return _Exec({"id": self.created_id})

    def get(self, fileId, fields):
        return _Exec(dict(self.meta))


class _FakeService:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def _noretry(fn):
    return fn()


def _snapshot(tmp_path, name="op.2026-08-30.txt", body="# url: x"):
    p = tmp_path / name
    p.write_text(body)
    return p


def test_an_upload_whose_md5_disagrees_is_not_recorded(tmp_path):
    """Drive computes md5 server-side, so the copy can be checked rather
    than assumed. A link to evidence that is not the evidence cited is
    worse than no link — the argument that took the file:// anchors out
    of the reader."""
    s = _script()
    svc = _FakeService(_FakeFiles(meta={"md5Checksum": "WRONG",
                                        "parents": ["FOLDER"]}))
    with pytest.raises(ValueError, match="Drive holds md5"):
        s.upload_one(svc, _noretry, _snapshot(tmp_path), "FOLDER", "RIGHT")


def test_an_upload_landing_outside_the_snapshots_folder_is_not_recorded(tmp_path):
    s = _script()
    svc = _FakeService(_FakeFiles(meta={"md5Checksum": "M",
                                        "parents": ["SOMEWHERE-ELSE"]}))
    with pytest.raises(ValueError, match="not in the snapshots folder"):
        s.upload_one(svc, _noretry, _snapshot(tmp_path), "FOLDER", "M")


def test_a_verified_upload_returns_its_ledger_entry(tmp_path):
    s = _script()
    svc = _FakeService(_FakeFiles(meta={"md5Checksum": "M",
                                        "parents": ["FOLDER"]}))
    entry = s.upload_one(svc, _noretry, _snapshot(tmp_path), "FOLDER", "M")
    assert entry["file_id"] == "FILE1" and entry["md5"] == "M"
    assert entry["uploaded"].count("-") == 2


# ---------------------------------------------------------------------------
# Folder addressing

def test_the_folder_is_created_under_the_handover_root(tmp_path):
    s = _script()
    files = _FakeFiles(created_id="NEWFOLDER",
                       meta={"parents": [drive.FOLDER_ID], "trashed": False})
    assert s.create_folder(_FakeService(files), _noretry) == "NEWFOLDER"
    assert files.creates[0]["parents"] == [drive.FOLDER_ID]
    assert files.creates[0]["mimeType"] == "application/vnd.google-apps.folder"


def test_a_folder_that_does_not_read_back_under_the_root_stops_the_run():
    """Create then `files.get`. Trusting the create is how a folder that
    is not where it was asked for becomes the destination of a sync."""
    s = _script()
    files = _FakeFiles(created_id="NEWFOLDER",
                       meta={"parents": ["MY-DRIVE-ROOT"], "trashed": False})
    with pytest.raises(SystemExit, match="does not read back"):
        s.create_folder(_FakeService(files), _noretry)


def test_a_missing_folder_id_stops_rather_than_creating_one():
    """The rule the duplicate archive cost: no fallback to creation, ever."""
    s = _script()

    def _raise(fn):
        raise RuntimeError("404 File not found: BADID")

    with pytest.raises(SystemExit, match="does not resolve"):
        s.require_folder(_FakeService(_FakeFiles()), _raise, "BADID")


def test_a_binned_folder_stops_the_run():
    s = _script()
    files = _FakeFiles(meta={"id": "F", "parents": [drive.FOLDER_ID],
                             "trashed": True})
    with pytest.raises(SystemExit, match="Drive bin"):
        s.require_folder(_FakeService(files), _noretry, "F")


def test_nothing_resolves_a_folder_by_name():
    """`Sync.folder` exists and queries by name; this script must not use
    it. A name query under drive.file that finds nothing creates a
    duplicate, which is how two archives of 429 site folders happened."""
    src = (ROOT / "scripts" / "sync_snapshots_drive.py").read_text()
    body = src.split('"""', 2)[2]
    assert ".folder(" not in body
    assert "files().list" not in body


# ---------------------------------------------------------------------------
# The ledger the sync writes

def test_the_written_ledger_reads_back_by_key(tmp_path, monkeypatch):
    s = _script()
    monkeypatch.setattr(drive, "SNAPSHOTS_FOLDER_ID", "FOLDER")
    out = tmp_path / "led.yaml"
    s.write_ledger("FOLDER", {
        "b.2026-08-30.txt": {"file_id": "F2", "md5": "m2",
                             "uploaded": "2026-09-01"},
        "a.2026-08-30.txt": {"file_id": "F1", "md5": "m1",
                             "uploaded": "2026-09-01"}}, out)
    led = sd.load_ledger(out)
    assert led["a.2026-08-30.txt"]["file_id"] == "F1"
    assert sd.url_for("b.2026-08-30.txt", led) == drive.file_url("F2")
    # Sorted, so the diff of a re-sync shows only what was added.
    names = [ln.strip().rstrip(":") for ln in out.read_text().splitlines()
             if ln.startswith("  ") and ln.endswith(".txt:")]
    assert names == sorted(names)


def test_every_recorded_snapshot_is_one_this_repository_holds():
    """A ledger entry for a file that is not in the store would be a
    Drive link to evidence nothing here cites."""
    from dcp.capacity_claims import OPERATOR_SNAPSHOT_DIR
    held = {p.name for p in OPERATOR_SNAPSHOT_DIR.glob("*.txt")}
    assert set(sd.load_ledger()) <= held


# ---------------------------------------------------------------------------
# The link a claim gets (WP-C)
#
# The whole reason this is not a date lookup: `capacity_claims` keeps
# every reading of a page and the store keeps every reading of the page
# itself, and the two do not line up. A link resolved by slug and date
# alone would put CyrusOne LON1's superseded 8.72 MW row against the file
# that reads 9 MW — a working link, under a citation naming a different
# figure. The claim's own verbatim quote is what decides.

def _held(dirpath, name, body):
    (dirpath / name).write_text(
        f"# url: https://example.com\n\n# fetched: 2026-08-30\n\n"
        f"## VISIBLE TEXT\n\n{body}")
    return dirpath / name


def _led(**files):
    return {name: {"file_id": fid, "md5": "m", "uploaded": "2026-09-01"}
            for name, fid in files.items()}


def test_a_claim_links_the_file_its_own_quote_is_in(tmp_path):
    import datetime as dt
    _held(tmp_path, "op-site.2026-08-20.txt", "reads 8.72 MW IT capacity")
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 9 MW IT capacity")
    led = _led(**{"op-site.2026-08-20.txt": "OLD", "op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", dt.date(2026, 8, 28), "9 MW IT capacity",
                       snapshot_dir=tmp_path, ledger=led) == drive.file_url("NEW")


def test_a_superseded_reading_reaches_the_older_file(tmp_path):
    """The 8.72 MW row is dated before the re-fetch that replaced the
    figure, and the older snapshot is still held: it links there, not to
    the page that now contradicts it."""
    import datetime as dt
    _held(tmp_path, "op-site.2026-08-20.txt", "reads 8.72 MW IT capacity")
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 9 MW IT capacity")
    led = _led(**{"op-site.2026-08-20.txt": "OLD", "op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", dt.date(2026, 8, 20), "8.72 MW IT capacity",
                       snapshot_dir=tmp_path, ledger=led) == drive.file_url("OLD")


def test_a_reading_whose_evidence_is_no_longer_held_gets_no_link(tmp_path):
    """The case that matters, and the corpus's own: the 8.72 MW row
    predates the append-only store, so the file it was read from was
    overwritten and only the 9 MW snapshot survives. No candidate
    contains its quote, so it links nothing — a claim never borrows its
    neighbour's evidence."""
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 9 MW IT capacity")
    led = _led(**{"op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", None, "8.72 MW Total Megawatts IT Capacity",
                       snapshot_dir=tmp_path, ledger=led) is None


def test_the_quote_is_matched_whitespace_blind(tmp_path):
    """Snapshots are extracted text, where a line break carries no
    meaning — the same normalisation the quote gate admits a claim on,
    so a link is offered on exactly the terms the claim was accepted."""
    _held(tmp_path, "op-site.2026-08-30.txt",
              "reads 9 MW\n   Total  IT Capacity today")
    led = _led(**{"op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", None, "9 MW Total IT Capacity",
                       snapshot_dir=tmp_path, ledger=led) == drive.file_url("NEW")


def test_a_file_with_no_drive_id_gets_no_link_rather_than_a_neighbours(tmp_path):
    """A snapshot fetched since the last sync has no copy on Drive. The
    honest rendering is the source URL alone — and specifically not the
    next candidate, which would be a link to different evidence."""
    _held(tmp_path, "op-site.2026-08-20.txt", "reads 8.72 MW IT capacity")
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 8.72 MW IT capacity")
    led = _led(**{"op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", dt_date(2026, 8, 20), "8.72 MW IT capacity",
                       snapshot_dir=tmp_path, ledger=led) is None


def test_a_claim_with_no_snapshot_behind_it_gets_no_link(tmp_path):
    """Register rows and filed accounts are most of the claims store.
    Their locator names a row or a page, not a slug."""
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 9 MW IT capacity")
    led = _led(**{"op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("row 47", None, "9 MW IT capacity",
                       snapshot_dir=tmp_path, ledger=led) is None
    assert sd.copy_url("op-other", None, "9 MW IT capacity",
                       snapshot_dir=tmp_path, ledger=led) is None


def test_a_claim_with_no_quote_gets_no_link(tmp_path):
    """Nothing to check the file against is nothing to link on. The 119
    register claims are exactly this case."""
    _held(tmp_path, "op-site.2026-08-30.txt", "reads 9 MW IT capacity")
    led = _led(**{"op-site.2026-08-30.txt": "NEW"})
    assert sd.copy_url("op-site", None, "", snapshot_dir=tmp_path, ledger=led) is None
    assert sd.copy_url("op-site", None, None, snapshot_dir=tmp_path, ledger=led) is None


def test_every_committed_operator_claim_links_to_its_own_snapshot():
    """Against the real store and the real ledger, so this measures the
    artefacts rather than a fixture.

    The YAML holds current readings only, so every one of them resolves.
    The superseded 8.72 MW reading is not here — it is a row in
    `capacity_claims`, kept because the table's content key includes the
    value and the date, and the file it was read from was overwritten
    before the store became append-only. It is the case
    `test_a_reading_whose_evidence_is_no_longer_held_gets_no_link`
    stands for, and a build renders it with no link.
    """
    from dcp import capacity_claims as cc
    led = sd.load_ledger()
    unlinked = [c.claim_name for c in cc.load_operator_claims()
                if not sd.copy_url(c.attrs["snapshot"], c.as_at, c.quote,
                                   ledger=led)]
    assert unlinked == []
