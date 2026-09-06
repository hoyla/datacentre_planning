"""Where the handover archive lives on Drive.

One constant, because three files disagreeing about this is not a
hypothetical: the sync resolved its destination by *name*, could not see
the operator-created folder under the `drive.file` scope, and quietly
built a second copy of the entire archive at My Drive root. Both trees
ended up with 429 site folders, and the exports went to the one nobody
was reading while the workbook and the reader linked to the other.

Import this. Do not retype the ID, and do not resolve the folder by name.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from dcp.release import EXPORTS

# One shape for a Drive URL, in one place. Three scripts used to spell
# the file form themselves and two maps the folder form;
# `tests/test_drive_url_one_shape.py` refuses a fourth. A URL built from
# the id keeps resolving after the file or folder is moved or renamed on
# Drive, which is the reason this module addresses Drive by id at all.
FILE_URL_PREFIX = "https://drive.google.com/file/d/"
FILE_URL_SUFFIX = "/view"
FOLDER_URL_PREFIX = "https://drive.google.com/drive/folders/"


def file_url(file_id: str) -> str:
    """The viewer URL for a Drive file id."""
    return f"{FILE_URL_PREFIX}{file_id}{FILE_URL_SUFFIX}"


def folder_url(folder_id: str) -> str:
    """The URL that opens a Drive folder by id."""
    return f"{FOLDER_URL_PREFIX}{folder_id}"


def file_url_sql(file_id_expr: str) -> str:
    """`file_url` as a SQL expression over a column or expression holding
    the id, for the export that builds its table in the database rather
    than in Python (`export_duckdb.py`). Same two constants, so the two
    cannot drift."""
    return f"'{FILE_URL_PREFIX}' || {file_id_expr} || '{FILE_URL_SUFFIX}'"

FOLDER_ID = "1vKevmR1NSh3_9wnsYRMl0BA5os9oaoPT"
FOLDER_URL = f"{FOLDER_URL_PREFIX}{FOLDER_ID}"

# The per-site document tree inside the handover folder. Linking the root
# lands a reader among the workbook and the database with the documents
# one more click away; this opens the folders themselves.
SITES_FOLDER_ID = "1wSMSDEm8xhxXFtAmUPCO5VgBYtfhiJEW"
SITES_URL = f"{FOLDER_URL_PREFIX}{SITES_FOLDER_ID}"

# The operator snapshots, beside `sites` rather than inside it: they are
# a different evidence class — what an operator published about its own
# facilities, held because a marketing page has no register behind it —
# but the same promise. "Our copy" means Drive for a planning document,
# and a reporter should not have to learn that it means a git repository
# for the page a capacity claim rests on.
#
# Created 2026-09-01 by `scripts/sync_snapshots_drive.py --create-folder`,
# which prints the id for pasting here rather than writing it. That is
# deliberately two steps: creating a folder as a side effect of a sync is
# how the duplicate archive above happened, so it has to be asked for
# once, and this constant is what every later run addresses. The sync
# `files.get`s it before uploading and stops on a 404 — it never falls
# back to creating one.
SNAPSHOTS_FOLDER_ID = "1NqIVr0y1aITvgAmQahatM3E4aCpBThlG"
SNAPSHOTS_URL = f"{FOLDER_URL_PREFIX}{SNAPSHOTS_FOLDER_ID}"

# The adjacent-power schemes — substations, energy centres, standby
# fleets consented in their own right — beside `sites` rather than inside
# any site's folder, since issue #252 took the class out of site
# membership (2026-08-30) and the 2.11 staging build found 744 held
# documents with nowhere to go (2026-09-02). One folder per application,
# each with an `_index.md` naming the sites the scheme stands beside.
#
# Created by the sync itself as a child of the root, so the id was read
# back from the sync ledger (`SYNC_LEDGER`, key `<root>/adjacent_power`)
# on 2026-09-02 and pinned here the way `SITES_FOLDER_ID` is: the reader
# links the class as a whole, and a link is addressed by id, never by
# name.
ADJACENT_POWER_FOLDER_ID = "1uYTW6qRhekflqonDUHJj_ddSmRb1gQYX"
ADJACENT_POWER_URL = f"{FOLDER_URL_PREFIX}{ADJACENT_POWER_FOLDER_ID}"


# The sync ledger: every folder and file the sync has created on Drive,
# by path, so a re-run uploads only what changed and a rename reads as a
# rename. Five scripts read it — the sync, the workbook export, the id
# recorder, the sample verifier and the ledger rebuild — and until
# 2026-09-02 each spelled its path itself, relative to the working
# directory. From anywhere else the sync found no ledger and would have
# started from nothing, re-uploading the whole tree beside the copy
# already there: the duplicate-archive mechanism described above,
# reached by a different door. One constant, absolute.
#
# And one writer, one lock, one reader, since 2026-09-06. Under
# `drive.file` this file is the only record of what the sync created,
# and `Sync.save()` used to `write_text` it in place, outside the lock
# that guards the state it serialises: a kill mid-write left truncated
# JSON, and two workers could pass the checkpoint in one order and
# finish their writes in the other, so the file fell up to fifty
# entries behind memory until the next checkpoint — bounded, and
# costing anything only if the run died inside that window, since the
# final forced save writes the whole state; the torn write is the one
# any kill hits. `write_ledger` replaces the file
# atomically; `acquire_ledger_lock` refuses a second process rather
# than letting two mutable ledgers race; `read_ledger` refuses a
# corrupt one rather than starting from nothing beside it.
SYNC_LEDGER = EXPORTS / ".drive_sync_state.json"


def write_ledger(path, payload: str) -> None:
    """Replace the ledger with `payload` in one indivisible step.

    Written to a sibling under a temporary name, flushed and fsynced,
    then `os.replace`d — which either happens or does not, so a reader
    never sees a torn file and an interrupted write leaves the previous
    ledger exactly as it was. The same contract `export_duckdb`'s
    `.building` and the staging build's swap already keep; the ledger was
    the resume file in this repository that did not.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass  # the rename is durable on its own for our purposes


