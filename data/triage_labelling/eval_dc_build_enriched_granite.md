# Triage eval: granite4.1:30b

Last updated 2026-08-03T19:20:49. JSONL: `eval_dc_build_enriched_granite.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 37/50 = 74%**
- **Deep-read accuracy: 36/50 = 72%**
- **Signal Jaccard average: 0.51**
- Mean per-call latency: 113.2s (min 13.7s, max 590.6s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 2 | 2 |

## Disagreements


### #9. G-Park Docklands probable — Foxglove #8

- Ref: `TowerHamlets/PA/22/01140/A1`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: maybe / LLM: maybe
- GT confidence: probable / LLM: sure
- GT why: Minor material amendment varying floorspace quantum on an existing DC permission; no new power kit
- LLM why: The description outlines demolition of an existing hotel and erection of a new data centre (Use Class B8) with a specific floorspace limit, indicating construction of new data‑centre capacity.
- GT signals: `data centre`
- LLM signals: `(none)`

### #17. North Lanarkshire — DC + substation + battery

- Ref: `NorthLanarkshire/25/01322/PAN`
- GT verdict: **pre_application** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Proposal of Application Notice for DC with BESS and possible S36 route
- LLM why: Description explicitly calls for construction of data centre building(s) along with a substation, battery energy storage and generation capacity.
- GT signals: `battery energy storage, substation, Section 36`
- LLM signals: `substation, battery energy storage, generation`

### #20. East Ayrshire — pre-application Scotland DC

- Ref: `EastAyrshire/25/0008/PREAPP`
- GT verdict: **pre_application** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Pre-application (ref PREAPP) for a data centre complex
- LLM why: Description explicitly seeks consent for a data centre complex with data halls and a substation, indicating new construction of capacity.
- GT signals: `substation`
- LLM signals: `substation`

### #23. Hillingdon — conditions discharge for DC redevelopment

- Ref: `Hillingdon/49261/APP/2026/1013`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Drainage condition discharge on a DC permission
- LLM why: The description explicitly calls for construction of a new data centre building (Class B8) with plant, an emergency generator, and electrical infrastructure such as a kiosk substation and MV Building.
- GT signals: `emergency generator`
- LLM signals: `emergency generator, kiosk substation, MV Building`

### #27. Bracknell — historic NMA referencing DC use

- Ref: `Bracknell/20/00818/NMA`
- GT verdict: **procedural** / LLM: **unknown**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: probable
- GT why: NMA re-wording the description to permit a data centre; admin only
- LLM why: The description lists a data centre as one possible use among several industrial classifications without indicating it is the substantive component, creating ambiguity about whether a data centre will actually be built.
- GT signals: ``
- LLM signals: `(none)`

### #33. MiltonKeynes

- Ref: `MiltonKeynes/21/02578/FUL`
- GT verdict: **not_dc** / LLM: **new_build**
- GT deep-read: no / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: Two commercial buildings B2/B8 with ordinary access/parking language; no basis for suspicion in visible info
- LLM why: External cross‑source linkage identifies the scheme as "ENIGMA DATA CENTRE", indicating a data‑centre development despite generic building classification in the description.
- GT signals: ``
- LLM signals: `(none)`

### #34. StAlbans

- Ref: `StAlbans/5/2026/0719`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: sure
- GT why: RM under an outline parameter-plan variation; development type not identifiable from visible text
- LLM why: The description details only a reserved‑matters variation (appearance, landscaping, layout, minor plan amendment) without introducing new substantive data‑centre elements; the parent outline permission is known to be for an NTT 56 MW data centre.
- GT signals: ``
- LLM signals: `(none)`

### #35. StAlbans

- Ref: `StAlbans/5/2025/1841`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: no / LLM: maybe
- GT confidence: guessing / LLM: sure
- GT why: Parameter-plan condition variation on an unidentified masterplan; no DC evidence visible
- LLM why: The description only seeks a minor variation of an approved condition; the substantive data‑centre scheme (NTT LON2-A, 56 MW) is referenced in external context rather than introduced anew.
- GT signals: ``
- LLM signals: `data centre, 56MW`

### #36. Broxbourne

- Ref: `Broxbourne/07/20/0907/RM`
- GT verdict: **not_dc** / LLM: **enabling_works**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: sure
- GT why: Spine road and drainage RM; outline reference not identified as a DC in visible text
- LLM why: The description details road and drainage works tied to a known data‑centre project, meeting the definition of enabling works for a data centre scheme.
- GT signals: ``
- LLM signals: `(none)`

### #37. Windsor

- Ref: `Windsor/26/00224/FULL`
- GT verdict: **unknown** / LLM: **enabling_works**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: sure
- GT why: Electrical/communication cable infrastructure with construction compounds; beneficiary not identified
- LLM why: The description details installation of underground and ground‑mounted structures for electrical and communication cabling, which are supporting works tied to a data‑centre scheme via the external “MANOR FARM – GRID CONNECTION CABLES” link.
- GT signals: `electrical connection`
- LLM signals: `electrical connection, communication cables`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Disguise suspect: technical services centre with IT facilities, substation and plant enclosures — 2008 coded language
- LLM why: Description explicitly proposes construction of a detached building for technical services centre, offices, IT facilities and includes dedicated power infrastructure (substation and plant enclosures), indicating new data‑centre capacity.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `detached substation, external plant enclosures`

### #48. Bassetlaw

- Ref: `Bassetlaw/21/00867/RES`
- GT verdict: **not_dc** / LLM: **new_build**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: probable
- GT why: RM to erect generic commercial units; nothing identifies a data centre
- LLM why: The description is a reserved‑matters (appearance, landscaping, layout and scale) submission that will bring forward the erection of commercial units; cross‑source data ties it to an “Innovative Data Centre & Office” development, so the substantive component is a new data centre.
- GT signals: ``
- LLM signals: `(none)`

### #49. EastRiding

- Ref: `EastRiding/16/02800/STPLF`
- GT verdict: **not_dc** / LLM: **adjacent_power**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Standalone 21MW gas peaking facility; no data-centre association visible in the description or address
- LLM why: The description explicitly outlines the erection of a gas‑fired energy reserve with multiple generators and transformers, indicating power infrastructure for a data‑centre site.
- GT signals: `gas-fired, energy reserve, gas reciprocating engine generators`
- LLM signals: `gas-fired, energy reserve facility, 21MW capacity, 14 gas reciprocating engine generators, transformers`