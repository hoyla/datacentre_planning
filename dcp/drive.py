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

FOLDER_ID = "1vKevmR1NSh3_9wnsYRMl0BA5os9oaoPT"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}"

# The per-site document tree inside the handover folder. Linking the root
# lands a reader among the workbook and the database with the documents
# one more click away; this opens the folders themselves.
SITES_FOLDER_ID = "1wSMSDEm8xhxXFtAmUPCO5VgBYtfhiJEW"
SITES_URL = f"https://drive.google.com/drive/folders/{SITES_FOLDER_ID}"

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
SNAPSHOTS_URL = f"https://drive.google.com/drive/folders/{SNAPSHOTS_FOLDER_ID}"


def file_url(file_id: str) -> str:
    """The viewer URL for a Drive file id.

    One shape, in one place. `export_handover.py` and `export_duckdb.py`
    each still build this string themselves; folding those in is their
    own change rather than this one's.
    """
    return f"https://drive.google.com/file/d/{file_id}/view"

# Encrypted database backups (scripts/backup_db.py). Deliberately NOT a
# subfolder of the handover archive above: Drive sharing inherits
# downward, and a pg_dump is the raw schema — Barbour's role-block
# contact details, objectors' names and addresses from consultee
# responses, everything the exports redact. A subfolder of the folder the
# reporting team can read would hand them all of it. Separate folder,
# unshared, and the dumps are encrypted anyway so that a mis-share still
# leaks nothing.
BACKUP_FOLDER_ID = "12-X9peqr2rm6SRndV7Q75A5HSwRJaheM"
BACKUP_FOLDER_URL = f"https://drive.google.com/drive/folders/{BACKUP_FOLDER_ID}"

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
    f"https://drive.google.com/drive/folders/{PHASE1_ARCHIVE_FOLDER_ID}")

# The Gemini Notebook, built by hand from scripts/export_notebook_bundle.py
# — one document per site, the site report with that site's findings
# tabulated beneath it.
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