def read_ledger(path) -> dict:
    """The ledger as a dict, or the empty ledger if the file is absent.

    A file that exists and does not parse is refused with a message,
    never treated as absent: a sync that starts from nothing beside a
    corrupt ledger re-uploads the whole archive beside itself. The
    previous copy is what to restore; `scripts/rebuild_drive_ledger.py`
    is the route when there is none.
    """
    path = Path(path)
    if not path.exists():
        return {"folders": {}, "files": {}}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"the sync ledger at {path} is not valid JSON ({exc}); refusing "
            f"to start from nothing beside it, which would re-upload the "
            f"archive. Restore the last good copy, or rebuild it with "
            f"scripts/rebuild_drive_ledger.py") from exc


class LedgerLocked(SystemExit):
    """Another process holds the ledger."""


class LedgerLock:
    """An exclusive, inter-process lock on the ledger, held for the life
    of the process that took it.

    `Sync`'s `threading.RLock` guards its own workers; nothing guarded
    two `drive_sync.py` processes, which would each load the same
    snapshot into separate memory and let the last writer discard the
    other's whole run. Taken before any API call and never merged: a
    second sync is refused, with the holder's pid, and told to wait.
    """

    def __init__(self, path):
        self.path = Path(path).with_name(Path(path).name + ".lock")
        self._fd: int | None = None

    def acquire(self) -> LedgerLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = ""
            try:
                holder = os.read(fd, 64).decode("ascii", "replace").strip()
            except OSError:
                pass
            os.close(fd)
            raise LedgerLocked(
                f"another sync holds the ledger lock {self.path}"
                + (f" (pid {holder})" if holder else "")
                + "; refusing to run two syncs over one ledger — wait for "
                  "it to finish, or if it is dead, remove the lock file")
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def acquire_ledger_lock(path=None) -> LedgerLock:
    """Take the ledger lock for the rest of the process, or exit saying
    who holds it. Flock releases with the process, so a run that dies
    does not leave the next one locked out."""
    return LedgerLock(path or SYNC_LEDGER).acquire()


# Encrypted database backups (scripts/backup_db.py). Deliberately NOT a
# subfolder of the handover archive above: Drive sharing inherits
# downward, and a pg_dump is the raw schema — Barbour's role-block
# contact details, objectors' names and addresses from consultee
# responses, everything the exports redact. A subfolder of the folder the
# reporting team can read would hand them all of it. Separate folder,
# unshared, and the dumps are encrypted anyway so that a mis-share still
# leaks nothing.
BACKUP_FOLDER_ID = "12-X9peqr2rm6SRndV7Q75A5HSwRJaheM"
BACKUP_FOLDER_URL = f"{FOLDER_URL_PREFIX}{BACKUP_FOLDER_ID}"

