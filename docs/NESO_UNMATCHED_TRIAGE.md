# The NESO register's unmatched demand rows: what they actually are

Triage run 2026-08-31 against `data/external_sources/neso-ea-register.xlsx`
(as-at 11 June 2025) and `neso-ea-register-matches.yaml`. This is the
phase-1 deliverable the ROADMAP asked for — **establish why the rows are
unmatched before proposing anything.** No matches have been written; that
is phase 2, and several rows below need a decision rather than a guess.

> **Read this first: 24 of the 106 had already been adjudicated.**
> `neso-ea-register-matches.yaml` carries a `considered` section written
> on 2026-08-20 covering six rows explicitly and eighteen more by name.
> This triage re-examined all of them without knowing, because the probe
> that was supposed to count them looked for a `row:` key where the file
> uses `rows:`, reported "considered: 1", and so made an existing triage
> invisible. **Where this document and that section differ, the earlier
> reasoning is usually better** — see *What was already settled*, below.
> Eighty-two rows had never been examined, and that is where the new
> work is.
>
> Four passes, and each of the first three hit something the project had
> already written down: the ROADMAP's own recorded trap about probes
> that cannot see what they look for; the `site_aliases.yaml` file, which
> names outright what a local-authority sweep reached by geography; and
> `environment-agency-permit-matches.yaml`, which had articulated two
> causes of unmatching this document lacked. The argument for reading the
> ROADMAP, HISTORY and the channel's own files *before* building a probe
> could not be better made than by the cost of not doing it here.

## The headline

**61 of the 106 unmatched rows are not data-centre schemes and never
will be.** The register lists transmission demand customers of every
kind, and the cohort is dominated by hydrogen electrolysis, rail traction
supply, carbon capture, steel and battery storage. Those rows are
correctly and permanently unmatched: they belong in `considered` with a
reason, not in a backlog.

What is genuinely actionable is **29 rows** — 19 with a corpus candidate
to test, 10 real data-centre schemes the corpus does not hold at all.
But 13 of those 19 were already adjudicated on 2026-08-20, so the honest
count of *new* candidates is six, of which three are strong: **Cato,
Relode Immingham and Bro Tathan**. Set against those, two things here
matter more than any single match: the "Green Energy Centre" portfolios —
8,660 MW of transmission demand across nineteen schemes with no planning
application anywhere in this corpus — and the Quest Park correction.

The framing "106 unmatched claims, any of which could move a site across
the line" overstates the pool by roughly four times.

## The taxonomy

| cause | rows | MW | what it means |
|---|---:|---:|---|
| `dc_candidate` | 19 | 8,405 | a data-centre scheme, and the corpus holds a site worth testing |
| `dc_no_site` | 10 | 3,570 | a data-centre scheme with no corpus presence — a lead, not a defect |
| `colocated_plausible` | 19 | 8,660 | Ethos Green "Green Energy Centre" — see below |
| `unknown` | 16 | 7,064 | the row names nothing that identifies what it is |
| `not_dc` | 42 | 17,086 | the row names its own technology, and it is not a data centre |
| **total** | **106** | **44,785** | |

Twenty-nine rows were adjudicated by hand; the rest by a transparent rule
pass over the claim name and connection point. The rule pass is a first
pass for the eye and decides nothing on its own.

### The bucket that changed on inspection

`colocated_plausible` exists because the rule pass was about to hide
8,660 MW behind a renewables brand. **Ethos Green Energy's "Green Energy
Centres" are integrated hubs of renewable generation, long-duration
storage and *colocated data centres*** — the company holds a joint
development agreement with Frontier Power for up to 5 GW of colocated
data-centre capacity in the UK. Nineteen GEC rows sit in the demand
register under a name that reads as generation.

This is the cohort most worth a second look, and not only for matching:
a developer with a reported ~10 GW of connection offers, appearing in the
demand queue under a green-energy name, is demand that a search for "data
centre" does not find. Whether any individual GEC is a data centre is
unestablished — which is the point.

**And the project has already met these schemes from the other side —
but not as gas.**

> **Correction, 2026-08-31.** An earlier version of this section said the
> same schemes hold "a gas generation connection and a transmission
> demand connection at once", on the strength of
> `docs/EXTERNAL_DATA_SOURCES.md` §3 placing a "Green Energy Centre"
> cluster inside its 139 gas rows. **That was wrong, and I repeated it
> without checking the field it rested on.** Re-queried against the live
> TEC register: 52 GEC rows, 42 schemes, and **not one carries any gas
> term**. Their plant types are combinations of `Demand`, `Energy Storage
> System`, `PV Array (solar)` and `Wind Onshore`. §3 is corrected in the
> same change.

