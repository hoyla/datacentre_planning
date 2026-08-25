# Handoff: Datacentre planning reader — story-finder redesign

## Overview

A redesign of the published reader for **hoyla/datacentre_planning** (Guardian
investigative dataset: UK data-centre planning applications). The current reader
is generated as one self-contained HTML file by `scripts/export_reader.py`, with
tabs Start here / Sites / Applications / Energy projects / Map / Operators /
Methodology / Data dictionary / Assistant's notes.

The problem it solves: the reader is organised like a database, and its target
users — Guardian journalists on tech, environment and data/visual desks — arrive
wanting to know which of 456 sites is worth opening. The anomalies that answer
that question currently sit in prose in the Assistant's notes tab.

The redesign adds a **Signals** layer over the existing data without removing any
of it, and reframes the site view as a page rather than an expanding row.

**Two design iterations are bundled. v2 supersedes v1.** v1 replaced data with
editorial framing, which was rejected for good reason (it converted a rigorous
data platform into unattributed AI judgement). v2 is the design to implement; v1
is included only to show what was tried and rejected.

## About the design files

The files in this bundle are **design references created in HTML** — prototypes of
intended look and behaviour, not production code to copy. The target codebase is
Python: the reader is emitted by `scripts/export_reader.py` as a single HTML file
with inline CSS/JS, no CDN, no build step. **Implement these designs by changing
that generator**, following its existing conventions (string templates, inline
styles, self-contained output), not by shipping these files.

Two hard constraints from the repo that the implementation must keep:

1. **One self-contained HTML file**, no CDN, no build step, no runtime dependency
   beyond map tiles. The prototypes load Google Fonts by `<link>`; the real build
   must substitute locally available fonts or the existing stack.
2. **Every number walks back to a document**, and **an absence is never silently a
   zero**. Both are load-bearing in this design, not decoration — see "Provenance
   rules" below.

## Fidelity

**High fidelity.** Colours, type, spacing, copy and interaction behaviour are
final and specified below. Figures in the prototypes are illustrative, taken from
screenshots of the 2.2 release; the real values come from the same queries the
current reader uses.

## The editorial-integrity rules this design encodes

These are the point of the redesign. An implementation that keeps the layout but
drops these rules has not implemented it.

1. **No language model writes anything a reader sees as fact.** Every item on the
   Signals screen is a deterministic query with its definition, its script path,
   its verification status and a mandatory "what it does not tell you" paragraph
   rendered from a required field. A cohort with no limits text must fail the
   build rather than render without it.
2. **Interpretation is attributed or absent.** The Reporter's note panel renders
   only human-authored, signed, dated text. Its empty state is a first-class
   design ("No one has written a note on this site yet"), not a placeholder.
3. **Machine text is boxed, labelled and collapsed.** The Generated digest is
   template-filled from adjudicated figures only, shows the template that produced
   it, carries no adjectives and no cross-site comparison, and is collapsed by
   default. Match strength is carried into the sentence and can never be promoted.
4. **Highlights never replace data.** Every panel that summarises has an
   expansion to the full underlying rows, including rows excluded from
   adjudication, each with its exclusion reason. Excluded rows are shown, not
   deleted.
5. **Coverage travels with every figure.** Partly-read sites say so at the top of
   the page and repeat "figures are floors" in the reading panel and in the sites
   list. Sites read in full that disclose nothing, sites partly read, and sites
   with no documents are three different states with three different labels, never
   combined into one count.

## Screens / views

### 1. Header (all screens)

- Full-bleed `#052962`, horizontal padding 32px, content max-width 1620px centred.
- Title "UK datacentre plans": Source Serif 4, 28px/1.1, 700, `#fff`.
- Release stamp beside it: Source Sans 3 14px, `#a8bad6` — phase, site count,
  application count, document count, findings count, generation timestamp, pipeline
  hash. Same fields as today's stamp, plus findings count.
- Tab row: 15px/600 buttons, padding 9px 12px 11px, `border-bottom: 4px solid`
  `#ffe500` when active and transparent otherwise, inactive opacity .75. Counts
  render inline at opacity .6.
