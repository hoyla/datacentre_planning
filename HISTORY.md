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
— `data/priors/site_partitions.yaml`, honoured by `dcp/sites.py` — but
only one boundary has been drawn with it, the International Trading
Estate split that moved records to site 443. Until more are, treat any
match to a site record covering an industrial estate as suspect; the
Environment Agency permits are the sharpest evidence for where the
boundaries fall, because each names a campus and gives a grid reference.

**Never let an external figure become a site's own number.** The two
reader panels say where their figures come from, and per-quantity
caveats replaced the single flat one once the sources multiplied — what
needs saying about a contracted grid ceiling is not what needs saying
about a marketing figure or a thermal rating. A test asserts every
quantity type that can reach the indicators panel carries a caveat, so a
new source cannot arrive unlabelled.

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

