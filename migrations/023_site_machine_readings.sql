-- A machine's reading of one site's documents, kept apart from the facts.
--
-- READER_REDESIGN_PLAN §7b. Everything else in this database is either
-- a source record or an adjudication of one: a finding is a quote with
-- a label, a power_adjudication row is a verdict on a finding. This
-- table is the first thing that is prose — a model's account of what a
-- site's tier-A documents say about its scale, power, generation and
-- who is behind it; the questions those documents raise and who could
-- answer them; and what could not be determined.
--
-- It is kept apart on purpose. The reader renders it collapsed and
-- labelled as what it is; the workbook and the DuckDB do not export it
-- (§3.2: no machine-generated interpretation in the granular artefacts).
-- Every figure in the text had to carry a verbatim quote that verified
-- against the cached text of the document it cites before the row was
-- written — the same gate the findings pass — and a reading that failed
-- is stored WITHHELD with the reason, never rendered, so that the
-- refusal is a row a person can read rather than a silence.
--
-- Append-only and idempotent: (site_key, model, prompt_version,
-- input_hash, gate_version) is unique. input_hash is over everything the
-- model was shown, so a site whose inputs have not changed is not
-- re-read, and a site whose inputs have changed gets a new row beside
-- the old one. gate_version is in the key because the gate is a
-- judgement too: a reading refused under one gate and accepted under a
-- stricter or a fairer one is two rows, not an overwrite, and the model's
-- answer is kept on disk so re-gating never costs a second call. A build
-- takes the latest non-withheld row per site.

CREATE TABLE site_machine_readings (
    id               BIGSERIAL PRIMARY KEY,
    site_key         TEXT NOT NULL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    input_hash       TEXT NOT NULL,     -- sha256 over the rendered input
    gate_version     TEXT NOT NULL,     -- dcp.machine_reading.GATE_VERSION
    -- What the model was shown, summarised so a reader of the row can
    -- see the reading's footing without re-deriving it.
    documents_read   INT NOT NULL,      -- documents whose pages were sent
    pages_read       INT NOT NULL,
    input_chars      INT NOT NULL,
    -- The reading, as structured JSON: three sections, each a list of
    -- paragraphs, each paragraph carrying the quotes it rests on.
    reading          JSONB,
    -- Set when the gate refused the reading. reading is kept so the
    -- refusal can be examined; it is never rendered.
    withheld_reason  TEXT,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_key, model, prompt_version, input_hash, gate_version)
);

CREATE INDEX idx_site_machine_readings_site
    ON site_machine_readings (site_key, inserted_at DESC);
