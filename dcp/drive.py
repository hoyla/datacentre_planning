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
WORKBOOK_SHEET_URL = (
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
# tabulated beneath it. Shared with the reporting team (Luke, 2026-08-11).
#
# Not written by any script and not refreshed by the release chain: the
# upload is manual, so the notebook holds whichever bundle was last
# uploaded and does not follow a regeneration. Re-upload after a rebuild
# that matters, the same caveat as the Sheet above.
NOTEBOOK_URL = (
    "https://notebook.google.com/notebook/"
    "91c4227e-7625-452d-8def-4fd6a667aabe")
