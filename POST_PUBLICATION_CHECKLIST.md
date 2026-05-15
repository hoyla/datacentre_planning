# Post-publication checklist

The repo is currently **private** on GitHub (since 2026-05-14) to halt
pre-publication exposure of editorial direction. After Aisha's story
lands, we'll flip it back to public.

**Status as of 2026-05-15:** the methodology-trail files are already
tracked in the private repo (PII scan done, gitignore widened, single
methodology-trail commit landed). Pre-deletes (Foxglove PDF + idox
exploration cache) also done. **Only the GitHub visibility toggle and
the post-flip verification remain for publication day.**

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

### Done 2026-05-15 (while the repo is still private)

The PII-scan, local deletions, gitignore widening, and methodology-trail
commit have all already landed. Specifically:

- **Local deletions** completed: `data/prior_art_sources/foxglove_gap_report.{pdf,txt}`
  and `data/idox_exploration/` (superseded by `tests/fixtures/idox/`) removed
  from the working tree.
- **PII scan** completed and clear on the to-be-tracked files
  (`sample_data_centre.json` has only "See source" / corporate-agent values;
  eval-report disagreements reference only corporate DC cases; methodology
  docs cover the three exemplar cases with no householder data).
- **`.gitignore` widened** with the new allow-list (see `.gitignore`
  in the repo — patterns landed in a single commit alongside the tracked
  files).
- **Methodology-trail commit landed** and pushed.

### Still to do on publication day

1. **Final visibility flip on GitHub.** Settings → General → Change
   visibility → Make public. No further repo edits required — the
   methodology trail is already there.

2. **Update the README's "Status" line** if it still says "private" or
   refers to the pre-publication phase. Best done in a separate commit
   the day before so the flip itself is mechanical.

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
