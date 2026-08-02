-- Construction-project records from commercial construction-intelligence
-- sources (currently Barbour ABI; licensed, credited in published output).
--
-- A *project* is the provider's unit of record — a construction scheme that
-- may map to zero, one, or several planning applications (one campus →
-- outline + reserved matters + variations of conditions), so applications
-- link via a separate many-to-many table rather than a column.
--
-- Principle 3: the provider's row is stored verbatim in raw_metadata;
-- promoted columns are query conveniences, never corrections. Stale provider
-- values (e.g. dead portal links — observed for Harlow / Havering / Slough)
-- stay as supplied; any re-resolved URL belongs on the linked application
-- row, not an overwrite here.

CREATE TABLE projects (
    id               BIGSERIAL PRIMARY KEY,
    source_id        INT NOT NULL REFERENCES sources(id),
    external_ref     TEXT NOT NULL,          -- provider's project id (Barbour 'Ptno')
    title            TEXT,
    stage_summary    TEXT,                   -- 'Pre Planning' | 'Planning and Not yet Started' | 'Under Construction' | 'Built' ...
    dev_type         TEXT,                   -- 'New Build' | 'Fit-out' | 'Extn' | ...
    description      TEXT,                   -- Barbour 'Details'
    address          TEXT,                   -- Site1..Site4 joined
    postcode         TEXT,
    longitude        DOUBLE PRECISION,
    latitude         DOUBLE PRECISION,
    value_gbp        NUMERIC,                -- Barbour 'Value'
    floor_area       NUMERIC,                -- as supplied; Barbour doesn't state units
    site_area        NUMERIC,                -- as supplied; Barbour doesn't state units
    authority_name   TEXT,                   -- provider's authority string, verbatim
    planning_ref     TEXT,                   -- provider's planning reference, verbatim (bare — no council prefix)
    planning_link    TEXT,                   -- provider's portal URL (hint only; link rot observed)
    plan_date        DATE,
    decision_date    DATE,
    start_date       DATE,
    completion_date  DATE,
    url              TEXT,                   -- provider's own project page (Barbour_ABI_link)
    raw_metadata     JSONB,                  -- the full source row, verbatim
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_ref)
);

CREATE INDEX idx_projects_planning_ref ON projects(planning_ref);
CREATE INDEX idx_projects_stage ON projects(stage_summary);

-- Which applications realise which projects. Populated by the adapter's
-- ref-matching pass (match_method records how each link was made) and by
-- manual curation. A project with no rows here is either pre-application
-- (nothing to link yet) or awaiting portal/PlanIt resolution. Ambiguous
-- ref matches (same bare ref in two councils) are never auto-linked.
CREATE TABLE project_applications (
    id               BIGSERIAL PRIMARY KEY,
    project_id       BIGINT NOT NULL REFERENCES projects(id),
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    match_method     TEXT NOT NULL,          -- 'ref_suffix' | 'ref_normalised' | 'manual' | ...
    matched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, application_id)
);

CREATE INDEX idx_project_applications_project ON project_applications(project_id);
CREATE INDEX idx_project_applications_application ON project_applications(application_id);
