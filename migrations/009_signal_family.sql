-- Canonical family alongside each finding's free-form signal_type.
--
-- The extraction prompt asks the model to name what it found in its own
-- words. That is right for extraction — `generator_testing_hours` says
-- more than a flat category would — but v1.0 asked for nothing else, and
-- the corpus ended up with 54,044 distinct labels across 346,653
-- findings, 42,384 of them appearing once or twice. The findings are
-- sound; the index was unusable.
--
-- signal_type is NOT touched: it stays exactly as the model emitted it,
-- per the principle that inferred values sit beside raw ones rather than
-- replacing them. This column is the index over it.
--
-- Two ways it gets populated, and family_source records which:
--   'derived'      - mapped from signal_type by dcp/signal_families.py.
--                    How the v1.0 corpus is classified, after the fact.
--   'model'        - supplied directly by the model under prompt v2.0,
--                    where the family is a controlled enum in the
--                    structured-output schema and cannot fragment.
--   'derived_fallback' - the model gave a family outside the vocabulary
--                    (possible only on the local path, which has no
--                    schema enforcement), so the label was mapped instead.
--
-- Keeping the provenance matters: a family the model chose while reading
-- the document carries more weight than one a regex inferred from a label
-- afterwards, and a reader comparing the two should be able to tell.

ALTER TABLE findings ADD COLUMN signal_family TEXT;
ALTER TABLE findings ADD COLUMN family_source TEXT;

CREATE INDEX idx_findings_family ON findings(signal_family);

COMMENT ON COLUMN findings.signal_family IS
    'Canonical family; see dcp/signal_families.py. Derived from '
    'signal_type for prompt v1.0, model-supplied under v2.0.';
COMMENT ON COLUMN findings.family_source IS
    'derived | model | derived_fallback — how signal_family was obtained.';
