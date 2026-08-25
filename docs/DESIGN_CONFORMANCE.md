# What the design handoff still asks for, and what the reader does

Written 2026-08-25, after Luke: *"You seem to have been quite reluctant to
use the already settled specifications… it appears to me that you have
ignored most of [the handoff] and only followed [the plan] when pushed."*

That is accurate, and it came from treating the two documents wrongly.
**The handoff is the specification. `READER_REDESIGN_PLAN.md` is a diff
against it** — a list of what we rejected, what we added, and the order
of work. Everything the plan does not touch, the handoff still governs.
Filling those gaps with invention is not a shortcut; it is discarding a
settled decision and replacing it with an unsettled one.

So: every element of the handoff, its status, and whether the reader
does it. Status is one of

- **stands** — the handoff specifies it, nothing has overruled it;
- **rejected** — `READER_REDESIGN_PLAN.md` §2 rejects it, with evidence;
- **modified** — the plan or a later finding changes it, and the change
  is named here.

The "in the build" column is checked against a generated page, not
asserted.

---

## Hard constraints (handoff, "About the design files")

| element | status | in the build |
|---|---|---|
| One self-contained HTML file, no build step | stands | yes |
| **No CDN** | **modified** — Luke, 2026-08-24: "Google fonts are fine to use… We use source across our toolset." The handoff says "the real build must substitute locally available fonts or the existing stack". | **no — Source Sans 3 and Source Serif 4 load from fonts.googleapis.com.** Vendoring the woff2 subsets would satisfy both the handoff and Luke; the licences never prevented it |
| Every number walks back to a document | stands | yes |
| An absence is never silently a zero | stands | yes |

## The editorial-integrity rules

| rule | status | in the build |
|---|---|---|
| 1. No language model writes anything a reader sees as fact | stands | yes — cohorts are deterministic; the machine reading is labelled and gated |
| 2. Interpretation is attributed or absent | **rejected in its specified form** (§2: "the signed Reporter's note") | n/a |
| 3. Machine text is boxed, labelled, collapsed | **modified** — the template digest is rejected (§2); the machine reading (§7b) replaces it under the same rule | yes |
| 4. Highlights never replace data; excluded rows shown with their reason | stands | **partly — the site page has no "show every figure found, including the excluded ones" expansion** |
| 5. Coverage travels with every figure; three states never combined | stands | yes |

## 1. Header

| element | status | in the build |
|---|---|---|
| Full-bleed `#052962`, 32px padding, 1620px centred | stands | yes |
| Title Source Serif 4 28px/1.1/700 `#fff` | stands | yes |
| Release stamp 14px `#a8bad6`, incl. findings count | stands | yes |
| Tabs 15px/600, 4px `#ffe500` underline active, .75 inactive, counts at .6 | stands | yes |
| Prototype-only "figures are illustrative" strip | **do not ship** (handoff says so) | correctly absent |

## 2. Start here

Rebuilt to spec 2026-08-25. All elements present: two columns with a
380px sidebar at 48px, intro Source Serif 20px/1.45 capped at 46em, the
two-ways card with its `#c70000` and `#052962` left rules and uppercase
labels, the pitfalls card with a 4px `#c74600` rule and five hairline-
separated items, and both sidebar cards.

## 3. Signals — **the largest gap**

| element | status | in the build |
|---|---|---|
| Explainer card first, 4px `#333` rule, max-width 62em | stands | **no** |
| …stating the query is deterministic, defined in `dcp/signal_families.py`, wording a fixed template, ordering cohort size weighted by reading coverage | stands | **no** |
| …and in bold, that **no language model selected, ranked or described anything on the screen** | stands | **no** |
| One card per signal: white, 4px `#c70000` rule, grid `minmax(0,1fr) 300px` | stands | **no — cards exist, not to this spec** |
| Family label 13px/700 uppercase `#c70000` | stands | **no** |
| Verification pill beside it: green hand-checked/re-verified, amber machine-read | stands | **no** |
| Headline Source Serif 4 25px/1.18, count in words, never a cause | stands | **no — titles are not in words** |
| Definition block: the actual query, IBM Plex Mono 13px on `#f2f4f7`, 3px `#a8bad6` left rule | stands | **no** |
| "What it does not tell you" paragraph, label bold | stands | partly — limits text renders, without the specified label |
| Actions row: primary pill "Open these N sites in the table", link to the script, cohort CSV | stands | partly — no script link, no CSV |
| Right column: 1px left border, count Source Serif 42px, unit 13px, floor statement under a rule | stands | **no** |
| Six named cohorts in a given order | **modified** — §2 rejects `standby_below_10pct`; §6 builds four, with true counts that differ from the prototype's | four, correctly |

## 4. Sites

