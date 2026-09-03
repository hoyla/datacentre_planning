# History

What has been built and decided, in order. The [roadmap](ROADMAP.md)
holds only what is still to do.

This is kept because the *reasons* matter more than the results: several
approaches here were tried and rejected, and knowing that saves someone
re-running them. Where a decision was reversed, the reversal is recorded
next to it rather than replacing it.

---

## v1 — the first investigation (May 2026)

Built with Aisha Down at the Guardian. The question: do data-centre
planning applications disclose on-site power generation that contradicts
public renewable marketing?

**Universe.** 1,894 UK applications, 2007–2026, from the PlanIt national
index — a broad keyword sweep, then operator-name expansion, a spatial
sweep around known sites, and a parent-application backfill that walked
PlanIt's `associated_id` chain to recover pre-2018 permissions referenced
by later procedural filings.

**Triage.** `granite4.1:30b` locally over the whole universe against a
written rubric, chosen after a five-model comparison — IBM's JSON tuning
plus 30b reasoning gave roughly 97% verdict accuracy at ~9s per
application. Verdicts are versioned per `(application_id, model,
inserted_at)`, so a second model overlays rather than overwrites.

**Documents and extraction.** Idox and Ocella adapters, with a manual
ingest path for one-off portals; ~99% coverage of the top-100 worklist.
Findings extracted human-in-the-loop, every evidence quote verified
verbatim against the cached page text before it entered the store.

**Release.** `dcp release` produced a versioned folder whose headline
artefact was a single-file HTML reader with a split card-and-map view,
plus text-only, xlsx and standalone-map companions. All eight
story-readiness items resolved; v1.0 shipped 2026-05-17.

**Rejected in v1, and why:**

- *Phase 5, a multimodal pass over site plans.* Nearly every PDF in the
  corpus has a text layer, so vision added little — and anything an
  applicant genuinely wants to conceal will not be in the drawings.
- *A browse UI.* The static single-file reader answered the access
  pattern without a server, and still does.

---

## v2 — the second dataset (August 2026)

### Barbour ABI, and what it exposed (Aug 2)

Cross-referencing the universe against Barbour ABI's licensed
construction-project data — 253 projects, ~200 linked to applications
with per-link match provenance — showed the keyword-built universe had
been missing whole classes of scheme. 62 previously-missed applications
were ingested and pre-2018 "Built" estates came into scope.

The gap ran both ways and was enumerated in both directions rather than
assumed. That reconciliation is what motivated everything below.

### The dc_build universe (Aug 3)

A new rubric — *is this a data-centre build application* — with eight
project classes, replacing v1's four. Five adjudication rules came out of
a conversational adjudication of 16 contested rows, the load-bearing one
being **classify the instrument, not the scheme it describes**.

Architecture locked after a trial: **Sonnet catalogues metadata**,
**every candidate site gets deep-read** — triage demoted from gatekeeper
to cataloguer, because the ground-truth exercise found 10 cases in 50
that could not be resolved from the description at all.

