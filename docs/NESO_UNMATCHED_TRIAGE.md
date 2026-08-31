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

What is genuinely actionable is **29 rows** — 16 with a corpus candidate
to test, 13 real data-centre schemes the corpus does not hold at all.

The framing "106 unmatched claims, any of which could move a site across
the line" overstates the pool by roughly four times.

## The taxonomy

| cause | rows | MW | what it means |
|---|---:|---:|---|
| `dc_candidate` | 16 | 7,155 | a data-centre scheme, and the corpus holds a site worth testing |
| `dc_no_site` | 13 | 4,820 | a data-centre scheme with no corpus presence — a lead, not a defect |
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

Two of these carry a trap:

- **Waltham (1354)** sits at the same substation as rows 630 and 632,
  already matched *tentatively* to site 49. Matching it without settling
  those risks three claims on one site from one substation.
- **Bro Tathan** is two rows (200 and 80 MW) on one development. Two
  agreements, one scheme — the same shape as West Burton below.

## The 13 leads with no corpus site

Edzell (800 MW), Baglan Bay (500), Seagull Data connect at Gravity (450),
Bryn Coch (450), Clydebridge (360), Micklefield (300), Laleham (200),
Inchinnan (180), Jawcraig (180), Radlett 1 and 2 (150 each), the
Easterhouse "Digital and Manufacturing Campus Including Data Centres"
(500), and **Cato (600 MW at Mossmorran)**.

These are correctly unmatched — the corpus does not cover them — and each
is an acquisition lead rather than a matching failure.

**Cato is worth flagging on its own.** The ROADMAP already carries a Cato
lead from the scheme's architect (graemenicholls.com, snapshotted, states
600 MW). The register independently states 600 MW for a Cato demand
connection at Mossmorran. Two unrelated sources, the same figure, and no
planning presence in the corpus.

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
  exists, holds 435 documents, and is the QuestPit S35 scheme. A
  place-name probe has to allow for the register and the register office
  disagreeing about a word.

What this triage cannot do is confirm a match. Every candidate above is a
prompt to read a document, not evidence. The `dc_candidate` and
`dc_no_site` split rests on corpus *presence*, which is a weaker test
than identity: a site can be present and be a different scheme.
