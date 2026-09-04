# The root-cause review of 2026-09-02, checked

An external read-only review of this repository
(`datacentre-planning-root-cause-review-2026-09-02.md`, supplied by Luke)
asked which mechanisms treat symptoms rather than causes, and proposed
five changes plus a list of mechanisms it says should stay.

This document is the check. Every claim below was verified against the
code, the live database (read-only) and the record — ROADMAP and HISTORY
read in full — before anything was accepted, and re-verified on
2026-09-04 against the corpus as 2.13 left it.

**The ROADMAP and HISTORY edits it produced are applied**; where each one
landed is indexed below rather than restated. **The code follow-ups are
not started** — they are listed at the end, each its own change.

What this file is for, once those land: the measurements, the items
declined with their reasons, and the record of what a careful outside
reading of this repository did and did not see. That last part is the
half worth keeping.

*The review document itself is deliberately not committed. Two of its
figures were stale on arrival, and a restated inventory is the thing that
goes stale — the rule this repository already keeps. It is named by date
here and in HISTORY.*

---

## Verdict in one paragraph

The review is careful and mostly right, and its value is not the
diagnoses — four of its six substantive points are already ROADMAP items,
one of them since May — but what it adds to each, plus one correction it
gets right and one design argument it wins. Two of its three "safe now"
items are **understated**: the water number is wrong in three shipping
places rather than two, and the deduplicated `pages_sent` already exists
in the runner. Its typed-outcome proposal is sound but missed that this
repository holds the distinction twice already on the audit path — and
checking it found the opposite defect live in two adapters. Its
document-split proposal is **declined**: the marker it wants is already
the empty body's own hash. Its `not_dc` section is behind the record. Its
"should remain" list matches HISTORY's rejected-approaches record exactly
and needs nothing.

---

## What was measured

Against the live database, read-only. Measured 2026-09-02 and
re-measured 2026-09-04 after 2.13 shipped: **every figure held** except
the deep-read row total, which grew with 2.13's reading. Re-measure
rather than re-quote; these move with the corpus.

| check | result |
|---|---|
| live membership rows on retired sites | **0** — fix in `dcp/sites.py`, PR #351; `preflight()` counts `stale_member_rows`; `tests/test_membership_doors.py` pins it |
| `deepread_log` rows with more entries than `pages_total` | **714** (ROADMAP says 21, as at 2026-08-12) |
| rows holding a page number more than once | **929** of 98,708 |
| document 52945 | the local-model row holds 148 entries for 32 distinct pages against `pages_total` 32; its gpt-5 row is clean |
| sites with a consumption or abstraction finding, under the site profile's own predicate | **169** of 500 live sites; 328 hold any water or cooling finding |
| `documents` rows carrying the empty body's sha256 | **3** — Warwick, Wakefield, Medway, exactly the three ROADMAP names |
| live-universe applications holding no documents, by latest outcome | 118 `none_published`, 94 `no_adapter`, 74 `error`, 5 never attempted, 1 `login_required`, 1 `portal_blocked` |
| `error` rows on detail `no_documents_or_unparseable` — re-fetched every sweep, for ever | **37** (31 Idox, 6 Arcus) |
| `none_published` settled on that same detail | **99** (90 Idox, 9 Ocella), every one dated 2026-08-08; 52 are the known refusal pages |
| `withdrawn_from_view` with no settled mapping | **7**, retried for ever for the same reason |

### How old each item is

The first commit carrying the sentence, which is the thing the review's
"root cause" framing most needed:

| ROADMAP item | first written |
|---|---|
| Promote `associated_id` to a typed `parent_ref` | **2026-05-12**, v1 — before #252's relationship-table recipe of 2026-08-30 |
| Make the dictionary's corpus statistics computed | 2026-08-11 |
| `pages_sent` counts a page once per chunk | 2026-08-12 |
| `no_documents_or_unparseable` is a conflated name | 2026-08-26 |
| `drive_sync.py`'s non-atomic `write_text` | 2026-08-30 |
| The materialise leaves membership rows unretired | 2026-09-02, PR #349 — superseded by #351 the same day |

---

## Item by item

### 1. Computed corpus statistics — valid, and understated

