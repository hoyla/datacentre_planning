-- A figure we assemble is not a figure a source states (#248).
--
-- 171 of 10,207 site-capacity figures hold a value that appears in no
-- number of their own quote (scripts/computed_figures.py, 2026-09-10).
-- Most are arithmetic the extractor did on the applicant's own words:
-- "1 x 1.25MWe and 57 x 2.4MWe diesel generators" stored as 138.05 MW,
-- "57 MW from Iver and 50 MW from Laleham" stored as 107. The arithmetic
-- is right. What is wrong is that the page renders each exactly as a
-- figure the document states, with a verbatim quote beneath that does
-- not contain the number, and a reporter checking one finds the
-- components and no total — with no way to tell a disclosure from our
-- multiplication.
--
-- Luke decided on 2026-09-10 that the classes whose operands are in the
-- quote and whose operation is stated (A, a product; B, a sum) become
-- derivation records: the operation, the operands with their units and
-- a derivation version, stored BESIDE the adjudication the way an
-- adjudication sits beside a finding, and rendered on the `w-modelled`
-- rung with the ≈ glyph, distinct from a figure a document states.
-- Existing rows stay untouched — the adjudication's value_mw is still the
-- number the page shows; this table is why the page may show it.
--
-- Append-only, the same contract as power_adjudication: a re-run under
-- the same derivation version is a no-op, and a later version adds rows
-- beside the old ones. A row is keyed to the adjudication rather than to
-- the finding because the value being explained is the adjudication's,
-- and the same finding can carry several adjudications over time.
--
-- The companion guard lives in dcp/derivation.py: from this migration
-- on, an adjudication write whose value appears in no number of its
-- quote is admitted as site_capacity only when it carries a derivation,
-- and is stored as `unclear` otherwise — a stated abstention beats a
-- confident invention.

CREATE TABLE figure_derivations (
    id                  BIGSERIAL PRIMARY KEY,
    adjudication_id     BIGINT NOT NULL REFERENCES power_adjudication(id),
    finding_id          BIGINT NOT NULL REFERENCES findings(id),
    value_mw            NUMERIC NOT NULL,
    -- fleet_sum: every (count × rating) the quote states, summed
    -- product:   two stated numbers multiplied
    -- sum:       stated figures added
    operation           TEXT NOT NULL,
    -- The operands as read, each with its unit, in the order the quote
    -- states them: [{"count": 57, "rating": 2.4, "unit": "MWe"}, ...]
    -- for a fleet; [{"value": 57, "unit": "MW"}, ...] for a sum or a
    -- product. The reading is of the quote as written or as repaired
    -- for the substrate's habits; `reading` says which.
    operands            JSONB NOT NULL,
    -- "1 × 1.25 MWe + 57 × 2.4 MWe = 138.05 MW", for a page or a sheet.
    operands_text       TEXT NOT NULL,
    reading             TEXT NOT NULL,          -- 'as written' | 'repaired'
    derivation_version  TEXT NOT NULL,
    inserted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (adjudication_id, derivation_version)
);

CREATE INDEX figure_derivations_finding_idx ON figure_derivations (finding_id);

COMMENT ON TABLE figure_derivations IS
  'Why a site-capacity figure may be shown when no number in its quote '
  'states it: the operation and operands, read from the quote, that reach '
  'the adjudicated value. Append-only; one row per adjudication per '
  'derivation version. A figure with a row here renders on the modelled '
  'rung with the ≈ glyph.';
