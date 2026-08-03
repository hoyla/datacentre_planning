# Triage eval: claude-sonnet-5

Last updated 2026-08-03T20:50:36. JSONL: `eval_dc_build_claude-sonnet-5_2026-08-03_2047.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 47/50 = 94%**
- **Deep-read accuracy: 41/50 = 82%**
- **Signal Jaccard average: 0.68**
- Mean per-call latency: 4.1s (min 2.3s, max 14.8s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 1 | 1 |

## Disagreements


### #30. East Riding — non-material amendment to Yorkshire Energy Park outline

- Ref: `EastRiding/24/40093/NONMAT`
- GT verdict: **procedural** / LLM: **new_build**
- GT deep-read: maybe / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: NMA clarifying energy infrastructure wording on the YEP outline
- LLM why: NMA explicitly touches the power axis ('clarification of the approved energy infrastructure') and removes the '600 racks' capacity figure from the data-centre description, so it is not purely administrative and is classified by the resulting outline data-centre scheme rather than as procedural.
- GT signals: `energy infrastructure`
- LLM signals: `energy infrastructure`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: 2008 coded language (technical services centre, I.T facilities, substation) but zero documents anywhere; identification of LCY20 unverified — FOI/Barbour-notes candidate
- LLM why: Full application for a new-build 'technical services centre' with offices, IT facilities, substation and plant enclosures, cross-linked to 'LCY20 - DATA CENTRE' project, so this is substantive new construction rather than procedural.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation, internal plant, external plant enclosures`

### #41. Stockport

- Ref: `Stockport/DC/090552`
- GT verdict: **enabling_works** / LLM: **unknown**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: guessing
- GT why: Demolition preceding DC build per Barbour (Under Construction); description silent
- LLM why: Prior approval for demolition of an industrial building with no data-centre reference in description or context beyond a generic 'demolition' project link, so association cannot be confirmed but shouldn't be discarded as not_dc.
- GT signals: ``
- LLM signals: `(none)`