What the two registers do show, jointly:

| | TEC register | Existing Agreements register |
|---|---|---|
| rows | 52, across 42 schemes | 19 of the same schemes |
| capacity | 57–2,050 MW cumulative | 8,660 MW of `Transmission Connected Demand` |
| plant type | `Demand` on 30 of 52, with storage and solar | demand only |

Two SPV families — twenty customers named "⟨substation⟩ NG Limited",
twelve schemes suffixed "(Ethos Green)" — and almost every scheme named
after the substation it connects at, which is what grid-capacity
acquisition looks like before a site is named. **None of the nineteen
has a planning application anywhere in this corpus.**

Ethos Green publicly describes these as hubs of generation, storage
*and colocated data centres*, under a 5 GW joint development agreement
with Frontier Power. So the `Demand` leg may be a data centre — but the
register does not say so, and §3's own null hypothesis, that a `Demand`
plant type is the import leg of a storage-and-solar hybrid, fits the
coding just as well and is untested here. What survives without
inference: 8,660 MW of transmission-connected demand behind a name no
data-centre search returns, and nothing in the planning corpus about any
of it.

## The rows to test

Strongest first. Each names the corpus site to check; none is a match
yet. **`†` marks a row already adjudicated on 2026-08-20** — for those,
read the `considered` entry first, and treat this row as a proposal to
reopen it rather than as new information.

| row | MW | register name | corpus candidate |
|---:|---:|---|---|
| 1091 † | 1,000 | Cottam Giga | `PTNO-12871423` former Cottam power station, "1GW advanced data centre campus" — name and capacity both agree |
| 1287 | 920 | Relode Immingham | `PTNO-12776851` The Humber Tech Park Data Centre, at Killingholme |
| 1367 † | 900 | Fiddler's Ferry Data Centre | Cuerdley/Widnes; corpus has Catalyst Business Park Widnes, not obviously the same |
| 610 † | 720 | Ratcliffe Data Centre | `SITE-NorthWestLeicestershire/23/01083/NAC`, Ratcliffe on Soar |
| 1459 † | 600 | Sundon DC | Central Bedfordshire — already rejected as neither fitting the name nor the scale |
| 1111 | 500 | MKE DC | East Claydon; the initialism is unexpanded |
| ~~722, 764, 1508~~ † | 435 each | Iver 1/2/3 Ark Estates | **Withdrawn.** The 2026-08-20 entry settles these: no Ark scheme at Iver anywhere in the corpus, Ark's presence is Union Park (Hayes), so they are "a null worth reporting, not matching" |
| 1519 † | 300 | Didcot Road 2 | `PTNO-12549436` Amazon data centre, Didcot — earlier entry calls the name "generic", which stands |
| 1620, 1621 | 200, 80 | Bro Tathan Development | `PTNO-12727863` CWL2 data centre campus — Vantage's St Athan site |
| 1673 † | 200 | Quest Park | site 83, Quest **Pit**, Ampthill Road, Houghton Conquest — the S35 scheme. **This is the row that overturns its earlier entry** |
| 1137 † | 160 | Edinburgh Business Park | `PTNO-12869683` Heriot-Watt, Currie — but the earlier entry rejected exactly this on a location conflict |
| 1460 † | 150 | Cardiff DC | `PTNO-12675606` Cardiff East park and ride — earlier entry names two candidates, not one |
| 1354 | 120 | Waltham | `PTNO-12406644` Google data centre, Waltham Cross |
| 1078 | 600 | Cato | `PTNO-12917829`, aliased "**Cato** Data Centre campus, Auchtertool, Fife (ILI Group)" — name identity, and in no earlier entry |
| 870 | 450 | Bryn Coch DC | `PTNO-12880893` former Ferodo site, Caernarfon Road — Pentir serves Bangor |
| 1681 † | 200 | Laleham DC | `PTNO-12814730` Manor Farm — the earlier entry already said name and connection point disagree, and the alias confirms it |

**Only three of these are both new and strong**: Cato (1078), Relode
Immingham (1287) and Bro Tathan (1620/1621), none of which appears in any
`considered` entry. Quest Park (1673) is new only as a *correction*.
Everything marked † is a reopening, and most of them should probably stay
closed.

