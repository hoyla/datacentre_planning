# Unsited claims — operator-claimed facilities with no planning record

Luke's suggestion, 2026-09-02, after an evening in which three of them
turned up in an hour: "maybe we should have a layer of vendor-claimed
sites that we haven't matched to any planning application or Barbour
site". This note is the design. Nothing in it is built.

## Why it exists

The corpus is a planning corpus. A building permitted before the
acquisition window, or filed under a landlord's name, or in a council
the adapters do not reach, is invisible to it by construction — and the
operators, the permit register and the map all say the building is
there. Tonight's examples, each checked against the corpus before it
was written down:

| what the operator says | what the corpus holds | why absent (as far as tested) |
|---|---|---|
| NTT Slough 2 and 3, 670 and 665 Ajax Avenue, 1.8 and 2.7 MW | nothing at 665-670; Segro's GB One shell at 650-660 is a different building | Gyron's estate, pre-window; the permit (2022) has no document |
| ServerChoice Stevenage, opened 2008, new halls 2021, SG1 2FP | nothing; GSK's fence 470 m away | pre-window build; the 2021 halls untested (sweep at 51.8887, -0.2047) |
| VIRTUS LONDON4 (14 Liverpool Road) and LONDON19 (unlocated) | nothing at 14 Liverpool Road | untested (sweep at 51.5230, -0.6219); LONDON19 has no address anyone can cite |

And the ones already written down elsewhere, as prose:

- `environment-agency-permit-matches.yaml`, `considered:` — "No site
  record describes these": Equinix LD5 (8 Buckingham Avenue) and LD11x
  (765/767 Henley Road), Amazon's Slough plant, Woking (214 MWth),
  Narborough, Digital Realty Watford, Amazon Swindon, VIRTUS LONDON14,
  Zenium's "London Two", and VIRTUS's Stockley Park campus at 470 MWth
  — "the second-largest permitted fleet in this register stands at a
  campus the corpus does not hold".
- `data/priors/operator_pages.yaml` and the review workbook: the
  tier-four rows, "operator pages with no site in the corpus", the
  Pulsant estate among them.
- ROADMAP, "Coverage gaps worth closing": CyrusOne DC2 at Prologis
  Park, and the rest.

Three homes, all prose or sheet rows, none of which reaches the reader
or the workbook. A reporter cannot today see "the operator says there
is a building here and we have no planning record", and that sentence
is a finding — it is the measure of the corpus's blind spot, and it is
the first thing a rival dataset (DCM, Baxtel, a directory) will be
compared against.

## What it is, and is not

**Claims, not sites.** A row here carries the standing of its source —
an operator's page (the weakest authority in the claims store, and
labelled as such), a permit (regulatory, but thermal input is not
electrical demand), a directory (a lead and nothing more) — and never
the standing of a planning record. It is not ranked, not partitioned,
not counted in any site total, and never merged into `sites`. When a
planning record appears for one, the row retires with the site key
that absorbed it and the claim is matched the ordinary way.

**Decisions already made — do not relitigate.** No external MW becomes
a site column (EXTERNAL_DATA_SOURCES §7.1, settled twice). Directory
addresses are leads recorded with what corroborates them
(EXTERNAL_DATA_SOURCES, Datacenters.com, 2026-09-02). Every quote is
verbatim against a committed snapshot, and every snapshot has a Drive
id. Campus boundaries follow the operator's page (the Iron Mountain
rule). First-party operator claims get a typed rung; third-party
aggregates stay tier-and-count. The store is append-only.

## Shape

A hand-curated prior, because every row is a judgement about what a
name on a page refers to: `data/priors/unsited_facilities.yaml`.