- Tabs: Start here · Signals (6) · Sites (456) · Applications (1,709) ·
  Energy projects (197) · Map · Operators (15) · Methodology · Data dictionary ·
  Assistant's notes · The package (8).
- Prototype-only strip beneath the header (`#fff9d9`, 1px `#e6dc9a` bottom border,
  13px `#4a4400`) stating the figures are illustrative. **Do not ship this.**

### 2. Start here

Two columns: content `minmax(0,1fr)`, sidebar 380px, gap 48px, page padding 32px.

- Intro paragraph: Source Serif 4 20px/1.45, max-width 46em.
- "Two ways in, and they are not the same thing" card: white, 4px `#052962` top
  rule, padding 20px 24px 22px. Two equal columns, gap 28px, each with a 3px left
  rule (`#c70000` for Signals, `#052962` for the data), an uppercase 13px/600
  label with .6px tracking in the rule colour, 15px/1.5 body, and a pill button.
  Primary pill: `#052962` fill, `#fff`, 15px/600, padding 9px 18px, radius 999px.
  Secondary pill: white fill, 1px `#052962` border, `#052962` text.
- "Where this data can mislead": white card, 4px `#c74600` top rule. Five items,
  each separated by 1px `#dcdcdc`, title 15px/600, body 15px/1.5 `#333`. Copy is
  the pitfalls list from the current Assistant's notes tab, verbatim.
- Sidebar card "Coverage, stated as a boundary": 4px `#052962` rule; rows of
  label/value (14px, value 600) with a 13px `#6b6b6b` note under each explaining
  what the number excludes. Five rows: documents held, prose analysed, sites
  disclosing a capacity, verified findings, read-twice status.
- Sidebar card "The rest of the package": 4px `#333` rule, secondary pill to the
  package screen.

### 3. Signals

- Explainer card first: white, 4px `#333` rule, max-width 62em. States that each
  signal is a deterministic query defined in `dcp/signal_families.py`, that the
  wording is a fixed template with the count substituted, that ordering is cohort
  size weighted by reading coverage, and — in bold — that **no language model
  selected, ranked or described anything on the screen**. Inline code style:
  IBM Plex Mono 13px on `#f2f2f2`, padding 1px 5px.
- One card per signal: white, 4px `#c70000` top rule, padding 20px 24px 22px,
  grid `minmax(0,1fr) 300px`, gap 36px, 16px bottom margin.
  - Family label: 13px/700 uppercase `#c70000`, .6px tracking.
  - Verification pill beside it (see pill tokens): green for hand-checked or
    re-verified, amber for machine-read.
  - Headline: Source Serif 4 25px/1.18, 700, max-width 30em, sentence case, states
    the count in words and the property — never a cause.
  - Definition block: IBM Plex Mono 13px/1.55, `#22303f` on `#f2f4f7`, 3px
    `#a8bad6` left rule, padding 10px 12px, `white-space: pre-wrap`. Contains the
    actual query.
  - "What it does not tell you" paragraph: 14px/1.5, label in bold.
  - Actions row: primary pill "Open these N sites in the table", link to the script
    that produces the cohort, link to the cohort as CSV.
  - Right column: 1px `#dcdcdc` left border, padding-left 22px; count in Source
    Serif 4 42px/700; unit 13px `#6b6b6b`; below a 1px `#ececec` rule, the floor
    statement (who cannot enter this cohort, and which way further reading moves it).
- Six cohorts, in this order, with exact copy in the prototype: no capacity in a
  fully-read file (22); stated demand exceeds stated connection (2, hand-checked);
  generation with no fuel named (61); generation larger than the computing load (9);
  one quantity to more than one audience (18); standby below 10% of stated load (14).

### 4. Sites

Filter bar (white, padding 14px 20px, 1px `#dcdcdc` bottom border):
- Search input: 15px, padding 9px 12px, 1px `#999`, radius 4px, width 300px.
  Placeholder "Search site, council, address, application".