Quest Park and Cato are not locality inferences: the alias file names
both schemes in the register's own words, so each is a name-identity
match and should be written at `strong` rather than `probable`. Cato's
alias also supplies the operator — ILI Group — which the register does
not. Edinburgh Business Park (1137) looks the same way at first —
`PTNO-12869683` is aliased "Heriot-Watt University, **Currie** — 200MW AI
Data Centre Campus (Apatura)" and Currie is the connection point — but
the 2026-08-20 entry rejected that pairing on a location conflict, so
the alias is a reason to re-read that reasoning, not to override it.
Cardiff DC (1460) likewise meets "**Cardiff East** Park and Ride —
Data Centre (Curtis Hall Limited)" against a Cardiff East GSP.

Three cautions, all of them from the alias file arguing *against* a match:

- **Laleham (1681).** `PTNO-12814730`'s alias places Manor Farm at
  **Wraysbury Reservoir**, not Laleham. The Spelthorne highway
  application does name the run between the Laleham substation and Manor
  Farm, so the lead survives — but it is weaker than the second pass
  made it, and belongs at the bottom of this table rather than in it.
- **The three Iver rows (722, 764, 1508).** The register calls them
  "Ark Estates". The corpus's Iver sites are aliased to *other*
  operators — "West London Technology Park — Iver (Greystoke)" and "Iver
  Heath Data Park — 90MW Data Centre (CyrusOne)". Three 435 MW
  agreements and no Ark-aliased site at Iver is a reason to look for a
  fourth site, not to match these to a neighbour.
- **Bryn Coch (870)** rests on the local-authority sweep alone; no alias
  supports it.

Two of these carry a trap:

- **Waltham (1354)** sits at the same substation as rows 630 and 632,
  already matched *tentatively* to site 49. Matching it without settling
  those risks three claims on one site from one substation.
- **Bro Tathan** is two rows (200 and 80 MW) on one development. Two
  agreements, one scheme — the same shape as West Burton below.

## What was already settled, and the one thing that has changed

The 2026-08-20 `considered` entries cover: the two Rye House rows
(1080, 1547), the three Iver rows (1508, 722, 764), Sundon (1459), and
eighteen named by class — Fiddler's Ferry, Micklefield, Cardiff DC, IPC
Tremorfa, Laleham, Edinburgh Business Park, Clydebridge, Inchinnan,
Jawcraig, the Easterhouse campus, West Burton Giga, Cottam Giga,
Ratcliffe, Seagull, This Gravity, West Horndon, Quest Park and Didcot
Road 2.

Several of those entries are sharper than what this triage produced
independently, and should be preferred:

- **The Iver rows.** "1,305 MW of contracted Ark demand at Uxbridge Moor
  with no Ark scheme at Iver anywhere in the corpus — Ark's known corpus
  presence is Union Park (Hayes). Either pre-application land or a scheme
  our sweeps have not seen. **A null worth reporting, not matching.**"
  That is the right answer and this document should not have relisted
  them as candidates.
- **Laleham.** "Laleham DC's name and connection point point at different
  places" — which is what the Wraysbury alias says, established eleven
  days earlier.
- **Edinburgh Business Park.** "conflicts with the Heriot-Watt campus
  scheme's location". Examined and rejected; this triage proposed it.
- **Cardiff DC.** "could be Latos Rover Way or Vantage St Mellons" —
  more careful than the single candidate offered above.
- **The two Rye House rows** were matched to Hoddesdon on 2026-08-20 and
  **retired the next day**, because the match rested on site 97 being
  the only Hoddesdon data centre in the corpus — "a fact about the
  corpus, not about Hoddesdon". They are not fresh unknowns; they carry
  a documented history and a stated test for settling them.

**One earlier conclusion is now wrong, and this is the correction worth
making.** The class entry says of its members that "no corpus site
exists in the right place… (Quest Park)". A corpus site does exist:
site 83, Quest **Pit**, Ampthill Road, Houghton Conquest, holding 435
documents and the S35 direction, and `site_aliases.yaml` names it "Quest
Park Data Centre, Quest Pit". The 2026-08-20 judgement was made with the
same rebrand blind spot this document walked into, which is the argument
for fixing the method rather than the row.

## The channel next door had already worked this out

`environment-agency-permit-matches.yaml` is the sibling of the NESO
matches file, and its header had already articulated two structural
causes of unmatching before this triage invented its own vocabulary.
Both apply here and neither was in the first taxonomy:

- **Blocked by clustering.** Where a site record holds a whole estate,
  attaching a claim to it asserts that every operator inside it is one
  site. Nine permits from seven operators once sat inside site 23 for
  exactly this reason; they were listed under `considered` as evidence
  for `site_partitions.yaml` rather than as evidence about a site, and
  six of them found a campus once site 23 was partitioned.
