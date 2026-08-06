# Methodology — UK data-centre planning dataset (v2)

*How the dataset is built, what has been measured about its accuracy,
and where its edges are. Companion to the [data dictionary](data_dictionary.md).*

## Universe construction

1. **Ingest broadly.** All UK planning applications matching a broad
   data-centre search across the PlanIt index of council portals
   (401 GSS-mapped councils; 2001–present, dense from 2018), plus
   operator-name expansions, spatial sweeps around known sites, and
   family links — 1,894 applications ingested to date. The search is
   deliberately wider than the story: the corpus must be able to
   surface null findings and counter-evidence, not only dramatic cases.
2. **Cross-source reconciliation.** Barbour ABI's construction-project
   list (253 projects, licensed, credited) is reconciled against the
   planning universe in both directions — what each source holds that
   the other misses is enumerated, not assumed.
3. **Site clustering.** Applications and projects cluster into 391
   sites via explicit record links, family references, and 1 km spatial
   proximity. Dense urban clusters merge conservatively (site counts
   there are a lower bound). 74 sites are currently unlocatable pending
   geocoding.

## Classification

Applications are classified by a language model against a written
rubric (v1: four classes; v2.1 "dc_build": eight project classes
distinguishing new build, expansion/refurbishment, enabling works,
adjacent power, pre-application instruments, procedural filings,
non-data-centre, and unknown). The rubric encodes five adjudicated
rules, including: classify the *instrument*, not the scheme it
describes; a filing is procedural only if it leaves the scheme
unchanged on whether it is a data centre, how big, and how powered;
data-centre association for power/enabling classes requires evidence,
not inference; the model's reasoning must not assert facts absent from
its input.

**Measured accuracy** (50 adjudicated ground-truth cases, labels
recording truth from all evidence, with rows unresolvable from the
visible text flagged): the production configuration (Claude Sonnet 5,
prompt v2.1, metadata-enriched) scored 47/50 overall — 38/40 on cases
resolvable from visible text, 9/10 on flagged cases. A 50-row
evaluation supports configuration choice; a larger stratified
adjudication of production output is planned before publication-grade
error rates are quoted. Every verdict retains model, confidence and
reasoning; all prior verdicts are kept.

## Document acquisition

Documents are fetched from council portals by adapters (Idox and
Ocella today; Agile, Arcus, Salesforce, Northgate and NEC portals are
queued by coverage), with an identifying User-Agent, multi-second
request delays, backoff on rate-limiting, and no circumvention of
portal access controls. Every fetched page is snapshotted; every
document is content-hashed with its source URL recorded; re-runs are
no-ops on unchanged content. Applications whose documents cannot be
fetched are classified and counted per portal family — the gap is
enumerated, never silent. Some older documents have been removed by
councils; those absences are recorded as absences.

## Extraction and verification

Facts about power, energy and environment are extracted from documents
in two stages: structured fact extraction first, comparison against
marketing/consenting claims second — the hypothesis is never baked
into the extraction. Every extracted fact carries a verbatim quote,
verified mechanically against the source text (with OCR fallback for
scanned documents) before it enters the dataset; quotes that fail
verification are rejected. 186 verified findings exist from the v1
deep-read of 33 applications; the v2 deep-read will cover all
candidate data-centre sites, extracting power generation and
consumption, water use, emissions, designated-site impacts (SSSI and
related), flood risk, noise, and EIA screening outcomes.

## Known limitations

- **Description ceiling.** Some truths are invisible from application
  metadata (the ground-truth exercise found 10 of 50); only document
  deep-read resolves them.
- **Statuses lag.** Council statuses are point-of-ingest and a refresh
  pass is pending; at least one known decision is stale.
- **Geocoding gaps.** 74 sites unlocatable pending the geocoding pass.
- **EIA indicators are a floor** (reference conventions vary; document
  coverage still growing).
- **Coverage asymmetries** are enumerated in the campaign manifest:
  portal families without adapters, defunct portals, withdrawn
  applications, and rate-limited councils awaiting a gentler retry.

## Provenance chain

Aggregate → site row → application → document → quote. Every number in
any published artefact can be walked back to a source document, its
page, its portal URL, the fetch timestamp, and the extraction model.
Where a link in that chain is inferred (a fuzzy match, a spatial
cluster, a model verdict), the inference is stored alongside the
original record with its method named — original records are never
overwritten.
