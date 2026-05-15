# Triage eval: gemma4:e4b

Last updated 2026-05-14T13:44:32. JSONL: `eval_gemma4_e4b_full.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 27/29 = 93%**
- **Deep-read accuracy: 24/29 = 83%**
- **Signal Jaccard average: 0.32**
- Mean per-call latency: 11.3s (min 5.7s, max 17.5s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 17 | 0 | 1 | 1 | 19 |
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
- LLM why: The application is a procedural variation of conditions for relocating an existing substation enclosure.
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `substation, Variation of Conditions`

### #28. Glasgow — university campus mixed-use mentioning 'energy centre'

- Ref: `Glasgow/24/02285/NMV01`
- GT verdict: **DC** / LLM: **unknown**
- GT deep-read: yes / LLM: yes
- GT confidence: guessing / LLM: sure
- GT why: It's very unlikely to be large scale on a university campus but the terms used merit inclusion for further examination
- LLM why: The scope explicitly includes both a Data Centre and an energy centre within a massive mixed-use campus variation.
- GT signals: `data centre, energy centre`
- LLM signals: `Data Centre, energy centre`