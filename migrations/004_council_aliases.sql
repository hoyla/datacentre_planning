-- Two fixes in one migration:
--
-- 1. `councils.notes` was declared TEXT but `repo.upsert_council` writes
--    `psycopg2.extras.Json` into it, which serialises to a JSON-encoded
--    string. The `_load_area_gss_map` lookup that does `isinstance(notes,
--    dict)` therefore always returned False — meaning the spatial sweep,
--    operator sweep, and parent-backfill all wrote NULL `council_gss`.
--    Convert to JSONB so the JSON path operators work and the loader picks
--    `area_name` out correctly. The existing rows hold well-formed JSON
--    strings, so a `USING notes::JSONB` cast is non-lossy.
--
-- 2. Council reorganisations (Buckinghamshire 2020, North/West Northamptonshire
--    2021) leave applications filed under legacy district names with no
--    matching current council. Joint planning services (e.g. Chiltern South
--    Bucks, Mid Kent) likewise sit under an area_name that doesn't directly
--    match any one GSS. Add a `council_aliases` table that maps a PlanIt
--    `area_name` (or ref-prefix) to a primary current GSS code. Loaded from
--    `data/priors/council_aliases.yaml`; the original `area_name` stays in
--    `applications.raw_metadata` per the never-mutate-originals principle.

ALTER TABLE councils ALTER COLUMN notes TYPE JSONB USING notes::JSONB;

CREATE TABLE council_aliases (
    alias_name    TEXT PRIMARY KEY,        -- the PlanIt area_name as it appears
    gss_code      TEXT NOT NULL REFERENCES councils(gss_code),
    kind          TEXT NOT NULL,           -- 'legacy_district' | 'joint_planning' | 'predecessor'
    notes         TEXT,                    -- short prose: why this mapping
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_council_aliases_gss ON council_aliases(gss_code);
