-- What a generation figure is a figure of, and what kind of plant makes it.
--
-- READER_REDESIGN_PLAN §4.1e. power_adjudication settled whether a figure
-- describes THIS development and which quantity it measures; it never
-- asked the two questions a reader needs before a generation number means
-- anything. "3.2 MW" above "112 units" is one engine, not a site; "50 MW"
-- at Elsham Wolds is twenty gas engines that run continuously, and the
-- same application discloses up to 650 back-up diesels that are a
-- different kind of plant entirely. Sorting, cohorting or summing across
-- those without the distinction compares a gas power station with a
-- machine that runs twelve hours a year.
--
-- Kept in its own table rather than as more columns on power_adjudication:
-- that table's rows are keyed (finding_id, model, prompt_version) under a
-- prompt that does not ask these questions, and 3,974 of them were stored
-- under power-1.0. A second question about the same finding is a second
-- row in a second table, not a widening of the first.
--
-- The vocabulary is the one the sample was hand-checked against
-- (scripts/adjudicate_power.py, GENERATION_SCHEMA). Both values of the
-- "subtotal" pair are kept — installation_total reads better on a row
-- than stated_group_total where no count is stated — while the scorer,
-- the rollup and the cohorts treat them as one family (Luke, 2026-08-23:
-- "the significance of the two is the same").
--
-- Append-only and idempotent, the same contract as power_adjudication: a
-- re-run under a new prompt_version adds rows beside the old ones, and a
-- re-run under the same one is a no-op. The evidence span is stored with
-- the verdict of the check that it was verbatim in the passage the model
-- was shown, so a row that rests on a span the model invented is visible
-- as such rather than indistinguishable from one that does not.

CREATE TABLE generation_adjudication (
    id               BIGSERIAL PRIMARY KEY,
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    finding_id       BIGINT NOT NULL REFERENCES findings(id),
    document_id      BIGINT REFERENCES documents(id),

    -- 1. What is this figure a figure of?
    figure_basis     TEXT NOT NULL,
        -- 'per_generator'      — the rating of ONE machine
        -- 'stated_group_total' — the combined rating of a STATED count
        -- 'installation_total' — the rated total of one named installation
        -- 'site_total'         — the whole development's generation
        -- 'not_generation'     — thermal, fuel, annual energy, storage
        -- 'unclear'            — the passage does not settle it

    -- 2. What kind of plant is it?
    plant_type       TEXT NOT NULL,
        -- 'standby_combustion' | 'prime_combustion' | 'renewable'
        -- | 'storage' | 'mixed' | 'unclear'

    -- Reported only where the passage states them; never computed from
    -- each other, and never multiplied together.
    unit_count       INT,
    unit_rating_mw   NUMERIC,

    -- The shortest run of the passage that decides the two questions,
    -- and whether it was found verbatim in the passage the model was
    -- shown. Both are stored: a false here is evidence about the model.
    evidence_span    TEXT NOT NULL,
    span_verified    BOOLEAN NOT NULL,

    reasoning        TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (finding_id, model, prompt_version)
);

CREATE INDEX idx_generation_adj_application
    ON generation_adjudication(application_id);
CREATE INDEX idx_generation_adj_basis
    ON generation_adjudication(figure_basis, plant_type);
