# Roadmap

What is still to do. Everything already built and decided — including
the approaches tried and rejected, which are worth knowing before
re-proposing them — is in [HISTORY.md](HISTORY.md).

Current state: **429 sites** (plus 26 pre-planning), **1,709
applications** in the site universe, **54,707 documents**, **18,645
analysed**, **462,221 findings**. Phase 1 of the handover is published;
acquisition is running again.

---

## Finishing Phase 1

The handover is out. These close it properly.

- **Re-stamp and regenerate.** Acquisition restarted after the first
  boundary, so the release is stamped when collecting stops.
  `scripts/phase1_finalise.sh` waits for the sweep and the Drive sync,
  re-stamps `phase1_snapshot.json`, rebuilds workbook, DuckDB and reader,
  syncs Drive and updates the Sheet. It stops short of the PR that
  deploys `index.html`.
- **Verify the Drive repair.** The document tree was rebuilt after a
  duplicate archive was found; confirm by sampling files' parents, not by
  trusting the sync counters. Then the duplicate folder
  `1UxxGmbiEI-9lR8DPJnEzonBj6OR6OpQe` can be deleted — an outward-facing
  deletion, so Luke's call.
- **Re-probe the password gate** after the next deploy. Unauthenticated,
  from outside, including `//index.html`, `///index.html` and
  percent-encoded separators — a browser session cannot show you this.
- **16 bad-chunk documents and 7 sites holding unread documents.** Small,
  but they turn into "why does this site say nothing" later.

## Phase 2 — finish the collecting, then the reading

- **The acquisition tail.** 108 applications are being worked now. Of
  those recorded unreadable, a host-by-host probe found **20 reachable
  without a browser, across eleven unrelated bespoke portals** — roughly
  one adapter per two applications, which is poor value. The larger and
  cheaper bloc is **31 that route through the browser**, using tooling
  that already works: 15 behind AWS WAF (the Coventry signature), 8 on
  LPAssure serving `UnsupportedWebBrowser`, 8 Salesforce needing a
  harvested document listing. Needs a human at the keyboard.
  Genuinely hard: 5 behind CAPTCHA, 7 refusing with 403/500/503
  regardless of user-agent, 1 Incapsula.
- **Deep-read the remainder.** Two thirds of the corpus is unread and
  the Anthropic budget is spent; the plan is OpenAI credits. Everything
  downstream already marks unread sites, so this raises figures rather
  than changing shape.
- **Re-list the corpus to find historical partial fetches.** A short
  fetch used to be recorded as complete. New ones are caught, but past
  ones are not measurable from the manifests, which record what was
  stored and not what was offered. Re-listing the document pages of the
  applications that hold documents would settle it. **Do this before
  anyone quotes per-site document counts.**

## Phase 3 — the second opinion

- **Second-model comparison across the corpus.** A subset is dual-read
  already. Where two models disagree, both readings are kept and the
  disagreement is the finding; the comparison is the deliverable.
- **Water adjudication**, once reading is complete — whether the 93
  sites disclosing consumption support anything firmer than the cooling
  method reported today.

## Coverage gaps worth closing

Prompted by the **Devon Data Campus** (Xlinks, North Devon), a scheme
with an active public campaign of which the corpus holds *nothing*: zero
matches for Xlinks, Valeon, Alverdiscott or Devon Data Campus. Three
gaps, in rising order of effort:

1. **Operator watch-list sweep** (cheap). Add Xlinks and Valeon, review
   the list generally, run a name-based PlanIt sweep. Catches an
   application when it is validated rather than when we next look.
2. **Pre-application and screening entries.** Councils publish EIA
   screening and scoping requests, and Scottish PANs, *before* any
   application exists. Our universe starts at submission, so this class
   is structurally invisible. Decide whether pre-planning entries become
   first-class universe members or a separate watch table.
3. **Section 35 Directions / NSIP discovery.** The energy layer is
   ingested, but a data centre attaching itself to an NSIP power project
   is still invisible on both sides of the join. Xlinks'
   Morocco–UK interconnector lands at Alverdiscott, which is plausibly
   *why* a data campus is proposed there. An NSIP spans hundreds of
   kilometres and many authorities, which the 1 km clustering rule
   handles badly — it wants its own node type and evidence-based rather
   than proximity-based association.

`adjacent_power` holds only ~15 applications universe-wide, which is
implausibly few and consistent with power schemes near campuses being
absent from the corpus rather than misclassified.

## Smaller things

- **Promote `associated_id` to a typed `applications.parent_ref`
  column.** Parent-backfill confirmed the field is reliable; a typed
  column makes family navigation a join rather than JSONB extraction.
- **CI on GitHub Actions.** `pytest -m "not integration"` on every push,
  plus `node --test` for the edge middleware. Feasible now the repo is
  public and Apache 2.0.
- **Four sites report a total site demand below their IT load.** All four
  are correct — the figures come from different applications at
  multi-building sites, and each figure names its source application in
  the reader. Worth adjudicating by hand rather than changing the
  rollup rule.

---

## Parked

Deferred consciously. Return when journalism need warrants.

- **DC01, the unidentified Foxglove case.** A 320 MW outline approved
  2025-02 with implausibly low emissions and no council, developer or
  address. Three of four originally-unidentified cases are resolved;
  this is the fourth. Most likely falls out of an operator-name sweep
  for hyperscaler-affiliated SPVs.
- **Document corpus mirror.** `data/raw/` is local-only and growing.
  Zenodo (DOI, CC-BY) is the leading candidate for a reproducibility
  mirror. Decide once the corpus stops moving.
- **`other_fields` normalisation.** PlanIt carries applicant and agent
  fields inside `raw_metadata`; promote to columns if a bigger
  operator-name sweep happens.
- **Pre-2018 broader-keyword backfill.** PlanIt thins sharply before
  2018. Parent-backfill already pulled in substantive pre-2018 parents; a
  separate sweep would catch cases with no child in our window.
- **Environment Agency public register.** Industrial installations and
  combustion plant, as triangulation against permitted on-site capacity.
- **Multimodal pass over drawings.** Rejected in v1 and still rejected:
  PDFs are overwhelmingly text-layered, and concealed plant will not be
  in the drawings. Revisit only for a specific application where both
  conditions fail.

---

## Open questions

- **Does the Google Sheet stay the annotatable copy?** It is a
  conversion, not the file the pipeline writes, so it drifts from the
  workbook unless `scripts/sheet_sync.py` is run. That is deliberate —
  the point is that people can comment on it — but it means two
  artefacts claim to be the workbook.
- **Do pre-planning schemes become first-class universe members?** See
  the coverage gaps above. Affects site counts, so worth settling before
  a number goes in print.
- **PlanIt rate-limit politics.** PlanIt is donation-supported and
  friendly, and we are a heavy user. It now 429s far more aggressively
  than in May — assume an hourly quota and plan sweeps at ≥10 s spacing.
  A courtesy email is overdue.
- **Public-data ethics for personal fields.** Householder applications
  can carry applicant names. The schema stores raw values and redaction
  happens at export; the pre-publication sweep needs re-running against
  any new aggregate that touches personal fields.
