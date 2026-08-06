# Triage eval: claude-sonnet-5

Last updated 2026-08-06T15:36:27. JSONL: `eval_dc_build_claude-sonnet-5_2026-08-06_1458.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 45/50 = 90%**
- **Deep-read accuracy: 38/50 = 76%**
- **Signal Jaccard average: 0.47**
- Mean per-call latency: 45.3s (min 3.4s, max 1051.1s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 0 | 0 |

## Disagreements


### #33. MiltonKeynes

- Ref: `MiltonKeynes/21/02578/FUL`
- GT verdict: **new_build** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: Project MK Datavault (Enigma DC, built) — filed as plain B2/B8 commercial buildings
- LLM why: Description is plain B2/B8 commercial construction with no data-centre or power language, but the cross-source link to 'PROJECT MK DATAVAULT - ENIGMA DATA CENTRE' suggests this may be a disguised data-centre building filed under generic use classes; insufficient description detail to confirm scale or systems.
- GT signals: ``
- LLM signals: `(none)`

### #39. ChilternSouthBucks

- Ref: `ChilternSouthBucks/PL/22/0864/VRC`
- GT verdict: **procedural** / LLM: **expansion_refurb**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Conditions variation quoting a parent of technical-services-centre/IT-facilities character; no new kit
- LLM why: Variation includes condition 4 'Additional floor space' on an existing data-centre building (technical services centre with substation per CH/2008/0629/FA, confirmed as data centre by cross-source link) — touching the how-big axis takes this out of procedural, so classified by the existing-building scheme as expansion_refurb.
- GT signals: `substation, plant`
- LLM signals: `substation`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: 2008 coded language (technical services centre, I.T facilities, substation) but zero documents anywhere; identification of LCY20 unverified — FOI/Barbour-notes candidate
- LLM why: Full application for redevelopment to provide a new technical services centre/data centre building with substation and plant, cross-linked to 'LCY20 - DATA CENTRE' project, making the data centre a substantive new-build component.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation`

### #41. Stockport

- Ref: `Stockport/DC/090552`
- GT verdict: **enabling_works** / LLM: **unknown**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: guessing
- GT why: Demolition preceding DC build per Barbour (Under Construction); description silent
- LLM why: Prior approval for demolition of an industrial building with no data-centre reference in description or context beyond a matching demolition project title; insufficient basis to link to a DC scheme, so unknown rather than not_dc per inclusive calibration.
- GT signals: ``
- LLM signals: `(none)`

### #48. Bassetlaw

- Ref: `Bassetlaw/21/00867/RES`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: RM under DC-bearing outline 15/01477/OUT; 'commercial units' may or may not include the DC — 23 docs held to resolve
- LLM why: Reserved matters bringing forward appearance/layout/scale for commercial units, and the additional context links this outline chain to an 'INNOVATIVE DATA CENTRE & OFFICE' project, so this RES submission itself brings forward the building substance rather than merely procedural detail.
- GT signals: ``
- LLM signals: `(none)`