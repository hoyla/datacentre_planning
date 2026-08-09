# The Mac Studio deep-read

The Studio (M1 Max, `36261`) runs the local MLX deep-read. It is the
machine to use for long reads: it never gets near thermal limits, stays
usable for other work while reading, and can be left for days. The
laptop is faster per document and overheats, so it is for bursts only.

Written down because it was not, and an evening was spent rediscovering
it from a session transcript.

## Connecting

| | |
|---|---|
| Host | `192.168.50.113` (LAN only; no Tailscale) |
| User | **`hoyla`** — *not* `luke_hoyland`, which is the laptop's user |
| Repo | `~/Code/datacentre_planning` |
| Log | `data/deepread_run.log` in that directory |
| Key | `~/.ssh/id_ed25519` on the laptop, already authorised |

Remote login has to be enabled in the Studio's Sharing settings. If the
key stops working, that is the first thing to check.

```sh
ssh hoyla@192.168.50.113 'scutil --get ComputerName'
```

## Starting a read

`HF_HUB_OFFLINE=1` matters: without it MLX tries to reach Hugging Face
and stalls if the network is unhappy.

```sh
ssh hoyla@192.168.50.113 'cd Code/datacentre_planning &&
  HF_HUB_OFFLINE=1 nohup .venv/bin/python -u scripts/deepread_run.py \
    >> data/deepread_run.log 2>&1 &'
```

Add `--shard 1/2` **only if the laptop is reading at the same time**
(it takes `0/2`). With one machine reading, no shard flag means it works
the whole cohort. Resume is automatic either way: `deepread_log` is the
contract, so nothing is read twice.

## Checking it is actually running

Both of these, not one:

```sh
ssh hoyla@192.168.50.113 '
  ps -Ao pid,command | grep "[d]eepread_run.py" | grep python
  stat -f "%Sm" -t "%H:%M:%S" Code/datacentre_planning/data/deepread_run.log
  date "+%H:%M:%S now"'
```

**`pgrep -f deepread_run` is not sufficient** — it matches a leftover
`tail -f` on the log file and reports a dead reader as alive. That
mistake was made, and the stale tail of a finished log read exactly like
live progress. Check for a *python* process, and check the log's mtime
is recent.

The authoritative check is the database, since a reader that cannot write
is not reading:

```sql
SELECT max(completed_at), now() - max(completed_at) FROM deepread_log;
```

## Stopping

```sh
ssh hoyla@192.168.50.113 'pkill -TERM -f "scripts/deepread_run.py"'
```

`TERM` lets the current document finish and its row commit. Only escalate
to `-9` if it is still there after a minute.

## The laptop dependency, and how to remove it

**Postgres lives on the laptop**, in Docker, at `192.168.50.213:5433`.
The Studio's `.env` points there. So the Studio only reads while the
laptop is awake and on the same network — closing the lid stalls it, and
taking the laptop to work stops it entirely.

Nothing is corrupted when that happens: the connection drops, the run
dies, and the next start resumes from `deepread_log`. But it does mean
the Studio idles exactly when it would otherwise be most useful.

**Do not move Postgres yet.** It looks like the obvious fix, and it is
the eventual one, but the sequencing matters: through Phase 2 the laptop
is doing the downloading, the ingesting and the API deep-reads, so the
database belongs where that work is. The Studio is only running the
Phase 3 corroboration read, which is the *least* urgent thing depending
on it. Moving the database now would put the active work across a network
hop to serve the background job.

**After Phase 2 completes, move it to the Studio.** By then the laptop's
role shrinks to editing and publishing, the Studio becomes the machine
that matters, and the dependency is the right way round. A `pg_dump`,
a restore, and an `.env` change on both machines.

**A local spool is the alternative** if the interruptions become
intolerable before then: the reader writes findings and log rows to a
file when the database is unreachable and a catch-up command replays
them. Real work, though — the replay has to be idempotent against the
same unique constraints, and a spool that silently diverges from the
database is worse than a reader that stops honestly.

Until one of those happens, the honest operating rule is: **start the
Studio read when the laptop is home and awake, and expect it to stop when
the laptop leaves.** `caffeinate -s` on the laptop holds sleep off; `-w
<pid>` releases it when a given job finishes.

## Reading the log correctly

The runner writes a line only when a document *completes*, so a log that
has not moved for several minutes usually means one long document under
inference, not a stall. MLX runs on the GPU, so low CPU is normal while
it generates; what tells you it is alive is ~29% of memory resident (the
35B model) and a live connection to the database.

When in doubt, ask the database rather than the log:

```sql
SELECT max(completed_at), now() - max(completed_at) FROM deepread_log;
```

That is the only check that distinguishes working from wedged.

## Keeping the code in step

The Studio's checkout drifts. As of 2026-08-09 it was on branch
`deepread-run`, 63 commits behind `main`, with local edits — which is how
a run failed on `--prompt-version`, a flag the deployed copy did not yet
have.

Before a long read, bring it up to date:

```sh
ssh hoyla@192.168.50.113 'cd Code/datacentre_planning &&
  git stash -u && git checkout main && git pull --ff-only'
```

`rsync` of a single script works in a pinch and was used once, but it
leaves the checkout inconsistent with itself. Prefer the pull.
