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

# The workbook converted to a Google Sheet, so it opens in a browser
# rather than downloading. This is a *conversion*, not the file the
# pipeline writes: `dc_handover_phase1.xlsx` in the folder above is
# regenerated on every export, and the Sheet does not follow it. Re-import
# after a regeneration that matters, or the two will drift.
WORKBOOK_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "174dkicvGxfjWgbD7Swnu9zWLmtF6UcTw/edit?gid=1246662960#gid=1246662960")
