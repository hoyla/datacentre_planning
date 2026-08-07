-- Deep-read bookkeeping: one row per (document, model, prompt_version)
-- attempt, including the documents deliberately not read (graphical skips,
-- sampled-out objection letters). The coverage statement in the
-- methodology — "we read these pages, in these documents, and sampled
-- these others" — is a query over this table, not a claim.
--
-- Append-only across prompt versions: a re-run with a revised prompt adds
-- rows under the new version and leaves the old audit trail intact.

CREATE TABLE deepread_log (
    id                BIGSERIAL PRIMARY KEY,
    document_id       BIGINT NOT NULL REFERENCES documents(id),
    application_id    BIGINT NOT NULL REFERENCES applications(id),
    model             TEXT NOT NULL,
    prompt_version    TEXT NOT NULL,
    tier              TEXT NOT NULL,        -- 'A' | 'B' | 'C' | 'skip'
    read_state        TEXT NOT NULL,        -- 'read' | 'skipped_graphical' | 'sampled_out' | 'no_text' | 'parse_failed'
    pages_total       INT,
    pages_sent        INT[],                -- 1-based physical page numbers sent to the model
    findings_inserted INT NOT NULL DEFAULT 0,
    quotes_failed     INT NOT NULL DEFAULT 0,  -- extracted but failed the verbatim gate; in the escalation queue
    elapsed_s         REAL,
    completed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, model, prompt_version)
);

CREATE INDEX idx_deepread_log_application ON deepread_log(application_id);
CREATE INDEX idx_deepread_log_state ON deepread_log(read_state);
