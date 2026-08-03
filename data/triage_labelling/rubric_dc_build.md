# dc_build rubric (v2) — project-class taxonomy

Second-generation triage rubric, replacing the v1 binary
(DC / adjacent / unrelated / unknown) with a project-class taxonomy for the
"datacentre build" phase of the investigation. The operative prompt is
`DC_BUILD_SYSTEM_PROMPT` in [dcp/triage.py](../../dcp/triage.py); this
document records the editorial decisions behind it.

## Why a taxonomy, not a binary

Scope decisions locked by Luke, 2026-08-03 (travelling; via Claude Code):

| # | Question | Decision |
|---|---|---|
| a | Refurbs / fit-outs of existing DCs? | **In the corpus** — they can add capacity — but classed distinctly (`expansion_refurb`), never conflated with new builds. |
| b | Enabling works (demolition, roads, grid connections)? | **In**, as a related class (`enabling_works`). |
| c | Adjacent power applications? | **Their own class** (`adjacent_power`), separate from enabling works. |
| d | Pre-application instruments (EIA scoping, Scottish PACs, LDO/SPZ)? | **In scope**, classed distinctly (`pre_application`) so downstream analysis can include or exclude them at will. |
| e | How broad is "build"? | **Broad**: any datacentre-related project is tracked, so schemes can be followed as they evolve — driven by the discovery that major DCs are filed as B8 warehousing with no DC language at all. |

Everything is categorisation, never discard (principle 1 — ingest broadly).
Procedurals, which v1 classed `unrelated`, get their own class so application
families remain trackable over time.

## The classes

| verdict | Meaning | Canonical examples (real) |
|---|---|---|
| `new_build` | New DC capacity: buildings, halls, campuses; outline/full/hybrid; substantive reserved matters that bring forward the buildings | Cambois Phase 1 REM; NTT LON2-A REM |
| `expansion_refurb` | Works to an existing DC: extensions, fit-outs, refurb, plant replacement, change of use *to* DC | Manchester Simon House change of use |
| `enabling_works` | Preparatory/supporting works tied to a DC scheme: demolition, access/spine roads, drainage, grid-connection cabling | Waltham Cross spine-road RM; Windsor grid cables |
| `adjacent_power` | Power generation/storage/fuel serving or co-located with a DC site | YEP 21MW gas reserve; BESS applications |
| `pre_application` | Pre-application & non-standard instruments signalling a DC scheme | WestLothian 250MW PAC; Havering scoping request |
| `procedural` | Variations, NMAs, condition discharges, non-substantive RMs on a DC parent | LCY20 conditions variation |
| `not_dc` | Unrelated | — |
| `unknown` | Insufficient info, **or a disguise suspect** | Graven Hill D1 REM (B8-worded 435MW campus) |

## The disguise-suspect rule

Some datacentres never say the words — Graven Hill's outline and reserved
matters describe only "B8 Storage or Distribution" across 104,008 sq m.
Large single-use B8/industrial schemes with DC-typical features (substation
provision, unusual cooling/plant, power-demand language, "services
infrastructure" emphasis) but no named DC use classify `unknown`, with the
features recorded in `signals` and the suspicion stated in `why`. The model
must never assert DC use the description doesn't support; a plain logistics
shed is `not_dc`. Cross-source lists (Barbour ABI) remain the recall
mechanism for what descriptions structurally cannot reveal.

## Ground-truth policy (revised 2026-08-03, adjudication session)

Labels record the **truth**, established from all evidence held — Barbour
links, family relationships, documents — with an
`invisible_from_description` flag on rows whose truth the prompt-visible
text cannot support (10 of 50 in the trial set). Models are scored twice:
against reality, and against the visible-information subset. The gap
between the two scores *is* the description ceiling, quantified — reported
as a finding rather than baked invisibly into the labels. (This reverses
the draft's description-only policy, on Luke's ruling that adjudicating
truth with full evidence is both easier and more honest.)

## Output schema

Unchanged from v1 apart from the verdict values: `verdict`,
`worth_deep_read` (yes/no/maybe), `signals[]`, `why`, `confidence`
(sure/probable/guessing). Verdicts land in the same append-only `triage`
table under the evaluating model's name; v1 and dc_build verdicts coexist
per application.

## Adjudication outcomes (Luke, 2026-08-03)

Sixteen contested rows adjudicated conversationally; five durable rules
emerged, to be folded into the prompt as v2.1:

1. **Instrument-first.** Classify the instrument, not the scheme it
   describes. Reference/type suffixes often name it directly (PREAPP, PAN,
   SCO/SCR, PPP, NMA, DOC/DRC, VCDN). Observed failure mode (granite,
   three times): right about the scheme, wrong about the instrument.
2. **Three-axes procedural definition.** `procedural` ⟺ the filing leaves
   the scheme's datacentre substance unchanged on all three axes —
   *whether* it is one, *how big*, and *how powered*. Touch any axis and
   it classifies by the resulting scheme, deep-read yes. Anchors: #9
   (quantum 27,637→33,870 sqm, verified from the parent decision notice),
   #27 (NMA introducing DC use), #35 (ridge height raised 18→20 m for a
   2-storey DC with roof plant — planning statement §4.9–4.10, in corpus).
3. **Association by evidence.** `adjacent_power` / `enabling_works`
   require a real DC association established by *any held evidence*
   (family, spatial, Barbour) — not by the description. Canonical case:
   the YEP 21 MW gas reserve (#49), the v1 smoking gun, whose description
   names no datacentre at all.
4. **Honesty rule.** The why-field must not assert facts absent from the
   input (e.g. the *direction* of a quantum variation). Route to deep-read
   rather than infer; verified in #9 where an inferred "increases" happened
   to be true but was only established by fetching the decision notice.
5. **Inclusion principle** (Luke, verbatim): "easy for the data
   journalists to remove something they can see; more difficult to add
   something they can't."

**Trial scores against adjudicated truth** (50 cases; visible-40 excludes
the 10 flagged rows):

| model | context | all 50 | visible-40 | invisible-10 |
|---|---|---|---|---|
| granite4.1:30b | description | 35 | 32 | 3 |
| granite4.1:30b | enriched | 39 | 35 | 4 |
| claude-sonnet-5 | description | 42 | 38 | 4 |
| claude-sonnet-5 | enriched | 42 | 36 | 6 |

Architecture locked on these numbers plus budget: **Sonnet 5 catalogues
the universe's metadata** (one-off, ~$15–20); **local granite + Claude
Code escalation deep-reads documents**, behind the model-agnostic
verbatim-quote gate; **100% of candidate DC sites get deep-read** —
triage is a cataloguer, not a gatekeeper. Even the best configuration
managed only 6/10 on the invisible rows: metadata enrichment raises the
floor, only documents remove the ceiling.

## Running an evaluation

```bash
scripts/eval_triage.py --rubric dc_build --model claude-sonnet-5 --labels <labels.json>
scripts/eval_triage.py --rubric dc_build --model granite4.1:30b   --labels <labels.json>
```

Claude models route via `ClaudeBackend` (Anthropic API, personal account —
same routing caveat as the v1 Read-tool extraction); anything else via
Ollama. First live smoke (2026-08-03, claude-sonnet-5): Graven Hill REM →
`unknown` (disguise suspect, correctly reasoned), YEP STPLF →
`adjacent_power`/sure, WestLothian PAC → `pre_application`/sure, at 2.6–4.6s
per call. granite4.1:30b's v1-rubric verdicts on the same descriptions were
`unrelated`/sure on Graven Hill — the taxonomy plus disguise rule is doing
real work.
