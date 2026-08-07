-- Per-development power capacity, adjudicated from existing findings.
--
-- The deep-read asked "what power facts appear in this document" and got
-- an honest answer: planning statements are dense with power figures, but
-- most are market context (Savills' European forecast), policy targets
-- (50GW offshore wind), grid statistics (600GW connection queue) or
-- regional demand ("known IT demand in the West London market"). Those are
-- the developer's argument *for* the scheme, not a description of it.
--
-- Sorting sites by their largest MW finding would therefore rank a Slough
-- application as a 30GW site. This table fixes that by recording, per
-- candidate finding, whether the figure describes THIS development — and
-- when it does, which quantity it measures. IT load, grid connection
-- capacity, on-site generation and cooling capacity are different numbers
-- that routinely differ by a factor of two or more for the same site;
-- collapsing them would be its own error.
--
-- Exclusions are recorded, not discarded. "Why doesn't Slough show 30GW?"
-- must have an answer that points at a row, per the defensibility
-- principle. Append-only: a re-adjudication under a new prompt_version
-- adds rows beside the old ones.

CREATE TABLE power_adjudication (
    id               BIGSERIAL PRIMARY KEY,
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    finding_id       BIGINT NOT NULL REFERENCES findings(id),
    document_id      BIGINT REFERENCES documents(id),

    -- What the figure turned out to be about.
    verdict          TEXT NOT NULL,
        -- 'site_capacity'  — describes this development
        -- 'market_context' — market/sector demand or supply statistics
        -- 'policy_target'  — national or regional policy ambition
        -- 'comparator'     — another named site or scheme
        -- 'unclear'        — cannot be attributed from the quote alone

    -- Populated only when verdict = 'site_capacity'.
    quantity_type    TEXT,
        -- 'it_load' | 'grid_connection' | 'onsite_generation'
        -- | 'cooling' | 'total_site' | 'other'
    value_mw         NUMERIC,   -- normalised; NULL for apparent-power units
    value_original   NUMERIC,
    unit_original    TEXT,
    unit_note        TEXT,      -- e.g. 'MVA is apparent power, not converted'
    is_maximum       BOOLEAN,   -- an ultimate/consented ceiling vs a phase

    reasoning        TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (finding_id, model, prompt_version)
);

CREATE INDEX idx_power_adj_application ON power_adjudication(application_id);
CREATE INDEX idx_power_adj_verdict ON power_adjudication(verdict);
CREATE INDEX idx_power_adj_quantity
    ON power_adjudication(quantity_type, value_mw)
    WHERE verdict = 'site_capacity';