**Prompt v2.2 tried and rejected.** Widening the model's signal
vocabulary cost two points against the adjudicated set (45/50 versus
v2.1's 47/50), and the entire loss was on the rows that depend on the
association rule. Reverted. The requirement was met better by extracting
environmental subjects **deterministically** from descriptions
([dcp/signals.py](dcp/signals.py)) — reproducible, free, and no risk to a
validated prompt.

### Acquisition (Aug 5–9)

Adapters in coverage order — Idox, Ocella, Agile, Arcus, Salesforce —
then five councils that each blocked differently and were each solved
and documented in [docs/PORTAL_NOTES.md](docs/PORTAL_NOTES.md):

| Council | Obstacle | Recovered |
|---|---|---|
| Coventry | AWS WAF; driven through a browser rather than scraped | 254 |
| White Horse | Documents on a migrated register | 884 |
| Runnymede | `ViewDocument?id=`; `DownloadFile` is a decoy | 982 |
| Broxbourne | Document list needs an explicit `pageSize` | 534 |
| Slough | Legacy PHP store; a `Referer` header was all it wanted | 164 |

Two habits are now enforced in code rather than remembered. **One client
per host**: a shared client let one council's 429 backoff (4s → 45s)
throttle every other council in a sweep. **An application is never marked
complete unless every listed document arrived** — 21 were wrongly settled
during a block, which is precisely the silent failure the pipeline exists
to avoid.

### Deep-read at scale (Aug 7–9)

18,645 documents read, 462,221 findings, every evidence quote
machine-verified against its source before insertion. A second model
re-reads a subset independently; where the two disagree, both readings
are kept and the disagreement is the finding.

**Power adjudication** was the most consequential correction. Taking the
largest MW figure in a site's documents produces nonsense, because
planning statements argue for approval by citing the market: under that
rule a Slough application reported 30 GW (a national storage target) and
a Chiltern one 22,700 MW (a Savills forecast). Every figure is now
adjudicated for *whose* it is, and only those the documents attribute to
the development itself are admitted. **Of the twenty-two largest figures
in the corpus, all twenty-two describe something other than the site they
appear in.**

**A re-read of the sites lacking a capacity figure was investigated and
rejected** — a useful negative result. Most hold no documents at all (an
acquisition gap, not an extraction one); **71 were read in full and
genuinely never state a capacity**. A regex sweep of their cached text
finds MW-like patterns in 2% of documents, all false positives — manhole
annotations, kWh/m² targets, EV charger ratings. That consented data
centres disclose no power figure is itself a finding.

**Water was reduced to cooling method, not volume.** The water findings
are dominated by the drainage and flood engineering every development
produces; only 93 sites disclose anything about consumption. A volume
would imply a precision the applications do not contain.

### The Phase 1 handover (Aug 9)

Three artefacts over one corpus: a **workbook** (61 columns, with a
column-by-column dictionary), a **DuckDB** file for people whose question
is not in a column, and a **reader** — one self-contained HTML page with
sites, applications, the energy layer, a map, the methodology and the
data dictionary, published behind an edge password gate.

Everything findings-derived on a partly-read site is marked as a floor
that can rise. Every "no documents" carries the reason it has none, from
the recorded acquisition outcome, so *checked and empty* stays distinct
from *never tried*.

**Corpus boundary.** Frozen at 08:50 to get the handover out, then
deliberately unfrozen when acquisition restarted the same evening. The
release is stamped when collecting actually stopped;
`data/exports/phase1_snapshot.json` records both boundaries and why the
first was superseded.

### Formats other than PDF (Aug 10)

The extractor was pypdf plus OCR, and dispatched on the filename
suffix. Everything else — Word supporting statements, Outlook consultee
responses, spreadsheets of plant schedules — yielded zero pages, and was
recorded as containing no text.

**Sniffing replaced the suffix**, because the filename lies: 255
documents arrive as `.bin`, and a 200-file sample of those was 54 Word
documents, 42 Outlook messages, 16 workbooks and 18 scanned TIFFs. Magic
bytes decide; ZIP and OLE containers are opened and identified by the
streams they hold, which is the only way to tell a `.doc` from an `.xls`
from a `.msg`. Checked against `file(1)` across every non-PDF format in
the corpus, the two agree on all of them.

**The real population was 2,082, not the 196 first counted** — that
figure was documents that had reached the deep-read, not the corpus.
Loaders now cover Word (both generations), RTF, workbooks, OpenDocument,
PowerPoint, Outlook and RFC 822 mail, HTML, CSV, plain text, standalone
images, and the exported-email ZIP bundles. Six documents remain
unreadable: the binary pre-2007 Excel and PowerPoint formats.

**Synthetic pagination is labelled.** Only a PDF has pages, so a `.docx`
is split into ~3,000-character sections, a workbook into worksheets, a
deck into slides — page-scoring needs something page-shaped — and the
cache records which kind of division it is. Anything but `"pages"` must
not reach a reader as a page number.

**Standalone images are OCR'd with orientation detection.** They are
often photographs — a campaign banner, a site notice — and as likely to
be sideways as upright. Read upright-only, one Oxfordshire objection
photograph returned `AUTHSCUOAXO TVUNY GNAIAC`, which is `DEFEND RURAL
OXFORDSHIRE` backwards.

### Findings idempotency, and a caveat that outran the coverage (Aug 10)

A full review of the v2 work found two defects that had reached the
published reader, both now fixed.

**5.6% of the published findings count was duplicate rows.** The runner
committed findings chunk by chunk and wrote the log row afterwards on a
separate commit, so a document whose run died between the two — or whose
`parse_failed` retry re-read chunks that had already landed — was
re-offered by the cohort query and re-inserted everything it had already
stored. 20,377 rows across 1,504 documents were exact copies of an
earlier row in every content column; migration 012 moves them to
`findings_removed_duplicates` (archived, not destroyed) and adds a
unique index over the content columns so the database now refuses what
the code used to permit. The runner commits each document's findings and
its log row in one transaction, and every findings writer inserts with
`ON CONFLICT DO NOTHING` — a re-run is now genuinely a no-op on
unchanged content. `prompt_version` joins the findings row at the same
time, backfilled to the 1.0 every read to date used. A further 7,771
rows share a quote but differ in a value column: same evidence, two
readings. Those are kept — they are Phase 3's raw material, not cleanup.

**The reader claimed "read in full" on sites it had barely read.** The
no-capacity caveat asserted "the documents held for this site were read
in full" whenever a site had documents and no figure — 213 times in the
published page, 173 of them on sites whose own banner said reading was
incomplete, including all 58 where nothing had been read. The estimator
never saw the coverage numbers. It does now, and the caveat states the
fraction read, marks the absence provisional, and only claims a full
reading — and calls the null result notable — when the coverage says
so. The workbook already compensated at the cell level; the reader
rendered the estimator's sentence raw.

**Migration 013 relabels the 227 rows migration 011 could not see** —
`no_text` with a page count of zero, the unhandled-format caches that
recorded no pages rather than no page count. The same bug in its fifth
costume, and the reason the Outlook consultee responses would never have
re-entered the cohort despite the format loaders existing.

### Backups, and the check that nearly wasn't one (Aug 10)

Until this point the database existed in exactly one place: a Docker
volume on one laptop, with no dump, no replication and no schedule. The
document corpus is mostly re-fetchable; 454,000 gated findings, the
adjudications and the append-only audit trail are not, and re-deriving
them would cost the API budget that produced them.

`scripts/backup_db.py` dumps through the container (whose `pg_dump`
cannot drift from the server, unlike the host's, which is a major
version behind and refuses outright), encrypts with AES256 before
anything leaves the machine, verifies, and uploads to **its own
unshared Drive folder** — never a subfolder of the handover archive,
because Drive sharing inherits downward and a `pg_dump` is the raw
schema, including the Barbour contact details and objector addresses
that every export redacts. Encrypted, the folder's permissions stop
being the only thing standing between that material and a mis-share.
Generational: nothing is ever overwritten, because a backup that
overwrites eventually copies a corrupt database over a good one.

**The verification was wrong first, in the project's own signature
way.** The obvious check — decrypt and run `pg_restore --list` — passed
a file truncated to 40%, because the table of contents lives at the
start of a custom-format dump: the catalogue was intact, the data was
gone, and the listing proved only that the listing existed. What
detects truncation is gpg's integrity check, and only if someone reads
its return code, which the first version did not. Verification now
decrypts the whole file in a pass of its own before parsing anything,
and was tested against intact, wrong-passphrase, truncated and
bit-flipped archives. `--restore-test` goes further and is the only
honest check: it restores into a scratch database and compares row
counts against live.

### What kind of quantity is this? (Aug 10)

Power adjudication was built to answer one question — is this figure
about this development — and answers it well. Nothing asked what *kind*
of quantity the figure was, and six families of error lived in that gap.
All six were found in an afternoon, by reading the largest figures and
then following each oddity, and every one had put a wrong number in
front of a reader.

**Energy recorded as power.** An ARK application gives a load as
"251,859,057.50 kW which equates to 94,197.29 kWh/m2". The unit says
power; the cross-reference says energy; the year's consumption over its
hours is about 28.7 MW. It reached the adjudication table as 251,859 MW,
four times the United Kingdom's generating capacity. Three drafts tried
to detect this in the text and each produced only false positives —
"energy centre capacity 47MW" is power, and so is "4000 GWh/year = 456
MW continuous load", where the document supplies both quantities
deliberately. What detects it is magnitude: nothing is 3 GW.

**Storage and heat recorded as generation.** A 1,000 MW battery at Rover
Way is a discharge rating; 1.2 GW of "Thermal Input" at Camilla Road is
fuel entering a plant, not electricity leaving it, and halved to a
defensible 600 MW once corrected. 115 rows moved to quantity types no
headline column consumes.

**Table rows recorded as capacities.** 116 verdicts rested on a quote
with no unit in it: "80% - 480W" became 480 MW, a table of pounds
sterling became a 384 MW IT load. Three sites lost a headline, and all
three had independently been flagged as contradicted by the grid
cross-check — two methods built from different evidence agreeing on
which figures were wrong.

**Substations recorded as grid connections.** Of seven sites reporting
more demand than their connection could carry, four were not connections
at all: a battery compound, a drawing schedule complete with the
substation's floor area, an earlier scheme's legacy plant, and fifteen
copies of "TEMPORARY 1MW SUBSTATION". Two were real and were left
standing — Watford Bypass states 218 MW of demand against a connection
designed for 120 MW — because a site whose demand exceeds its connection
is a fact the documents assert, not a blemish. One was a clustering
artefact: Ocean Estates merges a Salford scheme with a Trafford one
960 m away.

**Per-unit figures recorded as site totals.** Southside states "Each
building ... rated at 75MW" and, elsewhere, "Three data centre
buildings": the site is 225 MW, not 75. Both halves had been extracted
months apart and nothing had multiplied them.

**A single machine standing in for a fleet — the worst of them.** Amazon
Didcot recorded 2.9 MW of on-site generation, from "Mechanical Generator
- 2,873 kW", one unit's spec sheet. The same documents say "38 no.
2,640kW generator units per building": about 100 MW, against 120 MW of
consumption. Reasoning from the smaller number, the dataset described
the site as having life-safety backup only and being grid-dependent —
close to the opposite of what the application says, on an Amazon site,
about exactly the kind of undisclosed on-site generation this
investigation exists to find.

**Two editorial findings came out of the same work.** Of 666 generation
verdicts across 96 sites, 447 name no fuel or plant type at all, and 64
of the 96 sites disclose none anywhere — a megawatt figure with no noun.
And the null-capacity claim, re-run in committed form
([scripts/sweep_null_capacity.py](scripts/sweep_null_capacity.py)),
refused to print a number at all while candidate figures awaited
adjudication.

**Three adjudication routes now share one rubric.** The Anthropic batch
adjudicator cannot run — that budget is spent — so a Claude Code
subagent probe was measured blind against 229 already-judged figures:
94% agreement on the five-way verdict, 95% on the only distinction a
chart cares about, at ~1,150 tokens per figure. Subagents took the 1,005
consequential figures, where a verdict moves a headline; an OpenAI batch
took the 10,656-figure tail for a few dollars. All three import the
prompt and schema from one file, so a disagreement between them is a
fact about models rather than three drifting copies.

**What replaced remembering.** The corrections are idempotent and
re-runnable ([scripts/correct_adjudications.py](scripts/correct_adjudications.py));
the three exports refuse to build over uncorrected adjudications
([dcp/adjudication_gate.py](dcp/adjudication_gate.py)); and the rules are
named in the adjudication prompt itself as `power-1.1`, which is
declared but deliberately not default, because selecting it
re-adjudicates the whole corpus and it has not been validated yet.

### Phase 2.1 — what the artefacts were claiming (Aug 11)

A correctness release. No new documents, and almost no new reading: two
recovered from a parse-failure backlog. Everything that changed was a
claim an artefact was making, and most were reported by people using the
release rather than found by a test.

**A number that did not say what it counted.** A site panel read
"Standby generators: 109" above "Diesel (147), HVO (39)", and a reporter
reasonably asked how 147 diesel generators and 39 HVO ones fit inside
109. 109 is plant — the largest count disclosed in any one document. 147
and 39 are passages of text mentioning a fuel, out of 1,292 for that
site. Both correct, neither saying what it was of, two lines apart. Now
"109 units" and "Diesel (147 mentions)", with the noun on the leading
bracket only. The same idiom rendered fuels, cooling methods and party
names from three copies of one piece of code; it is now one function, so
the next correction cannot reach two of the three.

**A page number that was not a page.** 17,724 findings cite an index
that is not a page: a `.docx` has sections, a workbook has sheets, a deck
has slides. `dcp/extract.py` has recorded which since the format loaders
landed, but the caches are files on disk and every export is SQL, so the
distinction had never once reached a reader. Told "page 3" of a
spreadsheet, a reporter opens it, finds no page 3, and doubts the quote
rather than the label. Migration 020 adds `documents.pagination`,
constrained to the four values the loader table can produce because a
typo in a closed vocabulary stays invisible until it reaches a citation.
Null means *not recorded*, never "pages": most unrecorded documents are
ordinary PDFs, and "most" is not a provenance claim.

**Map card links that did nothing.** The card is a child of the map
element, so pressing one of its links reached the map's drag handler,
and the first pixel of pointer movement — which every real mouse
produces — hid the card before the mouseup that would have completed the
click. Internal and external links failed together, which reads as
"links are broken" rather than as a map bug. Overlays inside the map now
share a class the gesture guards key off, because a list of ids is a list
the next overlay gets left off.

**An 800 MW site that was 300.** North Hyde Gardens published 800 MW of
on-site generation against a 256 MW site total. The document says plainly
what the figure is: "100 generators across the site giving a thermal
output of over 800mw and nearly 300MWe". Two independent readers
described it as thermal in their own reasoning and filed it as generation
anyway. The existing correction matched "thermal input" — fuel going in —
and could not see heat coming out.

The rule written for it is worth recording as a method rather than a
patch. Matching the words would have touched 68 rows, most of them the
correctly stored *electrical* figure from a sentence that mentions both:
"a thermal output of 28MW and an electrical output of 11MW" stores 11 and
is right to. What identifies a mis-stored one is arithmetic, not
vocabulary — the quote gives an explicit MWe figure and we stored
something larger. Measured before adopting: 2 rows, both genuine, no
false positives.

**Coverage was being reported two ways on one page.** The read cohort
and the coverage figures had drifted: `plan_documents` samples every Nth
document of *what it is handed*, so a cohort filtered to one model's
backlog before planning sampled a different fifth than policy had. Both
now ask `deepread_select.universe_plan`, which plans the whole universe
in one canonical order. A first attempt at this introduced a *second*
definition of "prose" two hundred lines from the first — 36,744 against
37,992, both on the same page — which was caught only by building the
artefact and reading it.

**Unreadable is not unread.** 231 documents are held, classified as
prose, and contain no words: photographs of site notices, plans filed as
JPEGs, a 4.7MB Exif photo filed as "Supporting Information". Tesseract
read them as blank; Apple Vision, tried as a second opinion because it
handles orientation itself, read them as blank too — 0 of 10 on a
like-for-like sample, the only hits a logo and a photographed sign. Two
independent recognisers agreeing is as settled as this gets. They now
carry a `no_text` verdict instead of sitting in the outstanding column
for ever.

**The parse-failure backlog was two documents, not fourteen.** Of 456
documents that parse-failed, 442 still produced findings — the failure is
a truncated tail. Of the 14 that produced nothing, 12 have since been
read successfully by another model and still yield nothing. The two that
remained were spreadsheets, and both failed for one reason:
`chunk_pages` grouped whole units and never split one, so a worksheet of
551,003 characters went to the model in a single request and came back as
truncated JSON. A PDF page is a few thousand characters and never tripped
it. The Hillingdon document recovered from this is a data-hall schedule
giving 4.08 MW datahall capacity and a cooling load whose arithmetic
checks out against its own stated floor area.

**The evening's validation rules were audited** against this file and
ROADMAP, as ROADMAP had asked. One of six failed: the corroboration bands
called a generation-to-load ratio of 0.8–1.5 the classic full-redundancy
pattern, where the corpus shows that band holding 14 of 47 sites, a
median of 0.75, and a modal case below half. The labels now describe the
ratio rather than diagnose the engineering. The 3 GW ceiling passed with
a 2.5x margin over the largest genuine figure. The decimal-slip
heuristic fires zero times and is kept only as a tripwire. Full findings
in `docs/RULES_AUDIT.md`.

**A rule that was written but could never fire.** `classify_kind` tested
the drawing regex before the tier-A one, and the drawing regex contains
`section\b`. So "Section 106 Agreement" was a graphical document, though
`TIER_A_KINDS` listed `section 106` explicitly and had plainly been
written to catch it. 58 documents recording planning obligations were
never read — while "S106 Agreement" took the intended path, so whether
an obligation was read turned on how the council abbreviated it. Found
by Luke while sizing the skip tier for the Pinpoint upload, where the
same rule would have dropped them from the collection.

Both obvious fixes cost something, and the corpus was asked before
choosing. Testing tier A first moves 68 documents and 10 are genuine
drawings pulled in by an incidental word — TIER_A_KINDS contains
`water`, `noise`, `drainage` and `decision`, so "Water Treatment Plans,
Sections and Elevations" and "Drawing - Decision" come with them.
Excluding numbers from `section\b` un-skips "Section 1", "Section 01"
and "Section 03", which are drawing sheets. What is true is narrower
than either: a named statutory instrument is never a drawing, whatever
else its title says. That moves 60 documents and nothing else.

The general lesson is about the test suite rather than the regex. Four
hundred tests passed throughout, because **a dead rule passes every test
that exercises the live ones**. Nothing asserted that a rule which is
written is a rule that can fire — the same shape as the adjudication
gate asserting its two copies agree while nothing asserts either is
right, which is how the thermal-output hole survived.

**Versioning was set aside deliberately.** The rule is that a release
lands beside its predecessor so a citation keeps resolving. For 2.1 that
was overridden on knowledge of who was using what: the Sheet is refreshed
in place anyway, nobody was on the phase 2 workbook or database. Recorded
because the cost is invisible until someone hits it — a citation of "the
phase 2 workbook" no longer resolves to the file that produced those
numbers.

### Phase 2.2 — the four audiences (Aug 19–21)

A source release, not a reading release, and it answers the question the
whole arc opened with: **how do you find out a data centre's real power
demand when so few planning applications state one?** Of 456 sites, 109
had a figure their own documents disclosed or their standby plant
implied, 43 more could only be estimated from floorspace, and 304 had
neither. The answer turned out not to be better extraction. It was that
a data centre's size is stated to several *different* audiences, and
only one of them is the planning authority.

| Audience | Source | Claims |
|---|---|---|
| The planning authority | the site's own application documents | `power_adjudication` |
| The grid operator | NESO's Existing Agreements Register | 119 |
| The auditors | accounts filed at Companies House | 12 |
| Customers | operators' own websites | 59 |

190 claims, 41 matched to 25 sites across 15 operators, three matches
retired. Every figure machine-verified against a committed snapshot — a
spreadsheet row, the OCR of a filed-accounts page, a captured web page —
and every match to a site a hand-adjudicated inference carrying written
evidence. The design that made it possible is in *What kind of quantity
is this?* above: claims beside the planning data, never merged into it.

**What the release was for, in four findings.**

- **Utilisation is about a fifth of capacity, from three independent
  directions.** Ark's audited accounts give ~21% of built capacity
  drawn; VIRTUS's give ~15% of capacity *billed to customers*; UK Power
  Networks' half-hourly metering of ~100 real data centres gives a
  median of 18.1%. The VIRTUS figure is the sharpest, because its
  denominator is capacity customers are already paying for.
- **The same quantity, told differently to two audiences.** Only three
  sites qualified, and the comparison is deliberately narrow: IT load is
  *supposed* to be smaller than total site power, so most differences
  are not disagreements. Kingsnorth is 340 MW to the grid operator and
  49.9 MW to the planning authority; the former Mercure Hotel 435 and
  120. South Mimms is 400 MW to both — the useful one, two audiences
  given the same number by two independent routes.
- **Digital Realty publishes per-site capacity and renders none of it.**
  Eleven UK facilities carry a figure in embedded page state under
  `field_utility_power_capacity`; the visible page shows only "UPS
  redundancy: 2N". The eleven sum to exactly 179,900, matching the
  aggregate in the same payload, which is what establishes the unit.
- **Ark's Elstree page identifies the operator** behind the former
  Mercure Hotel scheme, which the planning record does not foreground.

**Four things landed after the release, all of them from Luke opening
the artefact and poking it.** The pattern is worth more than the fixes.

*The Operators page counted and cited nothing* — "6 sites here", "11
figures", no way to reach any of it. Rows now expand to the sites named
and linked and every figure with its value, what it was published as,
the document it appeared in, the verbatim span, and for external claims
the written evidence for the site match. A check counted the 157 source
links rather than an eye. Two things there were wrong rather than merely
unsourced: *"the operator calls this X"* was untrue for Digital Realty's
eleven, where X is a JSON key, and it now reads "published as"; and
like-for-like ratios show match confidence inline, so a 6.81× divergence
resting on a tentative match says so on the row.

*The map's sidebar described a different map.* Projecting Sites → Map
carried the filtered set but reset the map's controls, so the sidebar
reported "100 MW or greater: off" over exactly the >=100 MW set. The
search box needed the haystacks unified first — the map searched a
thinner one, so copying the term across would have dropped sites the
projection contained.

*The reader and the workbook disagreed about 43 sites.* The workbook
estimated power from floorspace at 1.71 kW/m²; the reader passed
`floorspace_sqm=None` and had since the day it was written. A site read
"30 MW — Estimated from floorspace" in the spreadsheet and "No capacity
disclosed" on the page. Eight of the 43 are over 100 MW, and the
reader's default filter hides anything without a figure, so they were
invisible in the artefact most people open. Both artefacts now call
`site_scale`.

*The DuckDB was a narrower view than the artefacts built on it*, and one
trap in the release chain — `sheet_sync` reconciling against the wrong
report — was fixed the same day.

**And a backup that quietly did not happen.** `backup_db.py` never
loaded `.env`. Every other entry point loads it for `DATABASE_URL`; this
one talks to Postgres through Docker and so never needed to, which meant
the passphrase sitting in `.env` was invisible and the script exited
telling you to export a variable you had already set.

**Two conclusions stated confidently, both wrong, both the same error.**
*"Per-site megawatts are peculiar to Ark"* failed because for VIRTUS the
operating company (06762600) was read, which states no capacity, rather
than the property company (09840065), which states a great deal. And a
tentative match of two 57 MW NESO rows to Hoddesdon rested on that being
*"the corpus's only Hoddesdon data centre"* — a fact about the corpus,
not about Hoddesdon; surveying operators turned up a second one, and the
match was retired with the reason on the row. Checking one member of a
group and generalising is the same mistake in both.

### The fifth audience: Environment Agency permits (2026-08-22)

The 2.2 release said a data centre's size is stated to at least four
audiences and held all four. There is a fifth, and it is the only one a
company cannot decline: the environmental regulator.

**Why it works.** Burning any fuel in plant rated at 50 MW thermal input
or more is a permitted activity under the Environmental Permitting
Regulations, a data centre's diesel standby fleet crosses that
threshold, and the permit states in prose what the planning application
often does not. Ark's Cody Park permit: "The combustion plant comprises
69 diesel fuelled standby generators. 36 of the generators have a thermal input of
2.71MWth, 24 generators at 5.38MWth and 9 generators at 3.66MWth each.
The aggregated total combustion capacity on site is approximately
260MWth."

**What landed.** 5,198 register rows → 97 candidates → 42 with a permit
publication on gov.uk → **42 claims, 7,439 MWth**, of which 31 state a
total their own per-engine breakdown corroborates. Eight matched to
sites by hand. The largest is Amazon's Didcot North campus at 925 MWth
across 129 generators, then VIRTUS Stockley Park at 470 and JVC Business
Park, Staples Corner, at 409.36.

Six of the 42 are read from a variation notice rather than the original
permit, because a variation supersedes what it varies and is the current
position. A seventh was nearly lost to a typo that is not ours: gov.uk
titles the VIRTUS Slough attachment "Pemit: Virtus Holdco Limited", and
classifying documents on the word "permit" alone dropped 180.5 MWth —
31 generators on the Slough campus — on the floor.

**Three design decisions worth keeping.**

*The register is an index, not a source of megawatts.* It has no
capacity column at all. So a register row is never loaded as a claim —
the permit document is. Rows whose activity type is "Combustion; Any
Fuel =>50MW" imply a floor, and a floor was deliberately not written
into a numeric column.

*Thermal input is not electrical demand, and the loader does not pretend
otherwise.* `value_mw` is null on every one of these claims. MWth does
not *convert* to MW, and there is no constant to convert it with: the one
permit stating both quantities is Telehouse Docklands, "The rated
generation capacity of the SBGs ranges from 1.6 megawatt electrical
(MWe) to 2.4 MWe (average thermal input of 5.1 MWth)", which puts
thermal input at roughly two to three times the electrical rating. That
is a reporter's inference to make in the open, with its spread stated,
rather than a loader's to make quietly. Same rule that keeps MWh out of
the megawatt column, applied to a unit that looks much more like it
converts.

An earlier draft of the caveat told the reader to divide by "roughly 2.4
to 2.5" and asserted that these fleets are "sized to peak load plus
redundancy". Both sentences came from the 2026-08-21 handover, neither
had a source, and both went into reader-facing text before anyone
checked. They are now replaced by what the permits themselves say, with
the permit named, and a test asserts the caveat still names it. Five of
the 42 state their redundancy — "N+1", "one generator more than would be
required to provide the total power for the site" — and the other 37 say
nothing about it, so nothing is assumed for them.

*The extraction is deterministic and cross-checks itself.* No model
reads these. The Environment Agency writes permits to a template, so
regex is enough — and where regex is enough, a failure is loud. The
per-engine ratings are summed and compared against the stated total, and
the comparison is on the claim: 31 agree, four disagree, four documents
state no total and are summed from the breakdown, and three state a
total with no breakdown to check it against. Each claim says which.

Two near-misses justify the whole apparatus. Ark's Spring Park permit
writes the fleet and the total as one sentence — "The total
thermal input of the 33 standby generators is 5 generators of 3.9 MWth …
(approximately 120MWth in total)" — and taking the first megawatt figure
after the word "total" published a 120 MWth site as **3.9**. Equinix's
Slough permit prints "13 X 5.714 MWthgenerators" with no space and "2 X
6.857th MWth" with a stray unit, and dropping those two groups turned
331.084 MWth into 243.088. Both are now tests.

**The matching is mostly a null, and the null is the finding.**
Thirty-four of the 42 claims are unmatched, and almost none of that is
about the permits. A permit describes plant that exists; most of this corpus
describes schemes that were proposed, and proximity cannot tell a
campus from its neighbour. More sharply, several site records hold a
whole industrial estate: **nine permits from seven operators, 1,430
MWth, all fall inside site 23**, the only site record on the Slough
Trading Estate. Site 5 holds Interxion, Global Switch and Telehouse;
site 59 holds Vantage, Colt and Equinix alongside Microsoft. And
VIRTUS's Stockley Park campus — 470 MWth, the second-largest fleet in
the register — has no site record within 2 km at all. Every one is
written into `environment-agency-permit-matches.yaml` under
`considered` with its reason, which makes the permits the best partition
evidence the project has — each names a campus and gives its grid
reference.

**Two register errors found by looking.** One Digital Realty permit
gives a Crawley address with Redhill coordinates and a Redhill local
authority; one Croydon installation is located at its holder's
registered office in the City of London. Neither is matched.

**Incidental findings kept.** Telehouse Docklands states 93.6 MWth for
19 generators and schedules 27, "increasing to 145 MWth if the future
expansion is required" — permitted headroom half as much again as the
installed fleet. The Environment Agency's own title for Ark's UB3 4QQ
permit is "Union Park", which places Ark's Union Park at Bulls Bridge
Industrial Estate and bears on the site-61 partitioning. And Linmere
Island is a "48MW data centre" in the planning record with a 324.6 MWth
permitted fleet — different quantities, and worth reading rather than
reconciling.

### The reader redesign, 2.3 to 2.7 (Aug 23–25)

A design handoff arrived for a redesigned reader —
`design_handoff_datacentre_reader/` — with a plan in
`docs/READER_REDESIGN_PLAN.md` that was a diff against it. The plan
scheduled five releases; they were built in one run.

**What the reader gained.** A Signals screen, where a named query over
the adjudicated figures is stated with its definition, the script that
produces it and what it does not tell you. Five cohorts. Sites became a
page rather than an expanding row, with the figure and its evidence read
as one object: the value, who it was told to, the document and page, the
model that read it, and the quote. Editorial rule 4 — every figure the
adjudicator saw, the ruled-out ones with their reasons — exists for the
first time. One filter bar serves the table and the map, which had kept
its own search box, its own 100 MW toggle and its own cohort select.

**And the thing that took longest to see.** The masthead measured to the
handoff on all seventeen of its specified properties and still did not
look like it, because the `@import` that loads the fonts sat several
hundred rules down a stylesheet and an `@import` is honoured only as the
first rule. No page had ever rendered in Source Serif. Checking that each
declared property matches is not checking that the design arrived.

Four more of the same shape followed: `.card`'s `border-top` shorthand
overriding two earlier `border-top-color` rules so the signal cards drew
grey; two different pills both called `.vpill`; a dead `.sigfam` from a
superseded card re-declaring the family label grey; and `.sitepage h2`,
left over from a heading that had been deleted, holding the site name at
22px where §5 asks for 32. None is visible by reading the CSS near where
the rule is written, and none changes a count, so `release_diff` sees
nothing. `docs/DESIGN_CONFORMANCE.md` had asserted conformance in a table
and been wrong three times; it is now
[tests/test_design_conformance.py](tests/test_design_conformance.py),
which asserts the handoff's numbers against a rendered page and which
found the fifth on its first run.

**The label audit.** §4.1e of the plan asked whether a finding's family
matches its text. It does not for 18.2% of the 10,605 findings a reader
sees — which is why a site's evidence could lead with landscape prose
filed under a power family. A flagged row is moved and marked with where
it was filed; nothing is deleted. Marking the hand sample produced a
fourth verdict the design had not anticipated, `not_a_finding`, for rows
that are neither filed correctly nor filed wrongly: an extractor's own
reasoning caught inside the quote, an empty form field, a job
description.

Auditing all of them settled a question the sample could not. The sample
put 57 of its 60 rows on the local `mlx` extractor while that extractor
is a quarter of the corpus, so its flag rate there confounded "worse
extractor" with "harder families" — and was withdrawn rather than
reported. Across everything, holding the family constant, the local model
misfiles 9% against 68% on `power_demand` and 9% against 34% on
`power_generation`. **No megawatt figure is affected**: a capacity reaches
a site's power panel through `power_adjudication`, keyed on the finding
rather than on its family.

**Two cohorts that would have asserted something false.**
`generation_exceeds_load` was withheld in August because the rule
selected nine sites on raw figures and at least two wrongly — JVC's
165 MW was "50 x 3.3 MWt Generators", which is heat. The generation batch
that would settle it ran, and nobody lifted the withholding; it now
computes five members from adjudicated totals only. And one of those five
entered on "generation totalling less than 50 MW", stated in every
passage the site gives, because above 50 MW a generating station in
England needs a DCO rather than local permission. A ceiling is not a
capacity, it counted off-site plant, and the site's own energy centre is
13.5 MW against a 27 MW load — it was in the cohort backwards. 855
findings across 51 sites state a sub-50 bound, which is a behaviour and
the same shape as Kingsnorth's 49.9.

---

## Lessons that changed how the code is written

Each of these was learned by getting it wrong, and each is now enforced
by something other than memory.

**Verify at the far side, not the near side.** Claiming Drive was correct
after looking at the local staging tree; claiming Pages was fine after
looking at the repo. Both were wrong, and both were caught later by
checking the actual endpoint. The password gate looked perfect in a
browser until an unauthenticated request from outside found
`//index.html` served the whole dataset. The backup verifier joined the
list before it had ever run in anger: listing a dump's table of contents
proved the table of contents, not the data behind it.

**Ask what kind of thing a number is, not only whose it is.** Six
families of error hid in that question on 2026-08-10, from a battery
counted as generation to a 251,859 MW site. Every stage was faithful:
the extractor quoted the document exactly, the adjudicator answered the
question it was asked. Nobody asked whether a figure denominated in kW
was power at all. A pipeline that reads the unit and the subject and
never the kind will keep finding new ways to be precisely wrong.

**A predicate written once is a predicate written twice.** Three regex
traps in one afternoon, each caught by a self-check rather than by
review: `\b` is a backspace in PostgreSQL and `\y` is the word
boundary, so a rule written with `\b` matched nothing and demoted 261
rows instead of 116; summing overlapping predicates is not counting
distinct rows; and a literal space never matches PDF text, which reads
"Substation       25.4m²". The migrations now abort on an unintended
count, and a test asserts no predicate contains a single literal space
before a digit — which failed on its first run and found another one.

**A correction deserves a durable form.** Two instructions — use the
Drive folder *ID*, never push to a merged branch — were in memory, were
repeated, and were broken anyway. They are now a constant the sync
defaults to ([dcp/drive.py](dcp/drive.py)) and a hook that refuses the
push ([.githooks/pre-push](.githooks/pre-push)).

**An empty result is not a null finding.** A blocked page and a council
that publishes nothing look identical to a scraper and mean opposite
things. Everything that can fail this way now records *why* it is empty.

**Silent partial success is worse than failure.** A fetch that retrieved
some documents was recorded as complete, and the queue only asked for
applications holding *none* — so a partly-retrieved application could
never come back. Short fetches are now `partial` and re-queued.

**"Nobody looked" must never be stored as "nothing there".** The same
mistake in six costumes now, each found by pulling on the last: the
deep-read logged a missing text cache as an empty one (4,836
documents); the extractor logged an unhandled format as an empty
document (2,082); the extractor also *cached* that empty result despite
a comment promising it did not, which made the miss permanent (1,119);
and a loader that failed transiently returned `[]`, which cached the
same way. The rule now has a mechanical form: **a stage that could not
read something writes no cache at all**, because the absence of the file
is what makes the next run retry. `engine: "skipped"` and
`engine: "unsupported"` are recognised as stale wherever they survive.

The fifth and sixth costumes turned up on 2026-08-10, which is the point
of writing them down. Migration 011 relabelled the missing-cache rows by
`pages_total IS NULL` and passed straight over 227 that recorded a page
count of *zero* — same fact, different spelling, still settled and still
invisible (migration 013). And the reader asserted that a site's
documents "were read in full" whenever it held documents and no capacity
figure, on 173 sites where reading was incomplete or had never started:
nobody looked, published as nothing to see, on the front page.

**Site fragmentation is the main matching hazard.** Proximity is not
identity where one site record holds several campuses, and the corpus
is full of them: Cody Park spans six site records across four councils,
JVC Business Park four across two, Colt's Hayes campus enough of them
that Colt's operator claims are loaded unmatched. Site 61 holds 287
applications, 188 of which name the former Nestle factory, and reading
district proximity as identity is what put the Union Park capacity match
there before it was retired. The mechanism for drawing a boundary exists
— `data/priors/site_partitions.yaml`, honoured by `dcp/sites.py` — and
one boundary has been drawn with it, the International Trading Estate
split that moved records to site 443. The seven campuses still tangled
inside site 61 are named in that same file, under the partitions, so
the next attempt starts from the list rather than rediscovering it.
Until they are drawn, treat any match to a site record covering an
industrial estate as suspect; the
Environment Agency permits are the sharpest evidence for where the
boundaries fall, because each names a campus and gives a grid reference.

**Never let an external figure become a site's own number.** The two
reader panels say where their figures come from, and per-quantity
caveats replaced the single flat one once the sources multiplied — what
needs saying about a contracted grid ceiling is not what needs saying
about a marketing figure or a thermal rating. A test asserts every
quantity type that can reach the indicators panel carries a caveat, so a
new source cannot arrive unlabelled.

**Asserting the specification is not asserting the artefact.** The
masthead was measured against all seventeen properties §1 of the design
handoff specifies — background, size, weight, line height, colour,
padding, opacity, the yellow underline — and every one matched while no
webfont had ever loaded, because the `@import` that fetches them sat
several hundred rules down a stylesheet and an `@import` is honoured only
as a stylesheet's first rule. The whole reader had been rendering in
Georgia. Four more rules were written correctly and then quietly stopped
applying, each invisible from where it was written and none changing a
count, so nothing downstream noticed. `docs/DESIGN_CONFORMANCE.md` had
been asserting conformance in a table and was wrong three times; the
numbers now live in a test that reads them out of a rendered page, and it
found a fifth on its first run.

**A guard that stops guarding is worse than none.** Three in one week.
The determinism test normalised the generation stamp with a pattern
written for an ISO timestamp, and had matched nothing since the masthead
changed format — so the line it existed to normalise was not being
normalised, and it failed only when two builds straddled a minute.
`release_diff` read the filter controls out of the sites view, and when
the bar moved above both the table and the map it reported every control
as removed — and would then have gone on reporting nothing if one really
had gone. And the label audit's span gate could not read a citation
written with an ellipsis, so it marked as unverified the four flags that
were correctly cited. In each case the fix is the detector, not the
reading past it.

**A build has to be a function of its inputs.** Diffing a build against
the last release is how regressions are caught here, and until
2026-08-22 that check was running against an artefact the database did
not fully determine. Two runs of the reader's per-site findings query
inside one `REPEATABLE READ` transaction — one snapshot, so the corpus
could not move underneath it — returned 2,503 of 10,425 rows in a
different position and **80 rows in a different set, across 69 sites**.
Those sites rendered a different selection of findings on two builds of
the same data.

Four causes, one mistake in four costumes, and the fourth only became
visible once the first three were fixed and the diff shrank to 42 lines.
A `row_number()` window ranking on a boolean and a string length with
nothing unique after them, so which rows survived `rn <= N` was
arbitrary among ties. An outer select with no `ORDER BY` at all. A
`DISTINCT ON` breaking ties on a timestamp two rows can share. And then,
in the rendering rather than the SQL, three `sorted(counts.items(),
key=lambda kv: -kv[1])` — Python sorts stably, so labels tied on a count
came out in whatever order the rows had arrived in, and one site's
cooling methods read "also referenced: Heat reuse / offtake, Air-cooled"
on one build and the reverse on the next.

The rule is now stated where it can be checked: **every ordering that
reaches an artefact must be total**, in SQL and in Python alike, and a
tie in a sort key is the same defect as a tie in an `ORDER BY`. The same
missing tiebreaks were swept out of the workbook and DuckDB exports at
the same time, since one fixed exporter and three unfixed ones still
leaves the diff too noisy to read.

What is worth keeping is how it was found and what did *not* find it.
It had survived a 560-test suite, because undefined behaviour is not
reliably reproducible: reverting the fix and re-running the new
integration tests, which build a deliberate tie, shows them passing
against the broken query — with a handful of rows Postgres returns them
in insertion order anyway. The fault only shows at corpus scale. What
caught it was running one query twice against one snapshot and
comparing, which is now a test, and reading a two-build diff, which is
now small enough to read.

---

## The Section 35 watcher, built the day journalism warranted it (2026-08-25)

The Guardian's 25 August story on two gas-supplied NSIP data centres —
Wapseys Wood and "Quest Park", 1.3GW between them — arrived with a
question from the story team: why are these two not in the corpus?
Wapseys Wood was — application `EN0110030`, all six PINS documents
read, 2,815 findings — but under the NSIP register's own name for it,
"SDC M40 Campus", with a site display name taken from the register's
location narrative; the words "Wapseys Wood" appear in neither. Quest
Park (QuestPit Limited, Ampthill Road, Stewartby — the same Quest Pit
whose film-and-TV-studio incarnation the corpus already holds as
`CB/22/03616/FULL`) was genuinely absent: its Section 35 Direction of
15 June, with no DCO yet filed, appears nowhere the adapters look —
not the LPA portal it bypasses, not PlanIt, not the NSIP register.

That gap was designed for in May
([data/nsip_research/findings.md](data/nsip_research/findings.md)):
Adapter 2, the Section 35 watcher, deferred until "there's a *second*
DC S35 direction to test against". The trigger then fired twice —
Quest Park in June, and a third direction on 1 July for a campus at
New Barn Road, Dartford (CSE52 Limited; reported nowhere, including
the Guardian piece) — and nothing noticed, because the watcher that
would notice was the thing not built. A trigger condition only an
unbuilt component was polling for is the pattern worth remembering.

`dcp/sources/s35.py` now does what the May design sketched: poll the
gov.uk Search API, screen hits with the register adapter's DC keyword
union, snapshot each publication's Content API page, and upsert a stub
application per direction with `discovered_via=['s35_direction']`. One
correction to the sketch mattered — the proposed
`filter_format=publication` would have excluded all three directions,
which gov.uk files as format `decision`. Three stubs landed, the
Wapseys direction included: it is a distinct record of a distinct
event from the register row, and clustering unifies them later rather
than ingest silently deduplicating them. Re-runs are free and no-ops
(`pages_from_cache: 3, snapshots_new: 0`).

The three publication bundles are cached under
`data/seed_cases/{wapseys_wood,quest_park,dartford_ebbsfleet}/`, and
the headline figures were read from the primary documents before being
quoted anywhere: QuestPit's request statement states a 1GW campus,
720MW IT load across four buildings, powered by its on-site gas
generating station until a grid connection it does not expect before
2034; Dartford's supporting statement states 300MW power and 240MW IT
load with a firm Gate 2 NGET allocation — grid-led, not gas-led, so
Foxglove's "two gas-fired" framing survives the third project's
existence. Barbour's own Wapseys record (Ptno 12913776, address
"Wapseys Wood Landfill", authority wrongly Cherwell) is now linked to
`EN0110030` by the manual pass in
`scripts/link_barbour_families.py`, so the reader stops rendering a
phantom "no application submitted yet" site beside the real one it
could not name.

