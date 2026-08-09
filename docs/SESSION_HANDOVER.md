# Session handover — 2026-08-09 evening

For whoever picks this up next. Written at the end of the day the Phase 1
handover was published, with acquisition running again overnight.

Read [ROADMAP.md](../ROADMAP.md) for what is outstanding and
[HISTORY.md](../HISTORY.md) for why things are the way they are. This
document covers only what is *in flight* and what is easy to get wrong.

---

## What is running right now

Two background jobs, plus a chain waiting on both.

| Job | What it is | Log |
|---|---|---|
| `fetch_outstanding.py` | 108 applications across Idox, Arcus, Agile, Ocella | `logs/phase2_acquisition.log` |
| `drive_sync.py` | repairing the document tree after a duplicate archive was found | `data/drive_sync.log` |
| `phase1_finalise.sh` | **waits for both**, then rebuilds everything once | `logs/phase1_finalise.log` |

`phase1_finalise.sh` re-stamps the corpus boundary, regenerates workbook,
DuckDB and reader, rebuilds the Drive staging tree, syncs it, and updates
the Google Sheet. It deliberately stops before the PR that deploys
`index.html`.

**First thing to check:** whether the chain has run, and what it said.

```bash
cat logs/phase1_finalise.log
pgrep -fl "fetch_outstanding|drive_sync|phase1_finalise"
```

If the chain completed, `index.html` will have changed and needs a branch
and PR to reach the deployment.

---

## Verify these before trusting them

Three claims made today turned out to be wrong when checked at the far
end. Do not take the near side as evidence.

**The Drive repair.** A second archive existed at My Drive root
(`1UxxGmbiEI-9lR8DPJnEzonBj6OR6OpQe`) because the sync had once resolved
its destination by *name*; today's uploads went into it rather than the
folder the reader links to. The ledger was purged of that tree and the
sync re-run. **Confirm by sampling files' actual parents through the API,
not by reading the counters** — a sample of ten found half in the wrong
tree last time, and the counters looked fine. Only then delete the
duplicate, which is Luke's call, not ours.

**The password gate.** Every path must redirect unauthenticated,
including `//index.html`, `///index.html`, `/%2findex.html` and
traversal forms. A double slash bypassed the matcher earlier today and
served the whole 7 MB dataset with a 200; nothing about that was visible
from a browser with a session. Probe from outside, with no cookie.

**Anything about Drive, Pages or the deployment.** Check the endpoint,
not the local directory or the repo.

---

## The three phases

**Phase 1 — nearly closed.** The handover is published behind the gate.
Remaining: the chain above, the Drive verification, a gate re-probe, and
16 bad-chunk documents plus 7 sites with unread documents.

**Phase 2 — collecting, then reading.** The acquisition tail is analysed
in the roadmap: 20 applications reachable headlessly across eleven
unrelated portals (poor value), against 31 that route through the
already-working browser tooling (good value, needs Luke at the keyboard).
Then deep-read the remaining two thirds of the corpus — the Anthropic
budget is spent, so this is planned on OpenAI credits.

**Phase 3 — the second opinion.** A subset is dual-read; the comparison
across the corpus is the deliverable, and disagreements are findings
rather than errors to resolve.

---

## The Mac Studio

It runs the local MLX deep-read and is the machine for long reads — it
never overheats and stays usable while working. Connection details,
start/stop, and how to tell a live reader from a stale log are in
[MAC_STUDIO.md](MAC_STUDIO.md). The short version: user `hoyla`, host
`192.168.50.113`, and `pgrep -f deepread_run` lies because it matches a
leftover `tail -f`.

**Postgres is on the laptop, and stays there through Phase 2** — the
laptop is doing the downloading, ingesting and API deep-reads, so the
database belongs with the active work. The Studio only runs the Phase 3
corroboration read. Move the database to the Studio *after* Phase 2, when
the laptop's role shrinks to editing and publishing.

## Things that will bite

**Drive is addressed by ID, never by name.** `dcp/drive.py` holds it.
Passing `--dest "DC Planning Dataset"` is how the duplicate archive was
created — the `drive.file` scope cannot see a folder it did not create,
so the lookup silently makes a new one.

**Push rules, enforced by `.githooks/pre-push`:** no PR or draft, push
freely; ready for review, ask first; merged, never. Enable with `git
config core.hooksPath .githooks` in a fresh clone.

**The Google Sheet is a conversion, not the workbook.**
`scripts/sheet_sync.py` refreshes its values in place so the hand
formatting survives; it must be a *native* Sheet, not an `.xlsx` opened
in Drive's Office mode, which looks identical and has no API behind it.

**The corpus boundary moved on purpose.** `phase1_snapshot.json` records
both the original 08:50 cutoff and the one that supersedes it. The
analysed percentage will read *lower* after the chain runs, because
acquisition enlarged the denominator while deep-read stayed paused. That
is expected and Luke has accepted it explicitly; say so on the front page
rather than letting it look like regression.

**Historical partial fetches are not measurable.** A short fetch used to
be recorded as complete. New ones are caught and re-queued, but the
manifests record what was stored, not what was offered, so past ones can
only be found by re-listing. **Do that before anyone quotes per-site
document counts.**

---

## How Luke works

He is a journalist who has spent three decades on newsroom software, on
the product and UX side, and he is unusually good at finding bugs by
opening the thing and poking it. Four of today's fixes were visibly
broken features that no amount of rereading the code would have caught.

He wants pushback, not agreement. If an idea is bad, say so and say why.
If he is right for the wrong reason, tell him that too. Cheap flattery
costs trust.

**When he corrects something, build the durable form of the fix** — a
default, a constant, a hook, a test — rather than resolving to remember.
Two instructions were in memory, were repeated, and were broken anyway
today; both are now enforced in code. He noticed the pattern before I
did, and he was right to ask whether the session had gone stale.

Keep the local file as the review loop: `open index.html`, he refreshes.
Batch changes into one PR rather than churning a 7 MB file per tweak.
