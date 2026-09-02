# Models — which one reads what, and why

The roster — task, model, route, the columns each cohort is versioned
by, with counts stamped on a date — is [ARCHITECTURE.md](../ARCHITECTURE.md),
"Which model runs which task", and is not repeated here. The standing
policy on the local reader — a second opinion, never a first read — is
ARCHITECTURE §3, "Reading at scale". What this file holds is the part
neither of those carries: **what was compared, what was decided on the
comparison, and what is still open.** Read it before proposing a model
change for any task and before scoring one; every comparison below
records the measurement it rests on and where that lives, so the next
comparison is scored against a record rather than against memory.

Opened 2026-09-02 by moving the model discussion out of ROADMAP, where
it had grown to some 170 lines of finished work with a handful of open
items inside it. ROADMAP keeps the open items and points here; the
narrative of what happened is HISTORY.

The rule for entries: a decision names its date, who made it, and the
measurement. Where a figure was measured in a session and never written
into the repository until this file, the entry says so and names the
artefact that corroborates it or the tool that re-measures it.

---

## Decisions in force — do not relitigate

- **Deep reads of new content run on `gpt-5` through the OpenAI batch,
  and the reading model does not change inside a phase** (Luke,
  2026-08-28, when a switch to terra was proposed on the strength of
  that day's comparison: "we should stick to gpt5 for consistency in
  this acquisition phase"). A corpus read by two models is one whose
  coverage differences are partly an artefact of which model saw which
  document, and the comparison had just measured that effect at 2.0
  against 4.0 power-family findings per document between two serious
  readers. A better model is a reason to plan the next phase, not to
  switch inside one. The `first_read` cohort and its flags are in the
  docstring of `scripts/deepread_escalate_openai.py`.
- **The local reader (`mlx:Qwen3.6-35B-A3B-4bit`) is a phase-3 second
  opinion and never the first read of anything** (2026-08-26; the
  standing policy is ARCHITECTURE §3, the measurement is HISTORY's
  label-audit entry). Not restated here.
- **Machine readings render from `gpt-5` / `reading-1.4`** (Luke,
  2026-08-31, PR #304 — terra having read every site that afternoon and
  stated about a quarter of the figures at the same prompt). The terra
  move is *deferred, not reversed*: `gpt-5` is a legacy model at
  OpenAI, so this bought correctness now rather than a durable answer.
  **Pass `--model gpt-5` every time**: the script's default is still
  `gpt-5.6-terra` (runbook step 4a), and `LATEST_SQL` renders the
  newest reading per site whatever model made it.
- **Future deep-read model choices are `claude-sonnet-5` and
  `gpt-5.6-terra`** (Luke, 2026-08-28, from the six-model comparison
  below): terra for coverage sweeps, Sonnet where labelling discipline
  matters more than yield. To be applied at a phase boundary, and
  re-validated on the validation cohort first — the escalate script
  refuses a bulk cohort until a validation batch for the same model tag
  has been collected. **Caveat, 2026-09-02:** the machine-reading
  result of 2026-08-31 is evidence about terra that postdates this
  decision. It is a different task — a fixed-schema synthesis over a
  site's adjudicated facts, not per-document extraction — and it showed
  terra shifting from stating figures to quoting around them under one
  prompt and not another. It does not overturn the deep-read choice; it
  is the reason the validation batch is not optional.
- **The label audit stays on `gpt-5` / `label-1.0`** (runbook). The
  incremental skip is keyed on the model-and-prompt pair, so moving the
  audit to a newer model silently re-audits every row.
- **Power adjudication is split by consequence, not preference**
  (ARCHITECTURE, "Which model runs which task"): the same rubric and
  the same model reached two ways, the subagent route reserved for
  figures that can move a site's headline number. Not restated here.
- **Triage runs `claude-sonnet-5` against the enriched dc_build rubric**
  (trial 2026-08-03: 47/50, and 9/10 on the invisibility cases; v1's
  five-model evaluation of May 2026 chose `granite4.1:30b`). Both are
  in ARCHITECTURE's design-decisions table.
- **No generative model is the text of record.** OCR is pypdfium2 with
  tesseract or RapidOCR; a vision model fails fluently and would let an
  invented quote verify (ARCHITECTURE, design decisions).
- **The drawings pilot runs `gpt-5.6-sol` and is quarantined by design**
  (`scripts/drawings_pilot_run.py`, migration 027): nothing joins
  `drawing_transcriptions` to adjudication or to any artefact, because
  the quote round-trip cannot verify a transcription against an image.
  The runner refuses to fall back to another model — a transcription is
  only interpretable beside the model that made it.

## Open

These are the lines ROADMAP points at. Each is a decision for Luke or a
measurement nobody has made.

1. **A prompt A/B on terra before it is tried again for machine
   readings** (Luke proposed it, 2026-08-31; not scheduled). Two or
   three prompts, scored on the sites where terra demonstrably lost
   figures — Didcot, Watford, Elsham — with `reading-1.3` as the
   baseline to beat. The hypothesis is specific: `reading-1.4`'s
   flagging instruction directs terra toward challenging figures rather
   than reporting them, so name what to state (each site's headline
   capacity, with unit and scope) rather than saying figures matter.
   Score both directions — figures recovered *and* quantity-type flags
   retained — since the two may trade against each other. **Score
   against the `gpt-5`/`reading-1.4` outcome below (4.23 figures per
   site, 40% of sites), not the `reading-1.2` baseline**, which would
   flatter any result.
2. **A durable model for the machine readings.** `gpt-5` is legacy at
   OpenAI. The return to it was a deferral; nothing yet says what the
   readings run on when it goes.
3. **Whether the machine-reading script's `--model` default follows the
   decision.** It is `gpt-5.6-terra`; the readings run on `gpt-5`; the
   runbook says to pass the flag every time. A default that disagrees
   with the decision is a regression waiting for a bare `--submit`; a
   default that follows it says terra is off the table, which was not
   decided either. One line of code, Luke's call.
4. **`gpt-5.6-sol` as a deep reader is untested.** Its validation batch
   stalled at 124 of 126 requests on 2026-08-28 and was never collected
   (queue time is not billed, so it cost nothing to leave; there is no
   `openai:gpt-5.6-sol` entry in `data/openai_measured_usage.json`). It
   is the drawings pilot's model, on a different task.
5. **Which reader re-extracts what the local model read** (ROADMAP,
   Phase 3): the findings whose families the label audit measured as
   the worst-filed in the corpus. The 2026-08-28 choice — Sonnet where
   labelling discipline matters — is the default position, not a
   decision; and if it runs it is a phase boundary, so the
   same-phase-same-model rule applies to whatever follows.

## What was compared

### Deep reads — six models on the validation cohort (2026-08-28)

Run on the 60-document validation cohort through
`scripts/deepread_escalate_openai.py --cohort validation` (the gpt-5
variants had reached only 21 of the 60). **The per-model yields and
quality figures below were measured in the 2026-08-28 session and
recorded outside the repository until this file.** Two artefacts
corroborate parts of them, and `scripts/compare_readers.py --models …`
re-measures the rest against the live database.

What the repository holds: `data/openai_measured_usage.json` records
126 requests each for `openai:gpt-5.6-luna` and `openai:gpt-5.6-terra`
over identical input (376,716 tokens), with output of 254,434 against
152,402 — 1,210 output tokens per request for terra, against roughly
2,194 for `gpt-5:low` (73.2M over 34,519 requests). ARCHITECTURE's
roster counts their findings: 2,971 luna, 1,964 terra — 49.5 and 32.7
per document.

What the session measured, per document unless stated:

| model | power-family findings | all findings | notes |
|---|---|---|---|
| `gpt-5:low` | 4.0 | | the reader in use; 51 quotes carrying two or more signal types |
| `gpt-5.6-terra` | 3.9 | 32.7 | level on the story families at half the output tokens; 24 label-split quotes; 126 requests in 3 minutes |
| `gpt-5.6-luna` | ~1.25× gpt-5:low | 49.5 | the highest raw yield, 1.58× overall — the extra was site identity, consultants, bat roosts, ground gas; 69% of its findings carried a signal type used nowhere else in the cohort; duplicated facts under near-identical labels (`waste_generating_process` / `waste_generation_process`, same quote) |
| `claude-sonnet-5` | 2.0 | | half the power material; the most disciplined on every quality measure — fewest labels per finding, a quarter of gpt-5:low's slicing, 1.3% gate rate |
| `mlx:Qwen3.6-35B-A3B-4bit` | | 7.4 | last |
| `gpt-5.6-sol` | untested | | stalled at 124 of 126, never collected |

**Decided on it** (Luke, 2026-08-28): terra and Sonnet for future
phases; stay on gpt-5 for the acquisition phase in progress; luna
rejected despite the yield. Recorded under Decisions above.

#### Re-measured 2026-09-02 with `scripts/compare_readers.py`

The database was up, so the tool the paragraph above names was run:
`--models openai:gpt-5.6-terra openai:gpt-5.6-luna claude-sonnet-5
openai:gpt-5:low openai:gpt-5 mlx:Qwen3.6-35B-A3B-4bit`. Its
definitions differ from the session's — per-document yield is over the
**21 documents all six read**, not the 60, and the gate-fail rate is
over each model's **entire run** as logged at read time, before the
2026-08-31 gate fix, so it overstates every model's invention by the
whitespace artefacts — which is why the two tables corroborate each
other's ranking rather than reproduce each other's digits.

| model | documents read | findings on the shared 21 | per document | gate fails | fail rate | parse fails |
|---|---|---|---|---|---|---|
| `openai:gpt-5.6-luna` | 60 | 875 | 41.7 | 103 | 3.4% | 0 |
| `openai:gpt-5.6-terra` | 60 | 544 | 25.9 | 36 | 1.9% | 0 |
| `openai:gpt-5:low` | 14,204 | 472 | 22.5 | 12,215 | 2.9% | 8 |
| `claude-sonnet-5` | 18,044 | 312 | 14.9 | 9,803 | 2.8% | 16 |
| `openai:gpt-5` | 60 | 153 | 7.3 | 6 | 0.9% | 18 |
| `mlx:Qwen3.6-35B-A3B-4bit` | 33,104 | 120 | 5.7 | 33,860 | 9.4% | 1,060 |

What it confirms: the yield order — luna, terra, gpt-5:low, Sonnet, the
local reader last — is the session's, and luna's gate-fail rate is
nearly twice terra's, the whitespace observation above seen from the
other side. What it adds is **agreement**, which the session did not
measure. Of the distinct quantitative figures (same document, same
value, same unit) in the shared documents, terra and gpt-5:low both
found 51 of 173 (29%); terra and Sonnet 40 of 161 (25%); terra and
luna 59 of 254 (23%), **139 of them found by luna alone** — the
"extra of the wrong kind" the session recorded, now as a count. Every
pair involving the local reader agrees on 6–19%.

`openai:gpt-5` in that table is the first live run of 2026-08-10 with
no reasoning-effort suffix — 692 findings over the 60 documents, 29% of
its requests answering nothing at all (the escalate script's docstring)
— not the `gpt-5:low` reader in use, so its 7.3 per document against
22.5 is the effort setting, not the model.

**Two measurement lessons outlived it.** All three serious readers
invent at about the same rate — roughly 1% of findings — so the raw
gate rate does not rank them. And the gate rate was actively
misleading: 63% of luna's rejections were whitespace artefacts against
37% of Sonnet's, because a model that tidies broken PDF text was
penalised against one that copies `d ata centres` verbatim. The same
day's measurement of the gate over a 900-rejection sample became the
gate fix (PR #295) and the re-gate (PR #298), measured corpus-wide at
29.8% of rejections — both in HISTORY.

### Machine readings — gpt-5 against terra (2026-08-31)

The narrative is HISTORY, "Terra read every site, and the readings went
back to gpt-5"; the PRs are #296 and #304. What a future comparison
needs from it:

**The six-site pilot compared across prompts, and its headline did not
survive.** gpt-5 at `reading-1.2` against terra at `reading-1.3`: terra
named figures where gpt-5 named categories (Didcot's "a 150MVA
substation" against "192MW IT load and 288MW gross power capacity"),
tied silence to the structured facts rather than reporting "no figures
in the pages", flagged naming discrepancies as discrepancies (Ark Data
Centres against ARK Continuity, Greystoke Land against Elsham Tech Park)
and caught the conditional green claim the seed-case walkthrough named
a Tier-1 signal. On that evidence the readings moved to terra (PR #296).
The full run overturned the figure-naming half: at the same prompt
gpt-5 states about four times terra's figures, and Didcot's `150MVA`
and `192MW` were gpt-5's under `reading-1.4` too.

**Three arms on 17 sites, `medium` effort throughout — the design that
separated model from prompt:**

| arm | items | quotes | power figures | sites with one |
|---|---|---|---|---|
| gpt-5 / `reading-1.2` | 21.00 | 34.18 | 6.65 | 65% |
| gpt-5 / `reading-1.4` | 21.18 | 35.41 | **8.53** | 65% |
| terra / `reading-1.4` | 16.88 | 36.59 | **2.18** | 53% |

Over the 344 sites both models read: terra 0.89 power figures per site
against gpt-5's 2.75, and 21.8% of sites carrying any figure against
33.1%. It produced *more* quotes per site than either gpt-5 arm — it
shifted from stating figures to quoting the text around them.

**Terra is erratic here rather than simply worse.** Same model,
`reading-1.3` → `1.4`, six sites: Didcot 8 → 0, Watford 6 → 0, Elsham
6 → 2 (losing the 1,000 MW headline it *did* state under 1.3), but
Union Park 0 → 10 and Yorkshire 0 → 3. Twenty figures became fifteen.
Its prompt-to-prompt variance on this axis is nearly as large as its
gap to gpt-5, which is why open item 1 is an A/B rather than a verdict.

**What terra did better, so it is not lost.** It flags quantity-type
errors well — four in one Elsham reading (figures typed as energy
storage on a quote stating a generation limit; on-site generation taken
from a hypothetical biomass plant's *fuel* requirement; per-unit engine
output and thermal fuel input both typed as whole-site generation)
where gpt-5 at `reading-1.2` caught one. It is better calibrated about
absence. One concrete catch: on Elsham Wolds it surfaced an Operational
Power Demand of 84 MW on a page gpt-5's reading never reached — a
smaller point than it first looked, because the 84 MW is an
inconsistency inside the applicant's own arithmetic rather than
anything that unsettles the corroborated 1,000 MW (ROADMAP, Coverage
gaps). **What gpt-5 did better:** fuller descriptive coverage (site
areas, GIA breakdowns, ramp-up schedules), a permission-history
question terra missed on Didcot, and at `reading-1.4` far more stated
figures.

**Cost: about $59 for terra against $33 for gpt-5** over ~359 sites.
Terra reasons roughly 2.3× harder — ~13,300 reasoning tokens per site
against 5,849 — while producing 6% *less* visible output.

**The outcome beat both arms it was chosen between.** Across the 361
readings rendered after the re-run (331 requests, 0 failed): **4.23
power figures per site, 40% of sites carrying at least one** — against
terra's 0.89 and 21.8%, and the `reading-1.2` baseline's 2.75 and
33.1%. The prompt change was worth more than the model change: it
lifted the figure rate 54% above where the corpus stood before either
was tried. One site still renders terra —
`SITE-CentralBedfordshire/CB/23/02827/DOC`, which the re-run did not
cover.

### Triage, adjudication, the local reader

- **Triage**: v1's five-model evaluation (May 2026; HISTORY) and the
  dc_build trial of 2026-08-03 are summarised in ARCHITECTURE's
  design-decisions table.
- **Adjudication**: subagent against API on 229 already-adjudicated
  figures — 94% agreement on the five-way verdict, 95% on the
  distinction a published chart cares about (ARCHITECTURE).
- **The local reader against Sonnet**: the label audit of 2026-08-25
  (HISTORY). Holding the family constant, `mlx` misfiles `power_demand`
  68% against Sonnet's 9% and `power_generation` 34% against 9%;
  seventeen of twenty families are worse. No megawatt figure is
  affected, because capacity reaches a site through
  `power_adjudication`, keyed on the finding rather than the family.

## What a machine-reading run costs, measured

The anchor is the 2026-08-29 batch: 182 sites alone overnight,
**$16.98** for 15,817,922 input and 1,439,745 output tokens, the OpenAI
console's day total matching the output files to the token. Per site:
71,865 in, 8,228 out, of which **5,849 is reasoning** — 71% of output,
and invisible in the stored reading, which is why cost cannot be
estimated from what is on disk. A full run over ~359 sites is about
26M input and 3M output tokens, **about $34** on gpt-5 (measured
2026-08-31 from the batch output files). ROADMAP's re-read tier table
quotes that figure; this is its derivation. An earlier "roughly 15M
input tokens" was this batch's own figure mistaken for a full run.

`_already()` in `scripts/machine_reading_openai.py` keys on
`(site_key, model, prompt_version, input_hash, gate_version)`, so a bare
`--submit` re-reads only the sites whose inputs moved — 47 at 2.11,
about 4.3M input tokens (runbook step 4a). A version bump re-reads
everything.

## Measurement lessons

Each was learned by getting it wrong once.

- **Compare at the same prompt.** The six-site pilot compared gpt-5 at
  `reading-1.2` with terra at `reading-1.3` and credited terra with
  figures the prompt had produced. The three-arm design — two models on
  one prompt, one model on two — is what separated the effects.
- **Score against the current baseline, not the one the decision was
  made against.** After `reading-1.4` the figure rate is 4.23 per site
  and 40% of sites; scoring an A/B against the old 2.75 flatters
  anything.
- **A prompt change can be worth more than a model change.** Measure
  the prompt before buying the model.
- **Reasoning tokens are invisible in the stored output.** A cost
  estimate from what is on disk misses 71% of the output on gpt-5 and
  more on terra.
- **Output-token ratios do not transfer between task shapes.** "Half
  the output tokens" held for 60 deep-read documents at `gpt-5:low` and
  did not hold for a fixed-schema reading whose length the schema sets.
- **The gate rate does not rank models** — all serious readers invent at
  about 1% — and it penalises a model that tidies broken PDF text. Look
  at what the rejections *are* before reading the rate.
- **Do not mix models inside a phase.** Coverage differences become an
  artefact of which model saw which document.
- **The page renders the newest reading whatever made it.** `LATEST_SQL`
  is deliberate — a withheld re-read must not fall back silently — so a
  model switch reaches the reader at the next build unless it is caught.
  After the terra collect, 331 of 363 sites would have rendered it. The
  append-only store protects history, not the page.
- **Cache on the model, not just the prompt** (PR #303). Six sites held
  terra answers at `reading-1.4`; a gpt-5 run would have re-used every
  one and recorded gpt-5 as their author.
- **Never fall back silently to a different model.** The drawings pilot
  checks the model list and refuses (`_require_model`); a row that names
  one model while another did the reading is a provenance failure.
- **Estimate tokens from real built requests, not characters ÷ 4.** The
  Sonnet bulk read of 2026-08-07 was estimated at about $313 and billed
  at $462 — dense technical text runs about 3.6 characters per token.
  Session-recorded; the practice it produced is `count_tokens()` on
  built requests in `scripts/adjudicate_power.py`.
- **Validate one live request before a batch.** A nullable enum written
  as `type: [string, null]` with `null` also in the enum failed every
  request of a 301-request adjudication batch, unbilled (2026-08-07,
  session-recorded); the `anyOf` form and the comment explaining it are
  in `scripts/adjudicate_power.py`.

## Tried and rejected

- **`gpt-5.6-luna` as a deep reader** (2026-08-28): the highest raw
  yield, of the wrong kind — see the table.
- **`gpt-5.6-terra` as the machine-reading model at `reading-1.4`**
  (2026-08-31): a quarter of the figures at the same prompt. Deferred
  pending the A/B, not rejected outright.
- **The local reader as a first read** (2026-08-26): the label audit.
- **A multimodal pass over the corpus's drawings** (v1, and again at
  2.8): PDFs are text-layered and concealed plant is not drawn. What
  survived is the quarantined pilot on the specific applications where
  the prose demonstrably fails to carry the figure (HISTORY, 2.8:
  "Drawings are worth reading, but only some of them").
- **Moving the label audit to terra alongside the reading switch**: it
  would have silently re-audited all 18,209 rows (runbook).
- **Switching the deep reader mid-phase on the strength of a
  comparison** (2026-08-28): Luke's consistency rule, above.