### Carrying the stubs into sites, and what that turned up (2026-08-25)

Everything the stubs needed to cluster is now in place: dc_build
verdicts (all three `pre_application`, so all three are in-universe),
coordinate priors for each — the Dartford one converted from the
applicant's own grid reference, `E 561948 N 171563`, cross-checked
two ways — and a new kind of prior for a problem the corpus had not
hit before.

**A provider pin can be wrong in a way that merges campuses.** Barbour
places the Wapseys Wood scheme at 51.5105, -0.5950 — Slough, 8.5 km
south of the address on its own record, and inside the former Akzo
Nobel cluster's radius. The pin created a spatial edge, and the
scheme's Barbour record joined a campus it has nothing to do with.
(The same record's authority field says "Cherwell", which is wrong the
same way; the Guardian question is what made anyone look.) So
`inferred_coords.yaml` now takes `ptno:` entries beside its `ref:`
ones, overriding a project's coordinates at clustering time while the
provider's row stays verbatim in the database — principle 3, the same
shape as every other prior here. An entry naming a Ptno the corpus
does not hold fails the run, as `site_partitions.yaml` does, because a
typo would silently leave the false edges standing.

With that in, the dry run clusters all three correctly. The run itself
**refuses**, on two things the stubs did not cause:

- **Four hand-adjudicated capacity claims would silently empty.**
  Their sites retire into merged clusters, and a match to a retired
  site does not error — it renders through a `retired_at IS NULL` join
  and stops appearing. That is the one consequence here a re-run
  cannot undo by itself, because re-pointing a match needs the
  judgement that made it. `sites.preflight()` now names each such
  claim and where its members went, and `materialise_sites.py` refuses
  rather than proceeding.
- **A 63-application, 16-project cluster spanning 9 km of east
  London** — Interxion, G Park Docklands, Telehouse, Global Switch,
  Republic — chained by spatial edges through a dense corridor. Site
  61 again, needing the same remedy of adjudicated partitions. Worth
  being clear that this is **latent in main already**: the clustering
  code produces it today, and only the sites table being stale since
  2026-08-20 has kept it out of sight. Materialising was going to
  surface it whenever it next ran; the stubs just made someone run it.

The lesson is the one the refusal encodes: a materialise had been
described as safe because it is idempotent and retires rather than
deletes, and that is true of everything it owns. It is not true of what
other people adjudicated *against* its keys. Anything hand-made that
points at a generated identifier needs the generator to say out loud
what it is about to invalidate.

### The sites are materialised, and most of it was not adjudication (2026-08-25)

Investigating the two blockers changed what they were. The east London
"mega-cluster" turned out to be two data errors wearing a boundary
problem's clothes:

- **A wrong coordinate.** Two Tower Hamlets records for "Mulberry Place
  Town Hall, 5 Clove Crescent" are geocoded 4.1 km west of the five
  other records carrying that identical address, landing in Limehouse.
  The pair welded Shoreditch to Docklands. Correcting them split 63
  applications into 16 and 46. Priors now win over a portal coordinate
  rather than only filling in for a missing one — all fourteen existing
  entries were for records with no coordinates, so the change is a
  no-op for every one of them.
- **One stray record.** `TowerHamlets/PA/18/00418/S` is a non-material
  amendment relocating a substation at the Castle Wharf petrol station
  on the Leamouth peninsula. Enumerating every cross-campus pair showed
  it was the *only* node joining Blackwall to Thameside West — two
  edges, both at 0.94 km. One petrol-station amendment was holding a
  9 km site together.

What remained was genuinely adjudication, and Luke settled it: Bidder
Street is not one campus with Telehouse and Global Switch, and
Silvertown Quays is not one with G Park — separate developments that
happen to share a dense quarter, on opposite banks of the Lea in the
first case. Both are now partitions with the evidence written down.
The 63-application, 16-project blob is five campuses of 0.8–1.8 km:
Interxion, Telehouse/Global Switch/Republic, G Park Docklands, Bidder
Street, Olympus Silvertown.

**Tried and rejected: making spatial edges skip `not_dc` applications.**
Family edges have refused to traverse `not_dc` since 2026-08-06, and
the Silvertown seam runs through one, so the symmetry was tempting.
Measured before adopting, as the family-edge rule had been: it moves
**208 of 2,278 members**, disappears 18 site keys and creates 21, and
orphans three adjudicated capacity claims — including West Burton,
which this same session had just re-pointed. A 9% corpus churn to fix
one seam that a three-line partition fixes exactly. Luke's instinct
that the two were "just close to each other" was the right reading, and
the number is here so nobody re-runs the experiment.

With that, the materialise ran: 73 sites new, 420 updated, 10 retired,
2,278 members. The two surviving orphaned claims were re-pointed in the
same sitting — West Burton to `SITE-Bassetlaw/22/01713/FUL`, which
still holds the West Burton Power Station application its evidence
names, and Romford North to `SITE-Havering/P0614.20`, which holds 3
*and* 5 King George Close under the one postcode the permit cites. The
old matches carry retirement reasons naming their successors; live
matches went 49 → 49 with none dangling.

Two things surfaced that are somebody's next job rather than this one:

- **`scripts/load_capacity_claims.py` has been broken since the SPV
  work.** `companies-house-claims.yaml` gained two `scheme_capacity`
  claims, and no migration ever added that value to
  `capacity_claims_quantity_known`, so the whole loader aborts on a
  check violation and rolls back. The ROADMAP already says the type
  "needs one"; until it gets one, nothing can be loaded through the
  script. The two re-points here went in through the same YAML via the
  project's own loaders, so a future run is a no-op on them.
- **The display name of a site is the address of whichever application
  sorts first**, which has no relationship to what anyone calls the
  place. West Burton Power Station is now "Land East Of Gainsborough
  Road Bole"; `SITE-EN0110030` was a paragraph of location prose. The
  second of those is what made the Guardian's story team conclude the
  corpus was missing Wapseys Wood.

---

## v2.7 — the release the redesign was for (2026-08-26)

The first release since 2.2 on 2026-08-21, carrying five merged
increments (2.3–2.7), the site materialisation, the Section 35 watcher
and this morning's adjudication of the corroboration read. Built as
`data/exports/phase2.7_build/`: **494 sites** (519 in the reader, with
pre-planning), 2,032 applications, 51,870 documents.

**What the chain turned up, in the order it turned up.**

*The corroboration read had never been adjudicated.* The Phase 3 read
ran 17–24 August and left **4,117 power figures** across 266
applications with no adjudication — invisible to the mandatory
corrections gate, which only checks adjudications that exist. Luke chose
to run the batch before building rather than ship without it. It
returned 4,115, and the gate then found **52** of the same six
quantity-kind errors it always finds, because the prompt that produces
them is unchanged. Sites awaiting adjudication went 5 → 0.

Worth recording how close this came to being missed: the artefacts do
not refuse to build over it, `sweep_null_capacity.py` did not print
PROVISIONAL, and the only reason anyone looked was that the runbook
lists step 1 before step 7. **A gate that checks the quality of what
exists cannot see what was never created.**

*A number that was actively misleading on the biggest site we hold.*
`consumption_integrity.py` reported **three** contradicted sites where
the runbook records two as known and says a third "means something new
to read". The third was Northumberland Energy Park (New Cambois): a
99.9 MW grid connection against 1,100 MW of stated demand, the largest
in the corpus. The two figures were not in conflict — they belonged to
different schemes. The 99.9 MW came from a **2013** application for a
substation "with the capacity to accommodate up to 99.9MW of offshore
wind power", which had clustered into the data centre's site because
both sit on the former Blyth power station land.

The adjudication was correct for its own application; the *boundary* was
wrong. Partitioned out as `blyth-offshore-wind-onshore-substation`
(the 2013 permission and its three documentary children), which returned
the contradicted count to two and left Cambois with no grid connection
figure at all — the honest position. A reporter reading 1,100 MW of
demand against a 99.9 MW connection would have drawn precisely the wrong
conclusion about the most prominent site in the dataset.

That site still holds 35 applications spanning four unrelated schemes —
the wind connection, Britishvolt's battery plant, JDR's subsea cable
factory and the data centre. Only the figure that was misleading has
been separated; the rest is on the roadmap.

**The release diff, which is the part that has to be read rather than
skimmed.** Three groups fell, all deliberate, and two of them are
citation breakage that belongs in the release notes:

- **Ten site keys retired**, each merged into exactly one live site.
  The mapping is in the release notes; a citation of any of them stops
  resolving.
- **Three workbook columns removed** — *Advisers and consultants*,
  *Applicant / operator*, *Planning authority (from documents)* — not
  dropped but split by the 2.4 parties work into more precise
  successors, which is why Sites columns went 64 → 75. Any script
  reading the old names breaks.
- **The "Exclude unknown MW consumption" filter control**, which the
  runbook already records as removed on purpose.

Everything else rose, and one figure is a useful check on the whole
morning: `power_adjudication` went 14,780 → 18,895, exactly the 4,115
the batch returned.

**The generation batch, finished quietly along the way.** It had sat on
the roadmap since 2.4 waiting on a hand-check bar. `gpt-5/generation-2.5`
has now answered all **1,667** figures — what each on-site generation
number describes (one machine, a stated fleet, or the site) and what the
plant is (standby combustion, prime, renewable, storage) — migration 024
is applied, and the workbook columns and cohorts that consume it ship in
2.7. Worth keeping the scoring method rather than the scores: every
prompt version was graded against the *same* forty hand-checked rows in
`data/generation_sample/generation-2.1_hand.csv` rather than
re-inspected, which is why 2.1's 33/40 basis and 2.2's 36/40 are
comparable at all. Re-checking a fresh sample per version would have
measured the sample as much as the prompt.

**A correction to the record.** The estimate that persuaded us to run
the batch — "69 sites would be understated" — was wrong. It came from a
query filtering `value_unit ILIKE '%W%'`, which also matches MWh and
kWp: energy and peak-PV figures that were never adjudication
candidates. The decision was right on the script's own authoritative
count, and the outcome bore it out, but the number was not evidence and
should not have been quoted as though it were.

---

## v2.8, and the links that pointed at a filesystem (2026-08-26)

2.8 shipped and Luke opened it. The document links pointed at his
computer: `file:///Users/hoyla/Code/.../Request_Statement_on_behalf_of_Questpit_Limited.pdf`,
401 of them, aimed at paths no reader has. 503 documents carry a
`file://` URL into a checkout that exists on no machine at all, and 9
more came from the manual-ingest path the same day.

The applications table had guarded against exactly this since it was
written — `not str(a[12]).startswith("file://")`. The three document
links had not. One rule, applied in one place and not the others.

**The first fix was the wrong half.** `doc_link` became that rule in one
place and rendered anything unfetchable as plain text. Luke: *"I don't
want to just suppress links to documents that people will want to see.
Can you actually fix it please?"* Every one of those 401 links named a
document this project holds a copy of. Hiding the title serves nobody:
the reporter still wants the document, and now cannot even see that it
exists.

**Our copy, with the register beside it.** The Drive archive is not a
convenience, it is the durable copy — a council can withdraw a document
from its register, renumber it, move the portal or put it behind a
session, and all four have happened here. So the title links to ours.
The register keeps a quieter link of its own, because Luke's point cuts
the other way too: *"For published reporting a journalist has to be able
to cite the public register, not a private Drive."* Both, because they
answer different questions.

Reader document links to our copy went **782 → 6,588**, 5,339 of them
carrying a register link alongside. The workbook gained 36 on *Figures
by audience*, where each row is a specific figure from a specific
document and the source link had been silently degrading to the
application page. No site panel lost a link.

Every one of the 26,293 documents cited on a live site resolves. The
3,952 that do not all belong to applications with no live `site_members`
row — the staging rule working as written, not a gap.

### And then: a Drive file is an id, not a path

> I thought we were identifying Drive files by ID, not name …

The *link* always was. `/file/d/{id}/view` survives the file being moved
or renamed on Drive, which is the entire reason this project addresses
Drive by id and never by name — a name lookup under the `drive.file`
scope finds nothing and once silently created a duplicate archive.

**Finding** the id did not. The export rebuilt each document's expected
staging path — site stem, application reference, and a number counting
the application's documents in `fetched_at, id` order — and looked that
path up in the sync ledger.

It was correct. 120 of 120 sampled links verified content-addressed, the
bytes on disk matching the md5 the ledger recorded for the Drive copy;
30 ids resolved live against the API; 25 filenames matched. *Correct
when measured* was the problem. Every input to that derivation can move,
and when one does the lookup either finds nothing — a document silently
loses its link — or finds the neighbouring file, which is a **working
link to the wrong document under a citation naming a different one**.
The first is annoying. The second puts a real quote against a real but
different source, is invisible from outside, and is what principle 7
exists to prevent.

Migration 031 adds `document_drive_files`, append-only with a unique
index on `(document_id, file_id)`. `scripts/record_drive_ids.py` writes
it after each sync; `--verify-bytes` hashes every local file and refuses
any id whose md5 disagrees with what the ledger says it uploaded. First
run: **52,908 ids recorded, 0 refused**, 3m15s over 138 GB.
`_drive_document_map` reads that table and nothing else, and the
derivation was deleted rather than kept as a fallback — leaving a second
way to find a file leaves the failure in place. The rebuilt artefacts
matched the derivation-based ones link for link, which is the check that
only the lookup changed.

**Nothing in the build had ever asserted where a link went**, which is
why 401 of them went nowhere. The new guard reads the built bytes; run
against the pre-fix `index.html` it fails with exactly those 401.

**Left open.** `test_two_builds_of_one_snapshot_are_identical` failed
once during this work and passed nine times after, so the failing run's
detail was never captured — it names the first differing line only in
the run that fails. On the roadmap under *Smaller things* rather than
waved off: a build that is deterministic most of the time is a build
whose release diff cannot be trusted, and that diff is the check
standing between a regression and a published one.

---

## The first automation checks rather than publishes (2026-08-27)

Two workflows were sketched on 2026-08-26, and the order between them
was the argument: a repo with no automation should get one that checks
before it gets one that publishes. This is the first. Three jobs on
every push to every branch, none of which needs Postgres, a secret or a
credential — which is why it could go first, and why a fork running it
gains nothing.

`pytest -m "not integration"` (986 tests), the two browser suites driving
the committed `index.html` through the `READER_HTML` fixture (37), and
`node --test tests/middleware.test.mjs` (17). Around 1m40s wall clock,
the three jobs in parallel.

**The reader job asserts Chromium launches before it runs anything.**
The `page` fixture skips the whole suite when it cannot, and a suite
that skips reports green while asserting nothing — the failure mode that
made the `READER_HTML` fixture necessary in the first place. A missing or
truncated `index.html` was already a hard failure, because conftest calls
`pytest.fail` there rather than `pytest.skip`; Chromium was the one route
left to a silent pass, so it is now a step of its own.

**The flaky test was not flaky.**
`test_a_withheld_paragraph_is_declared_before_it_is_found` had been
recorded as failing intermittently under load, always on a Playwright
30-second click timeout, passing when its file ran alone. It fails every
single time when run in isolation. The
test reads panels wherever they sit but ends by clicking back from the
site page — a view only the test *above* it opens. Deselect that
predecessor and the click waits the full timeout for a view that was
never on. It was three tests, not one: all three were the only tests in
the file missing `@pytest.mark.integration`, so `pytest -m "not
integration"` — the command this CI job runs without a database — was
selecting them. The other two navigate for themselves and so had only
ever skipped, which is why nothing showed.

The lesson is the one this repo keeps relearning: *load* was the
explanation available without a reproduction, and a defect described by
its symptom stays open. Running it once in isolation settled it.

**What the first run caught, which nothing local could.** Two
dependencies were declared only by being installed. `googleapiclient`
and `duckdb` are imported inside the functions that use them —
`drive_sync`, `sheet_sync`, `backup_db`, `create_workbook_sheet` for the
first; `export_duckdb` and `release_diff` for the second — so no module
load touches them and every machine that had ever run a sync or built a
database already had them. A clean clone had neither. This is exactly
the trap the `openai` comment in `pyproject.toml` describes, in two more
places, and it took a machine that starts from nothing to find it.

Worth knowing before the local suite is trusted as a proxy: a clean
worktree without `.env` reproduced the no-database condition faithfully
for everything *except* this, because the venv is shared. Only the
runner installs from the manifest alone.

**Ruff is deliberately not gated.** It reports 799 errors on the tree as
it stands. A check that is red on the day it lands is one people learn
to ignore, which costs more than the check is worth; cleaning the tree
first is its own piece of work.

---

## The Hayes/Southall corridor becomes ten campuses (2026-08-27)

Site 61 — `PTNO-12511337`, displayed as "NORTH HYDE GARDENS UNION PARK -
DATA CENTRES" — held 293 live applications and 8 Barbour projects, and
the name described one of the campuses inside it. Everything in the
corridor is pairwise within the 1 km radius, so no distance separates
any of it; the split needed adjudicated boundaries with written
evidence, which the International Trading Estate partition (2026-08-20)
had already shown how to draw. Ten partitions landed in
`data/priors/site_partitions.yaml`, covering every live member so
nothing is left to spatial chance.

**The boundary evidence is Hillingdon's own reference stems and the
applicant of record in the documents, and they agree — with exactly one
exception.** The stems were verified live (1331: 186, 75111: 57,
38421: 24, 49261: 5, plus 71554, 78343 and 21 stragglers), and the
applicants read from `party_applicant` findings rather than inherited
from the earlier session's table. That reading corrected the table on
two points:

- **Tudor Works and Hayes Bridge Retail Park are two Colt campuses, not
  one.** The table had them on one row. Distinct stems (38421 against
  78343/71554), distinct SPVs — HDCI Hayes London Limited at Tudor
  Works, HDCI Hayes Bridge Limited at the substation serving Hayes
  Bridge — and distinct Barbour projects (Colt London 4 against
  LON6/LON7/LON8).
