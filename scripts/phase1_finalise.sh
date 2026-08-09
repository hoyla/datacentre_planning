#!/bin/sh
# Wait for acquisition and the Drive repair, then rebuild Phase 1 once.
#
# The 08:50 boundary was a device for getting a handover out the same day.
# Acquisition has since restarted deliberately, so the release is stamped
# when the collecting actually stops instead — one regeneration against
# one boundary, rather than a series of artefacts each true for an hour.
#
# Order matters. The snapshot is stamped first so it records the corpus
# the exports are about to read; the staging tree is rebuilt before the
# sync so the sync has something current to send; the Sheet goes last
# because it reads the workbook file.
#
# Everything here is idempotent, so a re-run after a failure is safe.
#
#     nohup scripts/phase1_finalise.sh > logs/phase1_finalise.log 2>&1 &

set -u
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
RELEASE=data/exports/phase1_build

say() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
step() { say "$1"; shift; "$@" || { say "FAILED: $*"; exit 1; }; }

say "waiting for acquisition and the Drive sync to finish"
while pgrep -f fetch_outstanding >/dev/null || pgrep -f drive_sync.py >/dev/null; do
  sleep 60
done
say "both finished"

say "re-stamping the Phase 1 boundary"
$PY - <<'PYEOF' || exit 1
import json, sys, datetime as dt
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(".env"))
sys.path.insert(0, ".")
from dcp import db

out = Path("data/exports/phase1_snapshot.json")
prev = json.loads(out.read_text()) if out.exists() else {}
with db.connect() as c, c.cursor() as cur:
    cur.execute("SELECT count(*), max(id) FROM documents")
    docs, max_id = cur.fetchone()
    cur.execute("""SELECT count(DISTINCT document_id) FROM deepread_log
                   WHERE read_state='read'""")
    read, = cur.fetchone()
    cur.execute("SELECT count(*) FROM applications")
    apps, = cur.fetchone()
snap = {
    "phase": 1,
    "cutoff_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "documents": docs, "max_document_id": max_id,
    "documents_analysed": read, "applications": apps,
    # The first boundary is kept rather than overwritten: it is what the
    # earlier artefacts described, and the record of why this one moved.
    "supersedes": {k: prev.get(k) for k in
                   ("cutoff_utc", "documents", "max_document_id",
                    "documents_analysed")} if prev else None,
    "note": ("Acquisition was restarted after the first boundary, so the "
             "release is stamped when collecting stopped. Deep-read stayed "
             "paused throughout: documents acquired after the first "
             "boundary are held and unread, which lowers the analysed "
             "percentage without any reading having been lost."),
}
out.write_text(json.dumps(snap, indent=2) + "\n")
prevdocs = (prev or {}).get("documents")
print(f"  {docs:,} documents ({read:,} analysed)"
      + (f", was {prevdocs:,}" if prevdocs else ""))
PYEOF

step "workbook"  $PY scripts/export_handover.py --out $RELEASE/dc_handover_phase1.xlsx
step "database"  $PY scripts/export_duckdb.py --out $RELEASE/dc_phase1.duckdb
step "reader"    $PY scripts/export_reader.py --out $RELEASE/reader.html --publish index.html
step "drive staging" $PY scripts/build_drive_staging.py
step "drive sync"    $PY -u scripts/drive_sync.py --sync data/exports/drive_staging
step "google sheet"  $PY scripts/sheet_sync.py

say "done — index.html has changed and needs a PR to deploy"
git --no-pager status --short index.html
