# Triage eval: qwen3.6:latest

Last updated 2026-05-14T14:25:25. JSONL: `eval_qwen3_6.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 25/29 = 86%**
- **Deep-read accuracy: 22/29 = 76%**
- **Signal Jaccard average: 0.45**
- Mean per-call latency: 60.3s (min 27.8s, max 101.2s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 16 | 0 | 3 | 0 | 19 |
| **adjacent** | 0 | 2 | 0 | 0 | 2 |
| **unrelated** | 0 | 0 | 7 | 0 | 7 |
| **unknown** | 0 | 0 | 1 | 0 | 1 |

## Disagreements


### #6. Saunderton (Virtus) — Foxglove #6

- Ref: `Wycombe/22/06872/VCDN`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: probable / LLM: sure
- GT why: presence of substation and 'plant' doesn't guarantee on-site generation but worth reading in depth because Foxglove tend to use on-site generation
- LLM why: Procedural follow-on application (Variation of Conditions) referencing an existing parent DC permission, not introducing new power infrastructure.
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `electricity sub-station`

### #23. Hillingdon — conditions discharge for DC redevelopment

- Ref: `Hillingdon/49261/APP/2026/1013`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: This looks to be supporting documentation to the main plan, but does refer to plant and generation so might be worth reading
- LLM why: Procedural discharge of drainage condition for a previously permitted data centre; description is administrative follow-on with no new power infrastructure proposed.
- GT signals: `plant, emergency generator`
- LLM signals: `emergency generator, kiosk substation`

### #28. Glasgow — university campus mixed-use mentioning 'energy centre'

- Ref: `Glasgow/24/02285/NMV01`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: It's very unlikely to be large scale on a university campus but the terms used merit inclusion for further examination
- LLM why: The application is a procedural non-material variation to a mixed-use university campus; it adds no new substantive power infrastructure.
- GT signals: `data centre, energy centre`
- LLM signals: `Data Centre, energy centre`

### #29. Central Beds — discharge of conditions on a 5,150-dwelling mixed use mentioning DC zone

- Ref: `CentralBedfordshire/CB/26/01140/DOC`
- GT verdict: **unknown** / LLM: **unrelated**
- GT deep-read: maybe / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: Probably a small scale data centre for local use, but the terms used merit inclusion for further examination or at least checking what CB/12/03613/OUT and CB/25/02087/PAPC are
- LLM why: Procedural discharge of condition to an outline master-plan permission, not a substantive DC or power application.
- GT signals: `data centre, energy centre`
- LLM signals: `primary substation, energy centre`