- **Blocked by the corpus** — "a finding about coverage, not about
  matching". The permit file records 427 MWth of Equinix plant and
  151 MWth of Amazon's sitting at addresses the planning corpus has
  never seen.

The second is what this document called `dc_no_site`, arrived at
independently and named differently, which is worse than useless. **Read
it as "blocked by the corpus", the project's own phrase**, and treat the
ten as a coverage finding.

The first has no bucket here at all, and at least three rows want it:

- **The three Iver rows** (722, 764, 1508 — 435 MW each, "Iver 1/2/3
  Ark Estates" at Uxbridge Moor). The corpus's Iver sites are aliased to
  Greystoke and CyrusOne, and Ark's estate is aliased at Cody, Spring,
  Longcross, Alliance and Union Park but not at Iver. So these are
  either a coverage gap on an Ark scheme or a clustering problem at
  Uxbridge Moor, where site 443 already carries two matched rows
  (927 and 968). **Which of the two it is has to be settled before any
  of the three can be written**, and the permit file's Hayes entry — the
  same operator's Union Park, against site 61's six campuses — is the
  worked precedent.

The permit file's other warning applies too, verbatim: *"Postcode
proximity suggested a partition that the operator evidence then
refused."* Every locality-only candidate below is in that position.

## The rebrand problem, and what it changed

Luke, on reading the first pass: **"Quest Pit is the true location;
Quest Park is the operator rebrand."** That is not a note about one row.
It names a general cause of unmatching, and the first pass could not see
it: the register carries the name the *developer* uses, while the
planning record carries the name the *place* has — often the quarry,
pit, works or factory that was there before. A search for the register's
name against the corpus is blind to exactly that case, which is how the
first pass filed Quest Park as "no corpus site" when site 83 holds 435
documents.

So the thirteen were re-probed by a method that can see it: list **every**
corpus site in the containing local authority and look, rather than
matching a string. Three moved to `dc_candidate`:

- **Cato** (600 MW at Mossmorran) → `PTNO-12917829`, whose planning text
  is "Camilla Road, Auchtertool — data centre buildings" and whose
  **alias is "Cato Data Centre campus, Auchtertool, Fife (ILI Group)"**.
  The sweep reached it by geography; the alias names it outright.
- **Bryn Coch DC** (450 MW at Pentir) → `PTNO-12880893`, the former
  Ferodo site on Caernarfon Road. Pentir is the Bangor supply point.
  This one the sweep genuinely earned — no alias carries it.
- **Laleham DC** (200 MW at Sunbury Common) → `PTNO-12814730`, "Manor
  Farm — 147MW data centre & battery energy storage". The Spelthorne
  highway application that the first pass dismissed as noise in fact
  names the run *between* the National Grid Laleham substation and Manor
  Farm — though the site's own alias places it at Wraysbury Reservoir,
  so treat it as the weakest of the three.

The sweep was the right instinct and the wrong instrument. What it was
reaching for already exists as a curated file, and the next section says
so.

None is confirmed. Each is now a document to read rather than a gap.

## The 10 leads with no corpus site

Two kinds, and the difference matters for whether anyone should look
again:

**Nothing in the local authority at all** — Edzell (800 MW; Angus holds
no corpus site), Seagull Data connect at Gravity (450; Sedgemoor holds
one hospital), Inchinnan (180), Jawcraig (180). These are acquisition
leads: real schemes the corpus does not cover.

**A site in the area, but nothing that names the scheme** — Baglan Bay
(500 MW; the nearest is a 12MW Margam scheme, a different size of
thing), Easterhouse's "Digital and Manufacturing Campus Including Data
Centres" (500), Clydebridge (360; South Lanarkshire holds the M74
Central Eco Park), Micklefield (300; Leeds holds Skelton Grange), and
Radlett 1 and 2 (150 each; Hertsmere holds three data-centre sites, none
at Radlett). Locality-only, no name link — weaker than the three above
and not worth writing a match on without a document.

**Cato has left this list**, and it is the strongest row in the triage —
the one genuinely new candidate of any size, since it appears in no
`considered` entry. The identification itself was already held twice
over: `site_aliases.yaml` names `PTNO-12917829` "Cato Data Centre campus,
Auchtertool, Fife (ILI Group)", and `operator_pages.yaml` pairs the same
site with cato.ili-energy.com. What is new is that the NESO register
carries a Cato demand connection at the Mossmorran substation this site
sits beside.