| element | status | in the build |
|---|---|---|
| Filter bar, search 300px, chips 999px, active brand fill | stands | yes |
| Signal view grid `2fr 1.7fr 180px 200px` | **modified** — Luke, 2026-08-24: participants as its own column, signals narrower and stacked | yes, five columns |
| Site cell: name 18px/700 brand, councils · key, proposal extract | stands | yes |
| MW Source Serif 21px/700 with basis line | **modified** — 2026-08-20: no external MW on a sortable row; basis carried in weight and a mark | yes |
| Reading bar 6px, blue ≥94%, orange 1–94%, grey at 0, with words | stands | yes |
| Header row 12px/700 uppercase, 1px `#121212` bottom | stands | **no — headers are not to this spec** |
| Footnote: neither view drops a row | stands | **no** |
| Full-table view: the release's own column set, `min-width` 1500px | stands | partly — one table, not two views |

## 5. Site page

| element | status | in the build |
|---|---|---|
| Header card, 4px brand rule, signal pills, name Source Serif 32px, councils · address · key · classification | stands | **no** |
| Row of 14px links: register, Drive, findings CSV, DuckDB, Pinpoint, copy link | stands | partly |
| Caveat banner `#fdf6e3`, 4px `#c74600` left border, site-state specific | stands | **no** |
| Body grid `1.55fr 1fr` | stands | **no — single column since 2026-08-24** (Luke: the jigsaw). The plan's §8b asked for the reconciliation; the two-column body is the handoff's and was not rejected. **Worth re-deciding: the jigsaw was seven cards in four columns, not two.** |
| Reporter's note | **rejected** (§2) | correctly absent |
| Adjudicated power figures: grid `132px 1fr`, value Source Serif 23px, told-to-audience line, document link with locator, confidence, model, fetch date, quote in serif italic with a 3px left rule, gate status | stands | **partly — the content is there, the specified form is not** |
| "Show every figure found… including the excluded ones" → 7-column table with adjudication pills and reasons | stands | **no** |
| Other power indicators: value Source Serif 19px, source link, match strength, "Matched on X" | stands | partly |
| What the documents say: subject in mono `#3f5570`, "Showing N of M", CSV link, subject filter, notebook link | stands | partly |
| Planning applications table | stands | yes |
| Generated digest | **rejected** (§2), replaced by the machine reading | correctly absent |
| Reading coverage panel with bar and sentence | stands | partly |
| Who is behind it, with the counting caveat verbatim | stands | yes |
| Generation, cooling and water, with the plant caveat verbatim | stands | yes |

## 6. The package

| element | status | in the build |
|---|---|---|
| Auto-fill grid `minmax(360px,1fr)`, gap 18px | stands | **no** |
| Card: 4px brand rule, 13px/600 uppercase kind, Source Serif 21px name, "Reach for it when…", 15px/600 link | stands | partly — the copy exists, the form does not |
| Eight cards | stands | yes |
| Footer: Barbour credit, consultation-response position, Apache 2.0 | stands | yes |
| A tab of its own | **modified** — ours lives on Start | by decision |

## 7. Reference tabs

Applications, Energy projects, Operators, Methodology, Dictionary, Notes
stay as they are: **stands**, and they do.

Map gains signal colours and a count of filtered-but-unlocatable sites:
**stands**, and both are in (2026-08-25).

## Tokens

| token | status | in the build |
|---|---|---|
| Colours (brand, yellow, news red, orange, slate, inks, rules, pills) | stands | partly — brand, yellow, orange, slate and the inks are in; the four **pill colour sets** (green/red/amber/slate with background, text and border) are not |
| Type scale: Serif 32/28/25/23/21/19/18; Sans 15/14/13/12; mono 12–13 | **modified** — Luke, 2026-08-24 asked for larger average sizes; the reader uses a 13px floor and a 16px body | by decision, but the SERIF scale still applies and is only partly used |
| Spacing 4px base; page 32px; cards 18–24px; gaps 18/22/24/36/48 | stands | partly |
| Square cards, 4px top rules, 1px dividers, 3–4px left rules, inputs radius 4px, pills 999px, **no shadows** | stands | **no — shadows remain on the map card, tooltip and subset banner** |
| IBM Plex Mono for code, definitions and site keys | stands | **no — not loaded** |

## Interactions

Tab switching, chip filtering, search, deep links, back-preserves-state,
independent per-site toggles, 120–150ms colour transitions, hover
darkening to `#234b8a`, single column below 1100px, tables scroll rather
than reflow: **stands**. Implemented except the hover colour, the
transition timing, and the all-figures toggle (which does not exist).

---

## What this leaves, in the order I would do it

1. **Signals (§3)** — the largest gap and the screen the redesign exists
   for. Explainer card, per-signal cards with family label, verification
   pill, serif headline stating the count in words, the actual query in
   a mono block, the limits paragraph with its label, the actions row
   with script and CSV links, and the right-hand count column.
2. **Site page (§5)** — header card, caveat banner, the figures in their
   specified form, and the all-figures expansion, which is editorial
   rule 4 and currently missing.
3. **Package (§6)** and the remaining tokens — pill colour sets, IBM
   Plex Mono, no shadows, hover and transition.
4. **Re-decide the site page body**: the handoff's two columns against
   the single column built on 2026-08-24. The jigsaw complaint was about
   seven cards in four columns; two columns may be right.
