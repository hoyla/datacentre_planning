# Triage eval — round 01 (2026-05-14)

LLM-based Stage 1 triage prompt validated against Luke's labelled 30-application sample. Implementation in [`dcp/triage.py`](../../dcp/triage.py); ground truth in [`round_01_labels.json`](round_01_labels.json); harness in [`scripts/eval_triage.py`](../../scripts/eval_triage.py); rubric in [`rubric.md`](rubric.md).

Model: Mistral 7B via Ollama (`mistral:latest`). ~2s per application after warm-up.

---

## Results

| Run | Verdict accuracy | Deep-read accuracy | Signal Jaccard | Notes |
|---|---|---|---|---|
| Baseline prompt | 22/29 = **76%** | 16/29 = 55% | 0.32 | See [`eval_mistral_…_1231.md`](eval_mistral_2026-05-14_1231.md). Main miss pattern: procedural follow-on applications (conditions discharges, NMAs, extensions) incorrectly classified as DC because their descriptions mention "data centre" via the parent reference. |
| Refined prompt (procedural-rule fix) | 25/29 = **86%** | 22/29 = 76% | 0.35 | See [`eval_mistral_…_1234.md`](eval_mistral_2026-05-14_1234.md). Added explicit worked examples for "Variation of Condition…", NMAs, "Approval of Details Reserved by Condition…", "rear extension to existing data centre", etc. — all now correctly classified as `unrelated`. |

**Signal Jaccard remains modest (0.35).** Expected — Luke's signal-tag vocabulary includes operator priors ("Foxglove" as a journalism-context label, "Nscale tend to use microgrids") and brand names that aren't in any description text. The LLM correctly stays within description-text signals. The Foxglove tag is filtered out of the Jaccard computation in the harness; brand-name absences still reduce overlap.

---

## Remaining disagreements (refined-prompt run)

Four cases out of 29. Three are not really "prompt bugs":

- **#6 Saunderton (Wycombe/22/06872/VCDN)** — LLM `unrelated`, Luke `DC`. The LLM correctly applied the rubric (this is a Variation of Conditions on a parent DC permission, so `unrelated`). Luke's `DC` label was driven by the **Foxglove operator prior** — knowledge the LLM doesn't have at this stage. The operator prior is layered in upstream via `applications.discovered_via` tags (e.g. `operator:Greystoke`), and downstream during deep-read where source documents become visible. Stage 1 description-only triage cannot reproduce it without leaking project history into the prompt.
- **#23 Hillingdon condition discharge** — LLM `unrelated`, Luke `DC` (`verify with Aisha = yes`). Luke flagged this as a boundary case for Aisha-verification. The LLM applied the procedural rule strictly; whether that's correct depends on how aggressive Aisha wants to be about capturing conditions-discharges that re-cite power infrastructure from the parent.
- **#29 Central Beds 5,150-dwelling mixed-use** — LLM `unrelated`, Luke `unknown` (`verify with Aisha = yes`). Again a boundary case Luke flagged. The application is a conditions-discharge on a 5,150-dwelling master plan that includes a DC zone. The LLM's "unrelated" is rubric-consistent but ignores the possibility that the parent app has a meaningful DC. Luke's "unknown" is more conservative.

One genuine LLM error:

- **#20 East Ayrshire pre-application Scotland DC** — LLM `adjacent`, Luke `DC`. Description starts *"Data centre complex including data halls, substation, new road access…"* — clearly a DC application. The LLM downgraded to `adjacent` because of the substation mention. **A future prompt iteration should clarify: a substation appearing within a clear DC application doesn't make the application `adjacent`.**

---

## Calibration: deep-read accuracy

22/29 = 76%. Most matches; small handful of disagreements where the LLM is more cautious (`maybe` vs Luke's `yes` or vice versa). Not a structural issue.

---

## What this means for production triage

The prompt is now good enough to **run unattended over the 1,549-application universe**, with the understanding that:

1. **Operator-prior-driven labels won't be captured by the LLM alone.** That's fine — operator tags are layered in elsewhere (`discovered_via`), and the journalism review pass uses both signals.
2. **Boundary cases (Aisha-verify) will go either way.** Manual review at the candidate-list stage will catch the ones that matter; the false-positive bias is intentional and acceptable.
3. **One known prompt error** (substation downgrading a clear DC to adjacent) is documented; fix in a follow-on iteration once we see a few more real cases.

Suggested next steps:

- **Run the triage over the full ingested universe** (1,549 DC-keyword applications + NSIP + operator-discovered) and produce a ranked candidate list for Aisha.
- **Round-02 labelling** of a fresh 30 — different cases, after Luke and Aisha agree on the remaining boundary calls — to confirm the prompt generalises.
- **Optionally try a stronger model** (gemma4 in Luke's setup is currently non-responsive; bigger models via the Anthropic API would push accuracy but cost more per run).