**What the review said.** Both principal exporters hardcode "only 93
sites disclose water consumption"; compute it once instead. Do not
replace 93 with 119, which updates the symptom.

**What is true.** Worse than that. The count is typed by hand in three
shipping places and computed in none:

- the reader's front-page caveat, "only 93 sites disclose", in
  `scripts/export_reader.py`;
- the workbook's *Water figures* release row, the same 93, in
  `scripts/export_handover.py` — both copied from the phase-1 HISTORY
  sentence of 2026-08-09;
- the dictionary's *Water evidence* entry, "only 119 of 429 sites", also
  in `export_handover.py` — **which the reader renders into the same
  page as the 93**. One published HTML file states both, about a scroll
  apart.

The 76 this item attributes to the dictionary survives only in a comment
in `dcp/site_profile.py`. Under the profile's own predicate —
`COOLING_TEXTS_SQL` with `CONSUMPTION_SIGNAL_RE`, live sites and live
memberships — the figure is **169 of 500 live sites**. So
every published number is wrong, and the review's own warning applies to
the ROADMAP's inventory as much as to the exporters.

`dcp.corpus_stats` exists and is shared, but stops at the
universe/triage/documents/findings layer and has no site-profile
aggregate; neither exporter imports it. The per-site value is computed
already; only the roll-up is missing.

**The class is a dozen, not one.** The reader's methodology prose also
types "twenty-two largest figures, all twenty-two" three separate times,
"116 figures rested on a quote carrying no unit", "1,667 adjudicated
generation figures", "43 site rows", "855 findings across 51 sites"
(also typed in ROADMAP), "47 sites, median 0.75"; the dictionary types
"53 sites" for the 1.71 kW/m² calibration, "six campuses" and "28
applications behind bot protection" — the last two countable today from
`site_facilities.yaml` and `KNOWN_BLOCKED_HOSTS`. No test rejects a
literal count, and `tests/test_build_determinism.py` would preserve a
wrong constant byte for byte.

### 2. `deepread_log.pages_sent` — valid, and understated

**What the review said.** Define it as `sorted({page for pages, _ in
chunks for page in pages})`; leave historical rows; treat existing arrays
as sets.

**What is true, and what the August note did not say.** Two things.

**The canonical form already exists in the same function.** `sent_set` is
computed eleven lines above the write that ignores it, and it is what the
escalation JSONL records — the file `regate_escalations.py` actually
reads. The database column never gets read back at all: no
`array_length`, no `cardinality`, no `len()` but the progress line. So
the two records of "which pages the model saw" already disagree, and the
fix is to make the column match the JSONL rather than invent a third
convention.

**The list is not write-only.** The verbatim gate's fallback loop walks
the un-deduplicated `sent`, re-scanning a split page once per chunk — on
exactly the million-character worksheets where it costs most.

And the visible symptom is wrong in both halves: the progress line's
denominator is the document's *total* pages, not the pages selected.

Six writers share the defect: the runner, the two batch builders, and the
agent and retry runners that inherit their metadata.
`tests/test_chunking.py` asserts `nums == [1]` per chunk for a split
page, which is correct and stays — it is the flatten that must
deduplicate.

### 3. The Drive ledger — valid

**What the review said.** Serialise, write a temp sibling, fsync,
`os.replace`, release the lock only after; take an inter-process lock;
refuse a second process rather than merging two mutable ledgers; keep the
batching fix separate.

**What is true.** `Sync.save()` dumps the payload under the ledger lock,
releases it, then `write_text`s the final path. Both hazards are real:

- a kill mid-write leaves truncated JSON, which the next sync loads with
  a bare `json.loads` and dies on — loud rather than silent, but the
  ROADMAP's "before anyone relies on killing a sync safely" is exactly
  right;
- two workers can pass the fifty-change gate in one order and finish
  their writes in the other, so an older snapshot silently overwrites a
  newer one. The lost entries are files re-uploaded beside their Drive
  copies next run: the duplicate-archive mechanism `dcp/drive.py` exists
  to prevent.

