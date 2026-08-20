-- External capacity claims, and the inferences that attach them to sites.
--
-- The 2026-08-10 survey (docs/EXTERNAL_DATA_SOURCES.md) established that
-- no external megawatt measures the quantity a planning application
-- states, and its design consequence was specified but never built:
-- capacity claims belong in an append-only structure — one row per
-- (source, quantity, value, date, locator) — presented beside the
-- planning-derived data and never merged into it. The 2026-08-19/20
-- research sweep produced the first source worth building it for:
-- NESO's Existing Agreements Register, the only public NESO artefact
-- naming transmission demand customers with MW.
--
-- Two tables because a claim and a match are different kinds of record.
-- A claim is a fact about the source: "the register carries a row named
-- 'Mecure Data Centre', 435 MW, Elstree 400kV". The assertion that this
-- row *is* our Tylers Way site is our inference, with a method, a
-- confidence and its own audit trail — so a wrong match can be retired
-- without touching the claim, and a claim can stand unmatched
-- indefinitely. Findings taught the same separation the hard way:
-- store what the source says and what we conclude as separate rows,
-- never as one overwritten field.

CREATE TABLE IF NOT EXISTS capacity_claims (
    id              bigserial PRIMARY KEY,
    source_key      text NOT NULL,
    claim_name      text NOT NULL,
    quantity_type   text NOT NULL,
    value_original  numeric NOT NULL,
    unit_original   text NOT NULL,
    value_mw        numeric,
    stage           text,
    as_at           date,
    source_url      text NOT NULL,
    source_locator  text,
    attrs           jsonb,
    inserted_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE capacity_claims IS
  'External capacity figures, one row per claim as the source states it. '
  'Append-only. Never joined into a site capacity field; rendered beside '
  'the planning-derived figures with quantity_type visible.';

COMMENT ON COLUMN capacity_claims.claim_name IS
  'Project name verbatim from the source, misspellings included — '
  '"Mecure Data Centre" is evidence, not a typo to fix.';

COMMENT ON COLUMN capacity_claims.value_mw IS
  'Normalised megawatts beside the original, never instead of it. Null '
  'when the unit does not convert (MVA without a power factor, MWh/yr).';

COMMENT ON COLUMN capacity_claims.as_at IS
  'The date the source speaks as of — its own update stamp, not our '
  'access date. Access dates live in data/external_sources/README.md.';

-- The vocabulary is shared with power_adjudication.quantity_type where
-- the quantities coincide, so a register claim and a planning-document
-- adjudication of the same kind can be compared without a mapping
-- table. The three additions are quantities only external sources
-- measure. Constrained because these are hand- or loader-entered and a
-- typo would silently break that comparison.
ALTER TABLE capacity_claims DROP CONSTRAINT IF EXISTS capacity_claims_quantity_known;
ALTER TABLE capacity_claims ADD CONSTRAINT capacity_claims_quantity_known
  CHECK (quantity_type IN (
    'it_load', 'grid_connection', 'total_site', 'onsite_generation',
    'cooling', 'energy_storage', 'thermal_input',
    'built_capacity', 'metered_consumption', 'announced_capacity'));

-- Idempotency as a constraint, not a convention (the findings lesson,
-- migration 012): re-running a loader on the same snapshot inserts
-- nothing. NULLS NOT DISTINCT so two rows differing only in a null
-- locator still collide.
CREATE UNIQUE INDEX IF NOT EXISTS capacity_claims_content_key
  ON capacity_claims (source_key, claim_name, quantity_type,
                      value_original, unit_original, as_at, source_locator)
  NULLS NOT DISTINCT;

CREATE INDEX IF NOT EXISTS idx_capacity_claims_source
  ON capacity_claims (source_key);


CREATE TABLE IF NOT EXISTS capacity_claim_matches (
    id             bigserial PRIMARY KEY,
    claim_id       bigint NOT NULL REFERENCES capacity_claims(id),
    site_id        bigint NOT NULL REFERENCES sites(id),
    method         text NOT NULL,
    confidence     text NOT NULL,
    evidence       text NOT NULL,
    matched_by     text NOT NULL,
    inserted_at    timestamptz NOT NULL DEFAULT now(),
    retired_at     timestamptz,
    retired_reason text
);

COMMENT ON TABLE capacity_claim_matches IS
  'Adjudicated inferences attaching a capacity claim to a site. Each row '
  'is an assertion with written evidence; retirement is a timestamp, '
  'never a delete, so a withdrawn match stays inspectable.';

COMMENT ON COLUMN capacity_claim_matches.evidence IS
  'The written reasoning a reporter would need to defend the match: what '
  'in the claim and what in the planning record connect, and what the '
  'residual doubt is. Required — an unevidenced match is not a match.';

ALTER TABLE capacity_claim_matches DROP CONSTRAINT IF EXISTS capacity_claim_matches_confidence_known;
ALTER TABLE capacity_claim_matches ADD CONSTRAINT capacity_claim_matches_confidence_known
  CHECK (confidence IN ('strong', 'probable', 'tentative'));

-- One live match per claim: a claim names one project, and a project is
-- one site. Superseding a match means retiring the old row first, which
-- keeps the history a sequence of assertions rather than an overwrite.
CREATE UNIQUE INDEX IF NOT EXISTS capacity_claim_matches_one_live
  ON capacity_claim_matches (claim_id) WHERE retired_at IS NULL;

-- And full-row idempotency for batch loaders re-running the same YAML.
CREATE UNIQUE INDEX IF NOT EXISTS capacity_claim_matches_content_key
  ON capacity_claim_matches (claim_id, site_id, method, md5(evidence));

CREATE INDEX IF NOT EXISTS idx_capacity_claim_matches_site
  ON capacity_claim_matches (site_id) WHERE retired_at IS NULL;