- Cohort chips: 13px, padding 6px 13px, radius 999px; active `#052962` fill/white,
  inactive white with 1px `#c7c7c7` and `#052962` text. First chip "All 456 sites",
  then one per signal with its cohort count in parentheses.
- Right side: count string, then a pill toggle between "Switch to the full table"
  and "Switch to the signal view".
- **Count string honesty:** when a cohort is active it reads "N of M sites in this
  cohort shown in the sample"; unfiltered it reads "N of 456 sites". Never show a
  filtered count against the total.

Signal view (default): grid `minmax(0,2fr) minmax(0,1.7fr) 180px 200px`, gap 24px,
row padding 16px 20px, 1px `#dcdcdc` between rows, `align-items: start`.
- Column 1: site name (Source Serif 4 18px/700 `#052962`, click opens the site),
  then 13px `#6b6b6b` "councils · site key", then 14px/1.4 proposal extract.
- Column 2: signal pills, wrapped, 6px gap.
- Column 3: MW in Source Serif 4 21px/700 with a 13px `#6b6b6b` basis line beneath
  ("Disclosed IT load · may rise", "No capacity disclosed", "Inferred from
  floorspace — weakest class", "No documents held").
- Column 4: 6px reading bar on `#ececec` — fill `#052962` above 94%, `#c74600`
  between 1 and 94%, `#c7c7c7` at 0 — then "N/M documents read" and, in `#a13a00`,
  "Figures are floors" / "Complete" / "Nothing published".
- Header row: 12px/700 uppercase `#6b6b6b`, .6px tracking, 1px `#121212` bottom.
- Footnote beneath the table: neither view drops a row; a site with no figure
  appears with its reason and an unread site appears as unread, not as zero.

Full-table view: the release's own column set, nothing hidden — site key (mono
12px), site + councils, classification, proposal, power MW, basis, other
indicators, disclosure status, location, read, findings, source links. `min-width`
1500px inside an `overflow-x: auto` wrapper; 13px body, 11px uppercase headers,
1px `#ececec` row rules, `vertical-align: top`.

### 5. Site page

Header card: white, 4px `#052962` top rule, padding 22px 26px 24px.
- Signal pills, then name in Source Serif 4 32px/1.15/700 (max-width 28em), then
  15px `#6b6b6b` "councils · address · site key (mono) · classification".
- Row of 14px links, gap 24px: council register, N documents on Drive, findings CSV
  with count, query in DuckDB, Pinpoint collection, copy link to this site.

Caveat banner directly beneath: `#fdf6e3`, 4px `#c74600` left border, padding
14px 18px, 15px/1.55 `#3d2b00`. Text is site-state specific — reading incomplete
with the floor language / all documents analysed and nothing stated / register
publishes nothing, checked / figure inferred from floorspace / tentative register
match present.

Body: grid `minmax(0,1.55fr) minmax(0,1fr)`, gap 22px.

Left column, in order:
1. **Reporter's note** — 4px `#333` rule. Header row: uppercase label plus 13px
   `#6b6b6b` "Written by a person, signed, and dated. Nothing generated goes here."
   Filled state: Source Serif 4 18px/1.5 note, then 14px italic `#6b6b6b` byline
   with date and verification status. Empty state: 15px `#6b6b6b` "No one has
   written a note on this site yet. The figures below are the record; what they
   mean is not in the dataset." plus a secondary pill "Add a note".
2. **Adjudicated power figures** — 4px `#052962` rule. Intro explains grouping by
   audience and that different quantities are not contradictions. Each figure:
   grid `132px minmax(0,1fr)`, gap 18px, 1px `#dcdcdc` top rule. Left: value in
   Source Serif 4 23px/700, quantity 13px `#6b6b6b`. Right: "Told to **audience** ·
   published as "label""; then document link with locator, confidence, model that
   read it, fetch date; then the verbatim quote in Source Serif 4 italic 15px with
   a 3px `#dcdcdc` left rule; then 13px `#6b6b6b` gate status.
   Below: secondary pill "Show every figure found in this site's documents,
   including the excluded ones", expanding a 7-column table (value, unit, quantity
   as written, document, locator, read by, adjudication) at 13px, `min-width` 900px.
   Adjudication cell carries a pill — green "this site", amber "probable", slate
   "tentative" / "excluded" / "inferred" / "energy layer" — with the reason beneath
   in `#6b6b6b`. Closing note states how many of the site's numeric findings are
   shown, that excluded rows are kept rather than deleted, that a maximum over the
   table will be wrong, and links the findings CSV and DuckDB file.
