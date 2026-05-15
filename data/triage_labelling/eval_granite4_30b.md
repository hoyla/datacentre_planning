# Triage eval: granite4.1:30b

Last updated 2026-05-14T18:02:26. JSONL: `eval_granite4_30b.jsonl` (30 rows).


## Headline numbers

- **30** applications evaluated, 0 errors
- **Verdict accuracy: 28/29 = 97%**
- **Deep-read accuracy: 25/29 = 86%**
- **Signal Jaccard average: 0.46**
- Mean per-call latency: 9.2s (min 4.8s, max 37.1s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 18 | 0 | 1 | 0 | 19 |
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
- LLM why: The application is a procedural variation of conditions referencing an existing data centre permission, with only minor adjustment of the sub‑station location.
- GT signals: `Foxglove, plant, electricity sub-station, substation enclosure`
- LLM signals: `(none)`