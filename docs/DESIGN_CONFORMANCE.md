# Where the reader departs from the design handoff, and why

**The handoff is the specification.** `design_handoff_datacentre_reader/README.md`
governs everything it covers; `READER_REDESIGN_PLAN.md` is a diff against it —
a list of what was rejected, what was added, and the order of work. Everything
the plan does not touch, the handoff still governs, and filling those gaps with
invention is not a shortcut but the replacement of a settled decision with an
unsettled one.

This file used to be a table saying which parts of the handoff the build
honoured. It was wrong three times in a fortnight: it said Signals was unbuilt
when most of it was built, said IBM Plex Mono was not loaded when it was named
in the stylesheet, and never noticed that **no webfont had loaded at all**. A
document that asserts conformance cannot detect the day conformance stops.

So the handoff's numbers now live in **`tests/test_design_conformance.py`**,
checked against a real build in a real browser. Colours, sizes, weights,
spacing and shape from the token table and from each screen's specification are
assertions there. Deliberately breaking three rules — a specificity regression
on the signal card, a chip filled with the wrong colour, a drop shadow put back
— fails three tests, one each.

That test can check what the CSS *does*. It cannot know what was decided. This
file is the decisions.

---

## Departures from the handoff, with who made them

| what | the handoff | what the reader does | decided |
|---|---|---|---|
| **Fonts from a CDN** | "no CDN … the real build must substitute locally available fonts" | Source Serif 4, Source Sans 3 and IBM Plex Mono load from Google Fonts | Luke, 2026-08-24: "Google fonts are fine to use… We use source across our toolset." Vendoring the woff2 subsets would satisfy both; the licences never prevented it. |
| **Reporter's note** | Left column 1 of the site page; a signed, dated, human-authored panel with a designed empty state | Absent | `READER_REDESIGN_PLAN` §2: no mechanism exists to author or persist one, and an empty panel on 456 sites is furniture. |
| **Generated digest** | Right column 1; template-filled prose from adjudicated figures, collapsed | Absent; the machine reading (§7b) stands where it would have | `READER_REDESIGN_PLAN` §2 |
| **"Power on record"** as the power column heading | Signal view column 3 | "Power MW" | `READER_REDESIGN_PLAN` §2 rejects the phrase by name |
| **`standby_below_10pct`** cohort | One of the six signals | Not built | Review of 2026-08-23: the cohort is unsafe — Elsham, Watford and the PV sites enter it for reasons that are not the property it names |
| **Two views, with a toggle** | Signal view and full table, switched by a pill | One table, whose columns do not change with the filter | Luke, 2026-08-24: "the table layout should not change its columns when a filter is or is not applied" |
| **Signal-view columns** | Site · Signals · Power · Reading | Site · Who's behind it · Signals · Power MW · Power indicators · Reading | Luke, 2026-08-24: participants as a column of their own, signals narrower and stacked. Status and location dropped and moved to the site page's title block; **Read kept** after I argued it is the column that distinguishes "nothing there" from "not looked yet". |
| **External MW on a row** | Full table column "Other indicators" carries a figure | A confidence tier and a count, never a megawatt figure | 2026-08-20: a number beside Declared power reads as directly comparable to it, and a register claim can be a different quantity type |
| **Site name measure** | `max-width: 28em` | No measure | The 28em sized a name inside a column; the header card is the width of the page |
| **The package as a tab** | Eleventh tab, "The package (8)" | A section of Start here | Earlier release decision; the eight cards themselves are §6's |
| **Grey line under the site name** | "councils · site key" | site key · location · councils | Luke, 2026-08-25 |
| **Site names** | (not addressed) | Title-cased for display where the source shouts | Luke, 2026-08-25. `dcp/proposal.title_case`; `sites.display_name` keeps the register's own spelling, which is what the workbook and any citation use. |
| **Signal pills, centred** | Left-aligned in their column | Centred in the column and in the pill | Luke, 2026-08-25 |
| **Type scale** | Sans 15/14/13/12 | A 13px floor and a 16px body | Luke, 2026-08-24 asked for larger average sizes. The serif scale is unchanged. |
| **Dark scheme** | (none in the handoff) | None | Luke, 2026-08-24: colour here carries meaning, and a second palette is a second set of meanings to keep true |

| **Empty values** | A dash | A two-or-three-word reason in the muted style | Luke, 2026-08-26: "a dash for unknown is not doing its job". The convention is that a dash means *unknown*, and it was carrying at least four meanings — no documents held, documents not yet read, held and read and the fact is not there, and the field not applying. Only the third is a finding. 5,589 dashes became 153. Where the code cannot tell which silence applies it says "not established", which says nothing about why; the alternative — writing "none found" everywhere — asserts a null result on sites nobody read. |
| **Provenance on party fields** | (not addressed) | Every value names its register: "CSE52 Limited (documents)" | Luke, 2026-08-26. End user, applicant and advisers had read from Barbour alone, so 330 of 494 sites showed a dash and 179 of those had a document-stated applicant. "Barbour unless otherwise stated" is not defensible for a field Barbour fills a third of the time. `end_user` still comes from Barbour or a confirmed alias group only, per the 2.4 decision — it is an identity claim across documents, where the applicant is stated per application. |

## Still not built

- **Editorial rule 1's build-time guard.** "A cohort with no limits text
  must fail the build rather than render without it" — `dcp/site_cohorts.py`
  raises on a missing `limits`, `tone` or headline slot at import, which is
  the same guarantee one step earlier. Nothing checks the reader refuses to
  render a cohort whose text arrived empty by another route.
- **The signals' verification pill** distinguishes hand-checked from computed,
  but not "re-verified", which the handoff names as a third state.
