# Triage rubric (round 01)

Distilled from Luke's labelling of 30 applications in `round_01_sample.md`.

Two passes — a coarse universe filter (verdict) and a fine analytical call
(worth-deep-read + signals). Editorial defaults baked in:

- **Lean inclusive at every boundary.** Better to flag a false positive that a
  human rejects in seconds than to miss a real story.
- **Emergency backup generators are a deep-read trigger, not a finding.** Every
  DC has them. The journalism question is whether they're truly outage-only or
  used for grid services / supplemental supply — which only the documents
  resolve.
- **Operator-level priors matter** (Foxglove pattern, Nscale microgrids,
  renewable-energy partner names) but they're not visible from a single
  application's description. Capture them upstream as `discovered_via:operator:*`
  tags; don't expect Stage 1 triage to know them.

---

## Verdict — universe filter

| Value | When |
|---|---|
| `DC` | The application is a new data centre build (or substantial DC redevelopment) |
| `adjacent` | DC-related infrastructure that isn't itself a new DC: substation on a DC campus, cable to a DC, supporting kit |
| `unrelated` | The "data centre" keyword matched but the application isn't a DC and isn't generating-infrastructure: access roads to a DC, NMAs referencing past DC use, conditions discharges of an *underlying* DC permission (the parent will be captured separately) |
| `unknown` | Insufficient information to decide; or DC embedded in mixed-use where scale is unclear |

**Tie-breakers (lean inclusive):**

- If genuinely unsure between `adjacent` and `unrelated` → choose `adjacent`.
- If genuinely unsure between `DC` and `adjacent` → choose `DC`.
- Mixed-use developments where data centre is one named use among many residential/retail uses → `unknown` (likely small but worth capturing).
- NMAs and conditions discharges are usually `unrelated` only because the parent application carries the substantive content — we want that one captured, not the procedural follow-on.

---

## Worth deep-read — analytical call

The substantive question. Per Luke (2026-05-13): *prefer false positives to false negatives. Downstream manual review filters out the noise.*

| Value | When |
|---|---|
| `yes` | Description names power-related infrastructure (generators, substations, energy centre, gas, fuel storage, etc.) OR DC application by operator with known on-site-generation pattern OR substantial hyperscale DC where generation kit is expected even if not described |
| `maybe` | Description is sparse OR DC is embedded in mixed-use OR signals are ambiguous (substation alone with no other power language) |
| `no` | `unrelated` verdicts; routine ancillary works (access roads, internal extensions, NMAs); clear non-DC matches |

`yes` and `maybe` together = the deep-read worklist. Lean toward `maybe` rather than `no` when sparse.

---

## Signal tags

Power-related vocabulary observed in the description. Pick from the lexicon below; add new tags freely when present.

**Variant forms are synonymous.** Terms below are listed in one canonical form per entry, but downstream matching (in `scripts/worklist_preview.py` and any future ranker) treats common whitespace / hyphenation variants as equivalent. For example: `gas-fired` ≡ `gas fired`; `onsite generation` ≡ `on-site generation` ≡ `on site generation`; `behind the meter` ≡ `behind-the-meter`; `bridge-to-grid` ≡ `bridge to grid`. Don't proliferate near-duplicate entries; one canonical form per term is enough.

### Tier 1 — primary on-site generation (strong signal)

`energy centre` · `power station` · `power plant` · `power facility` · `prime power` · `gas turbine` · `gas-fired` · `gas reciprocating engine` · `reciprocating engine` · `CHP` · `combined heat and power` · `cogeneration` · `energy reserve` · `onsite generation` · `microgrid` · `behind the meter` · `bridge-to-grid` · `biomass` · `hydrogen` · `fuel cell` · `anaerobic digestion` · `energy from waste` · `district heating centre` · `district heating unit`

The two `district heating …` phrasings flag on-site combustion infrastructure producing heat for a network (case (a) — strong signal). Bare `district heating` is intentionally *not* a Tier-1 term because it conflates case (a) with connection to an existing external network (case (b) — neutral or positive, e.g. waste-heat reuse). The Tier-3 entry still catches bare mentions where (a) vs (b) can't be disambiguated from the description alone.

### Tier 2 — backup / standby (deep-read trigger, not finding)

`generator` · `generators` · `emergency generator` · `emergency back-up generator` · `backup` · `standby` · `generator yard` · `flue`

### Tier 3 — fuel signals

`diesel` · `gas` · `LPG` · `propane` · `fuel storage` · `fuel tanks` · `district heating`

### Tier 4 — storage

`BESS` · `battery energy storage` · `battery storage` · `energy storage`