- **One application breaks the stem premise.** `38421/APP/2024/2215` is
  filed under the Tudor Works stem but is the 2024 EIA screening for
  the Hayes Bridge redevelopment, addressed at the retail park and
  describing that campus. It is partitioned by what it says, not where
  it is filed — the same read-the-record discipline that kept stem 1331
  (Barratt London's hybrid permission with a consented data centre) in
  the universe on 2026-08-25.

**Two campuses nobody had named fell out of the drawing.** The former
Honey Monster food factory on Bridge Road, Southall is a CyrusOne
hyperscale scheme (`253874FUL`, 230 documents) — a different former
food factory from Nestlé's, a kilometre away, and the radius had
dissolved it into the same site. And the "gas powered electricity
generator" on land north of the North Hyde substation is **Clearstone
Energy's** — the developer behind the Dartford Section 35 direction —
with no documentary tie to Ark or anyone else; it was inside "Union
Park" on proximity alone, which is precisely the adjacency the
investigation wants visible on its own row.

The rest: the former Nestlé factory (Barratt London/SEGRO, 188),
Union Park itself (Ark, 59, keeping the site key and so the site id),
Southall Gas Works / The Green Quarter (Berkeley Homes, 6, including a
temporary energy centre), Silverdale Road (Marvell Developments, 6),
Western International Market and the Old Vinyl Factory (one stray
each, partitioned alone on the leamouth precedent).

**Preflighted against the live corpus before committing:** 7 new
sites, 2 revived keys (Tudor Works and Honey Monster existed from
earlier materialisations), 0 retiring, 0 orphaned claims — and a
baseline run with the unchanged priors confirmed the delta is entirely
the partitions. The cross-partition documentary-edge guard and the
unknown-ref guard both ran clean. The materialise itself waits for the
partitions to merge, per the sequencing the 2026-08-25 partitions
established.

What it unblocks, recorded in ROADMAP: re-matching Ark's retired
"99 MW for Union Park" claim, the Union Park 24/48/24 MW SPV claims
held under `considered:`, and the Colt operator tranche that was
"blocked on the Hayes fragmentation".

**Materialised, extended and cashed in the same day.** The first
materialise (7 new, 2 revived, 0 retired) exposed a second form of the
same conflation, inverted: four Ealing out-of-borough consultations
carrying no coordinates had each sat as an unlocatable singleton
*site* — 213, 214 and 215 all reading "Land at Tudor Works,
Beaconsfield Road" (the "three separate site records for the same
address" that the Colt claim's considered entry names as its blocker),
and 405 for the Nestlé factory. Coordinate priors in
`inferred_coords.yaml` (each pin is the Hillingdon stem's own portal
coordinate for the scheme the consultation restates) plus partition
membership dissolved all four into their campuses; the second
materialise retired them. 499 live sites.

Then the matches the split had been blocking, six loaded through
`load_capacity_claims.py` with the batch validator green: Ark's 99 MW
"Total Capacity" re-matched to site 61 — its 2026-08-21 retirement
entry had named "an adjudicated partition for Union Park" as the
release condition, and the new match sits beside the retired one in
`capacity_claim_matches`, append-only — the four Ark Estates 2 FY2025
figures (24 MW built, 48 MW under construction, 24 MW subject to
planning, £839.79m investment property), and Colt London 4's 31 MW to
site 75, where the evidence is no longer press-only: Barbour's title
for the record is "COLT LONDON 4 - DATA CENTRE BUILDINGS" and the
applicant of record in the planning documents is HDCI Hayes London
Limited. Every considered entry that held these back stays in place
with a SETTLED coda, because the reason for the hold is part of the
provenance of the match.

---

## The day between the split and the release (2026-08-27)

The corridor split and the CI workflow above were the morning; this is
the rest of the day, worked while 2.9 assembled. Each block was a
ROADMAP item or a user-review issue; what each *changed about how the
project works* is the part worth keeping.

**The gate states the adjudication tail** (PR #155). Every export's
`require_corrected()` now also prints the count of power-unit findings
with no verdict from ANY model, split by whether the row sits on a site
with no adjudicated capacity. Three properties are pinned by tests: the
count is unqualified by model (the 15,220-vs-299 trap), the unit list
stays in step with `adjudicate_power`, and the report cannot refuse a
build — a gate demanding zero would be overridden within two releases.
Measured at build: the tail was empty; the 299 from 2026-08-26 had been
closed by an `openai:gpt-5:low` batch of exactly 299 rows.

**An export limit is not a grid connection** (PR #158). The named rule
from the redesign review, measured before adoption: the candidate
population had grown from 16 rows to 40 since the corroboration read,
and the growth is why the predicate is value-adjacency rather than
vocabulary — Home of Production's "18 MW of import capacity as well as
10.5MW of export capacity" holds a correct import figure within eighty
characters of the word "export". 23 adjudications demoted across four
sites, one of them pinned (a chunk-cut fragment whose sibling rows hold
the sentence naming it the Maximum Permitted Export Capacity).
Deliberately untouched: Kingsnorth's 47,405 kW rows, the same figure at
leading and lagging power factor, which no predicate can settle and a
person can — they now stand as that site's largest grid figure.

**The refetch can be left unattended** (PR #162). Not
`fetch_outstanding`'s SIGALRM — that only works in the main thread and
the refetch runs worker shards — but a `threading.Timer` that closes
the shard's clients at the same 900s ceiling, so a stalled read raises
into the error arm and is recorded retryable, never settled.

**Northern Ireland needed a header, not a browser** (PR #163). The
register's Next.js pages draw everything from an anonymous TerraQuest
REST API whose only gate is a `TQ-Tenant` header published in the
page's own `__ENV.js` — and without that header the API answers `200`
with a JSON `null` body, indistinguishable from an application that
does not exist. The adapter exchanges a stable API route for a
~30-minute Azure SAS URL per document and unwraps the single-file zip
each blob is; the register's `x.pdf(2)` dedup naming (suffix AFTER the
extension) was caught because the first live file stored as
`<sha>.pdf(2)`. The held NI applications fetched through it the same
hour. PORTAL_NOTES has the route map; what remains is discovery, which
is the whole of Northern Ireland.

**Eleven user-review issues closed in the reader** (#144–#148, #150,
#152, #153, #156, #161, and #151 by decision). The ones that changed
more than pixels: every "What the documents say" statement now cites
its document inline — Drive copy, register, page (#146); the
applications list renders as a full-width band below BOTH columns,
after 19 Yeoman Street showed the old left-column overflow colliding
with the right column (#156); the provenance pie splits the 156 sites
carrying a figure into stated-load / grid-connection /
standby-inferred / floorspace-estimate, because `DISCLOSED_BASES` had
been folding the middle two invisibly into "Stated in the application"
— overstating disclosure on the chart about disclosure (#151, pie only
by Luke's call); and the chrome says "datacentre" (#161) with the
load-bearing exceptions recorded in the commit: quotes and
descriptions keep source spelling, the machine-reading gate's
banned-phrase regexes keep the space a model writes, and the workbook
headers stay because `sheet_sync` reconciles columns by name and a
rename is a formatting-destroying delete-plus-insert. The Assistant's
notes were de-editorialised on Luke's standing rule — say what is
significant, never rank what matters most, because that is the
journalists' call: "the silences are significant", not "the strongest
material".

**Two detector honesty fixes, found by the release chain itself.**
`release_diff`'s last-panel slice ran to end-of-document and attributed
a −154 from the post-table views to the National Physical Laboratory
panel (whose links had gone 3 → 4); it now stops at its `</tbody>`.
And `export_duckdb` writes to a `.building` sibling renamed on
completion, after its half-written file at the final name was twice
mistaken for debris mid-build — the runbook's traps now carry the
general habit: `lsof` before touching anything a lock protects, and a
WAL is replayed by opening the file, never deleted.

**The readings input-hash earned its keep in both directions.** The
morning batch regenerated all twenty sample sites (their inputs carry
the corpus-wide profiles, which the day's corrections and materialise
had moved); the pre-release refresh then re-read exactly one (JVC) and
skip-confirmed nineteen, proving the corrections had in fact preceded
the batch. One wasted call surfaced a defect: `SITE-EN0110030` in
SAMPLE_SITES is a dissolved key — its site merged into PTNO-12913776 —
so its reading generated against zero documents and renders nowhere.

**Three regulator requests drafted** (docs/requests/): CCA site-level
consumption to the Environment Agency copied to DESNZ, the NESO EIR
for the project-level demand queue, the DNO template addressed to all
fourteen licensed plcs — each carrying regulation 5(6) against section
105 pre-emptively. Handed to Luke for the team and the sending.

**A site can be called what people call it** (issue #169, PR #173) —
`data/priors/site_aliases.yaml`, and it is recorded here late, on
2026-08-31, having been built on the 27th and never written up. The
omission is the reason this entry exists: two passes of the NESO
unmatched triage searched derived names and member application text,
found neither Quest Park nor Cato, and reported them absent. Both are
in the file by name. A curated prior that the project's own record does
not mention is a prior the next session will re-derive, badly.

**What it is.** A site's display name is *derived* — Barbour's project
title where a project anchors the cluster, otherwise the address of
whichever application sorts first — and that derivation routinely
produces a name nobody uses for the place. The file attaches a curated
alias to a live `site_key`, with a `source` line recording where the
name comes from, "documentary, never taste". Per principle 3 the alias
sits *beside* the derived name and never over it: the derived default
stays visible on the site's own page as a "Derived name" row, so a
re-materialise cannot clobber curation and the record still shows what
it is built from. An entry naming a key that is not live **fails the
build** — the `site_partitions.yaml` contract — because a key changes
when a cluster's anchor changes, and an alias that quietly stops
applying is a regression nobody sees.

**Why it exists.** A site nobody can find by its own name is a site a
reporter concludes is missing. That is not hypothetical: it is what
happened when the Guardian's team asked about Wapseys Wood, which was
in the corpus all along under the NSIP register's own name for it, "SDC
M40 Campus", with a display name taken from the register's location
prose — the words "Wapseys Wood" appear in neither.

**What it is also for, which nothing had written down.** The aliases
are the project's record of the reconciliation between the name a
developer uses and the name the planning record carries — a pit becomes
a park, a works becomes a campus, and the two registers disagree about
a word. Entries hold both: "Quest Park Data Centre, Quest Pit"; "Cato
Data Centre campus, Auchtertool, Fife (ILI Group)". **So any name search
against this corpus must search the aliases alongside the derived
names**, and one that does not has a systematic blind spot rather than
a random one, failing towards confident negatives. Luke, 2026-08-31:
"Quest Pit is the true location; Quest Park is the operator rebrand."

**How it grew.** Fifty-six entries by 2026-08-31, curated in batches
rather than in one pass — #174 (Bletchley), #236 (South Mimms), #237
(three surfaces were reading the derived name and never saw the alias),
#242 (title casing must not be enforced on a user-defined name), #244
and #283 (Luke's own runs, and the operator-pages fold). It is standing
curation of the same class as `organisation_aliases.yaml`, not a task
that completes.

---

## The evening 2.9 shipped, and the guards that were not guarding (2026-08-27)

2.9 merged at 14:15 (PR #165). The evening behind it collected two
OpenAI batches, put a long-standing request into the reader, and found
three guards that were not doing their job. Six branches, one change
each.

**The batches.** The deep-read collected 543 documents into **13,138
findings**, 234 rejected by the verbatim gate — 1.7%, against a ~9%
baseline. The readings batch stopped at site 157 of 250: a model had
emitted a NUL inside a quote, and Postgres refuses JSON carrying an
escaped `\u0000`. The deep-read path had guarded against this since a
NUL arrived in 460,000 findings; the readings path never had, and its
flat per-field version would not have reached this one anyway, two
levels down inside a quote object. A recursive strip at the database
boundary — never before the gate, because a NUL the source never
contained is evidence about the model — and the re-run collected
**238 stored, 9 withheld, 3 unparseable** (PR #176).

**The sites list now says which of its rows are datacentres** (issue
#159, PR #178). The class folds both generations of triage verdict
using the clustering's own CTE, and is derived at build time, never
stored. Measured: **434 datacentre, 48 disguise suspect, 8 adjacent
power, 23 procedural only, 8 no planning record** across 521 rendered
rows. It is a filter and a badge, never an ejection.

Two rules had to be added that the agreed spec did not anticipate, and
**both were found by measuring rather than by reasoning** — which is
why the spec demanded a measurement before any styling:

- Nineteen live sites are Barbour project records with no planning
  application, so there is no verdict to fold; the first query dropped
  them silently. Filing them as procedural would have greyed out real
  datacentres, so they get a fifth class saying what is true. Its value
  is `no_planning_record`, not `barbour_only`, because that string
  already means something different on `sites.classification`.
- A Barbour title naming a data centre now settles the class. The first
  build badged "John Innes — Norwich Bioscience Institutes **Data
  Centre**" a *Disguise suspect*, a class whose definition opens "no
  application here is stated as a datacentre" while the site's own
  record stated it. Six sites showed the contradiction; 21 changed
  class. Deliberately a title test, not a membership test: Barbour's
  harvest is a sector sweep, so having a project record is not the same
  claim as being called a data centre.

Driving it in a browser caught three defects the markup could not: a
filter control claiming 19 for a filter that produced 44 rows (the
count-honesty rule broken where a reporter would check it); pre-planning
rows classified by hardcoding rather than by the rule, which told
readers "Virtus Data Centres — London 3 Data Centre" was neither a
datacentre nor holder of a planning record; and a site page asserting
"at least one application here is a datacentre proposal" one sentence
before "no planning application here states a datacentre".

**A group and its own member were being counted as two organisations**
(PR #179). After Global Infrastructure UK Limited was confirmed under a
new Google group, the sites table showed a `Google` pill *and* "and
Global Infrastructure…" beside it. Not the `(Barbour)` suffix, which is
stripped: the badge is the group name while de-duplication compared raw
canonical names. The same "one organisation, once" rule fixed on
2026-08-26 for two spellings of one name, needed one level up. "and X"
suffixes fell **25 → 14**; the eleven removed were all group members
standing beside their own group.

**A pre-planning page did not state the parties its row asserted** (PR
#181). Three Barbour rows showed **Segro** in the Who column — sourced,
`CyName_Client = "Segro Plc"` — while the page a reader clicked through
to never mentioned Segro, because pre-planning panels carried no party
fields at all. A column the page cannot substantiate is the one thing
provenance forbids.

**The determinism test kept nothing, and the snapshot did not cover
everything** (PR #180). `test_two_builds_of_one_snapshot_are_identical`
had failed once and never since, so the evidence was never captured; it
now keeps both builds, both normalised texts and a capped diff. Both
suspected causes were largely eliminated — and set-ordering by argument
rather than inspection, since the two builds are separate processes with
independent `PYTHONHASHSEED`, so such a dependence would fail nearly
every run. The likelier cause: the Postgres snapshot pins the database,
but the reader also reads `data/exports/.drive_sync_state.json`, which
`drive_sync` rewrites per file. The test now voids a comparison whose
ledger moved, and says so when it did not.

**Readings had no freshness guard after generation** (PR #182). Four of
258 rendered readings were already stale, one keyed to a site retired by
that morning's merges. Rebuilding one site's input to re-hash it costs
**8.2 seconds** — 35 minutes for the corpus — so the check is split:
liveness on every build, and an offline verifier that records its
verdict append-only, under the model tag `freshness-check` so a stale
marker can never occupy the unique key a genuine reading needs.

**The sweep's per-application ceiling had never fired** (PR #183). The
900-second deadline raised an ordinary `Exception`, and the adapters
catch `Exception` per document so one bad link does not cost a bundle —
so the timeout was filed as one document's failure and the loop moved
on. SIGALRM fires once, so the application then ran unbounded:
`Southwark/18/AP/1604` reached **216 minutes**, and the sweep's rate
fell from 321 documents an hour to under 50. `ApplicationTimeout` now
derives from `BaseException`, where a per-item `except Exception` cannot
reach it.

Three of the day's lessons rhyme: a guard nobody has watched fire is a
guard nobody knows works.

## The corrections that landed between 2.9 and 2.10 (2026-08-26 to 2026-08-29)

Moved here from the ROADMAP once each closed; the residuals that
survive them are still there.

**`load_capacity_claims.py` was broken from the SPV work until
2026-08-26; fixed.** `companies-house-claims.yaml` gained claims with
`quantity_type: scheme_capacity` and `investment_property_fair_value`,
and no migration had added either value to the
`capacity_claims_quantity_known` CHECK constraint — so the loader
aborted on a check violation and rolled the whole batch back, taking
every source with it, NESO and the Environment Agency permits
included. Migration 030 added both types with the reasoning for each;
10 claims inserted, 234 → 242 in the store, the pending SPV figures
loaded with the Court Lane matches already adjudicated and six new
ones held under `considered:` because their site records were
over-merged clusters.

**The incomplete Drive archive was explained, and the fix landed**
(2026-08-26). `build_drive_staging.py` stages a document only if its
application has a live `site_members` row; 143 applications discovered
2026-08-07 had no membership until the materialise of 2026-08-25, so
their 3,679 documents were never in the staging tree and invisible to
the sync's `skipped` and `failed` alike. The 08-21 sync was complete
and correct over the tree it was given — the ledger-loss episode is
exonerated. Now in code: the staging build prints what it did not
stage grouped by verdict and exits non-zero unless every one is
`not_dc`; it refuses to build when `max(sites.materialised_at)`
predates the newest first_seen; `verify_drive_sample.py` samples the
universe rather than the ledger, whose old frame was structurally
incapable of finding a document that never reached the tree.

**`build_drive_staging.py` removes what has left a site** (closed
2026-08-26). It was additive: after a re-partition the old site folder
kept application directories that had moved away, so one document
existed under two site folders and `drive_sync.py` could not read the
move as a move. The tree is now written to a `.building` sibling and
swapped in — 65 seconds for 494 sites and 52,000 documents, free on
disk because the documents are hard links. The tree root stays
deliberately additive so published artefacts from earlier phases keep
resolving.

**Every OpenAI finding was missing its family, and two panels select
on nothing else** (found and fixed 2026-08-26). The INSERT in
`deepread_escalate_openai.py` omitted `signal_family`, so all 557,747
findings from the three OpenAI runs carried NULL — 46% of the corpus —
and no OpenAI finding had ever reached the EIA-process or parties
panels, silently. Fixed at source and backfilled the same day
(`backfill_signal_family.py`, `family_source='derived'`, originals
untouched): EIA panel 190 → 234 sites, parties 296 → 304. The 49,039
local-model findings predating migration 009 were backfilled by the
same command. And `\b` cannot end a snake_case token — `eia\b` never
matched `eia_status` — corrected by writing the boundary over the
characters a label token is made of (`TOK_END`/`TOK_START`), re-run
scoped to `derived` rows left `unclassified`: EIA 234 → 239 sites,
parties 202,223 → 209,875 rows. Four editorial questions from that
measurement stay on the ROADMAP.

**The pre-build tail assertion** (2026-08-27): every export prints the
count of power-unit findings with no verdict from any model, beside
the corrections gate. Report-only by design, empty at the 2.9 build.

**The export-limit correction rule** (2026-08-27): 23 rows demoted,
value-adjacency not vocabulary, one pinned instance. Kingsnorth's
47,405 kW leading/lagging pair stays on the ROADMAP as a person's row.

**Reading freshness** (2026-08-27): `load_latest(live_only=True)`
drops readings whose site key retired — free, every build — and
`verify_reading_freshness.py` does the exact half offline, append-only
under the `freshness-check` tag so it can never occupy a real
reading's key. Where it runs in the release chain is still the
ROADMAP's question.

**The sort glyph no longer breaks onto its own line**: `th:after`'s
content now opens with a non-breaking space, binding ↕ to the
heading's last word — the remedy the ROADMAP item proposed, verified
in the CSS 2026-08-30.

**The alias groups outgrew their checkpoint** (verified 2026-08-30).
The ROADMAP had held "confirming the rest of the alias groups" at its
2.4-era snapshot — eight of ten seeded members confirmed, one
proposed. `organisation_aliases.yaml` now holds 12 groups with 31
confirmed members and 2 proposed, Luke confirming as the work finds
them (the Greystoke SPV group landed 2026-08-30 from the operator
pages review). The residual curation is standing procedure, the same
class as site aliases.

**`drive_sync` concurrency** (2026-08-29): the `--workers` flag
existed all along, defaulting to 1; the default is now 12, after a
58,799-file sync spent 9h16m reaching 54% because nobody passed the
flag. Batching and an atomic ledger write remain open.

**The search bundles' delta became computable, and the bundles joined
the chain** (2026-08-28/29; recorded here 2026-09-02 when the ROADMAP
item closed). The Pinpoint/Giant bundle last uploaded on 2026-08-12 had
its `_manifest.csv` — one row per bundled file with sha256, site, kind,
tier and action — on the previous laptop; retrieved 2026-08-28 to
`data/exports/pinpoint_bundle/`, it lets `export_pinpoint_bundle.py
--already-uploaded` build only what Pinpoint does not already hold,
with the deliberate exclusions separable from the genuine gap. The
notebook, Pinpoint and Giant bundles then became runbook step 13a
(Luke, 2026-08-29): they had been "off the chain, optional, local",
which is how the notebook came to be three releases stale and the
search tools four. Tranche 5 shipped with 2.11.

**The three Section 35 sites are no longer empty** (verified
2026-08-30). The ROADMAP had recorded Quest Park, Dartford and the
Wapseys stub at 0 documents and 0 findings each — a named site with no
evidence being the same failure that once made the Guardian's team
conclude Wapseys Wood was missing. As verified: Quest Park holds 435
documents and 5,672 findings, the Wapseys/SDC M40 site 8 and 2,838,
Dartford 7 and 97 — every one now reads as a site rather than a stub.
**The computed scale panel** (issue #166, shape agreed 2026-08-27,
shipped in the 2.10 build): "The rest of the package" — a button
pointing at content one scroll away — replaced by "The scale of what
the documents disclose", every figure computed at build and never
typed, every row linked to the query or cohort that produces it,
caveats in the panel's own words. The
12.73-GW-is-twelve-million-households correction that settled the
framing is the argument in one line: computed and citable beats vivid
and wrong.

## The relist audit measured the shortfall, and the refetch recovered the class that mattered (2026-08-26)

Historical partial fetches were invisible: a short fetch was recorded
as complete, and the manifests record what was stored, not what was
offered. `scripts/relist_audit.py` settled it by re-listing and
comparing, landing in `document_listing_audit` (migration 026,
append-only, idempotent on the listing's content hash), in three
passes cheapest first — snapshot HTML already held (1,166
applications at no portal cost), harvested Salesforce listings (64),
then live re-lists through the project's own adapters.

**As measured: 1,554 of 1,696 document-holding applications, and
2,260 URLs the registers offered that the corpus did not hold** —
never "2,260 documents missing": the refetch proved 62% of a 3,083-URL
sample byte-identical to documents already held under different URLs
(Buckinghamshire PL/24/0754/OA downloaded 170 and created no rows).
**1,380 of the 2,260 were then fetched (61%), and 249 of the 291
reports and statements (86%)** — the class where power disclosures
live. Northumberland Energy Park recovered 176 of 177 absent
documents, 161 of them reports and statements. 229 per-document
failures each carry a reason; Greater Cambridge's blanket 403 on file
downloads (158) and Tower Hamlets' persistent 504s on two energy
strategy reports are the genuine portal refusals. What was
deliberately deferred — Union Park's 157, Gilmorehill's 491 — stays on
the ROADMAP with the resume commands.

## Six models on the validation cohort (2026-08-28)

Written up on 2026-09-02, when the model discussion moved out of
ROADMAP into `docs/MODELS.md` and this comparison turned out never to
have been recorded in the repository at all — the decision it produced
had lived in a session's notes for five days. The figures are that
session's. What corroborates them here is `data/openai_measured_usage.json`
(126 requests each for `openai:gpt-5.6-luna` and `openai:gpt-5.6-terra`
over identical input, with terra at 1,210 output tokens a request) and
the roster counts in ARCHITECTURE; `scripts/compare_readers.py`
re-measures the rest against the database.

Five readers on the 60-document validation cohort (the gpt-5 variants
had reached 21 of the 60): `gpt-5:low`, `gpt-5.6-terra`, `gpt-5.6-luna`,
`claude-sonnet-5` and the local `mlx:Qwen3.6-35B-A3B-4bit`; `gpt-5.6-sol`
stalled at 124 of 126 requests and was never collected. **Terra beat
`gpt-5:low` outright** — level on the power families (3.9 against 4.0
findings per document), half the output tokens (1,210 against ~2,194
per request), half the label-splitting (24 against 51 quotes carrying
two or more signal types). **Luna was rejected despite the highest raw
yield** (49.5 findings per document — 1.58× overall but only 1.25× on
the power families): the extra was site identity, consultants, bat
roosts and ground gas, 69% of its findings carried a signal type used
nowhere else in the cohort, and it duplicated facts under
near-identical labels. **Sonnet found half the power material** (2.0
against 4.0) and was the most disciplined reader by every quality
measure. The local model was last, at 7.4 findings per document.

**Decided** (Luke): Sonnet and terra are the model choices for future
deep-read phases, and the phase in progress stays on gpt-5 — "we should
stick to gpt5 for consistency in this acquisition phase." A corpus read
by two models is a corpus whose coverage differences are partly an
artefact of which model saw which document, and this comparison had
just measured that effect at 2.0 against 4.0. A better model is a
reason to plan the next phase, not to switch inside one.

**Two measurement lessons outlived it.** All three serious readers
invent at about the same rate, roughly 1% of findings, so the raw gate
rate does not rank them. And the gate rate was actively misleading:
63% of luna's rejections were whitespace artefacts against 37% of
Sonnet's, because a model that tidies broken PDF text was penalised
against one that copies `d ata centres` verbatim. The same day's
measurement of the gate over a 900-rejection sample (~37%) became the
gate fix (PR #295) and the re-gate (PR #298), measured corpus-wide
three days later at 29.8% of rejections.

## v2.10 (2026-08-29/30)

Rebuilt in place across the 29th and 30th — Drive and the Google
Sheet brought current on the 30th, artefacts in
`data/exports/phase2.10_build/`, with `phase2.10_prior` kept as the
release-diff baseline — and released (Luke, 2026-08-30). The corpus
work of 2026-08-30 (the operator pages day, the adjacent-power chain,
the Kao merge — below) landed after the build and renders at the next
one, which builds on 2.10 as its base.

## The operator pages day (2026-08-30)

Issue #255 — "link the operator's web page" — turned into the largest
single-day advance the external-claims channel has had, because Luke
reviewed every pairing by hand and the review kept finding things.

**The review sheet** (`data/operator_pages_review/`, 68 rows, four
tiers by provenance plus his own additions): every site→page pairing
verified, three response columns (use the URL; notable claims on the
page; proposed alias), an actions column that became a work queue, and
a `page_kind` split after Luke realised corporate and consultation
sites say different things to different audiences.

**Shipped from it, same day:** `data/priors/operator_pages.yaml` (39
pairs, kind-labelled) with `dcp/operator_pages.py` on the
site_aliases contract and reader links labelled by audience (PR #265);
thirteen new snapshot pages including all nine consultation sites and
the Cato architect's page, every existing page refreshed to the
review's own read date (PR #267); eighteen new operator claims and
nineteen matches, every quote verified against a same-day snapshot
(PR #270) — Vantage Cardiff's 148 MW, issue #250's headline unmatched
claim, among them; aliases folded with the sheet winning on conflict;
and the Kao Harlow merge (PR #268) — Project Nobel's Barbour pin was
2.1 km from the campus its own application names, corrected by ptno
override, one site retired, key preserved.

**The decision over it: typed standing, not equal standing** (Luke).
First-party operator statements about their own facilities may become
a labelled rung on the declared-power ladder; third-party aggregates
stay tier-and-count. A recorded revision of the 2026-08-20 no-raw-MW
ruling's scope — that ruling was about comparability, and a labelled
rung is how the ladder already handles incomparability.

**The audiences finding, five for five and snapshot-backed:** every
reviewed site holding both kinds states MW on the corporate page and
nothing on the consultation page (East Havering 600, West London
Technology Park 90, Iver Heath 90, Abbots Langley 96, Humber 384 —
three of those from Greystoke's single listing page, whose figures sit
against zero MW mentions in all three schemes' consultation-site
snapshots). Apatura is the counter-example that sharpens it — its
consult pages state MW, and they are also its only scheme presence —
and Colt runs the other way, publishing 31 MW against larger planning
figures. Working hypothesis, Luke's endorsement: one page, one story;
two pages, two stories.

## Adjacent power leaves membership (2026-08-30)

Issue #252, opened in the morning out of the Stockley Park question
and shipped end to end the same day — stages, corrections to its own
premises included.

**Stage 1** (PR #253): migration 032's `site_adjacent_power`,
`dcp/adjacent_power.py`, materialised — 114 relationships across 42
records and 66 sites, tiered discovery/cohort/proximity, changing no
output. **The survivor check** (on the issue, with its query)
corrected the section's own claim before implementation: "seven
headline figures go" was measured with the wrong ladder; with the
reader's own preference order exactly two sites changed, because a
scheme restates its capacity across its own applications —
Kingsnorth's 49.9 stood on a `new_build` member, Colt fell to its own
3.2 MW disclosed IT load. **Stages 2 and 3 together** (PR #269,
decisions Luke's): the clusterer vetoes the `adjacent_power` verdict;
the reader renders an "Adjacent power" box — documentary rows as
entries, proximity as a count, because 71 distance-only rows rendered
as peers of 39 documentary ones would read as endorsement by volume.
Eight sites retired, not the predicted six — Hallen's and Barking's
remnants were not sites by the classifier's own rules — and the two
university leads (the Plymouth generator, Northampton's Newton DRUPS)
dissolved into a tracked ROADMAP note. **The veto had two more doors**
(PR #271, found by running it): project-linked applications join their
project's cluster regardless of the universe test, and the family
expansion re-admits a vetoed record when an in-universe discharge
cites it — 18 of the 42 sited records came straight back before both
paths honoured the veto. The Barbour linkage survives as a documentary
cohort relationship; two procedural singletons stranded as tracked
warts of the typed-`parent_ref` gap. End state, verified: zero
adjacent-power memberships, 501 live sites, 110 relationship rows.

**And the Kingsnorth follow-up dissolved on measurement** (PR #273).
The export figure was never the site's published headline — the table
showed 39.724 MW disclosed total site demand all along; "shows 49.9"
was the all-quantity-types max, the same conflation the survivor check
caught. What was genuinely wrong on published pages was five sites
ranked on the generation rung with plant the generation adjudication
calls `prime_combustion` or `renewable` — "standby generation … sized
to carry full load" asserted against energy-park export plant, two of
them wearing the sub-50 MW DCO threshold cap as if it were demand.
Fixed by making the ladder's generation rung honour `plant_type` in
both consumers; mixed and unclear keep their behaviour, because
exclusion needs a positive adjudication. Heyford Park 49.9 → 23.5,
three sites → a reportable absence, Kingsnorth untouched.

---

## The NESO triage, and a day spent re-deriving the record (2026-08-31)

**The alias fold from the operator-pages review landed** as PR #283 —
eleven operator-named site aliases, three renames, and the Greystoke
Land group with the Elsham and Humber Tech Park SPVs on Companies House
PSC evidence. Two loose ends closed with it. The Vantage ↔ Next
Generation Data organisation alias was **assessed and not written**:
zero organisation-name fields anywhere in the corpus contain "Next
Generation Data", which survives only in three Barbour *project titles*,
and all three of those projects already name Vantage Data Centres
Limited as client and end user, already resolving to the Vantage group.
A member keyed `nextgenerationdata` would have matched nothing. The Kao
KLON-03 merge turned out to have shipped the same evening it was
proposed (#268); only the prior's note still called it pending, fixed in
#286.

**The NESO register's unmatched rows were triaged** —
`docs/NESO_UNMATCHED_TRIAGE.md`, PR #284. **61 of the 106 are not
data-centre schemes at all**: the register lists transmission demand
customers of every kind, and the cohort is dominated by hydrogen
electrolysis, HS2 traction supply, carbon capture, steel and battery
storage. The actionable pool is 29, not 106, and after reconciliation
only six candidates are new. Cato is the strongest — `PTNO-12917829` is
aliased "Cato Data Centre campus, Auchtertool, Fife (ILI Group)", it
sits beside the Mossmorran substation the register names, and a
contracted 600 MW meets the architect's 600 MW and a stated 600 MW
`it_load`. The same documents also state 850 MW `it_load`, so that is
three quantity types landing on one number rather than three sources
agreeing, and the document says so.

**Two ROADMAP claims were corrected by it.** Global Switch London East
87 MW and London South 70 MW, named as the headline unmatched examples,
are not in this register at all — no row anywhere in the workbook
mentions Global Switch and no demand row is valued 87 or 70. They are
`operator_website` claims from globalswitch.com, belonging to a
different row of the ROADMAP's own table.

**The Green Energy Centres are not gas, and this file's own source
document said they were** (PR #288). `EXTERNAL_DATA_SOURCES` §3 placed a
cluster of "Green Energy Centre" projects inside its 139 gas rows; the
live TEC register has 52 GEC rows across 42 schemes and **not one
carries any gas term** — the plant types combine `Demand`, `Energy
Storage System`, `PV Array` and `Wind Onshore`. Of 102 rows whose plant
type names a gas technology, exactly one has a green-energy name, and it
is a *Hub*. The error was quoted onward into ROADMAP and the triage
before it was checked. What survives is better grounded and weaker, and
is now a coverage gap: nineteen of those schemes hold 8,660 MW of
transmission demand, almost every one is named after the substation it
connects at, and **none has a planning application in this corpus**.

**Four passes over one triage, each of the first three re-deriving
something the repo already held.** Pass 1 walked into the trap this file
records under the runbook's own heading — a probe that cannot see what
it is looking for — and filed Quest Park as absent when the corpus holds
it as Quest **Pit** with 435 documents. Pass 2 swept every local
authority to reach by geography what `site_aliases.yaml` names outright.
Pass 3 found that `environment-agency-permit-matches.yaml` had already
articulated two causes of unmatching the new taxonomy lacked. Pass 4
found the matches file's own `considered:` section, which had
adjudicated **24 of the 106 rows on 2026-08-20** and was invisible
because the probe counting it looked for a `row:` key where the file
uses `rows:`. Several of those earlier judgements are better than what
the triage produced independently, and the Iver rows were withdrawn on
the strength of theirs. One is overturned: Quest Park was recorded there
as having no corpus site.

**What came out of that, and is the durable part.** `AGENTS.md` (PR
#292) — a task-level entry point, the slot for which was empty: routing
only, restating nothing, with three rules ahead of it. Read whole files,
because corrections here are appended rather than applied and stopping
early leaves you implementing something already retracted. Read the data
before the prose about it. Check whether a thing exists before proposing
it, with the names of the sections that exist to answer that. It also
carries the PR discipline Luke set the same day: carry the documentation
your change makes stale, grep for the same claim elsewhere, and say in
the PR body what you searched for.

**Then the backlog that discipline cannot reach** (PR #293): corrections
appended while the superseded text was left standing. `nsip_research`
recommended the gov.uk `filter_format=publication` parameter and used it
in its worked query, while its addendum forbids it because the Section
35 directions publish as format `decision` — implementing from the body
rebuilt the bug that had already cost the Bedford and Dartford
directions. Three passages still had EdgeOne publishing, four months
after it became a redirect. Two runbook step numbers cited the scheme
the runbook itself warns is superseded. "No Google Fonts" still stood in
a section whose own header said it should read "no LINKED web fonts".

**And `site_aliases.yaml` got its entry here** (PR #287), having been
built on 2026-08-27 and never written up — the omission that cost two of
the four passes above.

---

## The re-gate reinstated the findings the gate had wrongly rejected (2026-08-31)

Moved here from ROADMAP on 2026-09-02, where it had stood as three
items — the gate fix, the machine-reading gate's squash and the
re-gate — with a DONE block appended to the third while the first still
said the re-gate had not run.

**The finding.** pypdf splits words at line breaks and around units,
so a page's cached text reads "acro ss the site", "d ata centres",
"940 µ g/m 3"; a model that quotes the passage correctly then fails a
gate comparing it against the broken text. A 900-rejection sample on
2026-08-28 put the loss at ~37%. Measured corpus-wide on 2026-08-31
over every one of the 50,517 `quote_failed_verification*` escalations
with cached page text: **29.8% were correct quotes** — 68.8% genuinely
absent under any normalisation, which is the gate working; 1.4%
already passing the normaliser's newer dash, glue and quote rules; 0.1%
on a page out of range — and 36.4% among the 1,144 rejections carrying
a numeric power unit. Median recovered length 122 characters, first
percentile 26, so the guard was set at 25: the 20-to-24 band is
repeated single-word labels ("GENERATORS GENERATORS") that verify
almost nothing, and excluding them costs 0.7% of recoveries.

**The fix** (PR #295): `verify_findings.fragments_present` falls back to
a whitespace-blind comparison behind that minimum-length guard, every
reader routes through it, and 14 tests hold it. The machine-reading
gate's squash — whitespace-blind since gate-1.2 with no minimum at all
— took the same guard as `gate-2.1` (PR #296), riding on the model move
that re-read every site anyway.

**The provenance question answered itself from the record.** An
earlier version of the item called the reinstated rows' model tag a
decision for a person, on the false premise that the prompt version in
force was lost. `deepread_log` carries `(document_id, model,
prompt_version)` for every read: 50,556 of the 50,565 escalations
resolve to exactly one pair, nine do not, and `prompt_version` is `1.0`
on every reader. So a recovered row carries the pair that produced it.
A synthetic `regate/<reader>` tag was rejected twice over — it would
assert a model that never read the document, and `model` and
`prompt_version` are in the `ON CONFLICT` content key, so it would make
every row permanently un-deduplicable against a genuine re-read, the
mechanism behind the 20,377 duplicates that predate the unique index.
Separability came from a new column instead: migration 033 adds
`findings.gate_version`, NULL for existing rows and set for re-gated
ones, matching what `site_machine_readings` already recorded.

**The write** (PR #298, `scripts/regate_escalations.py`). Dry run:
15,679 recoverable — more than the 15,042 measured earlier, because the
script searches the runners' own candidate order (the claimed page, its
neighbours, then the other pages sent) and never a page the model was
not shown; 34,877 stay absent under the fixed gate; 9 dropped as
unattributable. By original reader: 6,501 `openai:gpt-5:minimal`, 4,404
`openai:gpt-5:low`, 2,726 `claude-sonnet-5`, 1,965
`mlx:Qwen3.6-35B-A3B-4bit`, 83 `openai:gpt-5.6-terra`. **14,111
inserted; 1,568 already present** — findings a later successful read
had also produced, which the content key deduped on the true pair and
which the synthetic tag would have duplicated. Findings stood at
1,378,147 afterwards, the cohort separable on `gate_version =
'gate-2.1'`.

**Downstream, run in the same pass: under $6, and less churn than
predicted.** The power-unit tail was 385 after dedup, not the 416
measured before it; the adjudication batch ran 843 figures across 73
requests with nothing truncated, `correct_adjudications.py` fixed 14
(one `thermal_not_electrical`, six thermal-output-with-no-electrical,
seven `export_limit_not_connection`) and re-ran clean, and generation
added 51 with 2 correctly refused on span verification. The label
audit's cap analysis held — the reader renders the top 40 findings per
site and 91% of sites were already at the cap, so rendered moved
13,679 → 13,684, displacement not accumulation — but its churn estimate
did not: 270 findings across 7 requests, 269 verdicts, **47 flagged as
misfiled, 17.5% against the corpus baseline of 18%**. The reinstated
rows are no worse filed than what was already on the pages, which is
the null result the worry about the local reader's 1,965 recoveries
needed.

**Why it ran before the campus work.** Of the 50,565 quote-failure
rows, 15,111 carried a numeric value and 1,207 a numeric value with a
power unit, concentrated in `on_site_power_generation`,
`grid_connection` and `grid_connection_capacity` — the families the
facility prior and the campus-scope review reason over. Adjudicating
campus scopes against a corpus still missing them would have meant
redoing some of that adjudication when they landed.

---

## Terra read every site, and the readings went back to gpt-5 (2026-08-31)

Moved here from ROADMAP on 2026-09-02; the tables, the cost derivation
and the open items are `docs/MODELS.md`. This is the record of what
happened.

**The move** (PR #296, Luke's decision on quality). Six sites read on
both models at the same reasoning effort — gpt-5 at `reading-1.2`,
terra at `reading-1.3` — showed terra naming figures where gpt-5 named
categories, tying silence to the structured facts rather than
reporting "no figures in the pages", flagging naming discrepancies as
discrepancies, and catching a conditional green claim. It applied the
2026-08-28 model choice at a phase boundary, which is what that
decision said to do, and two parked changes rode on the re-read it
implied — the accumulation rule working as designed: `GATE_VERSION` to
`gate-2.1` (the squash's 25-character guard, which main was already
running under the old version string) and `PROMPT_VERSION` to
`reading-1.4`, which added one duty — name any adjudicated figure whose
quantity type contradicts its own quote, Luke's suggestion, validated
on the six sites first. The script's default `--model` became terra.

**The full run — 346 sites, collected clean: 346 stored, 0 withheld, 0
unparseable — contradicted the pilot.** Over the 344 sites both models
had read, terra stated 0.89 power figures per site against gpt-5's
2.75, and 21.8% of sites carried any figure against 33.1%. It was not
reading less — it produced more quotes per site than either gpt-5 arm —
it had shifted from stating figures to quoting the text around them.
Three arms on 17 sites at `medium` effort separated model from prompt:
`reading-1.4` *helped* gpt-5 (6.65 → 8.53 figures per site, and on
Didcot from 2 distinct figures to 15, including the `150MVA` and
`192MW` the pilot had credited to terra), while terra on the same
prompt stated 2.18. On Elsham gpt-5 stated the 1,000 MW campus load in
four places and terra in none. But terra was erratic rather than simply
worse — `reading-1.3` → `1.4` on six sites took Didcot 8 → 0 and
Watford 6 → 0 while Union Park went 0 → 10 — so its prompt-to-prompt
variance was nearly as large as its gap to gpt-5, which is why what
survives is a prompt A/B rather than a verdict. In terra's favour, the
pilot's open question was answered: it flags quantity-type errors well,
four in one Elsham reading where gpt-5 at `reading-1.2` caught one.

**Why it was urgent.** `LATEST_SQL` renders the newest reading per
site whatever version made it — deliberately, so a re-read the gate
refuses shows as withheld rather than falling back — and after the
collect 331 of 363 sites would have rendered terra. The append-only
store preserves the history; it does not protect the page. Nothing
reached a reader: no build ran between the collect and the fix.

**Decided** (Luke, PR #304): re-run on `gpt-5`/`reading-1.4`, the best
arm on every column and the only one keeping the new prompt's flagging
without the figure loss — about $33 against terra's $59, terra
reasoning roughly 2.3× harder for 6% less visible output. A deferral of
the terra decision rather than a reversal: gpt-5 is legacy at OpenAI,
so this bought correctness rather than a durable answer.

**Done the same evening — 331 requests, 0 failed — and the outcome
beat both arms it was chosen between:** 4.23 power figures per site
and 40% of sites carrying one across the 361 rendered readings, against
terra's 0.89 / 21.8% and the `reading-1.2` baseline's 2.75 / 33.1%. The
prompt change was worth more than the model change: it lifted the
figure rate 54% above where the corpus stood before either was tried,
and any A/B is to be scored against that, not the old baseline. What
rendered: 349 sites on `gpt-5`/`reading-1.4`, 13 still on `reading-1.2`
with no new input to read, one on terra
(`SITE-CentralBedfordshire/CB/23/02827/DOC`, which the batch did not
cover), and two withheld by the guard for the right reason — the
site's inputs changed between submission and collection. The sample
cache learned to key on the model as well as the prompt (PR #303): six
sites held terra answers at `reading-1.4`, and a gpt-5 run would have
re-used every one and recorded gpt-5 as their author.

**Cost, measured from the batch files and confirmed against the OpenAI
console.** The 2026-08-29 batch — 182 sites alone overnight — cost
$16.98 for 15,817,922 input and 1,439,745 output tokens; per site
71,865 in and 8,228 out, of which 5,849 was reasoning, invisible in
the stored reading. A full run is about 26M in and 3M out, about $34
on gpt-5, correcting an earlier "roughly 15M input tokens" that was
this batch's own figure mistaken for a full run.

---

## The snapshot store becomes append-only (2026-09-01)

The claims channel had kept every reading of a claim since it was built,
and the evidence behind those readings had not. `capacity_claims` holds
CyrusOne LON1 at 8.72 MW on 2026-08-20 and 9 MW on 2026-08-28 — both
rows, deliberately, because an operator replacing a precise published
figure with a round one is a fact about the disclosure. But
`fetch_operator_snapshots.py` wrote one file per slug and overwrote it,
so both rows named `cyrusone-lon1` and the file that name resolved to
contained only the 9. The 8.72 quote survived in a commit message.

**It was latent, and it was the wrong-document failure one layer up.**
LON1 was the only claim with two readings and neither is matched, so
nothing had yet rendered a claim its own evidence contradicts. What it
blocked was the next step: syncing snapshots to Drive so that "our copy"
means the same thing for a claim as it does for a document. Doing that
first would have put an "our copy" link on a file that does not support
the claim beside it — precisely what `document_drive_files` exists to
prevent for documents, and for the same reason.

Fixed on the shape the directory's own README had asserted all along:
*never mutate a snapshot; a re-fetch adds a new dated file beside the
old one.* The operator store was the one place under
`data/external_sources/` that did not keep that rule.

**Dated, not content-addressed** (Luke's call). A content hash makes an
unchanged re-fetch a no-op for free, which is why the sha256 stays in
the file header and is what the fetcher now compares against — but the
name a reporter sees on Drive has to mean something, and a date sorts
and reads where a hash does neither. So `<slug>.<YYYY-MM-DD>.txt`, with
the hash doing the deduplication behind it.

**One character of the naming was decided by sort order.** The spec's
same-day suffix was `-2`; `-` sorts before `.`, so `slug.2026-09-01-2`
would have sorted *ahead* of `slug.2026-09-01` and the day's second
reading would have looked like the older one. `_` sorts after `.` and
does not. The resolver sorts on the parsed date and sequence rather than
on the raw string, so the property holds however the store is filled,
and a test asserts the names a run produces come out in the order they
were written.

**The resolver is one function, because five call sites were the
hazard.** "Which file evidences this claim" is now
`capacity_claims.snapshot_path`, and the claims loader, both quote
checks and the facility prior's held-copy rule all ask it. Nothing else
in the repository constructs a snapshot path — checked by grep, and the
reader reaches snapshots only through those modules. That is the
`dcp/drive.py` lesson applied a second time: a rule about how to address
something survives as a shared function, not as a thing to remember.

The 81 committed files were renamed by `scripts/migrate_snapshot_names.py`
from the `# fetched:` date each already carried, so the migration
invented no dates and a file whose header could not be read would have
been left alone and reported rather than stamped with today. `git mv`,
so the history carries renames and the diff stays readable.

Written as WP-A of `docs/HANDOVER_SNAPSHOT_CHAIN.md`, and WP-B — the
Drive sync it unblocked — followed the same day (below). What remains
there: the reader and workbook links, which must resolve a claim to the
snapshot that existed at its `as_at` rather than to today's; the Iron
Mountain capture; and the ladder-rung design document.

---

## The snapshots reach Drive (2026-09-01)

WP-B, and it could only run because WP-A had run first. "Our copy" means
Drive everywhere else in this handover — a planning document links the
copy this project holds, with the council's register beside it — and a
capacity claim's evidence did not. It meant a file in a git repository,
which is not something a reporter checking a figure should have to know.

**Nothing was uploaded while the store overwrote in place.** Syncing
then would have put an "our copy" link on a file the claim beside it no
longer matched: the wrong-document failure `document_drive_files` exists
to prevent, one layer up, and the reason WP-B was blocked rather than
merely later.

**A committed ledger, not a table**, which was the one design choice the
spec left open. `document_drive_files` is a table because a document is
a database row and its id is the key. A snapshot is not: it is a file in
this repository, cited by name from committed YAML — the claims file,
the green-claims file, the facility prior. Its Drive id is a fact about
a committed artefact, so it lives in git beside it, survives a database
rebuilt from migrations, and arrives as a reviewable diff rather than as
an invisible insert. `data/external_sources/operator_snapshots_drive.yaml`,
read by `dcp/snapshot_drive.py`, keyed on the snapshot's own filename —
not its slug, because the store is append-only and one slug has many
readings.

**Folder creation is an asked-for act, not a side effect.** The grant is
`drive.file`, so a name query that finds nothing creates a duplicate;
that is how a second copy of the whole archive once came to exist at My
Drive root, both trees holding 429 site folders. So there is no name
resolution in this script at all — a test asserts the source contains no
`.folder(` and no `files().list`. `--create-folder` makes the folder,
reads the created id back to prove it landed under the handover root,
prints it, and stops; the id is pasted into `dcp.drive.SNAPSHOTS_FOLDER_ID`
and every later run addresses that constant. A 404 on it stops the run.
There is no fallback to creating one, ever.

**Every id was verified before it was written.** Drive computes md5
server-side, so each upload is read back and its md5 checked against the
local bytes and its parent against the snapshots folder. An id failing
either is reported and not recorded, on the same argument that took the
`file://` anchors out of the reader: a link resolving to the wrong
evidence is worse than no link.

**Checked at the far side, not from the log** — the lesson this file
already carries, applied. Listing the folder through the API: 81 files
on Drive, 81 in the ledger, 81 held locally, no name in any one of the
three missing from the other two, and every ledger id and md5 equal to
what Drive reports and to the local bytes. The sync is in the chain as
runbook step 11a rather than left to be remembered, and it runs before
the build that publishes `index.html` for the same reason step 11 does.

What remains is WP-C: rendering the link. The rule that needs care is
that a claim links the snapshot that existed at its `as_at` — CyrusOne
LON1's 2026-08-20 reading has to reach the 8.72 MW page, not the
2026-08-28 one that says 9. *That rule was necessary and not
sufficient, and the entry below says why: the 8.72 MW page is not held
at all, so a date rule would have landed the row on the 9 MW file it
contradicts. The quote is what discriminates.*

---

## Iron Mountain's pages are held, and the benchmark campus was not being measured (2026-09-01)

WP-D. The campus this project cites as its second self-auditing
operator — 61 MW stated, 8.7 + 27 + 25 = 60.7 across its own three
facilities — rested on pages nobody held. ROADMAP had the figures and
the reason they were uncitable; what it did not have was a copy.

**The block is Vercel Attack Challenge Mode, which is why backoff was
never going to work.** Every scripted client gets `HTTP 429` from the
whole host, its own homepage included, carrying
`x-vercel-mitigated: challenge`. Four header profiles were tried — the
fetcher's own UA, a current Chrome UA, the full `sec-ch-ua` and
`Sec-Fetch-*` set, and the exact UA of a browser that passes — and all
four got 429. The answer was an instrument change, not patience.

**The harvest is generalised rather than one-off.**
`fetch_operator_snapshots.py --from-file` stores bytes captured in a
browser through exactly the `render()` a direct fetch uses, so the
snapshot format cannot fork, and writes `# obtained: browser` in the
header — the same provenance the document store keeps per document.
`# obtained:` sits *below* the digest deliberately: everything that
reads a fixed number of header lines reads from the top, and a digest
pushed out of that window would have made every re-fetch look changed,
silently breaking the append-only store's no-op property.

**Two rules travel with it, both in docs/PORTAL_NOTES.md.** Harvest the
bytes the server sent, never the browser's rendered text — content
inside a collapsed `<details>` accordion is in the DOM and not in the
rendering, which is exactly how these figures were once reported as
published nowhere. And the URL comes from the script's curated `PAGES`
rather than the command line, so a snapshot always names a page this
project chose.

**What it produced**: three pages held (`lon-2` 404s and has none),
five quote-verified claims, five matches to site 529 — the site holds
all three facilities, so unlike VIRTUS Slough its campus total is
matchable — and an `operator_roster` identity for each facility beside
its planning or Barbour one. LON-1's own page says 8.75 MW where the
campus FAQ says 8.7; both are held and only the FAQ figure is a
component, or the building would be counted twice and the self-audit
would break. The three areas that page gives for one building —
17,000 m², 10,400 m², "14.000 square meters" — are recorded as a
divergence for the operator to settle, never averaged.

**And the benchmark was not being measured.** VIRTUS Saunderton is the
campus this project calls the exact self-audit, the standard for when a
sum can be trusted at all, and the one WP-E is meant to design against.
Its four facility claims carried no `component_of`, so
`reconcile_components()` had never included it — the arithmetic was
asserted in three prose files and computed nowhere. Fixed here, since
WP-D's own outcome was stated as "Iron Mountain beside Saunderton". The
five campuses now report:

| campus | stated | its own rows | gap |
|---|---|---|---|
| VIRTUS Saunderton | 78.0 | 78.0 | 0 |
| Iron Mountain London | 61.0 | 60.7 | 0.3 |
| Kao Harlow | 71.0 | 71.2 | −0.2 |
| VIRTUS Slough | 145.5 | 132.2 | 13.3 |
| VIRTUS Stockley Park | 112.5 | 72.5 | 40.0 |

A gap is not an error: Stockley's is a denominator (two of five
facilities disclose nothing), Slough's is a question for the operator,
and Kao's and Iron Mountain's are integer totals over decimal
facilities.

---

## The intermittent determinism failure was caught, and it was a rule that had never been implemented (2026-09-01)

`test_two_builds_of_one_snapshot_are_identical` had failed once on
2026-08-26 and passed every run since, and the ROADMAP's open question
was whether a failure would ever come with the drive ledger held. One
did, during an unrelated review. The evidence the test was taught to
keep — both builds, both normalised texts, a capped diff — was on disk,
5.8 KB, and it named two sites and one field:

    - Applicant of record: CityFibre, Euro-Tel Design (documents)
    - Advisers:            Cluttons LLP, TEP - Gateshead (documents)
    + Applicant of record: CityFibre (documents)
    + Advisers:            Euro-Tel Design, Cluttons LLP (documents)

on Redcar/R/2022/0351/FF, and `CityFibre, Michael Bingham` against
`CityFibre, R8 Tool Hire Ltd` on Uttlesford/UTT/23/2686/FUL. Neither
suspected cause was involved. The drive ledger was held, and the
snapshot did pin the database.

**The defect was `site_parties`' "one organisation, one role" rule.**
The extractor files a name under whichever family the sentence it read
suggested, so a firm can arrive as both applicant and adviser; the
family that names it most often wins. That comparison was a strict `>`
over the mention count alone, so when the two counts were EQUAL the
winner was whichever family the dictionary iterated first — and that
dictionary was built in the order Postgres returned rows in, from a
`PARTIES_SQL` whose own comment admitted it had no `ORDER BY`. Michael
Bingham, "Associate Planner at Murray Planning" in the documents that
name him, is filed twice as the applicant and twice as the adviser.
Which he was depended on the plan.

**The comment stated a rule the code had never implemented**: "ties go
to the family declared first, which is applicant". Implementing it as
written would have been wrong. The declaration order in
`signal_families` decides which regex claims a raw label, which is a
different question; and the corpus answers this one plainly. Of the
~36 names whose applicant and adviser counts tie at or above
`DOCUMENT_NAME_FLOOR` and at the name's own maximum — the ties the
order actually decides; 34 or 36 depending on how spelling variants
are merged, measured twice on 2026-09-01 — **essentially all are
advisers, agents or case officers**: "BUJ Architects", "Hannah Leary,
Barton Willmore LLP", "Mr D Chadwick, Chadwick Town Planning
Limited", "Matthew Payne, Consultant Engineer", "Ove Arup & Partners
International Limited author". The one arguable exception a re-probe
found is a developer-shaped compound string, "Stoford Developments
Ltd, Spetchley Developments" — so the direction rests on the cost
asymmetry plus the overwhelming majority rather than on unanimity,
and the first version of this entry claimed the stronger "every one",
corrected here. Applicant-wins-ties would have filed ~35 advisers as
the applicant of record, which is the panel's strongest claim and the
expensive way to be wrong, to protect one possible developer.

So `PARTY_FAMILY_TIE_ORDER` is stated where it can be read, weakest
claim first — adviser, authority, applicant, other — with `party_other`
below the three families that state a side, because "named without a
stated side" is the absence of a claim rather than a competing one.
Three sites change, and each is a correction: Euro-Tel Design leaves
Redcar's applicant field, BUJ Architects leaves Tower Hamlets', and
R8 Tool Hire Ltd — the occupier the Uttlesford site is named after —
takes the slot Michael Bingham had been taking half the time.
`operator_primary`, `end_user` and `named_in_documents` do not move on
any site: a name's mention count is unaffected by which field shows it.

**What the fix is held by, and what it is not.** Not the determinism
test: the failure is probabilistic, so a passing run proves nothing —
it had passed ninety-odd times over this defect. The tests that pin it
run `site_parties` over all 720 permutations of a six-row fixture built
from Uttlesford's real counts and assert one answer, and assert the
direction of the tie separately; both fail against the previous code,
the first with exactly the string the captured diff recorded. Against
the live corpus the same question was asked by running
`_parties_for_sites` twice with the SQL ordered forwards and then
backwards: the old code differs on **four** sites — the two the failure
happened to expose, plus TowerHamlets/PA/18/00418/S and
CentralBedfordshire/CB/21/00967/DOC — and the new code on none. A
probe that could see the defect, run before the claim that it is gone.

Two ordering repairs travel with it, both cheap and both the same rule
as "Lessons that changed how the code is written" above: every
ordering that reaches an artefact must be total. `PARTIES_SQL` gains
`ORDER BY s.site_key, f.signal_family, f.value_text, f.id` — 0.34s
against 0.23s over 235,581 rows, on a ten-minute build — and the ranked
sort inside `site_parties` gains the family as a last key, where one
name arriving under two families with one count had been left in the
order it was handed in.

The lesson is not the missing `ORDER BY`; that was known and written
down. It is that a comment describing a tie-break is a claim about
behaviour, and this one had been wrong since it was written — the
tie-break it described did not exist, and the tie-break it wanted would
have been the worse of the two.
## A claim links its own evidence (2026-09-01)

WP-C, and the last of the snapshot chain. An operator's capacity claim
rests on a marketing page with no register behind it, so the copy this
project holds *is* the evidence — and until today a reporter could only
reach it by cloning a repository. Each operator and green claim now
carries a Drive link to that copy beside the source URL it already
showed, on five surfaces: the site panel's claims box, the Operators
tab, the green-claims table, and the workbook's Capacity claims and
Figures by audience sheets.

**Led by the other link than a document's, deliberately.** A planning
document's title links our copy and the register comes second, because
councils withdraw documents. A claim's published page stays the primary
link, because it is what a story cites; our copy is the labelled
second. Same pair, opposite emphasis, and the reason is which one can
be taken away.

**The rule turned out to be the quote, not the date.** WP-C's own spec
had this right — its bolded rule is the nearest file *in which the
quote appears* — but the entry above and ROADMAP both stated it
date-first, and the spec's worked example was wrong in a way that
mattered. A date rule is necessary and it is not sufficient, and
CyrusOne LON1 is why. Its superseded 8.72 MW reading is
still a row in `capacity_claims`, because the content key includes the
value and the date; the file it was read from is *not* held, because it
was overwritten before the store became append-only three weeks later.
So the whole point of the date rule — the older reading reaching the
older evidence — cannot be met for that row, and a date rule would have
landed it on the 2026-08-30 file that reads 9 MW: a working link, under
a citation naming a different figure, which is the failure
`document_drive_files` exists to prevent one layer up. **Two further
things the spec did not have, both read off the database rather than
reasoned about**: the row carries no `as_at` at all, so it would have
taken the newest-first arm; and the reading is not in
`operator-claims.yaml` either, which holds current readings only.

So a claim links **the nearest held file in which its own verbatim
quote appears**, whitespace-normalised as the gate normalises, and
links nothing otherwise. The date still orders the search —
`snapshot_candidates` offers the files that existed when the reading
was taken, newest first, then the later ones oldest first, because a
reading routinely predates the next re-fetch — but the quote decides.
`snapshot_drive.copy_url` is the one helper every surface calls; it
returns nothing where no candidate contains the quote, and nothing
where the winning file has no ledger entry, because the neighbouring
file is different evidence rather than a fallback.

**80 of the 81 operator rows in the database resolve, and the one that
does not is the 8.72 MW row — which exists in the database only.** The
committed YAML holds 89 operator claims and every one resolves, nine of
them (the Saunderton and Iron Mountain facility claims) awaiting the
next `load_capacity_claims.py` run. All six green claims resolve. The reader
renders 166 links across the three surfaces; the workbook fills 80 of
264 claim rows and 37 of 118 audience rows, the blanks being register
entries and filed accounts, which are published documents with
permanent locations of their own and no snapshot behind them. A
register locator is "row 47" and a filing's is "page 12", so they
resolve to nothing by construction rather than by exclusion — and the
resolver refuses a locator that is not slug-shaped, so nothing is ever
matched by a glob reading a locator as a pattern.

**The guard was shown to fail on both shapes of the bug it is for.** A
built-page test asserts every rendered our-copy href names a file id in
the committed ledger. Against the real build it passes; against the
same page with one id altered it fails, and against the same page with
every our-copy link stripped it fails on the positive half. That is the
`test_no_link_in_the_built_page_points_at_a_filesystem` pattern, which
exists because 401 dead links shipped in 2.8 while every unit test
passed.

**Diffed against a build of `main` rather than against 2.10**, which is
the comparison that isolates a change: site-panel links 69,082 →
69,125, two workbook columns added, two dictionary entries added,
nothing fell. Against 2.10 several counts fall, and every one of them
is corpus movement since that release.

The DuckDB's claims tables are deliberately not touched, and are on
ROADMAP as their own change.

---

## Five priors and the release chain were one working-directory bug (2026-09-01/02)

A path written as `Path("data/…")` is a path relative to wherever the
command happens to be run, and this project had seven of them standing
in front of loaders that return empty for an absent file. From the
repository root every one worked. From anywhere else each layer
silently disappeared — and the guard written to catch exactly that
passed over the empty result, because a guard that checks the keys it
is handed has nothing to check. Measured on 2026-09-01 from `/tmp`:
the facility prior loaded 0 sites instead of 6; the site aliases 0
instead of 56; the operator pages 0 instead of 39; the coordinate pins
0 instead of 29, the reader's power-station overlay 0 plants instead
of 3,987; the clusterer 0 partitioned applications instead of 476 —
which re-merges the campuses the partitions exist to keep apart and
changes site keys, reporting clean.

Fixed as a family across five changes, each on the form
`capacity_claims` and `green_claims` already used —
`ROOT = Path(__file__).resolve().parent.parent` and every constant
resolved against it — with tests that pin the mechanism (the path is
absolute; a loader returns the same key set from a `chdir` directory)
rather than a count that grows: `site_facilities` (#331), the three
priors and the map/reader overlay (#332), the clusterer's `data_dir`
default (#335), the release diff (#336) and the release chain itself
(R7, this entry's occasion).

**The last two were the instruments, and they were worse than the
priors.** `release_diff.py` — the tool the diff-against-the-previous-
release discipline rests on — opened its priors check with `if not
path.exists(): continue`, so run from the wrong directory it skipped
the dangling-site-key check and printed a report indistinguishable
from one where every key resolved. It now reports the check it could
not run and exits 2, outside `--allow-fewer`'s reach: that flag can
declare a removal deliberate, not a check nobody ran. And
`dcp/release.py`'s `EXPORTS` — the one location the whole chain reads
to decide what to build — made `latest_release_dir()` return `None`
from anywhere else, at which point the reader fell back to
`phase1_build` and phase `"1"`, stamping its title, header and
database filename with a phase several releases old, into a folder
just as old, reporting success; the staging build took the same
folder; and the Drive sync, finding no ledger, would have started
from nothing and uploaded the whole tree beside the copy already on
Drive — the duplicate-archive mechanism by another door.

**The fallbacks are gone rather than made absolute.** A default that
names a release is right for exactly one release and wrong from the
next onwards, which this file recorded on 2026-08-11 and
`tests/test_release_defaults.py` was written to prevent. Three
survived it anyway, because that test read only the one line carrying
`default=` and each offender had put the named release on the line
after — and the test's own script glob was working-directory-relative,
so from elsewhere it parametrised nothing and passed. Now
`release.current_release_dir()` and `release.current_phase()` refuse
with a message naming the flag to pass when there is no release
folder to derive from; the defaults test resolves against the root
and follows a statement's continuation lines; and the sync ledger is
one constant, `dcp.drive.SYNC_LEDGER`, read by all three scripts that
need it.

The class is bounded by a grep and the boundary is stated:
`data/exports` is one repository location, because everything in the
chain reads it to decide what to build, so it resolves like the
priors. A one-off tool's `--out` is legitimately where the command was
run, and those defaults were named and left alone.

---

## v2.11 — the operator rung, and the release the guards earned (2026-09-01/02)

Built and released across the evening of 1 September and the morning
after, from a corpus that had moved a long way since 2.10 was stamped
on 30 August: **501 sites** (508 rows in the reader with pre-planning),
**1,978 applications**, 60,142 documents, 1,378,147 findings. The
theme, as ROADMAP redefined 2.11 on 31 August, is *what a site's power
figure means* — and the release carries the answer end to end.

**What is in it.** The re-gate's 14,111 reinstated findings with their
adjudication, correction, generation and label-audit passes; the
machine readings re-run on `gpt-5`/`reading-1.4` (figure rate up 54%);
the adjacent-power relationship table in place of membership (#252),
and the reader's "Adjacent power" box; the operator-pages fold, typed
standing, and `component_of`; the append-only snapshot store, its Drive
copies and the 166 "our copy" links (WP-A to WP-C); Iron Mountain's
roster and the five-campus reconciliation (WP-D); the NESO triage's
five matches; and **the operator rung** (#333), decided on all seven
points and built in a day — eight cells change, `at_least_100mw` goes
42 → 44 gaining Stockley Park and Vantage Cardiff, and every one of the
eight says on the row what it stands on and what the planning record
says instead.

**The chain, as run.** Steps 0 to 4 were no-ops or nearly — the
materialise stamped 501 sites and changed none, the adjudication tail
was empty, corrections zero, generation nothing to ask, the label audit
one finding — which is the 31 August work having already been paid
for. The readings were submitted the moment the corpus settled and
collected before the final build (**47 sites, 0 withheld, 0
unparseable**; the runbook gained step 4a for it, and the warning that
the script's default model is not the one the readings run on). Backup
verified and uploaded. The sync: **43 uploaded, 450 updated, 930
moved, 0 failed, 303 pruned** — the 930 moves being the point of the
next paragraph. Thirty sampled documents verified through to Drive
with the right bytes under the right parent.

**The staging guard fired, correctly, and adjacent power got a home.**
The first staging build since #252 vetoed the class from membership
found **743 held documents across 28 adjacent-power applications**
with nowhere to go — all on Drive, four cited by machine readings —
and a `--prune` sync would have binned them. They now sit under
`adjacent_power/` beside `sites/` and `operator_snapshots/` (Luke:
"next to, rather than inside, sites"), each folder's `_index.md`
naming the sites the scheme stands beside and how that is known; the
guard counts them as staged only once the build has written them, and
the recorder and the verifier read the folder name from the builder
(#338). The sync then recognised every one of them, and KLON-03's
documents merged into Kao Harlow, as **moves** — md5 for md5 — so
nothing was re-uploaded and no Drive id changed. The four citations
never broke.

**The release diff was the largest since 2.7 and was read, not
counted.** Every FELL but one was the 30 August corpus movement 2.10
predates: nine site keys gone (eight #252 retirements, the Kao merge),
56 adjacent-power memberships out, the party and application counts
following. The one that needed work — 168 site panels losing at least
one link — split 21 adjacent-power departures (436 links) from 147
others (2,039 links), and the 147 were the readings re-read: the
machine-reading box halved on those sites while citation density held
corpus-wide (2.78 → 2.74 links per thousand characters, the same
"p.N · ref" form, the boxes 3.5% shorter in total). Shorter readings,
not unlinked ones. The "Only adjacent power" filter control went with
the class it filtered.

**Two guards caught the release's own tooling, which is what they are
for.** The step-10 verifier reported 30 of 30 sampled documents as
never uploaded while the sync had just cached 57,109 of them: R7 had
made the verifier's staging default absolute against a ledger keyed
repository-relative, and its exact-string lookup could not see the
match the recorder made on the path's tail (#339). And the dead-host
probe's first pass reported forty-odd dead hosts that were nothing of
the kind — incomplete certificate chains the adapters handle with
`truststore` and a bare `urllib` does not; with it injected, 16 dead
and 5 challenged, recorded in ROADMAP against the 28 August list.
Both are the shape this file keeps recording: a probe that cannot see
what it is looking for, reported as absence.

**Also carried.** The runbook's "two known contradicted sites" named
West London for a month after the export-limit rule removed it;
Ferrybridge C has stood in its place since at least 28 August (grid
100 MW equalling storage 100 MW — a battery connection typed as the
data centre's, most likely, and a person's row). Pinpoint tranche 5 is
five files across three sites — the corpus barely moved in documents,
which is the release's shape. The notebook needed nothing added: the
only sites new since 2.10 are the two procedural singletons the #252
chain stranded, outside the datacentre-only export.

---

## Membership settled before the campus review (2026-09-02)

The first materialise after #351 and #352, run by Luke from an
up-to-date main after a dry run that matched the measured shape line
for line: `sites_new 0, sites_updated 501, sites_retired 0,
sites_revived 0, members 2,245, members_retired_with_site 65`. The
universe went from 1,978 to **1,999 applications** in the same 501
sites — the 21 the family door now unites with the member that admitted
them (most of them Houghton Regis North's unlocated reserved matters,
two VIRTUS stem-37977 applications into Stockley Park, Longcross's two
Surrey Heath parent permissions) — and one application moved: the
Blyth substation amendment carrying the 99.9 MW offshore-wind figure
left Cambois for the substation partition it cites, which the 2.7
partition intended and could not reach while family edges through
`not_dc` were skipped. The 65 membership rows left live on sites
retired since 6 August went with their sites, the class behind #349.
No key changed, so nothing keyed on a site — `campus_scope.yaml`,
`site_facilities.yaml`, the aliases, the operator pages — moved under
the campus review that follows.

Verified against the database afterwards rather than read off the
summary: 501 live sites; 1,999 application and 246 project memberships
live; zero stale rows; the named joiners in the sites predicted; the
unsited `not_dc` set holding documents down from 76 applications and
4,012 documents to 61 and 1,701, of which five are adjacent power's
paperwork under #352's rule, leaving 56 for the workbook's Excluded
applications sheet. What follows automatically: the six sites whose
membership moved re-read at the next step 4a, and the paperwork, the
four #349 applications and the 21 joiners get their Drive folders at the
next staging build and sync.

Why now rather than with the next release: the campus review writes
files keyed on site keys, and a materialise that could re-key sites had
to land first or the curation would be redone. It could not re-key
anything, as the dry run showed, but knowing that is the point of
running it before rather than after.

---

## Where a facility is, with the source that says so (2026-09-02)

Reviewing VIRTUS Slough, Luke found that looking the buildings up on a
map helped the decision, and asked whether `site_facilities.yaml` was
the right place to record where each facility is and whether the
addresses could be seen in a list. It is, on the roster's own contract:
a facility may now carry a `location` block — address, postcode,
coordinates — with `source` and `date` required and at least one of the
three given, and the loader refuses a location with no source the way it
refuses an attribution with a value. Filled piecemeal as authoritative
addresses are met, so an absent block means "not yet found", never
"nowhere", and the workbook's new **Facilities** sheet says exactly
that: one row per facility, named by its source, its location status,
the figure the roster attributes to it read from the claims store by
name at build time (never copied), and the planning-document
attributions where a document names the building. Seeded with the two
Slough locations the repository already had sources for — LONDON10 at
75 Buckingham Avenue from the Companies House charge, LONDON11's
postcode from its permit — and nothing else, because the pushback on
the way to this was that operators' campus pages mostly give no
addresses at all, so most rows will read "not yet found" for a while,
and that is the coverage gap made visible rather than a blank.

---

## The first campus reviewed: VIRTUS Slough (2026-09-02)

The 35-campus review began with the one the operator channel had put a
question to. Luke had the time for one; VIRTUS Slough was the natural
first because its scope question was already open, its roster names
seven facilities against the site's three, and settling it unlocks the
third rung displacement #250 had predicted.

**It was a different shape from Stockley Park.** The revised method —
confirm the operator's roster against the planning record, facility by
facility — assumed a planning record to confirm against. Slough's is
three Barbour catalogue records and one document-less 2018 outline
(Slough/T/138, LONDON10 at 75 Buckingham Avenue): no documents held, no
adjudicated figure, a power cell reading "no documents held". The roster
was the only evidence there was. VIRTUS's campus page states an IT load
for each of LONDON3, 4, 9, 10, 11, 12 and 19 on one basis, and a campus
total of 145.5 MW. Three of the seven have a planning record here. The
other four are nowhere in the corpus — no application, no Barbour
record, no SPV, no permit of their own — and the other Slough site
records were checked in case they were these buildings under another
name (Cyxtera, Virgin Media, Equinix, CyrusOne, two warehouses). So the
sourced denominator #247 asked for is three of seven, and the four are a
coverage gap of 105 MW of operator-stated load on the estate the corpus
covers most densely.

**Decided** (Luke): `distinct_facilities`, `total: withhold`, and
VIRTUS's own figure ranks the site — a `power_cell` on the entry
pinning the claim at 145.5, under the rung's empty-ladder extension,
since there is no planning figure to displace. The cell reads as
VIRTUS's, for VIRTUS's scope, with three-of-seven coverage and "no
planning document held" beside it. The alternative — leaving the campus
claim unmatched because the site holds three of seven — was named as
the #250 failure exactly: a 145.5 MW campus absent from the hyperscale
answer for a reason about our records. Saunderton was the precedent.

**Corrected the same evening, on the addresses** (Luke, from
Datacenters.com and Google Maps; each checked against what this
project can cite). The review had said LONDON4, 9, 12 and 19 were
nowhere in the corpus, having searched by VIRTUS's names. By address,
two are here under other names in other site records: LONDON9 is
`Slough/T/135`, "Single building for data centre development", Fullers
Logistics Ltd, 470-475 Malton Avenue, the sole application of Segro's
Malton Avenue site, its coordinates thirty-five metres from Google's
"Virtus London 9" pin; LONDON11 and LONDON12 are 580-581 Ipswich Road,
Barbour project 12522787 in Segro's Ipswich Road site, while LONDON11's
own Barbour record sits in the Liverpool Road site on a postcode
centroid. LONDON3 and LONDON4 share 14 Liverpool Road, unheld; LONDON19
has no directory page and no location. So VIRTUS's one campus spans
three site records under two landlords' names — a name search across
a landlord's records has the rebrand blind spot exactly — and the
question that came out is a partition, not a coverage gap: the Iron
Mountain rule says one campus, one site; the capacity model's own
definition says a campus is a claim about sites. **Decided the same
evening: Iron Mountain's rule applies (Luke).** The partition
`virtus-zenium-slough-campus` now names Slough/T/135 and Barbour
12409629 (LONDON9) and 12522787 (LONDON11/12); the Malton Avenue
partition and Segro's Malton Avenue site retire into it, Segro's
Ipswich Road site keeps 535-546 and Slough/t/131 and is aliased for
that one building, and the merged site keeps its key because 12216044
is the lowest Barbour number in it. The 145.5 stands, now for a site
that holds five of the seven. And the directory earned its standing on the
way: it places LONDON10 at Iron Mountain's 110 Buckingham Avenue
against a charge and an application at 75, and its megawatts are not
the operator's, so its addresses are leads recorded with what
corroborates them and nothing more.

**Two findings travelled out of it.** VIRTUS's stated total exceeds its
own seven rows summed by 13.3 MW, and 13.3 is LONDON11's figure to the
decimal. The temptation to conclude VIRTUS counted LONDON11 twice was
named and declined (Luke: "we'll keep their claimed figure, but not
decide how they came to it") — the arithmetic is ours, the explanation
would be a guess, and the claimed figure stands as claimed with the
discrepancy recorded as a question for the operator. And the site's key project, Zenium's "London One" at 12
Liverpool Road, is probably CyrusOne's LON1; the entry says the scope
decision does not turn on it and would survive its ejection, key change
and all. Luke also asked, on the way, where a facility's address should
live — the roster file, with a source, is the answer (ROADMAP).

---

## The workbook names what it leaves out (2026-09-02)

The third piece of the `not_dc` resolution. The staging build's
shortfall guard tolerates `not_dc` as "excluded by decision", and until
now the decision had no record a reporter could read: the applications
whose documents this project holds and shows nowhere — not in a site,
not under `adjacent_power/`, not in the reader, Pinpoint or the notebook
— were a count in a build log. Luke's instinct was "keep it or regret
it"; the measurement said the residue is mostly power schemes within
2.5 km of a site that the adjacency layer cannot see, plus a handful of
housing schemes and keyword false positives, and that none of it should
go to Drive. So it is listed instead. **Excluded applications** is one
row per such application: reference, both rubrics' verdicts, why we hold
it (the reader's route labels and the raw `discovered_via` tags, which
name the site each sweep ran outward from), documents held, findings,
findings whose quote names a data centre (the re-triage signal that
caught the Wychavon outline), the nearest live site and its distance,
the description and the register link. The adjacent class is excluded
through `dcp.adjacent_power.staged_applications`, the same rule the
staging build uses, so the sheet and the Drive tree cannot disagree
about what is where. Four dictionary entries explain it; a test holds
the columns and the dictionary to each other. The Sheet needs the tab
created by hand, or a new Sheet, at the next release — the runbook's
step 13 says so.

---

## Adjacent power takes its own paperwork with it (2026-09-02)

The second of the three pieces of work the `not_dc` resolution produced
(ROADMAP, the `not_dc` item). Which applications sit under
`adjacent_power/` on Drive was decided in three places — the staging
build, the id recorder and the sample verifier each carried its own
query — and #349 had just shown what that costs. It is decided once now,
in `dcp.adjacent_power.staged_applications`, and the three read it; a
test refuses any of them re-deriving the class from the verdict.

**What the shared rule adds.** A scheme's own paperwork. A discharge of
a substation consent's conditions, an amendment to its layout, a
variation of its hours is triaged `not_dc` by the rubric, and correctly:
it is not a data centre and its description ties it to nothing but its
parent. But the family door refuses `adjacent_power` (#252), so the
child was admitted to no site, its verdict put it in the shortfall's
"excluded by decision", and it sat in no folder while its parent had
one. The rule reads the reference instead of the verdict — `associated_id`,
else a three-segment reference in the description, through the same
extractor the clusterer uses — and files the child beside its parent,
its `_index.md` naming the parent and listing the sites the parent
stands beside, since the relationship table has rows for the scheme and
none for its discharges. Measured against the live corpus: **38
applications, 946 documents** — the 33 the verdict already covered, and
five pieces of paperwork: Union Park's four discharges of the
`75111/APP/2022/1007` site-clearance permission and one discharge at
Hallen, 50 documents that had no Drive home.

The shortfall guard now drops whatever this build wrote under
`adjacent_power/` whatever its verdict, so a staged `not_dc` discharge
is no longer reported as held-but-not-staged. Three integration tests
pin the rule — a discharge is staged with its scheme and a stray
`not_dc` is not; a member of a live site is never adjacent power's; an
application holding no documents is not listed — and the staging test
pins the child's index.

---

## Four small fixes (2026-09-02)

Asked for by Luke on reading the stale-content audit, each closing a
ROADMAP item that had been open since August.

**A Drive URL is built in one place.** `export_handover.py` spelled the
file form twice and the folder form twice, `export_duckdb.py` the file
form in SQL, `sync_snapshots_drive.py` the folder form in a print — six
correct copies of two strings, each free to drift. `dcp.drive` now
carries `file_url`, `folder_url` and `file_url_sql` over two constants,
and `tests/test_drive_url_one_shape.py` asserts the rule over every file
under `scripts/` and `dcp/`, the way the release-defaults test does.

**The zero-byte sweep has a durable home.** Three empty documents sit in
the store from before the fetch guard existed, and nothing since 2.8 had
looked for a fourth except by hand. `repo.zero_byte_files` is the check
— `find -size -1c` over a tree — and `build_drive_staging.py` runs it
over the tree it just wrote, which is hard links into the store, and
prints what it found beside its other counts every release;
`scripts/corpus_stats.py` reports the database's view of the same fact
through `repo.zero_byte_documents`. "Say so in the artefacts" — the site
report and coverage detail showing an empty document as unavailable
rather than read — stays on the ROADMAP.

**The reader's "Adjacent power" box links our copies.** Since #252 the
class's documents live under `adjacent_power/` beside `sites/` on Drive
(the 2.11 staging build's finding). The folder's id is pinned in
`dcp/drive.py` as `ADJACENT_POWER_FOLDER_ID`, read back from the sync
ledger rather than typed; the box links it, and each entry links its own
application folder once synced, beside the register link it already
carried, through `_drive_adjacent_map` on the same contract as the site
maps.

**The notebook card says what the notebook holds.** It said "Every
site's report and its full findings table"; since 2.10 the bundle
exports datacentre-classed sites only, which is what pays for the
per-document word budget. The card now states the scope with a computed
count — the datacentre-classed rows of the sites list it sits above —
and names where the other classes are, so a question the notebook does
not answer reads as out of scope rather than as absence.

**And a fifth, which verifying the third found.** Postgres was up, so
the reader was built from the branch: 61 adjacent-power boxes, all
linking the class folder, 20 of 45 entries linking their own — and of
the 25 that did not, two held documents. Both are members of sites #252
retired on 2026-08-30, and the materialise retires a site without
retiring its `site_members` rows (65 such rows on 63 applications). So
the staging build's "no live membership" test saw a live row on a dead
site, did not stage them under `adjacent_power/`, no live site's folder
held them either, and the 2.11 prune had already binned their old site
folders: **four applications, 144 documents, with no Drive home** — the
two university leads among them. The three queries that carry the test
(`build_drive_staging`, `record_drive_ids`, `verify_drive_sample`) now
require the site to be live, a test pins the clause over all three, and
the corrected query stages 33 applications against 28. The documents
return at the next staging build and sync; the durable fix, retiring
member rows with their site, is on the ROADMAP as a data change.

---

## How this project is worked on

Kept here rather than in a handover, because it has been true across
every session and is the thing a new one most needs.

Luke is a journalist who has spent three decades on newsroom software,
on the product and UX side. **He finds defects by opening the thing and
poking it**, and a large share of the corrections recorded above came
from him reading a rendered panel rather than from a test: the layout
break the claims box caused, the pompous sentence in a lede, the invented
term in a column headed "terms the operator uses", 1,835 permit pages
committed against a repository that redistributes nothing.

**He wants pushback, and he is right often enough that the pushback has
to be grounded rather than reflexive.** He asked for a raw megawatt
figure on the main site row; the argument against — that a number there
reads as comparable to the planning figure beside it when the quantities
differ — was accepted on its merits, and the column shows a confidence
tier instead. The reverse happens as often: the permit text should not
have been committed, and the argument for committing it did not survive
contact with the repository's own posture.

**Every claim needs a source, including the ones inherited from these
documents.** "Standby fleets are sized to peak load plus redundancy" and
"divide thermal input by 2.4–2.5" travelled from a handover into a
reader-facing caveat with no attribution behind either. Asked for one,
there was none. A project document records what *this project* decided;
where it also asserts a fact about the world, that fact entered
unattributed and every restatement launders it further.

**When he corrects something, build the durable form** — a constant, a
test, a shared function — rather than resolving to remember. Most of the
lessons above exist as one of those three.

**Sessions are scoped small, and a problem is stated before it is
investigated** (Luke, 2026-09-01, and both are experiments he can
revoke). The occasion: a session read ROADMAP in full at its start,
then two hundred thousand tokens later spent ten tool calls
re-establishing the Iron Mountain bot block, the collapsed-`<details>`
lesson and the campus arithmetic — all four of which were in its context
the whole time, along with the note that two earlier sessions had made
the same mistake.

**What that ruled out is the useful part.** The session proposed five
fixes and every one was already tried, self-contradictory, or the named
anti-pattern: mechanising rule 3 (tried, and the previous rounds cost
more context than they saved); inlining settled facts into handover docs
(the exact opposite of this repo's own rule that a restated fact is the
one that goes stale); marking decisions as settled (that policy exists
and is what was ignored); a hook (another conflicting source of truth);
and a per-task grep instead of the full read (rule 1's anti-pattern
verbatim). Luke rejected all five. **Do not re-propose them.** A session
is not a reliable witness on its own failure modes, and the ones it
proposes will tend to be interventions on what it *knows* — where the
failure is in what it *does next*.

So the two levers are outside the documentation. Shorter sessions put
the read and the use minutes apart rather than hours. And rule 4 in
AGENTS.md hands Luke the interception point at one line rather than
after ten tool calls.

**Rule 4's limit, which Luke identified as it was being written and
which the rule now states: it relies on him.** Recognition is cheaper
than recall, so it asks less of him than remembering unprompted — but
only while the material is recent. Both 2026-09-01 interceptions were of
passages written hours earlier. On a decision settled weeks back he will
not recognise it either. The residue that does not need his memory is
smaller and still real: a wrong direction costs one line to correct
instead of ten calls to unwind, whenever he is reading at all. Nobody
involved thinks this is the answer; it is the best available lever that
is not one of the five already rejected.


### Phase 2.8 — the gaps in the corpus (2026-08-26)

A day spent on what the corpus did not hold rather than on what it did.
The releases before this one improved how the material was presented;
this one went after the material that was missing, and most of what it
found was a check that could not see what it claimed to check.

**The Section 35 campuses had no documents.** Quest Park and Dartford
were named sites carrying nothing — the eleven PDFs had been cached by
hand into `data/seed_cases/` weeks earlier and acquisition never
followed up. Ingesting and reading them gave Dartford 300 MW total load
with 240 MW IT and a transitional NGET offer against a firm Gate 2
allocation, and Quest Park 1 GW with a 720 MW IT load powered by an
on-site gas station that would be an NSIP in its own right. Wapseys was
checked and left alone: its direction letter is already in the corpus
under `EN0110030`, textually identical.

**A Section 35 direction was classified as a drawing.** `DRAWING_KINDS`
contains `section\b` and is tested before `TIER_A_KINDS`, so a document
whose kind names the statute skipped the read entirely. The premise —
a named statutory instrument is never a drawing — now sits beside the
s106 rule it belongs with.

**2,260 documents the registers offered were not held.** The re-list
audit measured it without downloading anything, by re-reading the
documents-tab HTML each short fetch had already snapshotted. Refetching
recovered 249 of the 291 reports and statements, the class where power
disclosures live, and Northumberland Energy Park went from 177 absent
to one. It also corrected its own headline: of 3,083 documents fetched,
1,910 were byte-identical to a document already held under a different
URL on the same application, so 2,260 is an upper bound on URLs and not
a count of missing content.

**The incomplete Drive archive was explained, and the suspect was
innocent.** 143 applications discovered on 2026-08-07 had no site
membership until the materialise of the 25th, so their documents were
never *candidates* for the sync — invisible to both `skipped` and
`failed`. The 2026-08-21 ledger loss, the obvious culprit, is exonerated
by its own log: 50,406 tracked, 0 failed, and the arithmetic closes
exactly against the later runs. The staging build now states its own
shortfall and refuses; replayed against that cohort it reports 3,584
documents across 139 applications, so it would have stopped both the
08-09 and 08-21 builds. `materialise_sites.py` joined the runbook as
step 0, its absence having been half the defect.

**Half a million findings were invisible to two reader panels.** The
OpenAI insert path omitted `signal_family` from its column list, so all
557,747 of its findings carried NULL — and the EIA-process and parties
panels select on family alone. Separately, `\b` is a word boundary and
`_` is a word character, so `eia\b` could never match `eia_status` and
`family_for('eia_process')` returned `unclassified`. And `author` in
`party_adviser`, undelimited and declared first, matched inside
"authority" and made `party_authority`'s own `local_planning_authority`
token unreachable: 11,706 findings filed the decision-maker among the
consultants acting for the applicant. Fixing the three took the EIA
panel from 190 sites to 242 and the parties panel from 97,088 rows to
208,476.

**`none_published` is a settled verdict and was being awarded to
failures.** The mapping consulted `error_class`, which describes the
listing fetch, and never the per-document error count beside it. A live
sweep over the 128 settled applications found 17 wrong — every one
Newport, which serves an error page on its Idox documents tab and
publishes from a separate docstore. 413 documents offered and none
held, 350 of them at Uskmouth Power Station: 25 applications, no
documents, no findings. 52 more cannot be settled by script at all,
being Idox "Permission Denied" pages served with HTTP 200 and full
council chrome.

**Drawings are worth reading, but only some of them.** The v1 rejection
was right about a blanket pass and wrong about the premise: the sheets
are text-layered, and the text emerges in drawing order, so a
transformer sheet yields characters interleaved from adjacent tables.
The discriminator is authorship. A manufacturer's or DNO engineer's
drawing carries ratings; an architect's drawing of the building
containing the same equipment is dry. Two prompt rules earned their
place — a cell carries its column header or it is not a transcription,
and a symbol count may only be made on the overview image, never a
crop.

**The scheme SPVs disclose capacity by construction.** Operator accounts
were a null; a single-asset SPV's scheme *is* its investment property,
so FRS 102 makes the directors state what the valuation assumes. 111
companies resolved, 90 mapped to a site. The `has_charges` flag lies —
false for 44 of the 49 companies that carry charges — which is how
STX-A10 was found: no PSC, no parent disclosed, two charges to a company
whose own PSC is Alphabet, Inc. Court Lane's apparent 26% discrepancy
dissolved on reading the site's own environmental statement, which gives
"Total IT Load - 103.32 MW" and "Total Data Centre Load – 139.5 MW" in
one table.

#### What the day was actually about

Six checks returned confident answers to questions they were not asking.
A `pgrep` whose pattern matched its own command line, so the wait could
never end. A cross-check for wrongly-settled applications that queried a
population structurally excluding them, and returned zero. A Drive
verifier sampling the ledger it was auditing, unable by construction to
witness a document that never reached the tree. A word boundary that
could not see an underscore. A test that pinned a literal guard string
and reported a correct change as a regression. And, at the last gate
before publication, a release diff that phrased "panels that lost links"
so the bad direction was up, marked fifteen losses `+`, and exited 0.

The pattern is not carelessness in any single case. It is that a probe
returning a plausible number looks identical to a probe that works, and
nothing downstream distinguishes them. Where a guard exists, the useful
question is not "does it pass" but "could it fail, and has anyone
watched it do so".

#### What the reader gained, after the entry above was written

The half of 2.8 that came from reporters rather than from the corpus,
and every item is the same shape: the reader held the answer and did
not show it.

**A dash meant four different things.** The convention is that a dash
means *unknown*, and it was carrying "no documents held", "documents
not yet read", "held, read, and the fact is not in them", and "the
field does not apply". Only the third is a finding. 5,589 dashes became
153, each replaced with two or three words in the muted style the
operator column had used since 2.4. The wording is derived from each
site's own coverage rather than chosen, because writing "none found"
everywhere asserts a null result on sites nobody has read.

**The party fields read from Barbour alone**, which covers 164 of 494
sites — so 330 showed a dash for the applicant and 179 of those had one
stated in their own documents. "Barbour unless otherwise stated" is not
a defensible default for a field Barbour fills a third of the time.
They now fall back to the documents and every value names its register.
The operator field did not change: `end_user` asserts who runs a site
across every document, which is an identity claim and still needs a
confirmed alias, where `applicant_of_record` repeats what one
application's own form says about itself.

**The reading bar had two states**, so 90% read looked like 5% read.
Three now — and measured against documents that *can* be read, which is
the question a reporter is really asking of it: is the tool finished
with this site, or should I wait? Drawings and the sampled classes are
not a backlog, and a document tried and found unreadable can never be
read, so leaving either in the denominator reports unfinished work for
ever. 93 sites that showed red were complete; six more once the
unreadable left. Both subtractions are stated on the page, because
taking something out of a denominator without saying so is the quiet
kind of dishonesty this reader refuses everywhere else.

**Two internal vocabularies were being printed at reporters.**
"Classification: both" was our clustering shorthand; `discovered_via`
recorded why an application was in the dataset at all and was never
selected in the query, so a row with no documents and no register link
showed no reason for being there.

**And one more check that could not see.** Five sites said "not yet
synced to Drive" about folders that were on Drive — Dartford among
them, the site a reporter brief had been written about that afternoon.
The diagnosis was ledger lag, a runbook step was written around it, and
rebuilding against the new ledger changed the count by zero. The real
cause: `site_stem` truncates a site key to 40 characters *after*
sanitising it, and every lookup normalised the whole key, so a long key
could never match its own folder. Central Bedfordshire missed by one
letter, `FULL` against `FUL`. The runbook step stayed, because the
ordering does make it necessary, with a note saying it was justified by
evidence for a different bug — a step defended by the wrong number is
one somebody drops when the number stops appearing.

#### The release

Synced 1,344 uploaded, 477 updated, 53,522 cached, **0 skipped, 0
failed**, and 335 renamed twins pruned with none missing. That closing
arithmetic is the same shape as the 2026-08-21 run that looked perfect
while 10 GB was missing; what differs is that this candidate set came
from a staging build whose shortfall guard confirmed it covers the
universe minus the deliberately excluded. The counters were honest last
time too — about a set that was itself wrong.

The Google Sheet was replaced rather than refreshed, for the second
time and for two reasons. 2.8 introduces Parties and Cohorts, and
`sheet_sync` cannot add tabs. But the live Sheet was also still 2.2 —
five releases stale — so a refresh meant 17 column edits on Sites in
one batch, three of them deletions, against a 75-column tab. A
misplaced insert leaves formatting describing the wrong data, which is
the failure that script exists to prevent. Nothing was annotated, so
the refresh's only advantage did not apply.

EdgeOne carries it, gate proven by 22 refused paths including the
encoding and traversal variants that once bypassed the middleware
entirely. Cloud Run, added the same day, serves the same page behind
Guardian sign-in and changes only when its script is run — the first
release where publishing and merging are two separate acts.

## NTT's pages, actually fetched (2026-09-02)

Luke, driving Street View along Slough's trading estate, saw NTT's
signage and asked whether NTT was in the corpus. Three of its four UK
locations were — Dagenham, London Colney, and Hemel Hempstead under
Gyron's name, the one NTT stopped using — and the fourth, Slough 2 and
3 at 665-670 Ajax Avenue, was nowhere but the Environment Agency
register. On the way the claims channel turned out to hold **no NTT
claim at all**: the two NTT URLs registered on 2026-08-30 had moved,
NTT's server answered 200 with a "New 404" body, and the fetcher stored
both bodies as snapshots (of 84 held, the only two). An unreviewed
error page sat as evidence that the operator publishes nothing, which
is the wrong finding. `fetch_operator_snapshots.py` now refuses a page
whose title or first words say not-found (`looks_like_error_page`; a
real 404 already raised), the seven live pages — the London overview
with its "formerly operating as Gyron" line and the six facilities —
are registered and held, and the two dead snapshots stay in the store
as what was served that day. Nine claims and six matches followed:
London 1 at 64 MW full build-out with its 32 MW first building as a
component and an 80 MVA substation; Hemel Hempstead 2, 3 and 4 at 5.8,
20 and 12 MW, matched `probable` to Gyron's estate-scale site record,
which also holds the address on Amazon's Hemel permit and is now a
partition candidate; Slough 2 and 3 at 1.8 and 2.7 MW, unmatched
because no site exists. Two questions for the operator travel with
them: Hemel 2's page says "one of seven data centers we operate in the
area" where the overview lists three, and NTT's own permit says four.

## The reader leaves Drive (2026-09-02)

"No one reads the reader on Google Drive" (Luke), and "no one would
care" if it stopped going there. So it stops: `build_drive_staging.py`
stages the released suffixes only — the workbook and the database,
which "should definitely stay": they are what the team's R user works
from, and Drive is where that person finds them — and the rule is one
constant in
`dcp.release` shared with `drive_sync.py --prune`, whose root exemption
had kept *anything* at the root that was no longer built locally, and
would have kept the last reader.html on Drive for ever beside a
workbook it no longer agreed with. It now keeps released suffixes and
bins the rest, so the stale copy goes at the next sync. Git holds every
release's `index.html` and the container image holds the one deployed;
nothing is lost. What it opens is on the ROADMAP under the page's
weight: the one-file rule that shaped a 33.5 MB reader, 29 MB of it the
508 site pages rendered inline, was written for a copy that opened from
a Drive folder, and that copy no longer exists.

## Two hand-obtained records, and the tools they needed (2026-09-02)

Luke, preparing the release, had downloaded Creek Way's documents by
hand — `Havering/P0384.15`, the 2015 outline for a data centre at
Rainham, thirteen PDFs the Ocella adapter had recorded on 8 August as
`none_published` because it could not parse the page — and had checked
Melville Gate's Idox page (`Midlothian/07/00051/FUL`) and found it
lists no documents, printing both pages to PDF as proof. The inbox
could take neither as it stood. It resolved only top-level folders
named `Council_ref`, and his layout was `Council/ref (PTNO-…)`; and it
would have filed the Midlothian printout as that application's one
document, inverting the finding. `ingest_inbox.py` now resolves both
layouts and ignores a trailing annotation, and appends a `fetched`
outcome on the `manual` route when it ingests, because without that
row the fold went on saying the register publishes nothing while the
application held fourteen files. `record_portal_check.py` is new: an
append-only `acquisition_outcome` row for a check made by hand, on the
`browser_probe` route the August rows used, with who checked, when,
what they saw, and the page capture filed under `manual_bundles/` and
named in the row. Creek Way holds fourteen documents (the register page
among them, under a name that says what it is) and reads at the next
corpus reading; Melville Gate's `none_published` is now a person's,
with the page it rests on, rather than an adapter's "no documents or
unparseable". PORTAL_NOTES carries the inbox's rules.

## Adjudication by consequence, now in code (2026-09-02)

Creek Way's first read produced two power figures on a site that had
never carried an adjudicated capacity, and they went to the long-tail
GPT-5 batch because the runbook's step 1 named only that script. Luke
caught it — "don't we send adjudications to Sonnet subtasks?" — and the
record already said so: power adjudication is split by consequence,
the Sonnet subagent route for figures that can set a headline number,
the batch for the tail. The batch's one request was left uncollected
and its state file set aside with the reason, the Sonnet route
adjudicated both figures (site_capacity, 2.055 MW cooling and 2.055 MW
building services, neither a ceiling), and the rule moved into
`dcp/adjudication_routes.py`, read by both scripts: the long tail now
holds the consequential set, names it, and sends it only under
`--include-consequential`. The runbook's step 1 says which route first.
Luke's point stands wider than the script: who is responsible for a
single site's adjudication has to be written where the work is done,
not only where the decision was made.
## v2.12 — the corpus release the evening earned (2026-09-02)

Twenty-two PRs had merged since 2.11 shipped that morning, and none
of them reached the data and visuals teams until something rendered.
So the candidate is the corpus as it stood at the end of the day:
VIRTUS Slough one site on the Iron Mountain rule, with Segro's Malton
Avenue record retired into it and 580-581 Ipswich Road moved across
(#359, #360); membership settled, sixty-five stale member rows retired
with their sites and the `not_dc` residue named on its own workbook
sheet rather than hidden (#349–#355); the operator rung's first real
test at Slough, where the operator's 145.5 MW ranks a site whose
planning record states no total (#356); facility locations as far as
anyone can cite them, with a Facilities sheet to see them in (#357,
#358); NTT's six pages actually fetched after two dead snapshots had
silenced the operator entirely, nine claims and six matches (#361), the
organisation under its four names (#362), and Slough 2 and 3 recorded
as buildings the corpus does not hold (#363); adjacent power taking its
own paperwork into its own Drive tree (#352); Creek Way's fourteen
documents obtained by hand and read for the first time, with two
figures adjudicated by the consequential route after the long tail had
taken them by mistake (#368, #369); and the reader leaving Drive (#367),
the postcode sectors derived for the control that is not yet built
(#370), and the Sites table's cosmetics — centred columns, the design
system's chevrons, round markers, and a tooltip that no longer opens
off-screen (#372, closing #301).

**Run as the runbook says, with three things worth recording.** The
materialise retired one site and no more, verified by a set diff of the
rebuilt clusters against live membership: two clusters changed, 498
did not. The first read of Creek Way went through the GPT-5 batch in
five minutes for fourteen documents; its two figures then went to the
wrong adjudicator because the runbook named only one, which is why
`dcp/adjudication_routes.py` exists (#369). And the diff against 2.11
explained every line, twice: at step 8, the retirement, two panels whose
Drive links lagged the ledger until the step-12 rebuild, an amendment
that moved to its parent's site through the family door, and a
detector counting a control's number as its identity (#371); at step
12, the retirement again and six panels with fewer links, every one of
them a site whose machine reading changed that evening — three re-read
under their moved inputs and citing fewer documents, three withheld as
stale — which is the readings mechanism, not a link that broke.

**What the release carries.** Five hundred sites, 1,999 applications,
57,559 documents held, 45 sites at or above 100 MW (44 → 45, the
Slough figure), 282 capacity claims with 101 matched, 2,561 Drive ids
recorded for documents that reached Drive tonight and 2,376 uploaded,
nine machine readings refreshed for the sites whose inputs moved and
three withheld as stale by the freshness check — West London
Technology Park, the Mary Somerville Data Centre and the A41 Watford
Bypass. A re-submit run straight after found nothing to read, and the
reason is the read-in-full rule rather than a fault: a site's reading
is refreshed only once its prose is read in full, and these three are
deferred as partly read — 20 of West London's 955 documents and 61 of
Watford Bypass's 349 have no read-log row, and Mary Somerville now
holds no documents at all, its application having moved on. So the
2.13 path is the first read of those documents, then the readings
pass, which will pick them up on its own; the runbook's step 4a said a
bare `--submit` would, and now says when it will not. Seven of Creek Way's quotes failed the verbatim
gate and are not escalated. The step-5 reports came back as the
runbook expects: Ferrybridge C and Watford Bypass contradicted, five
generation-understated.

**Not in it, by decision.** The "near a postcode" control (specified,
the sectors committed, the control for 2.13 so that the diff stays
readable and a person sees it first); the site-11 partition; the
unsited-claims layer; the public feed.

**Released the same evening.** Candidate #373 reviewed and merged,
release #374 carrying `index.html` byte-identical to the step-12
build, deployed at 21:26 as Cloud Run revision `dc-reader-00008-drr`
with anonymous requests verified redirected to sign-in on every probed
path, and the EdgeOne signpost probe clean: 22 paths refused, forged
cookie rejected. 2.12 is the base.

## The bar gives the table its space back (2026-09-03)

Luke, an hour after the postcode box landed on localhost: "I wonder if
we're loading the top of the site page with too much and reducing the
amount of space for 'real content'." Measured at 1440 × 900 before
anything changed: masthead 45, tabs 49, the controls 131 because the
new box had pushed "Any origin" onto a second line, the chips and their
help paragraph 104, so the table's head began at 329 px and the first
site at 380 — two-fifths of the window above the first row. The three
menus were 343, 279 and 201 px wide for closed labels of 47, 95 and
63, because a native select is as wide as its widest option: "All
sites" was paying for "Only where reading or acquisition is
incomplete". His first question was whether a select could be as wide
as its label until opened — it can, by `field-sizing: content` where
supported and a measured width elsewhere — and his answer to the
answer was to shorten the options instead, one label per line,
applied verbatim: "Sites with power figure", "Fully read sites",
"Incompletely acquired/read sites", "Sites whose figures may rise",
"Sites near national energy projects"; the classes without their
"Only" ("Datacentres (427)", "Disguise suspects (48)", "Procedural
only (26)", "No planning record (6)"); "Nearby energy search" and
"Operator watchlist" among the origins. The class and origin labels
are single-sourced in `dcp`, so the rename shows wherever a class or
an origin is named — row, methodology, workbook — not only in the
menu. Abbreviation alone was measured as 184 px, short of the 210 the
bar needed at 1440, and it turned out to be enough: the six controls
fit on one line there with the count and map link on a second, the
menus at 263, 186 and 184 px. The paragraph under the chips, two lines
on every visit for people who read it once, went behind the bar's own
"?" — the same text, opening leftwards from the row's end on the table
and rightwards in the map's sidebar, where the icon stands at the left
edge and a leftward box would have been off-screen ("Agreed on putting
the labels paragraph into a help icon"). After: the controls 113, the
chips 50, the table's head at 257 px and the first site at 309 — the
table gets a fifth of the window back. Recorded in DESIGN_CONFORMANCE
as a departure; the labels have a source test of their own, and the
issue-#301 test now anchors to the base tooltip rule so the sidebar's
override does not trip it.

Label-fit sizing — a select as wide as its chosen label until opened —
was demonstrated on a scratch copy before being declined: choosing the
longest option moved the boxes to its right by 169 px and re-wrapped
the bar, which is the movement Luke was worried about, so the choice
was abbreviation ("OK, let's just use abbreviation"). The postcode
box's placeholder lost its example — "Near a postcode", not "Near a
postcode, e.g. SL1 4BG": "people don't need to know how to write a
postcode", and since the parser reads a typed sector the example was
teaching a form that no longer matters — and the box is sized to the
label, 150 px rather than 230. At 1440 px the six controls and the
count now share the first line and only the map link and its "?" sit
on a second; the whole bar on one line needs 1,563 px.

"Oh god it's so agonisingly close to fitting on our standard laptop
screen width now." Three more cuts, none to his labels: the search
input at 230 px rather than the handoff's 300 (its placeholder was
already clipped at 300; "Search site, council, applicant…" fits at
230 and the full list is the box's title), the radius reading "10 km"
beside "Near a postcode" rather than "within 10 km", and the gap
between controls, which the handoff does not give, at 10 px rather
than 14. The whole bar now needs 1,418 px: one line at 1,440, where
the controls stand 73 px tall and the first site row starts at 269 px
against 380 at the start of the morning; two lines still at 1,280.
The conformance test that asserted the handoff's 300 px moved with the
departure and cites the row that records it.

Three more from Luke, and a fourth he found by looking: the search
box's placeholder is his "Search site, council, address etc", with a
title that lists everything the search actually matches — site name
and key, address, council, proposal, applicant, operator, end user,
advisers, organisations named in the documents, cooling method,
nearest energy project, application references; the map link reads
"See on map" whether or not anything is filtered ("The 'all' isn't
necessary" — the count beside it already says, and the 2026-08-25
rule that put "all" there only when it meant it retires); and its
"?" follows it at 5 px as the column headers' do, where the row's gap
plus the icon's own margin had made 15. Then the placeholder lost its
last letter to "a lot of unusable space on the right": a search input
reserves room for its clear button while empty — Chromium hides the
button with visibility, not display — so the box is 230 px and the
button is hidden with display while the placeholder shows, appearing
with something to clear. The bar needs 1,398 px now. Luke, on the
standard Guardian laptop: it goes to two lines only when "N cannot be
placed" lengthens the count, "and I'm OK with that".

## Near a postcode, built (2026-09-02/03)

Luke asked for it the evening the Guardian's reader callout went out,
kept it out of 2.12 on the session's advice so the release diff stayed
readable and a person saw it first, and asked for it the moment 2.12
was live. Built as specified: a second search-shaped box and a radius
select beside the search input in the shared filter bar — the 2.3
redesign removed the map's own controls so that one bar serves the
table and the map, and a map-only box would have put that back — at
sector precision from the 11,088 centroids derived from the August
2026 ONS Postcode Directory (#370) and embedded in the page, so no
lookup leaves it and the build stays a function of its inputs. "SL1
4BG" resolves to sector SL1 4, about a kilometre; an outward code
alone to the mean of its sectors; nonsense says "no such postcode
sector" beside the count rather than emptying the table silently.
Survivors reorder nearest first and carry their straight-line distance
at the head of the row's grey line — not a new column, so the table
keeps its shape and the diff its column count — and go back in their
own order when the box clears. A site with no coordinate cannot be
placed, is not shown, and is counted beside the count string, because
to a reader "nothing near your postcode" reads as "no data centre".
The state travels in the hash as `near:` and `km:`, "See on map"
frames the radius rather than the survivors, a jump to one site clears
it like the other filters, and the release diff now reads the bar's
text inputs by id so the control is tracked. The directory's
attribution renders beside the map's tile credit and in the
methodology's sources. Driven headlessly on a scratch build and by a
smoke test in CI: SL1 4BG within 5 km keeps the Slough Trading Estate's
sites nearest first, states what cannot be placed, and restores the
table on clearing.

**Two defects from the first hour on localhost (Luke, 2026-09-03):**
"I don't think a full postcode actually works — you have to enter a
district." The full postcode did work; two other things did not, and
together they looked like that. The parser read a typed sector, "SL1
4", as a district SL14 that does not exist — the regex took the digit
into the outward code because the space had been stripped before the
match — so the precision the control claims was the one input it
could not read; and a postcode typed on the Map tab filtered the pins
without moving the map, which left 22 survivors as a dot among 197
energy rings at the country's zoom. Now the space is the parse, a
lone trailing letter is a postcode mid-keystroke, an unspaced "SL14"
falls back to sector 4 of SL1 when no such district exists, and a
postcode typed or arrived at while the map is the view on screen
frames the radius the way "See on map" does, once per postcode and
radius, returning to the plotted set when it clears. The parser is
exercised under node from the page's own source, the map framing in
the smoke test.

The first CI run on the branch failed twice for one reason: CI drives
the committed `index.html`, the 2.12 release, which has no postcode
box and keeps the handoff's 300 px search input. The near smoke test
waited thirty seconds for a `#near` that was not there, and the
conformance test asserted 230 px of a page that had never been
crowded. Both now feature-detect the box rather than key off
`READER_HTML`: without it the smoke test skips, saying the page
predates the control, and the conformance test expects the handoff's
300 — so a scratch build of this code is still driven in full, and
the released page is asserted as what it is. The behaviour reaches CI
proper with the release that carries the control.
