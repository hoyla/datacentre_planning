-- Whether a finding's family matches what the finding actually says.
--
-- READER_REDESIGN_PLAN §4.1e, and §7a depends on it: "What the documents
-- say" groups a site's evidence by family, "excluding rows the 2.3 label
-- audit flags". The audit did not exist when 2.6 shipped, which
-- scripts/export_reader.py says in a comment where the exclusion would
-- go, so nothing has been excluded on that ground and the defect the
-- review found is still on the page: Watford's evidence leads with
-- `it_load — Existing tree cover, the enclosed nature of the existing
-- views…`, landscape prose filed under a power family and promoted
-- because it was long.
--
-- The extractor asked a model to name what it found in its own words,
-- which produced 54,044 distinct labels; `signal_family` is the
-- 25-value canonical index over them (dcp/signal_families.py). A label
-- can be wrong at either step — the model's word for it, or the family
-- that word maps into — and neither is visible from the family alone.
-- So this asks a second model one question about the rows a reader
-- actually sees: does the family fit the text?
--
-- **It never touches `signal_type` or `signal_family`.** The extractor's
-- label is the record of what the extractor said, and a project that
-- overwrites the thing it is auditing has audited nothing. The verdict
-- lands here, beside it, and a build reads it or ignores it.
--
-- Append-only and idempotent on (finding_id, model, prompt_version), the
-- same contract as power_adjudication and generation_adjudication: a
-- re-run under a better prompt adds rows beside the old ones.

CREATE TABLE finding_label_audit (
    id               BIGSERIAL PRIMARY KEY,
    finding_id       BIGINT NOT NULL REFERENCES findings(id),

    -- The family the row carried when it was audited. Stored rather than
    -- joined so a verdict stays interpretable after a re-classification:
    -- "does_not_fit" means nothing without the family it did not fit.
    family_audited   TEXT NOT NULL,

    verdict          TEXT NOT NULL,
        -- 'fits'          — the text belongs under this family
        -- 'does_not_fit'  — it belongs under `suggested_family`
        -- 'unclear'       — the text does not settle it; the row stands
        -- 'not_a_finding' — no family would hold it: the extractor's own
        --                   reasoning caught in the quote, an empty form
        --                   field, a job description. Added 2026-08-25,
        --                   from marking the sample: the other three
        --                   assume every row belongs somewhere.

    -- Populated only when verdict = 'does_not_fit'. One of the 25
    -- families. NULL for the other three, including 'not_a_finding',
    -- where the whole point is that no family would hold the row.
    suggested_family TEXT,

    -- The shortest run of the finding's own text that decides it, and
    -- whether it was found there verbatim. A flag that rests on words
    -- the finding does not contain is a flag about nothing.
    evidence_span    TEXT NOT NULL,
    span_verified    BOOLEAN NOT NULL,

    reasoning        TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (finding_id, model, prompt_version)
);

CREATE INDEX idx_label_audit_verdict
    ON finding_label_audit(verdict, family_audited);
