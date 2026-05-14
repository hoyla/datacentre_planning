# Triage eval: mistral-small3.2:24b

Last updated 2026-05-14T13:47:41. JSONL: `eval_mistral_small_3_2_24b.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 26/29 = 90%**
- **Deep-read accuracy: 22/29 = 76%**
- **Signal Jaccard average: 0.36**
- Mean per-call latency: 6.3s (min 3.5s, max 27.9s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 16 | 0 | 2 | 1 | 19 |
| **adjacent** | 0 | 2 | 0 | 0 | 2 |
| **unrelated** | 0 | 0 | 7 | 0 | 7 |
| **unknown** | 0 | 0 | 0 | 1 | 1 |

## Disagreements


### #6. Saunderton (Virtus) — Foxglove #6

- Ref: `Wycombe/22/06872/VCDN`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: probable / LLM: sure
- GT why: presence of substation and 'plant' doesn't guarantee on-site generation but worth reading in depth because Foxglove tend to use on-site generation
- LLM why: Variation of Conditions application referencing a parent data centre permission
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `(none)`

### #23. Hillingdon — conditions discharge for DC redevelopment

- Ref: `Hillingdon/49261/APP/2026/1013`
- GT verdict: **DC** / LLM: **unrelated**
- GT deep-read: yes / LLM: no
- GT confidence: guessing / LLM: sure
- GT why: This looks to be supporting documentation to the main plan, but does refer to plant and generation so might be worth reading
- LLM why: Procedural follow-on application for drainage conditions discharge
- GT signals: `plant, emergency generator`
- LLM signals: `(none)`

### #28. Glasgow — university campus mixed-use mentioning 'energy centre'

- Ref: `Glasgow/24/02285/NMV01`
- GT verdict: **DC** / LLM: **unknown**
- GT deep-read: yes / LLM: maybe
- GT confidence: guessing / LLM: guessing
- GT why: It's very unlikely to be large scale on a university campus but the terms used merit inclusion for further examination
- LLM why: Mixed-use campus with embedded data centre and energy centre of unclear scale
- GT signals: `data centre, energy centre`
- LLM signals: `Data Centre, energy centre`