-- 1. Track *how* we found each application — DC-keyword sweep, operator-name
--    sweep, spatial proximity, etc. Multiple discovery paths are common
--    (e.g. a Greystoke application surfaces both in the DC sweep and the
--    operator sweep); the upsert appends rather than overwrites.

ALTER TABLE applications ADD COLUMN discovered_via TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
CREATE INDEX idx_applications_discovered_via ON applications USING gin (discovered_via);

-- 2. Co-located candidate links produced by spatial sweep. An anchor DC
--    application points to a candidate application within radius_used_km
--    that matched at least one energy-generation keyword. distance_m is
--    computed at insert time from the two lat/lng pairs.

CREATE TABLE colocated_candidates (
    id                BIGSERIAL PRIMARY KEY,
    anchor_app_id     BIGINT NOT NULL REFERENCES applications(id),
    candidate_app_id  BIGINT NOT NULL REFERENCES applications(id),
    distance_m        REAL,
    radius_used_km    REAL NOT NULL,
    keyword_hits      TEXT[] NOT NULL,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (anchor_app_id, candidate_app_id, radius_used_km),
    CHECK (anchor_app_id <> candidate_app_id)
);

CREATE INDEX idx_colocated_anchor ON colocated_candidates(anchor_app_id);
CREATE INDEX idx_colocated_candidate ON colocated_candidates(candidate_app_id);
CREATE INDEX idx_colocated_keyword_hits ON colocated_candidates USING gin (keyword_hits);
