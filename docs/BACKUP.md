# Backups

The document corpus is mostly re-fetchable. The database is not.

454,000 findings behind a verbatim-quote gate, the power adjudications,
the append-only `source_snapshots` audit trail, the deep-read log and
every site cluster are three months of work, and until 2026-08-10 they
existed in exactly one place: a Docker volume on one laptop. Re-fetching
would not restore them either — portals have moved, PlanIt now rate
limits far harder than in May, and the interpretive layer would have to
be recomputed from scratch at the cost of the API budget that produced
it.

## Running one

```bash
export DCP_BACKUP_PASSPHRASE='…'
.venv/bin/python scripts/backup_db.py
```

Dumps, encrypts, verifies, uploads to Drive, prunes old local copies.
About 100 MB and under a minute. Safe to run while a deep-read is in
progress — `pg_dump` takes an MVCC-consistent snapshot and blocks
nothing.

| Command | What it does |
|---|---|
| `backup_db.py` | The whole cycle: dump → verify → upload → prune local |
| `backup_db.py --no-upload` | Local only |
| `backup_db.py --list` | What exists, here and on Drive, and how stale the newest off-site copy is |
| `backup_db.py --verify-only FILE` | Prove one archive decrypts and parses |
| `backup_db.py --restore-test FILE` | **The rehearsal.** Restore into a scratch database and compare row counts against live |
| `backup_db.py --create-folder` | One-off: mint the Drive folder and print its ID to pin |

## The passphrase

Symmetric AES256, from `DCP_BACKUP_PASSPHRASE`, never in the repository
and never in argv (it travels on its own file descriptor, because argv
is world-readable in `ps`).

**Keep it in a password manager. Nothing here can recover it, and a
backup you cannot decrypt is not a backup.** If it is ever lost, the
answer is to take a fresh backup under a new passphrase immediately —
the old archives become landfill the moment the passphrase does.

Encryption is not decoration. A `pg_dump` is the raw schema, and the raw
schema holds what every export redacts: Barbour's role-block contact
details (held under the Guardian editorial code) and objectors' names
and addresses from consultee responses. Encrypted, the Drive folder's
permissions stop being the only thing between that material and a
mis-share.

## Where they go

`data/backups/` locally (gitignored), and a **separate, unshared Drive
folder** — `dcp.drive.BACKUP_FOLDER_ID`, never a subfolder of the
handover archive. Drive sharing inherits downward: a subfolder of the
folder the reporting team reads is a folder the reporting team reads.

Pinned by ID, for the reason recorded in [dcp/drive.py](../dcp/drive.py):
under the `drive.file` scope a name lookup cannot see a folder it did
not create, so resolving by name silently makes a second one. That
already happened once, to the document archive.

## Retention

Every run writes a new timestamped file; nothing is ever overwritten. A
backup that overwrites will one day faithfully copy a corrupt database
over the last good copy of a healthy one.

Local copies are pruned to the most recent 14. **Drive keeps every
copy** — pruning the off-site copy is the one action here that can lose
data, so it is never automatic. At ~100 MB a run, a daily schedule is
about 3 GB a year; tidy it by hand when it matters.

## Verification, and why it has two halves

`--verify-only` decrypts the archive twice on purpose.

The first pass decrypts the whole file to nowhere, so gpg reads every
byte and runs its AES256 integrity check. The second parses the table of
contents with `pg_restore --list`.

That order exists because the obvious single check is wrong, and was
wrong here first. `pg_restore --list` reads only the table of contents,
which lives at the *start* of a custom-format dump — truncate the file
to 40% and it still cheerfully lists all eighteen tables, because the
catalogue is intact and the data is gone. It is this project's own
recurring bug wearing a backup's clothes: a listing that proves the
listing exists. What catches truncation is gpg's integrity check, and
only if someone reads its return code, which the first version of this
script did not.

Tested against four cases — intact, wrong passphrase, truncated,
single bit flipped mid-file. The last three all fail loudly and exit
non-zero.

**Verify is still the near side.** It proves the ciphertext is whole and
the catalogue parses; it does not prove the rows are in there.
`--restore-test` is the far side: it restores into a scratch database
(`dcp_restore_check`, dropped afterwards) and compares row counts
against live. Backup counts may be *lower* than live — a deep-read runs
for days — but never higher and never zero. Run it monthly, and after
any change to this script.

## The scheduled job

A launchd agent runs the cycle daily at 03:00, logging to
`logs/backup.log`:

```bash
cp scripts/launchd/com.dcp.backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dcp.backup.plist
```

The passphrase reaches it from `~/.config/datacentre_planning/backup.env`
(mode 600), which is the one file that must exist outside the repository
for the schedule to work. If the laptop is asleep at 03:00 the run is
skipped, not queued — so check `--list` occasionally. It prints how old
the newest off-site copy is and flags anything over two days.

## Restoring

```bash
gpg --decrypt data/backups/dcp_<stamp>.dump.gpg > /tmp/dcp.dump
docker exec -i datacentre_planning-postgres-1 \
    createdb -U dcp dcp_restored
docker exec -i datacentre_planning-postgres-1 \
    pg_restore -U dcp -d dcp_restored --no-owner --no-privileges < /tmp/dcp.dump
```

Restore beside the live database, not over it, and point `DATABASE_URL`
at the restored copy once you have looked at it. Overwriting the live
database is the one step no runbook should make easy.

`pg_dump` runs **inside the Postgres container**, deliberately: it must
be at least the server's major version, and the host's Homebrew
`pg_dump` is 14 against a 16 server, which refuses outright. Taking both
dump and restore from the container means the versions cannot drift.

## What is not backed up

- **`data/raw/` — the ~70 GB document corpus.** Roughly 50,000 of those
  documents are on Drive already through the per-site staging tree, and
  the rest are re-fetchable, if slowly. A full mirror is a separate
  decision (Zenodo is the candidate on the roadmap).
- **`data/raw_text/` — the extracted text caches.** Rebuildable from the
  documents by `scripts/extract_text_corpus.py`, at a few hours of CPU
  and no API spend.
- **The Drive tree itself.** It is a copy, not an original.
