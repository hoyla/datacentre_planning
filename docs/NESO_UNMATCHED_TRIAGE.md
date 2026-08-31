# The NESO register's unmatched demand rows: what they actually are

Triage run 2026-08-31 against `data/external_sources/neso-ea-register.xlsx`
(as-at 11 June 2025) and `neso-ea-register-matches.yaml`. This is the
phase-1 deliverable the ROADMAP asked for — **establish why the rows are
unmatched before proposing anything.** No matches have been written; that
is phase 2, and several rows below need a decision rather than a guess.

## The headline

**61 of the 106 unmatched rows are not data-centre schemes and never
will be.** The register lists transmission demand customers of every
kind, and the cohort is dominated by hydrogen electrolysis, rail traction
supply, carbon capture, steel and battery storage. Those rows are
correctly and permanently unmatched: they belong in `considered` with a
reason, not in a backlog.

What is genuinely actionable is **29 rows** — 19 with a corpus candidate
to test, 10 real data-centre schemes the corpus does not hold at all.
Three of the 19 arrived on a second pass, after Luke pointed out that a
developer's name for a site and the planning record's name for the same
ground are routinely different things; *the rebrand problem*, below, is
the general form of that and the reason the first pass under-counted.

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

## The 16 to test first

Strongest first. Each names the corpus site to check; none is a match yet.

| row | MW | register name | corpus candidate |
|---:|---:|---|---|
| 1091 | 1,000 | Cottam Giga | `PTNO-12871423` former Cottam power station, "1GW advanced data centre campus" — name and capacity both agree |
| 1287 | 920 | Relode Immingham | `PTNO-12776851` The Humber Tech Park Data Centre, at Killingholme |
| 1367 | 900 | Fiddler's Ferry Data Centre | Cuerdley/Widnes; corpus has Catalyst Business Park Widnes, not obviously the same |
| 610 | 720 | Ratcliffe Data Centre | `SITE-NorthWestLeicestershire/23/01083/NAC`, Ratcliffe on Soar |
| 1459 | 600 | Sundon DC | Central Bedfordshire, Houghton Regis / Linmere Island — locality only |
| 1111 | 500 | MKE DC | East Claydon; the initialism is unexpanded |
| 722, 764, 1508 | 435 each | Iver 1/2/3 Ark Estates | Uxbridge Moor (Iver B); Ark is a known operator with Iver-area sites |
| 1519 | 300 | Didcot Road 2 | `PTNO-12549436` Amazon data centre, Didcot |
| 1620, 1621 | 200, 80 | Bro Tathan Development | `PTNO-12727863` CWL2 data centre campus — Vantage's St Athan site |
| 1673 | 200 | Quest Park | site 83, Quest **Pit**, Ampthill Road, Houghton Conquest — the S35 scheme |
| 1137 | 160 | Edinburgh Business Park | `PTNO-12869683` Heriot-Watt 200MW AI data centre campus, at Currie |
| 1460 | 150 | Cardiff DC | `PTNO-12675606` Cardiff East park and ride, Old St Mellons |
| 1354 | 120 | Waltham | `PTNO-12406644` Google data centre, Waltham Cross |
| 1078 | 600 | Cato | `PTNO-12917829`, aliased "**Cato** Data Centre campus, Auchtertool, Fife (ILI Group)" — name identity |
| 870 | 450 | Bryn Coch DC | `PTNO-12880893` former Ferodo site, Caernarfon Road — Pentir serves Bangor |
| 1681 | 200 | Laleham DC | `PTNO-12814730` Manor Farm — but see the caution below |

**Two of these read differently once the aliases are searched.** Quest
Park (1673) and Cato (1078) are not locality inferences at all: the alias
file names both schemes in the register's own words, so each is a
name-identity match and should be written at `strong` rather than
`probable`. Cato's alias also supplies the operator — ILI Group — which
the register does not. Edinburgh Business Park (1137) firms up the same
way: `PTNO-12869683` is aliased "Heriot-Watt University, **Currie** —
200MW AI Data Centre Campus (Apatura)", and Currie is the connection
point. Cardiff DC (1460) likewise meets "**Cardiff East** Park and Ride —
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

**Cato has left this list**, and it is the strongest thing the triage
found. The alias file already names the site — "Cato Data Centre campus,
Auchtertool, Fife (ILI Group)", sourced to the operator's own
cato.ili-energy.com — so the register row and the corpus site agree on
the word *Cato*, and the site sits beside the Mossmorran substation the
register names. Against that: the scheme's architect states 600 MW
(graemenicholls.com, snapshotted, already in the ROADMAP) and the
register states 600 MW. **A named site, a named operator, and two
unrelated sources on the same figure** — the one row here that looks
ready to write at `strong` on the evidence already held.

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