```yaml
facilities:
  - id: ntt-slough-3                      # operator slug + facility
    operator: NTT Global Data Centers     # organisation_aliases group where one exists
    facility: Slough 3 Data Center
    identity:                             # as site_facilities.yaml: who says it exists
      - source: operator_roster
        url: https://services.global.ntt/.../slough-3-data-center
        snapshot: ntt-slough-3
        date: 2026-09-02
      - source: permit_register
        ref: EPR/YP3633QA
        date: 2026-09-02
    location:                             # as site_facilities.yaml: source + date, ≥1 of address/postcode/coords
      address: 665 Ajax Avenue, Slough Trading Estate, Slough
      postcode: SL1 4BG
      lat: 51.5162
      lon: -0.6141
      source: operator page; permit grid reference 496260,180610 (300 m, a postcode centroid)
      date: 2026-09-02
    claims:                               # names only — the figures live in the claims files
      - NTT Slough 3                      # operator-claims.yaml
    why_absent:
      reason: pre_window                  # pre_window | landlord_name | council_uncovered | not_fetched | unknown
      tested: false
      test: null                          # e.g. "PlanIt spatial sweep, 500 m, 2026-09-09"
      result: null
    nearest_record:                       # what the corpus does hold nearby, so nobody re-derives it
      site_key: PTNO-12602383
      distance_m: 700
      note: Segro's GB One shell at 650-660, the same postcode, a different building
    status: open                          # open | sited
    sited:
      site_key: null                      # set when a record appears; the row is never deleted
      date: null
```

Rules the loader (`dcp/unsited.py`) enforces, copied from the two
priors that already work this way:

- identity has at least one source with a date; a `snapshot` must
  resolve through `capacity_claims.snapshot_path`;
- location follows `site_facilities.LOCATION_FIELDS`: source and date
  required, at least one of address, postcode, coordinates, inside the
  UK bounding box;
- every name under `claims` exists in `operator-claims.yaml` or the
  permit claims, and is **unmatched** there — a matched claim is sited
  by definition, and the row must say so;
- `why_absent.reason` is from the closed set, and `tested: true`
  requires `test` and `result`;
- **a row whose coordinates fall inside a live site's radius fails the
  build** with the site key, because that is the moment it stopped
  being unsited. This is the test that keeps the layer honest: the
  corpus grows, and a row that was true in September is false in
  October.

## Feeds

1. **Operator snapshots.** For each `sources:` operator, its roster
   against `site_facilities.yaml` and the claim matches. The operator
   pages review already did this once by hand (tier four); the
   snapshots make it repeatable.
2. **The permit register.** Every `considered:` entry whose reason is
   "no site record describes these", with the grid reference the
   permit carries. Fourteen tonight.
3. **Directories and maps**, as leads: an address, with what
   corroborates it, and never a figure.
4. **A person on Street View.** Tonight's route.

## Rendering

- Workbook: a sheet, "Unsited facilities", one row per facility —
  operator, facility, address, postcode, coordinates, identity sources,
  claim names with their figures pulled from the claims tables (not
  restated here), why absent and whether tested, nearest record and
  distance, status. Dictionary entries for each column, in the
  handover's own words.
- Reader: a section, "Buildings the operators say exist that the
  planning corpus does not hold", with the count by reason at the top
  and the list beneath, each row linking its snapshot's Drive copy. The
  methodology paragraph says what the count measures.
- Both fold `sited` rows out of the live view and keep them in the
  sheet as history, so that "we found it later" is visible.

## The queue

Every open row with coordinates is a register sweep waiting to run:
`iter_by_spatial` through the PlanIt adapter at the row's point, a
radius the row's `test` records, on the adapter's politeness schedule.
Either an application turns up under another name — a new site at the
next materialise, the row retires as `sited` — or nothing does, and
`why_absent` becomes tested. The two tonight are 14 Liverpool Road and
SG1 2FP.

## Sequencing

1. The file, the loader, the tests, and a seed of tonight's rows plus
   the fourteen from `considered`. Docs: this note, ROADMAP,
   EXTERNAL_DATA_SOURCES cross-reference.
2. The workbook sheet and its dictionary entries; the sheet tab Luke
   creates by hand, as with Facilities (sheet_sync cannot add tabs).
3. The reader section, in the release after next, once the sheet has
   been read by someone.
4. The sweep runner: one row at a time, results written back as
   `test`/`result`, never as a deletion.

## What this note deliberately does not propose

- Estimating capacity for a building from its footprint, its permit's
  thermal input, or a directory's figure. The row carries the claims
  the sources make and nothing derived.
- Putting unsited rows into `sites`, the capacity model, any cohort, or
  any total.
- Scraping a directory. Datacenters.com's terms forbid it, and a hand
  read with attribution is what the location rule already allows.
- A "verified" status short of a planning record. Corroboration is
  recorded in words on the row; the only thing that closes a row is a
  record.

## Open, for Luke

- The file's home: `data/priors/` (hand-curated, as proposed) or
  `data/external_sources/` (where the claims it points at live).
- Whether `sited` rows stay on the sheet as history or move to their
  own tab.
- Which release carries the reader section.
