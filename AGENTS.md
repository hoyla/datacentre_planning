# Working on this repo

Routing, not content. **Every line here points at a file that is
authoritative; nothing here restates a fact it points at**, because a
restated fact is the thing that goes stale. If you find this file
asserting a figure, a threshold or a schema detail, that is a bug in this
file.

Start with [README.md](README.md) for the map and
[ARCHITECTURE.md](ARCHITECTURE.md) for the seven principles, the pipeline
and the schema. [ROADMAP.md](ROADMAP.md) is what is still to do;
[HISTORY.md](HISTORY.md) is what was built and decided, **including what
was tried and rejected**.

---

## Three rules, before the routing table

**1. Read whole files, not the section you need.** Corrections in this
repo are *appended*, not applied, so a superseded instruction usually
still sits in the body with its correction further down. Reading linearly
and stopping early does not leave you ignorant — it leaves you
confidently implementing something the project already retracted. The
live example, and the reason this rule is first:
`data/nsip_research/findings.md` recommends a gov.uk search parameter in
its body and forbids that same parameter in its addendum. Read the
addenda, the headers, and any block that starts "Correction".

**2. Read the data before the prose about it.** Where a claim is about
what a file, register or table contains, open it. Prose describing data
drifts from the data; the YAML entry's own `note`, the register's own
field, and the commit that changed it are the record. A count that
disagrees with its source file is a *folding* question first — most
tables here are append-only, so the latest row per subject is the
current state and the raw count is history.

**3. Check whether it already exists before proposing it.** The commonest
failure on this project is poorly re-deriving something that was
carefully arrived at months ago. Search HISTORY and ROADMAP for the
topic, read the
relevant priors file's header comment, and look for the sections named
**"Decisions already made — do not relitigate"**, **"Approaches tried and
rejected"**, **"What is already done and needs no repeating"** and
**"what this note deliberately does not propose"**. They exist precisely
to stop this.

A corollary of all three: **something looking broken is not evidence that
it is.** Several guards here are designed to fail loudly in normal
operation, and the runbook, `docs/BACKUP.md`, `docs/MAC_STUDIO.md` and
`docs/PORTAL_NOTES.md` each list cases where the alarming output is the
system working. Check those before reporting a fault.

---

## What to read, by task

Read these **before** touching the area, in the order given.

| Doing this | Read |
|---|---|
| Anything at all | [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md) |
| Proposing or using an external data source | [docs/EXTERNAL_DATA_SOURCES.md](docs/EXTERNAL_DATA_SOURCES.md) — README calls this out by name — then ARCHITECTURE §5 |
| Matching an external claim to a site | that source's `data/external_sources/*-matches.yaml`: **its header comment and its `considered:` section**, which records rows examined and rejected with reasons. `environment-agency-permit-matches.yaml` is the worked precedent for the vocabulary |
| Searching for a site by name | [data/priors/site_aliases.yaml](data/priors/site_aliases.yaml) **as well as** derived names — the alias file is where a developer's name for a place and the planning record's name are reconciled. ARCHITECTURE §4 |
| Site boundaries, campuses, partitions | `data/priors/site_partitions.yaml`, `data/priors/campus_scope.yaml`, ARCHITECTURE §4, and the campus sections of ROADMAP |
| Organisations, SPVs, ownership | `data/priors/organisation_aliases.yaml` header, [docs/PLAN_OWNERSHIP.md](docs/PLAN_OWNERSHIP.md) (has a do-not-relitigate section) |
| The reader, or any UI change | [design_handoff_datacentre_reader/README.md](design_handoff_datacentre_reader/README.md) is **the specification**; [docs/READER_REDESIGN_PLAN.md](docs/READER_REDESIGN_PLAN.md) is the diff against it; [docs/DESIGN_CONFORMANCE.md](docs/DESIGN_CONFORMANCE.md) records who decided each departure; `tests/test_design_conformance.py` enforces the numbers |
| Regenerating or releasing anything | [docs/REGENERATION_RUNBOOK.md](docs/REGENERATION_RUNBOOK.md) **in full**, including its Traps and its already-done sections |
| Acquisition, portals, a council that returns nothing | [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md), ARCHITECTURE §3 |
| Reading documents — deciding **which reader** gets the work | [ARCHITECTURE.md](ARCHITECTURE.md) §3, "Reading at scale", which carries the standing policy on what reads first and what only ever reads second. Settle this before touching any runner |
| Operating the Studio, once that policy says to | [docs/MAC_STUDIO.md](docs/MAC_STUDIO.md) — the machine's operating manual, **not** the policy on which reader to use |
| The database, backups, restores | [docs/BACKUP.md](docs/BACKUP.md) |
| Adjudication rules or corrections | [docs/RULES_AUDIT.md](docs/RULES_AUDIT.md) — and use its method: write down the domain fact a rule asserts, then check that fact against HISTORY, ROADMAP and the corpus |
| Ranking, scale, or choosing sites to chase | [docs/SCALE_RANKING_RESEARCH.md](docs/SCALE_RANKING_RESEARCH.md) |
| Consumption context | [docs/PLAN_CONSUMPTION_CONTEXT.md](docs/PLAN_CONSUMPTION_CONTEXT.md) (has a do-not-relitigate section) |
| Publishing, quoting or reusing any figure | [DATA-LICENSING.md](DATA-LICENSING.md) — several sources require named attribution |
| Prior reporting on this subject | [prior_art.md](prior_art.md) |

---

## Opening a pull request

Besides the repo's own git conventions:

**Carry the documentation your change makes stale.** A change that
supersedes a statement in a document should update that statement in the
same PR — corrections *caused by* the change are part of the change, not
follow-up work. Unrelated staleness you notice on the way gets its own
PR or a flag; do not fold it in.

**Then check the same claim is not asserted elsewhere.** Grep the repo
for the figures, filenames, parameters and section numbers your change
touches, and **say in the PR body what you searched for**. An unbounded
"I checked for contradictions" is unfalsifiable; a list of search terms
is reviewable.

**Prefer correcting the original sentence to appending a note.** Rule 1
above exists because this repo appends. Where a claim can be checked by
code instead — the pattern `docs/DESIGN_CONFORMANCE.md` describes, having
moved its assertions into a test — that is better than prose either way.

**State what you measured and how.** Provenance applies to statements
about the corpus, not only to findings in it.