# The workbook converted to a *native* Google Sheet, so it opens in a
# browser rather than downloading — and, unlike an .xlsx opened in Drive's
# Office compatibility mode, can be written by the Sheets API. The two
# look identical in a browser and share a /spreadsheets/d/ URL; only the
# native one has an API behind it, which is what scripts/sheet_sync.py
# needs to refresh the data without destroying the hand formatting. This is a *conversion*, not the file the
# pipeline writes: `dc_handover_phase1.xlsx` in the folder above is
# regenerated on every export, and the Sheet does not follow it. Re-import
# after a regeneration that matters, or the two will drift.
#
# A release that introduces TABS needs a new Sheet, not a refresh.
# sheet_sync.py writes into an existing Sheet and cannot add tabs — that
# restraint is deliberate, since a tab it created would arrive
# unformatted and be reformatted by hand after every release. So the
# rule has held twice: 2.2 introduced four tabs (Capacity claims,
# Operator disclosure, Figures by audience, External aggregates), and
# 2.8 introduced two (Parties, Cohorts). Refreshing in place would have
# left each of those releases silently out of the Sheet.
#
# 2.8 was a replacement for a second reason worth recording. The live
# Sheet was still 2.2, five releases stale, so a refresh meant 17 column
# edits on Sites in one batch — three deletions among them — against a
# 75-column tab. A misplaced insert leaves formatting describing the
# wrong data, which is the failure sheet_sync exists to prevent and the
# one nobody notices. A replacement has no reconciliation to get wrong.
# Nothing was annotated, so the refresh's only advantage did not apply.
#
# scripts/create_workbook_sheet.py makes the replacement; every previous
# Sheet is left where it is, so a citation of an older one keeps
# resolving.
WORKBOOK_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1jCMg1jrmQbFiAOObPrZmHaHVWHRzTBOy_ES3B2B63-M/edit")

# The Sheet 2.2 was published as, kept so its citations keep resolving.
WORKBOOK_SHEET_URL_PHASE22 = (
    "https://docs.google.com/spreadsheets/d/"
    "1KBhBD4vv-R24p2WaCCBlQH3hWZEndbSIqdyi3XYmVUQ/edit")

# The Sheet 2.1 was published as, kept so its citations keep resolving.
WORKBOOK_SHEET_URL_PHASE21 = (
    "https://docs.google.com/spreadsheets/d/"
    "18WB-yRWxOa3IRNQLIR4nOsKMKCQ4WsCA83Je73CUpdw"
    "/edit?gid=1246662960#gid=1246662960")

# Superseded releases. Phase 1's artefacts were moved here by hand when
# phase 2 was built, so the handover folder shows the current release
# only. Recorded because their absence from the root looks like a failed
# upload otherwise, and because it is the reason `drive_sync.py --prune`
# refuses to touch files at the tree root: those files have no local
# counterpart any more, which to a path-based prune is indistinguishable
# from a rename, and binning them would destroy the published phase 1.
#
# Treat it as where phase 1 lives, not as a guarantee of what is in it:
# on 2026-08-11 the workbook had been left in a different folder and Luke
# was tidying it back. Either way both artefacts keep their file ids, so
# a citation resolves wherever the file has been filed.
PHASE1_ARCHIVE_FOLDER_ID = "1udCAR_bD5ghLO4qJOBThXqmSPSlzb3wT"
PHASE1_ARCHIVE_URL = (
    f"{FOLDER_URL_PREFIX}{PHASE1_ARCHIVE_FOLDER_ID}")

# The Gemini Notebook, built by hand from scripts/export_notebook_bundle.py
# — one document per **datacentre-classed** site (the default since 2.10;
# `--classes all` puts the other classes back), the site report with that
# site's findings tabulated beneath it. The disguise suspects, the
# procedural-only and adjacent-power sites and the no-planning-record
# rows are on Drive, in Pinpoint, in the workbook and in the reader, and
# not in the notebook.
#
# **New notebook for 2.10, created empty by Luke on 2026-08-28.** A
# notebook's URL is fixed at creation and does not change as sources are
# added, so it is made and recorded here before the chain runs; the
# sources follow once step 9 has rebuilt the staging tree the bundle is
# welded from. Its predecessor (91c4227e-…) holds the bundle uploaded on
# 2026-08-11 and is superseded, not deleted — the saved notes in it were
# out of date, which is why a fresh notebook was preferred to adding to
# that one.
#
# **It is empty until the bundle is uploaded.** Until then the reader
# links somewhere emptier than the page implies. That is the honest
# failure of the two — an empty notebook announces itself, where a stale
# one reads as current — but the upload still belongs before deployment.
#
# Not written by any script and not refreshed by the release chain: the
# upload is manual, so the notebook holds whichever bundle was last
# uploaded and does not follow a regeneration. Re-upload after a rebuild
# that matters, the same caveat as the Sheet above.
NOTEBOOK_URL = (
    "https://notebook.google.com/notebook/"
    "64207c7d-b53f-4128-b0b9-9accdd232684")

# The Pinpoint collection, built by hand from
# scripts/export_pinpoint_bundle.py — the planning application documents
# themselves, flattened and recompressed to fit the 100GB quota, for
# full-text search across the corpus (Luke, 2026-08-12).
#
# Same manual-upload caveat as the Sheet and the notebook above: nothing
# in the release chain refreshes it, so it holds whichever bundle was last
# uploaded.
#
# It is a search index, not the archive of record. Drive keeps the
# originals at full resolution; the bundle drops drawings and exact
# duplicates and recompresses PDFs, and `_manifest.csv` maps every file in
# it back to its staging path, site, application and content hash.
PINPOINT_URL = (
    "https://journaliststudio.google.com/pinpoint/search"
    "?collection=d38a75e5577d57bc")