3. **Other power indicators** — 4px `#333` rule. Intro states these come from
   outside the planning system, measure different quantities with different
   authority, and that divergence is the finding rather than an error to reconcile.
   Rows: value (Source Serif 4 19px/700), label + entity, source link with locator
   and match strength, then "Matched on X" plus a match note.
4. **What the documents say** — findings list. Subject in IBM Plex Mono 12px
   `#3f5570`, text 14px/1.5, document link and locator in `#6b6b6b`. Header shows
   "Showing N of M verified findings"; footer links all findings as CSV, a subject
   filter, and the notebook.
5. **Planning applications at this site** — reference (600) with proposal beneath,
   status, received, verdict, document count link, register link.

Right column:
1. **Generated digest** — `#f2f4f7` panel, 4px `#3f5570` rule, collapsed by
   default with a Show/Hide text button. Always-visible caption: machine-written
   from this site's own adjudicated figures using a fixed template, not editorial
   content, not a finding. Expanded: the digest in Source Serif 4 16px/1.5, then
   the template itself in IBM Plex Mono 12px on white.
2. **Reading coverage** — bar plus a sentence naming documents analysed, what the
   remainder is (OCR queue, deep-read queue, drawings without prose), and that
   figures are floors.
3. **Who is behind it** — role/value rows, with the counting caveat verbatim
   ("Names are counted, not ranked by role…").
4. **Generation, cooling and water** — label/value rows, with the plant-counting
   caveat verbatim (highest disclosed in any one document; bracketed numbers count
   passages, not units; cooling and fuel are not adjudicated for attribution).

### 6. The package

Auto-fill grid, `minmax(360px,1fr)`, gap 18px. Each artefact card: white, 4px
`#052962` top rule; 13px/600 uppercase `#6b6b6b` kind; Source Serif 4 21px/700
name; 14px/1.5 what it is; a "**Reach for it when** …" line; and a 15px/600 link.
Eight cards: this portal, the workbook, the DuckDB file, the Drive tree, the
Pinpoint collection, the notebook bundle, methodology + data dictionary, the
assistant's notes. Footer states the Barbour ABI credit requirement, the
consultation-response personal-data position, and the Apache 2.0 code licence.

### 7. Reference tabs

Applications, Energy projects, Map, Operators, Methodology, Data dictionary and
Assistant's notes stay as they are today. In the prototype they render a card
stating what is unchanged and what small change the redesign implies — the map
gains the signal colours and a count of filtered-but-unlocatable sites; the energy
table links back to sites carrying the co-location signal; the dictionary becomes
reachable from column headers; the notes tab keeps its framing while the patterns
it buried become queries on the Signals screen.

## Interactions & behaviour

- Tab click → screen switch. The Sites tab stays visually active while a site page
  is open.
- Signal card "Open these N sites" → Sites screen, cohort chip applied, search
  cleared, signal view forced.
- Cohort chip click → filter; "All 456 sites" clears it.
- Search input → case-insensitive substring over name, councils, address, proposal.
- Row site-name click → site page; resets the all-figures and digest toggles to
  collapsed.
- "Back to sites" → Sites screen, preserving the active cohort and search.
- View toggle → signal view ↔ full table, filter preserved.
- All-figures toggle and digest toggle are independent, per-site, collapsed on entry.
- Transitions: colour and border only, 120–150ms ease. No scale, no bounce.
- Hover: links darken to `#234b8a` and underline; pill buttons darken their fill.
- Responsive: single column below ~1100px (sidebar drops beneath content); tables
  keep `overflow-x: auto` rather than reflowing — a column must not be hidden.

