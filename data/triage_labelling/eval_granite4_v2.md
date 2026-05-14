# Triage eval: granite4.1:8b

Last updated 2026-05-14T13:34:43. JSONL: `eval_granite4_v2.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 24/29 = 83%**
- **Deep-read accuracy: 22/29 = 76%**
- **Signal Jaccard average: 0.26**
- Mean per-call latency: 4.3s (min 1.4s, max 17.7s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 18 | 1 | 0 | 0 | 19 |
| **adjacent** | 0 | 2 | 0 | 0 | 2 |
| **unrelated** | 0 | 3 | 4 | 0 | 7 |
| **unknown** | 0 | 1 | 0 | 0 | 1 |

## Disagreements


### #6. Saunderton (Virtus) — Foxglove #6

- Ref: `Wycombe/22/06872/VCDN`
- GT verdict: **DC** / LLM: **adjacent**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: sure
- GT why: presence of substation and 'plant' doesn't guarantee on-site generation but worth reading in depth because Foxglove tend to use on-site generation
- LLM why: The variation describes moving the substation enclosure, indicating new power infrastructure associated with an existing data centre.
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `sub-station, relocation of substation enclosure`

### #22. Old Oak Park Royal — Phase 2 conditions

- Ref: `OldOakParkRoyal/26/0082/AODOPDC`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: yes
- GT confidence: guessing / LLM: sure
- GT why: Appears not to be an application for the data centre itself (which, hopefully, is identified elsewhere) so this is unlikely to carry technical details of power requirements
- LLM why: The description refers to a substation as part of the data centre development, indicating associated power infrastructure.
- GT signals: ``
- LLM signals: `data centre, substation`

### #26. Brent — temporary accessway for DC extension

- Ref: `Brent/26/0665`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Planning for access to data centre rather than for the data centre itself - but we might want to check that we know about the data centre extension plan itself
- LLM why: The description specifies an access road specifically for implementing works related to a proposed data‑centre extension, indicating supporting infrastructure for the DC.
- GT signals: `____`
- LLM signals: `access road, data centre`

### #27. Bracknell — historic NMA referencing DC use

- Ref: `Bracknell/20/00818/NMA`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Non-material amendments would not cover the introduction of power generation facilities or substations
- LLM why: The description explicitly mentions the construction of a data centre within an industrial redevelopment, indicating associated power infrastructure.
- GT signals: ``
- LLM signals: `data centre, infrastructure`

### #29. Central Beds — discharge of conditions on a 5,150-dwelling mixed use mentioning DC zone

- Ref: `CentralBedfordshire/CB/26/01140/DOC`
- GT verdict: **unknown** / LLM: **adjacent**
- GT deep-read: maybe / LLM: yes
- GT confidence: guessing / LLM: sure
- GT why: Probably a small scale data centre for local use, but the terms used merit inclusion for further examination or at least checking what CB/12/03613/OUT and CB/25/02087/PAPC are
- LLM why: The description mentions an energy centre and primary substation serving a data centre, indicating adjacent power‑infrastructure.
- GT signals: `data centre, energy centre`
- LLM signals: `data centre, primary substation, energy centre`