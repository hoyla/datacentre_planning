# Session handover — 2026-08-09 evening

For whoever picks this up next. Written at the end of the day the Phase 1
handover was published, with acquisition running again overnight.

Read [ROADMAP.md](../ROADMAP.md) for what is outstanding and
[HISTORY.md](../HISTORY.md) for why things are the way they are. This
document covers only what is *in flight* and what is easy to get wrong.

---

## What is running right now

| Job | Where | What it is | Log |
|---|---|---|---|
| `extract_text_corpus.py` | laptop | text-extracting ~26,800 documents that have no cache | `logs/extract_corpus.log` |
| `deepread_run.py` | **Studio** | Qwen corroboration read, cohort now 45,309 | `data/deepread_run.log` on the Studio |
| `caffeinate` | laptop | holding sleep off | — |

Acquisition and the Drive repair both finished overnight, and
`phase1_finalise.sh` ran to completion: the boundary was re-stamped at
22:42 UTC with 55,678 documents, all artefacts regenerated, Drive synced,
the Sheet refreshed. **Phase 1 is published and closed.**

Extraction takes roughly five hours at ~86 documents/minute and costs
nothing but CPU. It is a **Phase 2 prerequisite with no Phase 1 value** —
nothing but the deep-read consumes cached text, and a deterministic regex
sweep over it was already tried and produced only false positives.

---

## The extraction bug, and the two it was hiding

This is the substantive discovery of the session and the reason the
numbers moved.

**`no_text` meant two opposite things.** The runner logged it both when
the text cache was missing — nobody had extracted the document — and when
the cache existed and held no words. An absence of *processing* recorded
as an absence of *content*. Because the cohort query excludes anything
already logged, the first kind was never revisited.

**4,836 of 5,073 were the never-extracted kind.** Sampling the supporting
statements among them found every one carried a full text layer:
thousands of characters in the first pages, one 86 pages long. Supporting
Information is where capacity figures live. Corpus-wide, 28,433 documents
had no cached text at all.

Fixed on branch **`not-extracted-fix`, which still needs a PR**: the
runner logs `not_extracted` and retries it, the log upserts instead of
`DO NOTHING` (so a later success replaces the earlier miss), and
migration 011 relabels the mislabelled rows. The Studio was stopped,
resynced and restarted mid-session because it was minting fresh
mislabelled rows.

### What that left, once measured honestly

**237 documents genuinely have no extractable text — and 196 of them are
not PDFs.** The extractor is pypdf plus OCR, so anything else yields zero
pages and is logged as though it were empty:

| Format | Count |
|---|---|
| `.docx` / `.xlsx` | 127 |
| `.doc` / `.msg` / `.xls` | 55 |
| JPEG | 25 |
| RTF | 14 |
| PDF | 12 |
| HTML / other | 4 |

The same bug in a third costume: *the extractor does not handle this
format*, recorded as *this document contains no words*. The Outlook
`.msg` files are consultee responses, which is where objections and
technical challenges live. `openpyxl` is already a dependency;
`python-docx`, `striprtf` and `extract-msg` would cover 196 of the 237.

**14 documents genuinely lost to parse failure** — the original task
list's "16 bad chunks", and roughly right. 380 parse-failed rows exist
but 368 still produced findings; the failure is a truncated tail. The 14
are mostly short ancillary items, though two are VIRTUS supporting
statements and one a 37-page Cardiff "Additional Information".
`deepread_escalate.py` is the salvage path.

**58 sites hold documents with nothing read at all** — 8,212 documents,
17 of them named as data centres or carrying an MW figure, including
Google Waltham Cross (500 documents), Saunderton VIRTUS (289), Langston
Road 50MW (182) and LCY20 (177). That is not a loose end, it is the body
of Phase 2.

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

**Phase 1 — closed.** Published behind the gate, regenerated against the
22:42 boundary, Drive verified by sampling 40 documents' actual parents
(all correct), the Sheet refreshed. Only a gate re-probe remains, from
outside with no cookie, after the next deploy. The duplicate Drive folder
`1UxxGmbi…` is safe to delete whenever Luke wants.

**Phase 2 — collecting, then reading.** The overnight sweep resolved 37
of 108 applications and gained 1,573 documents; 68 remain as retryable
errors. Still to come: the 31 applications that route through the browser
tooling (good value, needs Luke at the keyboard) against 20 reachable
headlessly across eleven unrelated portals (poor value); format handling
for the 196 non-PDF documents; and the deep-read itself over the
remaining corpus, on OpenAI credits since the Anthropic budget is spent.

**Start here in the next session:** open a PR for `not-extracted-fix`,
then add non-PDF format handling to the extractor. Both are prerequisites
for the deep-read being worth running.

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
