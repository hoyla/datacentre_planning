# Post-publication checklist

The repo is currently **private** on GitHub (since 2026-05-14) to halt
pre-publication exposure of editorial direction. After Aisha's story
lands, we'll flip it back to public. This document records what to do
on flip day so the decisions get made carefully now, not in a hurry
then.

For background see [ARCHITECTURE.md §Storage](ARCHITECTURE.md) and the
[ROADMAP](ROADMAP.md) "Privacy" Done-log entry.

---

## What gets tracked, what doesn't

The current `.gitignore` blocks all of `data/` except an explicit allow-list.
On flip day we'll widen the allow-list to expose the methodology trail.

### Already tracked (no change needed)

| Path | Why |
|---|---|
| `data/operators.yaml` | Operator-name sweep configuration. |
| `data/triage_labelling/rubric.md` | The distilled triage methodology — the editorial-decision document. |
| `data/priors/*.yaml` (`foxglove_top10.yaml`, `council_aliases.yaml`) | Reproducible priors. |
| `data/priors/osm/uk_power_plants.geojson` | OSM `power=plant` snapshot for the map (ODbL-licensed; reproducibility matters). |

### Add to allow-list at publication

These are the methodology / reproducibility files a third party would
want to understand how we built the dataset:

| Path | Why |
|---|---|
| `data/seed_cases/walkthrough_findings.md` | Hands-on findings from Aisha's three exemplar applications — methodology grounding. |
| `data/seed_applications.md` | The exemplar list (Wapseys Wood / Yorkshire Energy Park / Loughton). |
| `data/planit_exploration/findings.md` | API behaviour discoveries (rate limits, `associated_id` semantics, etc.). |
| `data/planit_exploration/sample_data_centre.json` | Already a test fixture; small JSON. |
| `data/colocated_energy_spike/findings.md` | Spatial-sweep methodology + the Yorkshire Energy Park proof-of-concept. |
| `data/nsip_research/findings.md` | NSIP CSV discovery + adapter design. |
| `data/prior_art_sources/foxglove_top10.md` | Verbatim transcription of Foxglove's top-10 list. |
| `data/prior_art_sources/foxglove_reconciliation.md` | Our reconciliation analysis against the keyword-sweep universe. |
| `data/triage_labelling/eval_*.md` | Per-model evaluation reports — justifies why granite4.1:30b was chosen. |
| `data/triage_labelling/eval_summary.md` | Comparative summary across the five evaluated models. |

### Deliberately stay gitignored

| Path | Reason |
|---|---|
| `data/raw/` | Document corpus, ~2 GB+ and growing. Future hosting candidate (S3 or zenodo.org), not git. |
| `data/triage_labelling/round_01_sample.md`, `round_01_labels.json` | Householder names sometimes appear in planning-application descriptions; PII risk. Keep out of git even if Luke's own labelling is editorially defensible. |
| `data/triage_labelling/eval_*.jsonl` | Per-app raw model outputs — point-in-time data, large, better reproduced than reused. Anyone who wants this can re-run `scripts/eval_triage.py`. |
| `data/prior_art_sources/foxglove_gap_report.pdf` + `.txt` | Foxglove's report; their copyright. Our verbatim transcription in `foxglove_top10.md` does the citation work. **Also delete locally** once we're confident the pipeline logic doesn't need to re-reference the PDF (see pre-flip step below). |
| `data/exports/` | Point-in-time hand-off artefacts (markdown + xlsx + map). Not useful to a third party; they should regenerate via `dcp export` / `dcp map`. |
| `data/worklist/` | Same as `exports/` — quick-scan preview output. |
| `data/planit_exploration/all_data_centre_records.json` | Large response cache; PlanIt is the canonical source. |
| `data/planit_exploration/api_docs.html` | Captured PlanIt API docs; third parties should fetch the current version from planit.org.uk. |
| `data/planit_exploration/areas.json` | Captured areas list; same — PlanIt is canonical. |
| `data/idox_exploration/` | Superseded by `tests/fixtures/idox/halton_22_00028_documents.html`. Can drop entirely. |

---

## Pre-flip mechanical steps

Do these in order on the day of publication, after Aisha's piece is live:

1. **Delete locally-only files no longer needed.**
   ```bash
   # Foxglove PDF — only kept as a local reference during dev
   rm data/prior_art_sources/foxglove_gap_report.pdf
   rm data/prior_art_sources/foxglove_gap_report.txt
   # Idox exploration superseded by tests/fixtures/idox/
   rm -rf data/idox_exploration/
   ```
   These deletions are local-filesystem only — files were never tracked,
   so nothing to commit.

2. **Sanity-scan the to-be-tracked files for PII / unintended leakage.**
   Open each file in the "Add to allow-list" table above and look for:
   - Householder applicant names, agent names, contact details.
   - Editorial commentary that references unpublished story angles or
     reporter contacts.
   - Internal council-officer names beyond what's already public.

   Anything you flag, redact in-place or move into a `_archive/` outside
   the planned allow-list.

3. **Update `.gitignore`.** Append the new exemptions in the same shape
   as the existing ones (allow-the-dir, block-everything-in-it,
   allow-specific-paths):

   ```gitignore
   # --- post-publication: methodology trail ---
   !data/seed_cases/
   data/seed_cases/*
   !data/seed_cases/walkthrough_findings.md

   !data/seed_applications.md

   !data/planit_exploration/
   data/planit_exploration/*
   !data/planit_exploration/findings.md
   !data/planit_exploration/sample_data_centre.json

   !data/colocated_energy_spike/
   data/colocated_energy_spike/*
   !data/colocated_energy_spike/findings.md

   !data/nsip_research/
   data/nsip_research/*
   !data/nsip_research/findings.md

   !data/prior_art_sources/
   data/prior_art_sources/*
   !data/prior_art_sources/foxglove_top10.md
   !data/prior_art_sources/foxglove_reconciliation.md

   # Triage eval reports (markdown only — .jsonl raw outputs stay local)
   !data/triage_labelling/eval_summary.md
   !data/triage_labelling/eval_*.md
   ```

   Verify the negation patterns are exhaustive: a file glob-matches the
   most recent matching pattern, so the order matters.

4. **Stage and verify.**
   ```bash
   git add .gitignore data/seed_cases/walkthrough_findings.md \
           data/seed_applications.md \
           data/planit_exploration/findings.md \
           data/planit_exploration/sample_data_centre.json \
           data/colocated_energy_spike/findings.md \
           data/nsip_research/findings.md \
           data/prior_art_sources/foxglove_top10.md \
           data/prior_art_sources/foxglove_reconciliation.md \
           data/triage_labelling/eval_*.md \
           data/triage_labelling/eval_summary.md
   git status -sb            # confirm only intended files are staged
   git diff --cached --stat  # quick line-count audit
   ```

   Then `git check-ignore -v data/raw/sample/file.pdf data/exports/x.html
   data/triage_labelling/eval_granite4_30b.jsonl` to confirm the
   still-blocked paths are still blocked.

5. **Commit, then flip the repo to public** via the GitHub web UI
   (Settings → General → Change visibility → Make public).

   ```bash
   git commit -m "Publication-day: expose methodology trail in data/"
   git push
   ```

   Then on GitHub, flip the visibility. The README's "Status" line should
   already reflect publication date by then; if not, update it in a
   separate commit so the flip is mechanical.

---

## Post-flip verification

After flipping, do a quick sanity pass from a logged-out browser:

- Confirm the repo's `data/` tab shows only the intended files.
- Open `data/triage_labelling/round_01_labels.json`'s expected URL — should 404 / not-found.
- Open `data/raw/idox/<some_app>/<sha>.pdf` URL — should 404.
- Spot-check a tracked file (e.g. `walkthrough_findings.md`) renders correctly.

If anything's exposed that shouldn't be, **flip the repo back to private
immediately**, fix, and re-flip.

---

## Notes worth recording for the public version

When flipping public, consider also:

- Adding a `CITATION.cff` with the project metadata so academic mirrors
  can cite it cleanly.
- A `LICENSE` (decide before flip — likely MIT or Apache 2.0 for code;
  the `data/priors/osm/` content stays under ODbL by upstream
  attribution).
- A "How to reproduce the dataset" section in the README pointing at
  `scripts/` + the `dcp` CLI commands in order.
- A note on the document corpus location (where `data/raw/` lives if
  mirrored to S3 / zenodo / similar) and any access conditions.
