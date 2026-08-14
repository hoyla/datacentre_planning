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
  HF_HUB_OFFLINE=1 nohup .venv/bin/python -u scripts/deepread_run.py --tier A,B \
    >> data/deepread_run.log 2>&1 &'
```

**`--tier` is not optional.** Without it the cohort is the entire
corpus: on 2026-08-11 a restart from the bare command above picked up
43,020 documents (`A:2508, B:29348, C:1253, sampled_out:4204,
skip:5707`) instead of the 2,508 tier-A documents outstanding — about
107 hours of reading in place of six, on the wrong material.

Omitting it is worse than slow, which was not understood when the above
was written. Tier C is sampled 1-in-5, and `load_cohort` plans that
sample *after* filtering to unread documents, so the fifth an unscoped
run reads is not the fifth the global policy chose — see
`universe_plan` in `dcp/deepread_select.py`, which exists to fix exactly
this and which the runner does not yet use. Naming the tiers keeps the
runner away from it, because sampling only ever touches tier C.

**As of 2026-08-14 the scope is `--tier A,B`.** The flag takes a list.
Tier B is the outstanding bulk; tier A stays named so that prose
arriving later — a new Environmental Statement is tier A — is picked up
by the next start. A is read first regardless of the order given.

**Check the cohort line before walking away.** The first thing the run
prints says exactly what it is about to do, and the tier breakdown is
the tell:

```
deep-read cohort: 29338 documents pending (A:5, B:29333) — model mlx:Qwen3.6-…
```

Tiers you did not ask for mean the flag did not take. `C:` or
`sampled_out:` in that line is the whole corpus, and not what was
wanted.

**Expect about 320 hours.** Measured 2026-08-14 from the 1,033 tier-B
documents already read: a blended 39.2s each, so 29,338 is a fortnight
of continuous reading. `--shard` across both machines halves it. The
blend is worth knowing — 4.1% of tier-B documents end `parse_failed`,
and they take 42.7% of the time (411s mean against 23s for a clean
read), so roughly a third of the fortnight buys the class of document
that `docs/` already records as the worst for quote-gate rejection.

Add `--shard 1/2` **only if the laptop is reading at the same time**
(it takes `0/2`). With one machine reading, no shard flag means it works
the whole cohort. Resume is automatic either way: `deepread_log` is the
contract, so nothing is read twice.

## If the laptop will be away

The database lives on the laptop, so the Studio cannot write while it is
asleep or off the network. Since 2026-08-11 that no longer costs
anything: the run detects the outage, keeps reading, and spools verified
findings to `data/deepread_spool.jsonl`, draining them when the database
comes back and again at startup.

One gap in that was measured on 2026-08-12 and closed the same day. The
document *being read* when an outage began was still re-read from
scratch, because the connection was opened before the read and held
across it, so the failure surfaced at commit — two outages that day cost
696s and 576s of Studio time on documents already read and already
verified. The connection is now opened after the read, so the retry
ladder retries the write.

Nothing needs doing — but if a run ends with

```
WARNING: database still unreachable — N documents remain in …spool.jsonl
```

then those N are read and verified and *not yet stored*. Re-run once the
laptop is back and they are written before anything else happens.

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

`TERM` lets the current document finish and its row commit, then drains or
reports the spool before exiting. **This became true on 2026-08-12**; the
sentence had been here since before anything implemented it. There was no
handler, so TERM took Python's default disposition and killed the process
where it stood — nothing corrupted, because findings stay uncommitted
until the `deepread_log` row lands, but a document up to 86 minutes in was
thrown away by the documented way of stopping.

Three levels, in order of what they cost:

| | |
|---|---|
| `pkill -TERM` | finishes the current document, then stops |
| `pkill -INT` | abandons the current document, still lands the spool |
| `pkill -9` | immediate; the spool stays on disk for the next start |

**Do not escalate to `-9` after a minute.** The old instruction to do so
predates TERM working, and following it now throws away exactly what the
graceful stop was preserving — a large Environmental Statement can
legitimately take over an hour. Acknowledgement of the signal is itself
delayed until the current *chunk* of generation finishes, because MLX
generates inside a C call and Python runs handlers between bytecodes, so
several minutes of apparent silence after a TERM is normal. Watch the log
for `stop requested`, and if you genuinely cannot wait, use `-INT`.

Nothing is lost at any of the three levels: a killed run's spool is
drained by the next start, before the cohort is selected.

## The laptop dependency, and how to remove it

**Postgres lives on the laptop**, in Docker, at `192.168.50.213:5433`.
The Studio's `.env` points there. So the Studio only reads while the
laptop is awake and on the same network — closing the lid stalls it, and
taking the laptop to work stops it entirely.

That no longer stops the read — see *If the laptop will be away* above:
the run goes offline, keeps reading and spools. What the dependency still
costs is visibility, since nothing is queryable until the laptop returns.

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

**The local spool was the alternative, and it is what got built** (PR #50,
2026-08-11, extended 2026-08-12), which is why the move is no longer
urgent. It is not a substitute for it: a spool keeps the Studio reading
but leaves the results unqueryable until the laptop is back, so a long
absence still delays every count, export and adjudication that depends on
them.

The operating rule is now: **start the read whenever the Studio is free,
and expect the results to appear when the laptop next comes home.**
`caffeinate -s` on the laptop holds sleep off if you want the writes to
land as they happen; `-w <pid>` releases it when a given job finishes.

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
