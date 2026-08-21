#!/usr/bin/env python3
"""Encrypted, generational database backups — local and on Drive.

The document corpus is mostly re-fetchable. The database is not: 454,011
findings behind a verbatim-quote gate, the power adjudications, the
append-only source_snapshots audit trail and the deepread log are three
months of work that exists in exactly one place, on one laptop, on one
SSD. This closes that.

Three decisions worth knowing:

**The dump is encrypted before it leaves the machine.** A pg_dump is the
raw schema, and the raw schema holds what the exports redact: Barbour's
role-block contact details, objectors' names and addresses from
consultee responses. Encrypting with a passphrase means Drive folder
permissions stop being the thing standing between that material and a
mis-share. The passphrase lives in the environment, never in the repo.

**Backups go to their own Drive folder, never a subfolder of the
handover archive.** Sharing inherits downward, so a subfolder of the
folder the reporting team can read is readable by the reporting team.
The destination is pinned by ID for the same reason the handover archive
is (see dcp/drive.py): under the drive.file scope a name lookup cannot
see a folder it did not create, so resolving by name silently makes a
second one. `--create-folder` mints it once and prints the ID to pin.

**Nothing is overwritten.** Each run writes a new timestamped file. A
backup that overwrites will, one day, faithfully copy a corrupt database
over the last good copy of a healthy one.

The dump runs inside the Postgres container: pg_dump must be at least
the server's major version, and the host's Homebrew pg_dump is 14
against a 16 server, which simply refuses. Taking it from the container
means the two can never drift.

pg_dump takes an MVCC-consistent snapshot without blocking writers, so
this is safe to run while a deep-read is in progress.

Usage:
    export DCP_BACKUP_PASSPHRASE='…'          # keep it in your password manager
    scripts/backup_db.py                       # dump, verify, upload, prune local
    scripts/backup_db.py --no-upload           # local only
    scripts/backup_db.py --create-folder       # first run: make the Drive folder
    scripts/backup_db.py --verify-only FILE    # prove an existing backup restores
    scripts/backup_db.py --list                # what exists, locally and on Drive

Restore (to a scratch database, which is the only way to rehearse it):
    gpg --decrypt data/backups/dcp_<stamp>.dump.gpg > /tmp/dcp.dump
    docker exec -i datacentre_planning-postgres-1 \
        pg_restore -U dcp -d dcp_restore_test --clean --if-exists < /tmp/dcp.dump
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Every other entry point loads .env for DATABASE_URL; this one talks to
# Postgres through Docker and so never needed it, which is why the
# passphrase sitting in .env has been invisible to it. Without this the
# script exits telling you to export a variable you have already set,
# and the backup quietly does not happen.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

BACKUP_DIR = ROOT / "data" / "backups"
CONTAINER = os.environ.get("DCP_PG_CONTAINER", "datacentre_planning-postgres-1")
PG_USER = os.environ.get("DCP_PG_USER", "dcp")
PG_DB = os.environ.get("DCP_PG_DB", "dcp")
PASSPHRASE_ENV = "DCP_BACKUP_PASSPHRASE"

# Local retention. Drive keeps everything unless --prune-drive is asked
# for explicitly: deleting the off-site copy is the one action in this
# script that can lose data, so it is never the default.
KEEP_LOCAL = 14


def _passphrase() -> str:
    pw = os.environ.get(PASSPHRASE_ENV)
    if not pw:
        sys.exit(
            f"{PASSPHRASE_ENV} is not set. The backup is encrypted because "
            "the dump holds unredacted personal data; without a passphrase "
            "there is nothing to encrypt it with.\n\n"
            "  export DCP_BACKUP_PASSPHRASE='…'\n\n"
            "Store it in your password manager. A backup you cannot decrypt "
            "is not a backup, and this script cannot recover it for you.")
    if len(pw) < 12:
        sys.exit(f"{PASSPHRASE_ENV} is shorter than 12 characters.")
    return pw


def _container_running() -> bool:
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True)
    return CONTAINER in out.stdout.split()


def dump(out_path: Path, passphrase: str) -> Path:
    """pg_dump (custom format) -> gpg -> file, streamed, never landing
    the plaintext dump on disk."""
    if not _container_running():
        sys.exit(f"container {CONTAINER!r} is not running (docker compose up -d)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".partial")

    # The passphrase travels on its own file descriptor, not argv: argv is
    # world-readable in ps output.
    read_fd, write_fd = os.pipe()
    os.write(write_fd, (passphrase + "\n").encode())
    os.close(write_fd)

    t0 = time.time()
    with tmp.open("wb") as fh:
        pg = subprocess.Popen(
            ["docker", "exec", "-i", CONTAINER,
             "pg_dump", "-U", PG_USER, "-d", PG_DB, "-Fc", "--no-password"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gpg = subprocess.Popen(
            ["gpg", "--batch", "--yes", "--symmetric", "--cipher-algo", "AES256",
             "--passphrase-fd", str(read_fd)],
            stdin=pg.stdout, stdout=fh, stderr=subprocess.PIPE,
            pass_fds=(read_fd,))
        pg.stdout.close()  # so pg sees EPIPE if gpg dies
        gpg_err = gpg.communicate()[1]
        pg_err = pg.stderr.read()
        pg.wait()
    os.close(read_fd)

    if pg.returncode != 0:
        tmp.unlink(missing_ok=True)
        sys.exit(f"pg_dump failed: {pg_err.decode()[:400]}")
    if gpg.returncode != 0:
        tmp.unlink(missing_ok=True)
        sys.exit(f"gpg failed: {gpg_err.decode()[:400]}")

    tmp.rename(out_path)
    size = out_path.stat().st_size
    print(f"  dumped and encrypted: {out_path.name} "
          f"({size / 1e6:.0f} MB, {time.time() - t0:.0f}s)")
    return out_path


def verify(path: Path, passphrase: str) -> bool:
    """Decrypt the whole archive and parse its table of contents.

    Both halves matter, and the first one is the one that nearly got
    away. `pg_restore --list` reads only the table of contents, which
    lives at the *start* of a custom-format dump: truncate the file to
    40% and it still lists all eighteen tables happily, because the
    catalogue is intact and the data is gone. That is this project's own
    recurring bug wearing a backup's clothes — a listing that proves the
    listing exists.

    What actually catches it is gpg. AES256 with its modification
    detection code fails loudly on a truncated or altered ciphertext,
    but only if someone reads the return code, which the first version
    of this function did not. So: gpg must exit clean (the whole file
    decrypted and passed its integrity check) AND pg_restore must parse
    what came out AND the essential tables must be present. Any one of
    those alone is a near-side check.

    Stronger still is --restore-test, which puts the data in a real
    database and counts it. That is the only check that proves the
    bytes, and it is what a rehearsal should use.
    """
    def _gpg(stdout):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, (passphrase + "\n").encode())
        os.close(write_fd)
        proc = subprocess.Popen(
            ["gpg", "--batch", "--quiet", "--decrypt",
             "--passphrase-fd", str(read_fd), str(path)],
            stdout=stdout, stderr=subprocess.PIPE, pass_fds=(read_fd,))
        return proc, read_fd

    # Pass one: decrypt the whole file to nowhere. pg_restore --list would
    # stop reading at the end of the table of contents, close the pipe,
    # and leave gpg's integrity check unreached — so the byte-for-byte
    # check gets a pass of its own, where nothing can short-circuit it.
    with open(os.devnull, "wb") as devnull:
        proc, fd = _gpg(devnull)
        gpg_err = proc.communicate()[1]
        os.close(fd)
    if proc.returncode != 0:
        tail = (gpg_err.decode(errors="replace").strip().splitlines()
                or ["no detail"])[-1]
        print(f"  VERIFY FAILED: decryption or integrity check failed — "
              f"{tail[:200]}")
        return False

    # Pass two: the table of contents, now that the ciphertext is known
    # whole.
    proc, fd = _gpg(subprocess.PIPE)
    lst = subprocess.Popen(
        ["docker", "exec", "-i", CONTAINER, "pg_restore", "--list"],
        stdin=proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdout.close()
    toc, lst_err = lst.communicate()
    proc.wait()
    os.close(fd)

    if lst.returncode != 0:
        print(f"  VERIFY FAILED: {lst_err.decode()[:300]}")
        return False

    tables = [ln for ln in toc.decode(errors="replace").splitlines()
              if "TABLE DATA" in ln]
    names = {ln.split()[-2] for ln in tables if len(ln.split()) >= 2}
    # The tables whose loss would end the project. Present in the table of
    # contents is not proof of row counts, but their absence is proof of a
    # bad dump.
    essential = {"findings", "documents", "applications", "deepread_log",
                 "source_snapshots", "power_adjudication", "sites"}
    missing = essential - names
    if missing:
        print(f"  VERIFY FAILED: essential tables absent from archive: "
              f"{', '.join(sorted(missing))}")
        return False
    print(f"  verified: decrypts, parses, {len(tables)} tables present")
    return True


def restore_test(path: Path, passphrase: str) -> bool:
    """Restore into a scratch database and count what arrived.

    The rehearsal. `verify` proves the ciphertext is whole and the
    catalogue parses; only this proves the rows are in there, because it
    is the only check that puts them in a database and asks. Row counts
    are compared against the live database, so a dump that restores but
    arrives half-empty fails here rather than in an emergency.

    The scratch database is dropped and recreated each run and holds
    nothing anyone would miss. It is named unmistakably for that reason.
    """
    scratch = "dcp_restore_check"
    print(f"  restoring into scratch database {scratch} …")

    def psql(sql: str, db: str = "postgres"):
        return subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "psql", "-U", PG_USER,
             "-d", db, "-tAc", sql],
            capture_output=True, text=True)

    psql(f'DROP DATABASE IF EXISTS "{scratch}"')
    made = psql(f'CREATE DATABASE "{scratch}"')
    if made.returncode != 0:
        print(f"  RESTORE TEST FAILED: could not create scratch db: "
              f"{made.stderr[:200]}")
        return False

    read_fd, write_fd = os.pipe()
    os.write(write_fd, (passphrase + "\n").encode())
    os.close(write_fd)
    t0 = time.time()
    gpg = subprocess.Popen(
        ["gpg", "--batch", "--quiet", "--decrypt",
         "--passphrase-fd", str(read_fd), str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(read_fd,))
    rest = subprocess.Popen(
        ["docker", "exec", "-i", CONTAINER, "pg_restore", "-U", PG_USER,
         "-d", scratch, "--no-owner", "--no-privileges"],
        stdin=gpg.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    gpg.stdout.close()
    rest_err = rest.communicate()[1]
    gpg.wait()
    os.close(read_fd)
    if gpg.returncode != 0 or rest.returncode != 0:
        print(f"  RESTORE TEST FAILED: {rest_err.decode()[:300]}")
        return False

    ok = True
    print(f"  restored in {time.time() - t0:.0f}s; comparing row counts")
    for table in ("findings", "documents", "applications", "deepread_log",
                  "source_snapshots", "power_adjudication", "sites",
                  "triage"):
        live = psql(f"SELECT count(*) FROM {table}", PG_DB).stdout.strip()
        back = psql(f"SELECT count(*) FROM {table}", scratch).stdout.strip()
        # The live database may have grown since the dump — a deep-read
        # runs for days — so the backup may hold fewer rows. It must
        # never hold more, and it must not be empty.
        mark = "ok"
        if not back.isdigit() or not live.isdigit():
            mark, ok = "UNREADABLE", False
        elif int(back) == 0 and int(live) > 0:
            mark, ok = "EMPTY", False
        elif int(back) > int(live):
            mark, ok = "MORE THAN LIVE", False
        elif int(live) and int(back) < int(live) * 0.95:
            mark = f"{100 * int(back) / int(live):.0f}% of live (dump is older)"
        print(f"    {table:22} backup {back:>9}  live {live:>9}  {mark}")

    psql(f'DROP DATABASE IF EXISTS "{scratch}"')
    print("  scratch database dropped")
    return ok


def drive_folder_id(create: bool) -> str | None:
    from dcp import drive as drive_const
    pinned = getattr(drive_const, "BACKUP_FOLDER_ID", None)
    if pinned:
        return pinned
    if not create:
        print("  no BACKUP_FOLDER_ID pinned in dcp/drive.py — run once with "
              "--create-folder, then pin the id it prints.")
        return None

    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    ds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds)
    svc = ds.get_service()
    fid = svc.files().create(
        body={"name": "DC Planning database backups",
              "mimeType": "application/vnd.google-apps.folder"},
        fields="id").execute()["id"]
    print(f"\n  created Drive folder: {fid}")
    print("  Pin it in dcp/drive.py as:\n")
    print(f'      BACKUP_FOLDER_ID = "{fid}"\n')
    print("  It is unshared and owned by you. Keep it that way: it is not "
          "a subfolder of the handover archive precisely so that sharing "
          "the documents never shares the database.\n")
    return fid


def upload(path: Path, folder_id: str) -> str:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    ds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds)
    from googleapiclient.http import MediaFileUpload

    svc = ds.get_service()
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            resumable=True, chunksize=8 << 20)
    t0 = time.time()
    fid = svc.files().create(
        body={"name": path.name, "parents": [folder_id]},
        media_body=media, fields="id").execute()["id"]
    print(f"  uploaded to Drive: {path.name} ({time.time() - t0:.0f}s)")
    return fid


def prune_local(keep: int) -> None:
    backups = sorted(BACKUP_DIR.glob("dcp_*.dump.gpg"))
    surplus = backups[:-keep] if keep else []
    for p in surplus:
        p.unlink()
        print(f"  pruned local: {p.name}")
    if surplus:
        print(f"  {len(backups) - len(surplus)} local backups retained "
              f"(Drive keeps every copy unless pruned explicitly)")


def list_backups(folder_id: str | None) -> None:
    local = sorted(BACKUP_DIR.glob("dcp_*.dump.gpg"))
    print(f"local ({len(local)}):")
    for p in local:
        print(f"  {p.name}  {p.stat().st_size / 1e6:.0f} MB")
    if not folder_id:
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "drive_sync", ROOT / "scripts" / "drive_sync.py")
    ds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds)
    svc = ds.get_service()
    res = svc.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(name,size,createdTime)", pageSize=200,
        orderBy="createdTime").execute().get("files", [])
    print(f"\nDrive ({len(res)}):")
    for f in res:
        mb = int(f.get("size", 0)) / 1e6
        print(f"  {f['name']}  {mb:.0f} MB  {f['createdTime'][:16]}")
    if res:
        newest = res[-1]["createdTime"][:10]
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(res[-1]["createdTime"].replace("Z", "+00:00")))
        flag = "  <-- STALE" if age > timedelta(days=2) else ""
        print(f"\nmost recent off-site copy: {newest} "
              f"({age.days}d {age.seconds // 3600}h old){flag}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-upload", action="store_true",
                    help="Dump and verify locally; skip Drive.")
    ap.add_argument("--create-folder", action="store_true",
                    help="Create the Drive backup folder and print its id.")
    ap.add_argument("--verify-only", type=Path, default=None,
                    help="Verify an existing backup file and exit.")
    ap.add_argument("--restore-test", type=Path, default=None,
                    metavar="FILE",
                    help="Restore a backup into a scratch database and "
                         "compare row counts against live. The rehearsal; "
                         "worth running monthly.")
    ap.add_argument("--list", action="store_true",
                    help="List backups locally and on Drive.")
    ap.add_argument("--keep-local", type=int, default=KEEP_LOCAL)
    args = ap.parse_args()

    if args.create_folder:
        # Standalone: making the destination is setup, not a backup, and
        # must not require the passphrase.
        return 0 if drive_folder_id(create=True) else 1

    if args.list:
        list_backups(drive_folder_id(create=False))
        return 0

    if args.verify_only:
        ok = verify(args.verify_only, _passphrase())
        return 0 if ok else 1

    if args.restore_test:
        pw = _passphrase()
        ok = verify(args.restore_test, pw) and restore_test(args.restore_test, pw)
        return 0 if ok else 1

    passphrase = _passphrase()
    folder_id = (drive_folder_id(create=args.create_folder)
                 if not args.no_upload else None)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    out = BACKUP_DIR / f"dcp_{stamp}.dump.gpg"
    print(f"backing up {PG_DB} from {CONTAINER}")
    dump(out, passphrase)

    if not verify(out, passphrase):
        print("\nThe archive did not verify. It is kept for inspection but "
              "must not be relied on.")
        return 1

    if folder_id:
        upload(out, folder_id)
    elif not args.no_upload:
        print("  not uploaded (no folder id) — this backup is on the same "
              "disk as the database it protects.")

    prune_local(args.keep_local)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
