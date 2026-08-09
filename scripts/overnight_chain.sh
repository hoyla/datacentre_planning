#!/usr/bin/env bash
# Overnight: wait for acquisition to go quiet, ingest what the browser
# harvested, rebuild the Drive staging tree, and sync it.
#
# The destination folder ID is hard-coded on purpose. A previous run was
# started without --dest-id and drive_sync, doing as it was told, created
# a second "DC Planning Dataset" folder by name instead of writing into
# the one that already held the material. Passing the ID is the whole
# difference between adding to the shared archive and forking it, so it
# is not a parameter here and the run aborts if a write probe against it
# fails.
set -u
cd "$(dirname "$0")/.."

DEST_ID="1vKevmR1NSh3_9wnsYRMl0BA5os9oaoPT"   # folder Luke shared; matches existing ledger root
PY=.venv/bin/python
LOG=logs/overnight_$(date +%Y%m%d_%H%M).log
mkdir -p logs
exec >>"$LOG" 2>&1

say() { echo "[$(date +%H:%M:%S)] $*"; }

say "=== overnight chain starting ==="
say "destination folder ID: $DEST_ID"

# 1. Wait for the fetchers. Quiet means: no campaign, no salesforce, no
#    agile/arcus process, and the browser harvest directory unchanged for
#    two consecutive checks (the browser job writes continuously while
#    working, so a still directory is the only signal it is done).
prev_count=-1
for i in $(seq 1 240); do          # up to ~8 hours at 2 min
  running=0
  for p in fetch_dc_campaign fetch_salesforce fetch_agile_arcus fetch_aifusion; do
    pgrep -f "$p" >/dev/null && running=1
  done
  count=$(ls data/raw/browser_harvest 2>/dev/null | wc -l | tr -d ' ')
  if [ "$running" -eq 0 ] && [ "$count" = "$prev_count" ]; then
    say "acquisition quiet (harvest steady at $count files)"; break
  fi
  [ $((i % 15)) -eq 0 ] && say "waiting: fetchers_running=$running harvest_files=$count"
  prev_count=$count
  sleep 120
done

# 2. Browser-harvested documents into the corpus.
say "--- ingesting browser harvest ---"
$PY scripts/ingest_browser_harvest.py || say "WARN: harvest ingest returned $?"

# 3. Corpus size before/after is the honest measure of what the night did.
BEFORE=$($PY -c "
from dotenv import load_dotenv; load_dotenv('.env')
from dcp.db import connect
with connect() as c, c.cursor() as cur:
    cur.execute('SELECT count(*) FROM documents'); print(cur.fetchone()[0])")
say "documents in corpus: $BEFORE"

# 4. Confirm we can still write to the intended folder before building
#    anything. If the token or the folder is wrong, stop here rather than
#    discover it after an hour of staging.
say "--- probing Drive destination ---"
if ! $PY scripts/drive_sync.py --probe-id "$DEST_ID"; then
  say "ABORT: cannot write to $DEST_ID — no sync attempted"
  exit 1
fi

# 5. Rebuild the staging tree, then sync it INTO the shared folder by ID.
say "--- rebuilding Drive staging ---"
$PY scripts/build_drive_staging.py || { say "ABORT: staging build failed"; exit 1; }

say "--- syncing to Drive (by ID, never by name) ---"
$PY scripts/drive_sync.py --sync data/exports/drive_staging --dest-id "$DEST_ID"
say "sync exit: $?"

say "=== overnight chain finished ==="
