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

## Ground-truth policy

Labels are **description-only**: the ground truth for each application is
what its description supports, not what we know from Barbour, family links,
or documents. This measures the classifier fairly and measures the *ceiling*
of description-based triage — the B8-disguise cases are expected to land
`unknown`, not `new_build`, and that is scored as correct.

## Output schema

Unchanged from v1 apart from the verdict values: `verdict`,
`worth_deep_read` (yes/no/maybe), `signals[]`, `why`, `confidence`
(sure/probable/guessing). Verdicts land in the same append-only `triage`
table under the evaluating model's name; v1 and dc_build verdicts coexist
per application.

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
