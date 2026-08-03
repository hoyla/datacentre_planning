# Triage eval: claude-sonnet-5

Last updated 2026-08-03T09:13:49. JSONL: `eval_dc_build_claude-sonnet-5_2026-08-03_0908.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 42/50 = 84%**
- **Deep-read accuracy: 35/50 = 70%**
- **Signal Jaccard average: 0.62**
- Mean per-call latency: 6.7s (min 3.5s, max 12.4s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 3 | 3 |

## Disagreements


### #9. G-Park Docklands probable — Foxglove #8

- Ref: `TowerHamlets/PA/22/01140/A1`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Minor material amendment varying floorspace quantum on an existing DC permission; no new power kit
- LLM why: Minor material amendment increases the permitted data-centre floorspace quantum (33,870 sqm GIA) for a demolition-and-erection scheme, a substantive change tied to the DC building itself rather than mere admin re-wording.
- GT signals: `data centre`
- LLM signals: `(none)`

### #34. StAlbans

- Ref: `StAlbans/5/2026/0719`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: guessing
- GT why: RM under an outline parameter-plan variation; development type not identifiable from visible text
- LLM why: Reserved matters submission bringing forward appearance/landscaping/layout/scale (substantive building details) under an outline permission, though no data-centre reference or power kit is stated in this description itself.
- GT signals: ``
- LLM signals: `(none)`

### #35. StAlbans

- Ref: `StAlbans/5/2025/1841`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: no / LLM: maybe
- GT confidence: guessing / LLM: probable
- GT why: Parameter-plan condition variation on an unidentified masterplan; no DC evidence visible
- LLM why: Variation of condition adjusting parameter plan boundaries/heights on an existing permission adds no new substantive kit, just amended parameters; parent scheme substance not disclosed here.
- GT signals: ``
- LLM signals: `(none)`

### #36. Broxbourne

- Ref: `Broxbourne/07/20/0907/RM`
- GT verdict: **not_dc** / LLM: **enabling_works**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: probable
- GT why: Spine road and drainage RM; outline reference not identified as a DC in visible text
- LLM why: Reserved matters for Phase 1 infrastructure — spine road and drainage — tied to an outline parent scheme, matching the enabling-works example pattern.
- GT signals: ``
- LLM signals: `(none)`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Disguise suspect: technical services centre with IT facilities, substation and plant enclosures — 2008 coded language
- LLM why: Full application for a new detached 'technical services centre' with I.T. facilities and a detached substation constitutes new-build data-centre-type development.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation, external plant enclosures, internal plant`

### #41. Stockport

- Ref: `Stockport/DC/090552`
- GT verdict: **not_dc** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: Prior approval for demolition of an industrial facility; no DC connection visible
- LLM why: Demolition prior approval for an industrial building with no stated data-centre connection, so cannot confirm enabling_works vs not_dc from description alone.
- GT signals: ``
- LLM signals: `(none)`

### #48. Bassetlaw

- Ref: `Bassetlaw/21/00867/RES`
- GT verdict: **not_dc** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: RM to erect generic commercial units; nothing identifies a data centre
- LLM why: Reserved matters for generic 'commercial units' with no data-centre naming or scale/power details to confirm or rule out a DC link, so classified as unknown rather than not_dc per the ambiguity guidance.
- GT signals: ``
- LLM signals: `(none)`

### #49. EastRiding

- Ref: `EastRiding/16/02800/STPLF`
- GT verdict: **not_dc** / LLM: **adjacent_power**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Standalone 21MW gas peaking facility; no data-centre association visible in the description or address
- LLM why: Describes construction of a 21MW gas-fired generation facility with reciprocating engines and transformers, matching adjacent_power criteria directly.
- GT signals: `gas-fired, energy reserve, gas reciprocating engine generators`
- LLM signals: `gas-fired energy reserve facility, gas reciprocating engine generators, transformers`