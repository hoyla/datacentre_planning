# Triage eval: claude-sonnet-5

Last updated 2026-08-03T20:47:12. JSONL: `eval_dc_build_claude-sonnet-5_2026-08-03_2044.jsonl` (50 rows).


## Headline numbers

- **50** applications evaluated, 0 errors
- **Verdict accuracy: 44/50 = 88%**
- **Deep-read accuracy: 41/50 = 82%**
- **Signal Jaccard average: 0.58**
- Mean per-call latency: 3.6s (min 2.3s, max 14.2s)


## Verdict confusion (ground truth → LLM)

|  | →DC | →adjacent | →unrelated | →unknown | total |
|---|---|---|---|---|---|
| **DC** | 0 | 0 | 0 | 0 | 0 |
| **adjacent** | 0 | 0 | 0 | 0 | 0 |
| **unrelated** | 0 | 0 | 0 | 0 | 0 |
| **unknown** | 0 | 0 | 0 | 1 | 1 |

## Disagreements


### #31. Cherwell

- Ref: `Cherwell/25/03310/REM`
- GT verdict: **new_build** / LLM: **not_dc**
- GT deep-read: maybe / LLM: no
- GT confidence: probable / LLM: probable
- GT why: Graven Hill D1 REM — B8-worded but identified to exact unit by Barbour (435MW campus); docs to verify
- LLM why: Reserved matters for B8 storage/distribution buildings with generic 'services infrastructure' phrasing, no scale figures, power kit, or data-centre-typical features to trigger disguise suspicion.
- GT signals: `services infrastructure`
- LLM signals: `(none)`

### #32. Cherwell

- Ref: `Cherwell/22/01829/OUT`
- GT verdict: **new_build** / LLM: **unknown**
- GT deep-read: maybe / LLM: maybe
- GT confidence: guessing / LLM: guessing
- GT why: Graven Hill D1 outline — B8-worded 104,008sqm; Barbour-identified DC campus
- LLM why: Large single-use B8 scheme (104,008 sq m) with services infrastructure emphasis but no data-centre naming, matching the disguise-suspect pattern rather than a confirmed data centre.
- GT signals: `services infrastructure`
- LLM signals: `services infrastructure`

### #33. MiltonKeynes

- Ref: `MiltonKeynes/21/02578/FUL`
- GT verdict: **new_build** / LLM: **not_dc**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: probable
- GT why: Project MK Datavault (Enigma DC, built) — filed as plain B2/B8 commercial buildings
- LLM why: Plain B2/B8 commercial buildings with ordinary access, parking and landscaping language, no data-centre indication or scale/features suggesting disguise.
- GT signals: ``
- LLM signals: `(none)`

### #35. StAlbans

- Ref: `StAlbans/5/2025/1841`
- GT verdict: **new_build** / LLM: **procedural**
- GT deep-read: yes / LLM: maybe
- GT confidence: guessing / LLM: probable
- GT why: S73 raising Zone 1A ridge 18→20m for 2-storey DC with roof plant (planning statement 4.9-4.10) — scale axis
- LLM why: Variation of Condition 3 adjusting parameter plan boundaries, landscaping buffer, and building height restrictions reads as a refinement to an existing scheme's plans rather than a change to whether/how big/how powered the data centre is, though height changes warrant a closer look.
- GT signals: ``
- LLM signals: `(none)`

### #40. ChilternSouthBucks

- Ref: `ChilternSouthBucks/CH/2008/0629/FA`
- GT verdict: **unknown** / LLM: **new_build**
- GT deep-read: yes / LLM: yes
- GT confidence: probable / LLM: probable
- GT why: 2008 coded language (technical services centre, I.T facilities, substation) but zero documents anywhere; identification of LCY20 unverified — FOI/Barbour-notes candidate
- LLM why: Full application for a new detached technical services centre with offices, I.T facilities, substation and plant enclosures — a substantive new-build scheme with power infrastructure, not a procedural filing.
- GT signals: `substation, external plant, I.T facilities`
- LLM signals: `substation, internal plant, external plant enclosures`

### #41. Stockport

- Ref: `Stockport/DC/090552`
- GT verdict: **enabling_works** / LLM: **not_dc**
- GT deep-read: no / LLM: no
- GT confidence: probable / LLM: probable
- GT why: Demolition preceding DC build per Barbour (Under Construction); description silent
- LLM why: Prior approval for demolition of a generic high-bay industrial building with no data-centre reference in description or context.
- GT signals: ``
- LLM signals: `(none)`