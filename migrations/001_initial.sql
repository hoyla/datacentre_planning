-- Initial schema.
-- Append-only by default: source_snapshots preserves every fetch; triage and findings are versioned by inserted_at (latest wins).

CREATE TABLE sources (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,   -- 'planit', 'nsip', 'idox:northumberland', ...
    kind         TEXT NOT NULL,          -- 'aggregator' | 'nsip' | 'council'
    base_url     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE councils (
    gss_code     TEXT PRIMARY KEY,       -- ONS GSS code, e.g. 'E07000063'
    name         TEXT NOT NULL,
    portal_kind  TEXT,                   -- 'idox' | 'civica' | 'tascomi' | 'ocella' | 'bespoke'
    base_url     TEXT,
    notes        TEXT
);

-- Append-only audit log of every fetch we make.
-- Same (source, key, content_sha256) triple = no-op; reruns are idempotent.
CREATE TABLE source_snapshots (
    id                BIGSERIAL PRIMARY KEY,
    source_id         INT NOT NULL REFERENCES sources(id),
    key               TEXT NOT NULL,           -- canonical request key (URL or composite)
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_sha256    TEXT NOT NULL,
    raw_bytes_path    TEXT,                    -- relative to DATA_DIR for large bodies
    raw_bytes_inline  BYTEA,                   -- inline for small bodies
    status_code       INT,
    UNIQUE (source_id, key, content_sha256)
);

CREATE INDEX idx_source_snapshots_source_key ON source_snapshots(source_id, key);

CREATE TABLE applications (
    id               BIGSERIAL PRIMARY KEY,
    source_id        INT NOT NULL REFERENCES sources(id),
    application_ref  TEXT NOT NULL,
    council_gss      TEXT REFERENCES councils(gss_code),
    title            TEXT,
    description      TEXT,
    address          TEXT,
    postcode         TEXT,
    date_received    DATE,
    date_decided     DATE,
    status           TEXT,
    url              TEXT,
    raw_metadata     JSONB,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, application_ref)
);

CREATE INDEX idx_applications_council ON applications(council_gss);
CREATE INDEX idx_applications_status ON applications(status);

CREATE TABLE documents (
    id               BIGSERIAL PRIMARY KEY,
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    url              TEXT NOT NULL,
    kind             TEXT,                  -- 'application_form' | 'design_statement' | 'environmental_statement' | 'site_plan' | 'me_specification' | 'other'
    content_sha256   TEXT,
    bytes_path       TEXT,                  -- where the raw doc lives on disk / S3
    text_path        TEXT,                  -- extracted text location
    ocr_used         BOOLEAN DEFAULT FALSE,
    page_count       INT,
    fetched_at       TIMESTAMPTZ,
    UNIQUE (application_id, content_sha256)
);

CREATE INDEX idx_documents_application ON documents(application_id);

-- Append-only versioned triage records. Latest by inserted_at wins.
CREATE TABLE triage (
    id               BIGSERIAL PRIMARY KEY,
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    model            TEXT NOT NULL,         -- 'ollama:llama3.2', 'fake', ...
    verdict          TEXT NOT NULL,         -- 'data_centre' | 'adjacent' | 'unrelated' | 'unknown'
    confidence       REAL,
    est_capacity_mw  REAL,
    notes            TEXT,
    raw_response     JSONB,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_triage_application ON triage(application_id, inserted_at DESC);

-- Append-only versioned structured findings.
-- One row per (application, document, signal_type, extraction_run).
CREATE TABLE findings (
    id               BIGSERIAL PRIMARY KEY,
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    document_id      BIGINT REFERENCES documents(id),
    signal_type      TEXT NOT NULL,         -- 'generator_count' | 'fuel_type' | 'rated_capacity_mw' | 'fuel_storage_hours' | 'green_claim' | 'substation_mention' | ...
    value_text       TEXT,
    value_number     NUMERIC,
    value_unit       TEXT,
    evidence_text    TEXT,                  -- the supporting quote
    evidence_page    INT,
    model            TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_findings_application ON findings(application_id);
CREATE INDEX idx_findings_signal ON findings(signal_type);
