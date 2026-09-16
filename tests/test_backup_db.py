"""The backup's own checks, on a mangled archive and a wrong passphrase.

`scripts/backup_db.py` guards the one asset nothing can re-fetch, and
until 2026-09-16 nothing tested it. `verify()`'s first pass decrypts the
whole archive so gpg's integrity check runs over every byte — the
docstring records why a table-of-contents listing alone would pass a
file truncated to 40%. That pass needs only gpg, so it can be tested
here; the second pass and `restore_test` need the Postgres container
and are the rehearsal's job. `prune_local` decides which backups to
delete, and the newest must survive whatever `keep` says.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import backup_db  # noqa: E402

needs_gpg = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg not installed")


def _encrypt(plain: bytes, path: Path, passphrase: str) -> None:
    src = path.with_suffix(".plain")
    src.write_bytes(plain)
    subprocess.run(
        ["gpg", "--batch", "--yes", "--quiet", "--symmetric", "--cipher-algo", "AES256",
         "--pinentry-mode", "loopback", "--passphrase-fd", "0", "-o", str(path), str(src)],
        input=(passphrase + "\n").encode(), check=True, capture_output=True)
    src.unlink()
    assert path.stat().st_size > 1000


@needs_gpg
def test_a_truncated_archive_fails_verification(tmp_path, capsys):
    archive = tmp_path / "dcp_20260916.dump.gpg"
    _encrypt(os.urandom(64_000), archive, "pw")
    whole = archive.read_bytes()
    archive.write_bytes(whole[: int(len(whole) * 0.6)])
    assert backup_db.verify(archive, "pw") is False
    assert "VERIFY FAILED" in capsys.readouterr().out


@needs_gpg
def test_an_altered_byte_fails_verification(tmp_path):
    archive = tmp_path / "dcp_20260916.dump.gpg"
    _encrypt(os.urandom(64_000), archive, "pw")
    whole = bytearray(archive.read_bytes())
    whole[len(whole) // 2] ^= 0xFF
    archive.write_bytes(bytes(whole))
    assert backup_db.verify(archive, "pw") is False


@needs_gpg
def test_the_wrong_passphrase_fails_verification(tmp_path):
    archive = tmp_path / "dcp_20260916.dump.gpg"
    _encrypt(os.urandom(8_000), archive, "pw")
    assert backup_db.verify(archive, "not-pw") is False


def _backups(dir_: Path, days) -> list[Path]:
    paths = [dir_ / f"dcp_202609{d:02d}.dump.gpg" for d in days]
    for p in paths:
        p.write_bytes(b"x")
    return paths


def test_prune_keeps_the_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path)
    _backups(tmp_path, [1, 2, 3, 4, 5])
    backup_db.prune_local(2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "dcp_20260904.dump.gpg", "dcp_20260905.dump.gpg"]


def test_prune_with_keep_zero_deletes_nothing(tmp_path, monkeypatch):
    """`keep=0` reads as "keep none" and must never mean that."""
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path)
    _backups(tmp_path, [1, 2, 3])
    backup_db.prune_local(0)
    assert len(list(tmp_path.iterdir())) == 3


def test_prune_never_deletes_the_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path)
    _backups(tmp_path, [1, 2, 3])
    backup_db.prune_local(1)
    assert [p.name for p in tmp_path.iterdir()] == ["dcp_20260903.dump.gpg"]
