# Triage eval: granite4.1:30b

Last updated 2026-08-03T09:30:51. JSONL: `eval_dc_build_granite4.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 35/50 = 70%**
- **Deep-read accuracy: 41/50 = 82%**
- **Signal Jaccard average: 0.62**
- Mean per-call latency: 27.1s (min 6.8s, max 369.5s)


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
- LLM why: The description explicitly calls for demolition of an existing hotel and erection of a new data centre building with specified floorspace, fitting the definition of constructing new data‑centre capacity.
- GT signals: `data centre`
- LLM signals: `(none)`

### #17. North Lanarkshire — DC + substation + battery

- Ref: `NorthLanarkshire/25/01322/PAN`
- GT verdict: **pre_application** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Proposal of Application Notice for DC with BESS and possible S36 route
- LLM why: The description explicitly calls for construction of data centre buildings together with a substation, BES and generation capacity, indicating substantive new infrastructure.
- GT signals: `battery energy storage, substation, Section 36`
- LLM signals: `substation, battery energy storage (BES), generation`

### #20. East Ayrshire — pre-application Scotland DC

- Ref: `EastAyrshire/25/0008/PREAPP`
- GT verdict: **pre_application** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Pre-application (ref PREAPP) for a data centre complex
- LLM why: Description explicitly calls for a data centre complex with data halls and a substation, indicating new construction of data‑centre capacity.
- GT signals: `substation`
- LLM signals: `substation`

### #22. Old Oak Park Royal — Phase 2 conditions

- Ref: `OldOakParkRoyal/26/0082/AODOPDC`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Landscaping condition details on a DC outline
- LLM why: The description outlines demolition followed by redevelopment into a new data centre (Use Class B8) of substantial size with associated plant, substation and extensive ancillary works.
- GT signals: ``
- LLM signals: `substation`

### #23. Hillingdon — conditions discharge for DC redevelopment

- Ref: `Hillingdon/49261/APP/2026/1013`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Drainage condition discharge on a DC permission
- LLM why: The description explicitly calls for construction of a new data centre building (Class B8) with associated plant, an emergency generator and a kiosk substation, indicating substantive new capacity.
- GT signals: `emergency generator`
- LLM signals: `emergency generator, substation, plant at roof level`

### #27. Bracknell — historic NMA referencing DC use

- Ref: `Bracknell/20/00818/NMA`
- GT verdict: **procedural** / LLM: **pre_application**
- GT deep-read: no / LLM: maybe
- GT confidence: probable / LLM: sure
- GT why: NMA re-wording the description to permit a data centre; admin only
- LLM why: The description outlines an outline planning permission that proposes redevelopment including a data centre, fitting the pre-application category.
- GT signals: ``
- LLM signals: `(none)`

### #28. Glasgow — university campus mixed-use mentioning 'energy centre'

- Ref: `Glasgow/24/02285/NMV01`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: maybe / LLM: maybe
- GT confidence: probable / LLM: sure
- GT why: Non-material variation on a mixed-use masterplan whose parent includes a 3,000sqm DC and energy centre
- LLM why: The description explicitly includes a dedicated Data Centre (Class 4) of up to 3,000 sq m and an energy centre, indicating new data‑centre capacity within a mixed‑use campus.
- GT signals: `energy centre`
- LLM signals: `Data Centre, energy centre`

### #29. Central Beds — discharge of conditions on a 5,150-dwelling mixed use mentioning DC zone

- Ref: `CentralBedfordshire/CB/26/01140/DOC`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: no / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Condition discharge on a mixed-use outline with embedded DC
- LLM why: The outline permission explicitly lists a 'data centre' among the proposed uses, meeting the new_build criteria despite being an outline with reserved matters.
- GT signals: ``
- LLM signals: `data centre, primary substation, energy centre`

### #34. StAlbans

- Ref: `StAlbans/5/2026/0719`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: maybe / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: RM under an outline parameter-plan variation; development type not identifiable from visible text
- LLM why: The description only concerns reserved‑matters and a minor condition variation without introducing any new substantive data‑centre works or power infrastructure.
- GT signals: ``
- LLM signals: `(none)`

### #35. StAlbans

- Ref: `StAlbans/5/2025/1841`
- GT verdict: **unknown** / LLM: **procedural**
- GT deep-read: no / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: Parameter-plan condition variation on an unidentified masterplan; no DC evidence visible
- LLM why: The description details only a minor variation of conditions affecting layout, height, and landscaping buffers for an existing data‑centre scheme; no new substantive works or power infrastructure are proposed.
- GT signals: ``
- LLM signals: `(none)`

### #36. Broxbourne

- Ref: `Broxbourne/07/20/0907/RM`
- GT verdict: **not_dc** / LLM: **enabling_works**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: sure
- GT why: Spine road and drainage RM; outline reference not identified as a DC in visible text
- LLM why: The description explicitly ties the reserved‑matters submission to Phase 1 infrastructure (spine road, drainage) for a data‑centre outline planning permission, which are enabling works rather than building or power elements.
- GT signals: ``
- LLM signals: `(none)`

### #37. Windsor

- Ref: `Windsor/26/00224/FULL`
- GT verdict: **unknown** / LLM: **enabling_works**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: sure
- GT why: Electrical/communication cable infrastructure with construction compounds; beneficiary not identified
- LLM why: The description explicitly mentions underground/ground‑mounted structures for electrical connections and communication cabling tied to a data centre site.
- GT signals: `electrical connection`
- LLM signals: `electrical connection, communication cables`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **expansion_refurb**
- GT deep-read: maybe / LLM: maybe
- GT confidence: probable / LLM: probable
- GT why: Disguise suspect: technical services centre with IT facilities, substation and plant enclosures — 2008 coded language
- LLM why: The description outlines redevelopment of an existing site into a technical services centre with IT facilities, indicating conversion/refurbishment of an existing building to data‑centre use.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation, external plant enclosures`

### #48. Bassetlaw

- Ref: `Bassetlaw/21/00867/RES`
- GT verdict: **not_dc** / LLM: **procedural**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: sure
- GT why: RM to erect generic commercial units; nothing identifies a data centre
- LLM why: The description only requests approval for appearance, landscaping, layout, and scale of commercial units without mentioning any data‑centre specific infrastructure or use.
- GT signals: ``
- LLM signals: `(none)`

### #49. EastRiding

- Ref: `EastRiding/16/02800/STPLF`
- GT verdict: **not_dc** / LLM: **adjacent_power**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: Standalone 21MW gas peaking facility; no data-centre association visible in the description or address
- LLM why: The description explicitly outlines construction of a gas‑fired energy reserve with generators and transformers for power provision to a data centre site.
- GT signals: `gas-fired, energy reserve, gas reciprocating engine generators`
- LLM signals: `gas-fired, energy reserve facility, 21MW, gas reciprocating engine generators, transformers`