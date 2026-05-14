# Triage eval: granite4.1:8b

Last updated 2026-05-14T13:25:19. JSONL: `eval_granite4.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 24/29 = 83%**
- **Deep-read accuracy: 21/29 = 72%**
- **Signal Jaccard average: 0.24**
- Mean per-call latency: 3.4s (min 1.4s, max 20.2s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 18 | 0 | 1 | 0 | 19 |
| **adjacent** | 0 | 2 | 0 | 0 | 2 |
| **unrelated** | 0 | 3 | 4 | 0 | 7 |
| **unknown** | 0 | 0 | 1 | 0 | 1 |

## Disagreements


### #6. Saunderton (Virtus) — Foxglove #6

- Ref: `Wycombe/22/06872/VCDN`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: probable / LLM: sure
- GT why: presence of substation and 'plant' doesn't guarantee on-site generation but worth reading in depth because Foxglove tend to use on-site generation
- LLM why: The description is a procedural variation of conditions referencing an existing data centre permission (08/05740/FULEA); it does not introduce new substantive power infrastructure.
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `(none)`

### #25. Havering — rear extension to existing DC

- Ref: `Havering/P1169.25`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: maybe
- GT confidence: sure / LLM: probable
- GT why: Planning for access to data centre rather than for the data centre itself
- LLM why: The description specifies an extension to an existing data centre, indicating ancillary infrastructure rather than a new central build.
- GT signals: ``
- LLM signals: `data centre`

### #26. Brent — temporary accessway for DC extension

- Ref: `Brent/26/0665`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: yes
- GT confidence: sure / LLM: sure
- GT why: Planning for access to data centre rather than for the data centre itself - but we might want to check that we know about the data centre extension plan itself
- LLM why: The description specifies an access road for a proposed extension of an existing data centre, indicating related infrastructure.
- GT signals: `____`
- LLM signals: `access road, data centre`

### #27. Bracknell — historic NMA referencing DC use

- Ref: `Bracknell/20/00818/NMA`
- GT verdict: **unrelated** / LLM: **adjacent**
- GT deep-read: no / LLM: maybe
- GT confidence: sure / LLM: probable
- GT why: Non-material amendments would not cover the introduction of power generation facilities or substations
- LLM why: The amendment explicitly adds 'a data centre or data centres' to the permitted uses of an outline planning permission.
- GT signals: ``
- LLM signals: `data centre or data centres`

### #29. Central Beds — discharge of conditions on a 5,150-dwelling mixed use mentioning DC zone

- Ref: `CentralBedfordshire/CB/26/01140/DOC`
- GT verdict: **unknown** / LLM: **unrelated**
- GT deep-read: maybe / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: Probably a small scale data centre for local use, but the terms used merit inclusion for further examination or at least checking what CB/12/03613/OUT and CB/25/02087/PAPC are
- LLM why: The description is a discharge of condition related to an outline planning permission for mixed-use development, including a data centre among many other uses; it does not introduce new substantive power infrastructure.
- GT signals: `data centre, energy centre`
- LLM signals: `(none)`