### Tier 5 — connection / infrastructure (lower-priority, often noise)

`substation` · `electricity substation` · `electrical infrastructure` · `kiosk substation` · `MV building`

(`grid connection` was explicitly flagged as low-value by Luke — most large planning applications have one. Not in the lexicon.)

### Tier 6 — cooling (newly added per Luke 2026-05-13)

`water cooling` · `water pumping`

(Generic `cooling` and `air cooling` are not strong signals — air-cooled DCs are common and often the greener variant. Water cooling raises local environmental impact questions worth flagging.)

### Tier 7 — context / scale

`hyperscale` · `NSIP` · `data centre campus`

### Tier 8 — operator / supplier names (capture verbatim if present)

`Foxglove` (the Foxglove top-10 list as a label, not a description signal — internal use) · `Nscale` · `VoltaGrid` · `Scale Microgrids` · `Enchanted Rock` · `GridPoint` · `Uplight` · `SLB` · `Liberty Energy` · `Baker Hughes` · `Langley Holdings` · `MWM` · `AVK`

These would surface in source-portal documents and applicant fields more than in PlanIt descriptions. Mostly relevant when source docs get fetched in deep-read.

---

## Confidence

About the **generation-signal call** specifically (verdict + worth-deep-read + signals together).

| Value | When |
|---|---|
| `sure` | Strong description signals OR confirmed by external context (source docs, operator priors) |
| `probable` | Some signals present but ambiguity remains (e.g. substation could be grid-connection or could be primary gen) |
| `guessing` | Sparse description, weak signals, or insufficient context |

The downstream prompt-eval uses confidence as a calibration measure — disagreements between LLM and Luke on `guessing` cases are less worrying than disagreements on `sure` cases.

---

## Editorial principles baked in

1. **Ingest broadly, analyse second.** Decisions about *what's worth a story* happen downstream of structured facts.
2. **Defensibility.** Every aggregate claim must be drillable back to source material; the triage must preserve provenance.
3. **Don't decide the story upfront.** Be ready for null findings — "actually most are honest" is a legitimate outcome.
4. **Backup generators are not the story.** Every DC has them. Whether they're *truly* emergency-only is the story.
5. **Operator-level priors enrich but don't replace description signals.** Stage 1 triage works from description alone; operator priors are layered in upstream (`discovered_via`) and downstream (deep-read).

6. **Don't filter on polarity (removal / demolition / decommission).** Power-infrastructure signals are flagged regardless of whether the application is *installing* the kit, *removing* it, *modifying* it, or just *referring* to it. Reasoning: ~33% of worklist descriptions contain "removal" / "demolition" / "dismantling" / "decommission" language, but the overwhelming majority are the *constructive* pattern — *"demolition of existing buildings and construction of a data centre"*, *"removal of fill material and installation of an Energy Park"*, etc. Genuinely "remove-without-replacement" cases (e.g. Halton/22/00028/S73, a Tesco supermarket removing its CHP plant for net-zero compliance) are rare (single-digit cases out of ~800) and editorially interesting in their own right when they sit near a real DC site. Trying to encode polarity in either the LLM prompt or the worklist renderer risks over-correcting and dropping cases like *"removal of legacy gas turbine to install new hydrogen fuel cell array"* — which IS a story. Decision (Luke + Claude, 2026-05-15): keep the lean-inclusive stance; rely on the reader to scan the description (which the worklist card surfaces verbatim). The cost of a few false-positive Tesco refits is much smaller than the cost of missing one DC retrofit.

---

## Open questions Luke flagged for Aisha

These five cases were marked "verify with Aisha":

- **#12 Dromenagh Iver Heath** — source URL broken; hyperscale prior is strong but description is thin.
- **#14 Linmere / Houghton Regis (AWS-linked)** — explicit emergency generators in source docs alongside "no fossil fuels for day-to-day operation" claim. Boundary case for the deep-read worklist.
- **#22 Old Oak Park Royal conditions** — does discharging a landscaping condition on a DC count as "DC-related" for our purposes? Probably no, since the parent application carries the substantive content — but worth checking.
- **#23 Hillingdon DC redevelopment conditions discharge** — similar boundary case; description does reference plant and emergency generator.
- **#29 Central Beds 5,150-dwelling mixed-use mentioning DC zone** — embedded DC in master-plan, scale unclear, worth a check whether Aisha cares about these.

These become the agenda for the targeted follow-up with Aisha. The rubric defaults handle them as: #22, #23 = `unrelated` (parent app is the source of truth); #29 = `unknown` (embedded DC, unclear scale); #12, #14 = `DC` with `worth_deep_read=yes` (operator priors + thin description still merits a look).