No inter-process lock exists anywhere in the tree. The concurrent-write
test pins the in-memory dict against mutation during iteration and
asserts after a final uncontended save, so it can see neither hazard.
Under `drive.file` the ledger is the only record of what the tool
created; `scripts/rebuild_drive_ledger.py` rebuilds a *lost* one, which
does not help a *partial* one that under-describes Drive without
announcing it.

The pattern to copy is in the repo already — `relist_refetch.py`'s
`_save_state` writes a temp sibling and replaces it, and the DuckDB
export and staging build use `.building` siblings. The ledger is the odd
one out.

Two readers still spell the ledger path themselves, outside the
`SYNC_LEDGER` constant that `tests/test_release_paths.py` enforces.
`prune()` reads and mutates the state outside the lock, safe only because
it runs after the pool closes.

### 4. Typed portal parse outcomes — sound, and more urgent than the review says

**What the review said.** Return `recognised_with_documents` /
`recognised_empty` / `unrecognised_response` / `access_refused`; a
recognised empty needs positive evidence; roll out one family at a time
against captured fixtures; allow settlement last.

**What is true, and what the review missed.** Four adapters set
`no_documents_or_unparseable` on `len(links) == 0` — Idox from three
indistinguishable `return []` paths, any table or none. Since the
2026-08-09 tightening `acquisition_outcome` refuses to settle that, so it
lands as `error` and is re-fetched on every sweep with no exit but a
hand-written row. The label has sat on both sides of the bug: it wrongly
settled before the 9th and wrongly refuses to settle since. The reader
prints the raw detail string verbatim as an application's reason for
holding nothing.

**The distinction is not new here.** `scripts/fetch_newport_docstore.py`
returns `None` for a page that did not parse and `[]` for an empty store,
and says why in its docstring — then throws the difference away one
function later with `or []`. `dcp/relist_audit.py` classifies `blocked`
against `empty_listing` on the pages' own refusal wording and a byte
floor, with migration 029's "the register is UNMEASURED". Both are on
the audit path only.

**Two adapters carry the opposite defect, live.** Agile's `documents()`
returns `[]` for any 200 body that is not a JSON list, and NI's `or []`
does the same for a null `supportingDocuments` — so an error object
served with a 200 reads as `no_documents` and **settles** as
`none_published`. Nobody looked, stored as nothing there, which is the
failure this project fears most and has recorded in six costumes. Both
are one-line fixes.

**And it gates the existing decision item.** Re-fetching the 52 refused
pages with today's adapter can settle only a page that now serves
documents; one that still refuses lands as `error` and joins the loop.
So the typed outcome comes first, not after.

Positive evidence exists for Idox: `table#Documents` present with at most
a header row, or the tab strip's `Documents (0)` / `nodocuments` marker,
both visible in the single captured fixture. No fixture exists for an
empty tab or a refusal — the real bodies are in `source_snapshots`, and
capturing a Selby refusal and a confirmed empty tab is the first act of
the work.

### 5. An application-relation table, not a scalar `parent_ref` — the review wins

**What the review said.** PlanIt's `associated_id` is free text that can
hold several references and comments, so the proposed scalar is not
future-proof; record relations in an append-only table, populate it
alongside current behaviour, and require an exact-or-explained cluster
diff before switching.

