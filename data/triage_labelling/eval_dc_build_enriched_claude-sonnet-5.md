# Triage eval: claude-sonnet-5

Last updated 2026-08-03T17:50:00. JSONL: `eval_dc_build_enriched_claude-sonnet-5.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 39/50 = 78%**
- **Deep-read accuracy: 33/50 = 66%**
- **Signal Jaccard average: 0.63**
- Mean per-call latency: 4.2s (min 2.8s, max 11.9s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 1 | 1 |

## Disagreements


### #19. Newport — cable connection from substation to DC

- Ref: `Newport/25/1071`
- GT verdict: **enabling_works** / LLM: **adjacent_power**
- GT deep-read: maybe / LLM: yes
- GT confidence: sure / LLM: probable
- GT why: Grid-connection cable from substation to a data centre — enabling infrastructure
- LLM why: Application's own substance is a grid power connection (132kV substation to data centre), so it's power-infrastructure kit rather than mere trenching enabling works.
- GT signals: `132kV substation, underground cable`
- LLM signals: `132kv substation, underground cable connection`

### #31. Cherwell

- Ref: `Cherwell/25/03310/REM`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Disguise suspect: RM bringing forward large B8 buildings with services emphasis, no DC naming
- LLM why: Reserved matters bring forward appearance/layout/scale of new buildings on the Graven Hill D1 site, which cross-referenced context confirms is a 435MW data centre campus despite the description's B8 'Storage or Distribution' wording — substantive new-build content, not a procedural amendment.
- GT signals: `services infrastructure`
- LLM signals: `services infrastructure`

### #33. MiltonKeynes

- Ref: `MiltonKeynes/21/02578/FUL`
- GT verdict: **not_dc** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: Two commercial buildings B2/B8 with ordinary access/parking language; no basis for suspicion in visible info
- LLM why: Description reads as plain B2/B8 commercial buildings with no power/cooling/scale signals, but cross-source data links this filing to 'Enigma Data Centre' - treating as disguise suspect rather than asserting new_build or not_dc from description alone.
- GT signals: ``
- LLM signals: `(none)`

### #34. StAlbans

- Ref: `StAlbans/5/2026/0719`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: probable
- GT why: RM under an outline parameter-plan variation; development type not identifiable from visible text
- LLM why: Reserved matters submission bringing forward appearance, landscaping, layout and scale for the data-centre buildings (linked via 5/2025/1841 to NTT LON2-A 56MW data centre) counts as new_build per the RM-brings-buildings rule, despite being framed partly as a condition variation.
- GT signals: ``
- LLM signals: `(none)`

### #35. StAlbans

- Ref: `StAlbans/5/2025/1841`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: no / LLM: maybe
- GT confidence: guessing / LLM: probable
- GT why: Parameter-plan condition variation on an unidentified masterplan; no DC evidence visible
- LLM why: Variation of Condition 3 (approved plans) adjusting parameter plan boundaries and building heights adds no new substantive content itself, though cross-source context ties it to the NTT LON2-A 56MW data centre scheme.
- GT signals: ``
- LLM signals: `(none)`

### #36. Broxbourne

- Ref: `Broxbourne/07/20/0907/RM`
- GT verdict: **not_dc** / LLM: **enabling_works**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: probable
- GT why: Spine road and drainage RM; outline reference not identified as a DC in visible text
- LLM why: Reserved matters cover spine road, drainage and landscaping (Phase 1 infrastructure) tied to an outline data-centre parent (linked to Google data centre project), not the buildings themselves.
- GT signals: ``
- LLM signals: `(none)`

### #37. Windsor

- Ref: `Windsor/26/00224/FULL`
- GT verdict: **unknown** / LLM: **enabling_works**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: probable
- GT why: Electrical/communication cable infrastructure with construction compounds; beneficiary not identified
- LLM why: Underground/ground-mounted structures for electrical connection and communication cables with construction compounds match grid-connection enabling works, though the description itself doesn't explicitly name a data-centre scheme (cross-source context 'grid connection cables' project ties it to related works, weighed toward enabling_works over unknown).
- GT signals: `electrical connection`
- LLM signals: `electrical connection, communication cables`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Disguise suspect: technical services centre with IT facilities, substation and plant enclosures — 2008 coded language
- LLM why: Full application for a new-build technical services centre with offices, IT facilities, substation and plant enclosures on a redevelopment site — substantive new data-centre construction, corroborated by cross-source link to 'LCY20 - DATA CENTRE'.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation, internal plant, external plant enclosures`

### #41. Stockport

- Ref: `Stockport/DC/090552`
- GT verdict: **not_dc** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: Prior approval for demolition of an industrial facility; no DC connection visible
- LLM why: Prior approval for demolition of an industrial building at an address with no stated data-centre connection; possibly enabling works for a DC scheme but description gives no such tie, so treated as unknown rather than not_dc given ambiguity.
- GT signals: ``
- LLM signals: `(none)`

### #48. Bassetlaw

- Ref: `Bassetlaw/21/00867/RES`
- GT verdict: **not_dc** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: guessing
- GT why: RM to erect generic commercial units; nothing identifies a data centre
- LLM why: Reserved matters for generic 'Commercial Units' with no data-centre wording in the description itself; only cross-source linkage to a 'Data Centre & Office' project suggests possible DC content, so classified unknown rather than new_build/not_dc per description-only rule.
- GT signals: ``
- LLM signals: `(none)`

### #49. EastRiding

- Ref: `EastRiding/16/02800/STPLF`
- GT verdict: **not_dc** / LLM: **adjacent_power**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Standalone 21MW gas peaking facility; no data-centre association visible in the description or address
- LLM why: Description explicitly proposes a gas-fired energy reserve facility with generators and transformers, matching adjacent_power criteria directly.
- GT signals: `gas-fired, energy reserve, gas reciprocating engine generators`
- LLM signals: `gas-fired energy reserve facility, gas reciprocating engine generators, transformers`