## State management

- `tab`: start | signals | sites | site | apps | energy | map | operators |
  method | dictionary | notes | downloads
- `filter`: signal key or null
- `query`: search string
- `view`: signal | table
- `selected`: site key
- `showAll`: boolean, all-figures table
- `showDigest`: boolean, generated digest

No data fetching — the generator inlines the dataset, as today. Deep-linking:
today's reader supports a copy-link-to-site URL; keep that and add cohort and view
to the same mechanism so a signal cohort can be shared.

## Design tokens

Colours
- Brand blue `#052962` — header, primary actions, section rules, links
- Yellow `#ffe500` — active tab underline only
- News red `#c70000` — signal rules and family labels
- Orange `#c74600` — caution rules (pitfalls, partial reading)
- Slate `#3f5570` — machine-generated content and finding subjects
- Ink `#121212`; body `#333`; secondary `#6b6b6b`
- Rules `#dcdcdc`, light rules `#ececec`, page `#f6f6f6`, paper `#fff`
- Pills: green `#e9f3ec`/`#1d6b38`/`#c7e0d0`; red `#fdecec`/`#a51818`/`#f3c9c9`;
  amber `#fdf0e6`/`#a13a00`/`#f2d6bd`; slate `#eef1f6`/`#3f5570`/`#d6dde8`
  (background / text / border)
- Caveat banner `#fdf6e3` on `#3d2b00`; prototype strip `#fff9d9` on `#4a4400`

Type
- Headlines and figures: Source Serif 4 — 32/28/25/23/21/19/18px, 700, line-height
  1.1–1.2, sentence case
- UI, metadata, tables: Source Sans 3 — 15/14/13/12px, 400/600/700; uppercase
  labels 12–13px/700 with .6–.7px tracking
- Code, definitions, site keys: IBM Plex Mono 12–13px
- Verbatim quotes: Source Serif 4 italic 15px/1.45
- Substitutes for the Guardian's proprietary families (Guardian Headline /
  Egyptian / Text Sans). Swap to the licensed stacks, or to whatever the current
  reader already ships, at implementation.

Spacing: 4px base. Page padding 32px; card padding 18–24px; row padding 16px 20px;
table cell padding 8–11px 10–14px; grid gaps 18/22/24/36/48px.

Shape: square cards, no radius. 4px coloured top rules on cards; 1px `#dcdcdc`
dividers; 3–4px left rules for quotes and callouts. Inputs radius 4px. Buttons and
pills radius 999px. No shadows anywhere.

## Assets

None. No images, no icon font, no SVG icons — the design uses type, rules and
colour only, and the one glyph used is a text arrow ("← Back to sites"). Fonts are
loaded from Google Fonts in the prototypes; the shipped reader must not depend on
a CDN.

## Screenshots

`screenshots/` holds one capture per screen, in reading order:
01 Start here · 02 Signals · 03 Sites, signal view · 04 Sites, full table ·
05 Site page · 06 Site page with the all-figures table and generated digest
expanded · 07 The package. They are references for layout and density; the
prototype file is authoritative for exact values.

## Files

- `Datacentre story finder v2.dc.html` — **the design to implement.** Self-contained;
  opens in a browser. All screens, all copy, all interactions.
- `Datacentre story finder.dc.html` — v1, superseded. Included only as the record of
  a rejected direction: it replaced provenance with editorial framing.
- `support.js` — runtime for the prototype format. Not part of the design and not
  to be ported.

Source repository for the implementation: `hoyla/datacentre_planning`, generator
`scripts/export_reader.py`; cohort definitions belong beside
`dcp/signal_families.py`, `dcp/capacity_claims.py` and
`dcp/operator_disclosure.py`.

## Open question for the team

Whether the Reporter's note is editable in the page and persisted, or authored
upstream (a YAML or table in the pipeline) and generated in. The design assumes the
latter — the reader is a handover artefact with no backend — but the empty state is
written to work either way.