**The figures need stating by quantity type, because a shared number is
not agreement.** Four routes reach roughly this scale and they measure
four things:

| source | figure | quantity |
|---|---|---|
| NESO EA register, row 1078 | 600 MW | contracted grid connection |
| the scheme's architect (graemenicholls.com) | 600 MW | unstated — marketing |
| the site's planning documents | 600 MW | `it_load` |
| the same documents | 850 MW | `it_load` |

The site also holds 800 MW `total_site`, 650 MW `cooling`, and the
1,200 MW `thermal_input` that `docs/REGENERATION_RUNBOOK.md` carries a
standing warning about — fuel entering a plant, not electricity leaving
it, and once mistaken for the dataset's largest site capacity.

So the honest reading is **not** "three sources agree on 600". It is that
a contracted connection, a marketing figure and one of two stated IT-load
figures all land on 600, while the same documents also state 850. The
convergence is worth reporting and the 600/850 split inside one document
set is worth resolving first — and neither is a reason to delay the
match, which rests on the name and the substation, not on the number.

## Two corrections to the ROADMAP

**1. Global Switch is not in this register.** The ROADMAP names "Global
Switch London East 87 MW and London South 70 MW" as examples of the 106.
Neither is a register row: a search of every row in the workbook returns
zero mentions of Global Switch, and no demand row is valued 87 or 70 MW.
Those two figures are `operator_website` claims read from
globalswitch.com, so they belong to the operator channel's 35 unmatched,
not the NESO 106 — a different row of the ROADMAP's own table.

**2. The 106 is not a work queue.** See the headline. The ROADMAP's
sentence "any of those, matched, could move a site across the line"
is true of 29 rows, not 106.

## Method, and what it cannot see

Rows were classified from the register's own fields — claim name,
connection point, capacity, connection date — plus a corpus search over
live sites, their member applications and projects (names, titles,
addresses, postcodes). Two probe defects were found and fixed while
running it, both worth recording because they are the kind that produce
confident negatives:

- A substring search for `ark` matched every "Park" in the corpus.
- Searching for "Quest Park" returned nothing, and the first read of that
  was "no corpus site". The corpus spells it **Quest Pit**. The site
  exists, holds 435 documents, and is the QuestPit S35 scheme.

The second defect turned out to be the general one. Luke: *"Quest Pit is
the true location; Quest Park is the operator rebrand."* A developer
renames the ground it builds on — a pit becomes a park — and the register
records the new name while the planning file keeps the old. **A name
search across the two therefore has a systematic blind spot, not a random
one**, and it fails in the direction that produces confident negatives.

**HISTORY records the same failure twice without ever generalising it.**
Wapseys Wood was in the corpus all along under the NSIP register's name
for it, "SDC M40 Campus", with a display name taken from the register's
location prose — "the words 'Wapseys Wood' appear in neither" — and that
is what made the Guardian's story team conclude the corpus was missing
it. The mechanism is stated plainly elsewhere in HISTORY: "the display
name of a site is the address of whichever application sorts first, which
has no relationship to what anyone calls the place." Quest Park is the
third instance. The rule below is what those three cases were waiting
for.

### The probe was searching the wrong corpus of names

Both earlier passes searched site display names and the titles, addresses
and postcodes of member applications and projects. **Neither searched
`data/priors/site_aliases.yaml`** — which is precisely where this project
records the reconciliation the rebrand problem creates. The alias file
holds both names in one string:

- `PTNO-12669230` → "**Quest Park** Data Centre, Quest Pit"
- `PTNO-12917829` → "**Cato** Data Centre campus, Auchtertool, Fife (ILI
  Group)"

Either would have matched the register's own string immediately. The
local-authority sweep that found Cato was doing expensively, and with a
weaker result, what one join to the alias map does exactly (Luke,
2026-08-31).

**So the rule for any future name search against this corpus: search the
aliases alongside the derived names.** A derived name is what a source
called a place; an alias is what a person established it *is*. Fifty-six
aliases carry that work, and a probe that skips them re-derives it badly.
Re-run alias-aware across all 106, twenty rows hit an alias, and the
material results are in the corrections above and below.

The `dc_no_site` bucket stays split into "nothing in the authority" and
"something in the authority, but nothing that names the scheme", because
a name-only negative is untested rather than absent.

What this triage cannot do is confirm a match. Every candidate above is a
prompt to read a document, not evidence. The `dc_candidate` and
`dc_no_site` split rests on corpus *presence*, which is a weaker test
than identity: a site can be present and be a different scheme.