**What is true.** The item has read "promote `associated_id` to a typed
`applications.parent_ref` column" since 2026-05-12. It predates the
recipe this project arrived at on 2026-08-30 for the same disease: **do
not sharpen the container, add the missing relation with its evidence**
(#252, `site_adjacent_power`).

A scalar cannot hold what the field holds. `EPF/1165/22(Outline
EPF/1136/19)` and `1331/APP/2020/3388 A1/A3/A4/B1/B8/D1/D2
1331/APP/2017/1883` are the extractor's own worked examples, and
Saunderton's `22/06872/VCDN 08/05740/FULEA` in `tests/test_backfill.py`
carries the 2008 parent the backfill exists to recover. A scalar would
have to choose one and would drop the outline the master-plan note in
`dcp/sites.py` says it needs. "Parent-backfill confirmed the field is
reliable" was a claim about resolution hit-rate, not cardinality.

**What the gap costs today, which the review did not see.** Six callers
share the one tokenizer and feed it four different inputs — the backfill
mines the full description only when told to and only for three
`app_type`s; the clusterer's family pass mines 400 characters whenever
`associated_id` yields nothing; the adjacent-power staging rule mines
600; the Barbour scripts mine none. So the family edges, the staged
adjacent-power paperwork and the Barbour family links are **three
slightly different graphs nobody has diffed**, and which token resolved
to which application, by which route, is re-derived at every materialise
and written nowhere.

One correction to carry: ROADMAP's "two procedural singletons stranded"
predates #352, which stages them under `adjacent_power/` by
re-extraction. What is still missing for them is the relationship row.
Re-measure before quoting.

### 6. Retiring a site retires its membership rows — the review is right that this is done

`dcp/sites.py` retires every live membership on a retired site — all
retired sites, not only the run's own, so it was the backfill as well as
the guard — and reports `members_retired_with_site`; `preflight()` counts
`stale_member_rows`; `tests/test_membership_doors.py` pins both. Luke's
materialise that afternoon retired the 65. Measured that evening: zero.

Two things the review did not catch. ROADMAP **contradicts itself** — the
item is open under *Smaller things* while the capacity-model section four
hundred lines earlier records the same 65 rows retired. And the open item
mis-cites its own PR: the three-query workaround was #349, not #346
(#346 was the four small fixes from the stale-content audit).

One thing the review got wrong: it reports stale comments in
`tests/test_drive_staging_shortfall.py` describing the old behaviour.
There are none — the block is written in the past tense and is accurate.

A real residue it did not find: `UNSTAGED_SQL`, the shortfall counter,
still tests the member row alone, correct only because the materialise
now retires the rows, and its test checks for a substring rather than the
join.

### 7. Separating listed documents from held bytes — declined

**What the review said.** A `documents` row means both "the register
listed this" and "we hold usable bytes"; separate the listed record, the
acquisition attempt and the held content object.

**Why not.** The separation already exists at the grain this
investigation reasons about. `document_listing_audit` names every offered
and missing URL per listing, append-only and idempotent on the listing's
content hash; `acquisition_outcome` records every attempt;
`document_drive_files` records the Drive copy. What was missing is one
condition at the document grain — and it turns out not to need a schema
change at all: **the three zero-byte rows carry the empty body's own
sha256**, which `repo.EMPTY_SHA256` already names and the fetch guard
already compares against. Verified: exactly three rows, the Warwick,
Wakefield and Medway files ROADMAP lists.

So the outstanding action ("say so in the artefacts") is one condition in
the two coverage queries plus a line in the reader's coverage detail and
the site report. A three-table split for three rows would re-point the 99
places that count `documents`. Principle 6 applies: look at the data
before committing infrastructure.

The one table that might earn its place later is a per-URL offers table,
and only if per-URL retry state becomes a recurring need; today
`relist_refetch.py` re-derives it from the audit's `missing` set on each
run, and that is fine.

### 8. Derivation provenance for computed findings — agreed, and it is already staged correctly

The review is right that labelling all 234 as modelled before classifying
them is a presentation patch, and right about the shape. Two corrections:
234 is *figures* of 9,747 (2.4%), not findings; and the ROADMAP already
requires the classification first. The target shape is worth writing down
so the classification knows what it is feeding.

### 9. `not_dc` admission — behind the record

The review presents the choice as open between three vetoes and says the
dry-run is the right instrument. The dry-run is built and the measurements
are as it states, but ROADMAP records the question **resolved with Luke
on 2026-09-02**: the veto is the wrong instrument, because by their own
documents 27 of the 149 name a data centre — Google's Waltham Cross
reserved matters among them — and vetoing at the family door would eject
exactly the material the invisibility flags said only the documents could
fix. The default stays `off`; what remains is the figure-level rule and
three re-triages. No edit.

### 10. Mechanisms that should remain — agreed, no action

The review's list of deliberate safeguards — append-only stores, priors
that fail on unknown references, recorded Drive ids, resolving a claim's
snapshot by its own quote, browser-assisted acquisition, refusal gates,
refusing to infer campus totals from unlike figures — matches HISTORY's
"approaches tried and rejected" record. Nothing to add.

Its signal-family stance (editorial, not mechanical) matches ROADMAP
exactly. One term is not ours: "legacy-derived-family" does not appear
in this repository; the item meant is "2,183 rows sit in a family the
mapper no longer derives".

---

## Where each item landed

The edits were applied on 2026-09-04, on the branch this document
arrived with. They are **not** restated here: ROADMAP carries the items
and HISTORY carries the account, and a third copy is the one that goes
stale. This section is the index.

| review item | where it now lives |
|---|---|
| Computed corpus statistics | ROADMAP, *Smaller things* — "Make the corpus statistics the artefacts quote computed", with the three shipping literals named, the live 169 and the test that stops the next one; the water-adjudication bullet and the test-surface paragraph now point at it instead of carrying their own copies |
| `pages_sent` | ROADMAP, *Smaller things* — the rule stated ("the sorted set of physical page numbers, everywhere it is written"), the 714/929 re-measurement, and the two things the August note lacked |
| The Drive ledger | ROADMAP, *Smaller things* — split into a durability bullet and the batching bullet, so the first does not wait behind the second |
| Typed portal outcomes | ROADMAP, *Acquisition decisions waiting on a person* — placed **before** the re-fetch bullet it gates, which now says it is gated |
| A relation table, not `parent_ref` | ROADMAP, *Smaller things* — the shape, the six-callers measurement, the staged rollout and the `moved` list `preflight()` needs; the capacity-model wart points at it |
| Membership retirement | ROADMAP, *Smaller things* — struck and closed, with the #346/#349 citation corrected and the `UNSTAGED_SQL` residue named |
| Zero-byte documents | ROADMAP, under *Say so in the artefacts* — the `EMPTY_SHA256` predicate, and the split declined with its reason |
| Derivation provenance | ROADMAP, #248 — the target shape, after the classification the item already requires |
| The account of the review itself | HISTORY, "An external root-cause review, and what it changed (2026-09-04)" |

Two items produced no edit. The `not_dc` framing is behind the record
and the record is right. The list of mechanisms that should remain
matches HISTORY's approaches-tried-and-rejected section already.

---

## The code follow-ups the edits set up

Each its own branch off main, one change each, **none started**. Ordered
by what the evidence says is most urgent rather than by size.

1. **Agile raises on a non-list body; NI relabels its genuine empty as
   `no_documents`.** Two lines, two tests. This is the live false-null
   path — "nobody looked" settling as "nothing there".
2. **`pages_sent` deduplicates** at the three builders, plus the
   log-line denominator and tests. `tests/test_chunking.py` untouched.
3. **The ledger writes atomically** under the lock, takes a lock file,
   folds the two stray path spellings into `SYNC_LEDGER`, three tests.
4. **The computed water statistic** in `dcp.corpus_stats`, both exporters
   interpolating it, and the literal-count test over the tree.
5. **`UNSTAGED_SQL` gains the `sites` join** and its test asserts the
   join rather than a substring.
6. **The `EMPTY_SHA256` condition** in the two coverage queries, the
   reader's coverage detail and the site report.
7. **`preflight()` gains a `moved` list** — needed before the relation
   table can be diffed, useful on every materialise regardless.
8. **Idox typed outcomes** with two captured fixtures, and the
   `withdrawn_from_view` mapping — after Luke picks the settled class for
   a refusal.

The relation table itself (Edit 5) is a design to schedule, not a
follow-up to slot in: it wants its own plan document, the way the
operator rung and the unsited-claims layer did.

---

## What this document deliberately does not propose

- **Committing the review.** Its inventory was partly stale on arrival
  and a restated fact is the one that goes stale.
- **Any `not_dc` veto.** Settled 2026-09-02; the veto is the wrong
  instrument.
- **A three-table document model.** Declined above, with the reason.
- **Correcting `ward`.** ROADMAP calls it the one token deliberately left
  broken, with the arithmetic; the review listed it as a correction to
  make, which inverts the item.
- **Editing `ARCHITECTURE.md`'s "no schema change needed".** That
  sentence is about the parent backfill's `discovered_via` provenance,
  not about the relation model, and reads correctly in place. If Edit 5
  is built, the sentence is re-read then.
- **Any change to the mechanisms the review says should stay.** They
  match the record.
