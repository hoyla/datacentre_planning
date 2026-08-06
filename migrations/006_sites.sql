-- Sites: the derived, site-level unit of the dc_build universe. A site is
-- a cluster of applications and/or Barbour projects joined by explicit
-- links, family edges (associated_id), or spatial proximity (≤1 km).
--
-- Derived data, kept separate from `projects` deliberately: `projects`
-- holds Barbour's records verbatim (raw stays canonical); clustering is
-- our inference and lives here, recomputable at any time. `site_key` is
-- the stable public identity that spreadsheets, annotations, reports and
-- releases reference: 'PTNO-<n>' for Barbour-anchored sites (lowest Ptno
-- in the cluster), 'SITE-<application_ref>' otherwise (alphabetically
-- first application in the cluster). Re-materialisation updates
-- membership but never reuses a site_key for a different site.

CREATE TABLE sites (
    id               BIGSERIAL PRIMARY KEY,
    site_key         TEXT NOT NULL UNIQUE,
    classification   TEXT NOT NULL,   -- 'both' | 'ours_only' | 'barbour_covered' | 'barbour_only' | 'unlocatable'
    display_name     TEXT,            -- best available human label (Barbour title, else lead application address/description)
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    coord_source     TEXT,            -- 'application' | 'barbour' | 'inferred_prior' | NULL
    radius_km        DOUBLE PRECISION NOT NULL,  -- clustering radius used
    materialised_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at       TIMESTAMPTZ      -- set when a re-run no longer produces this site (merged/split); rows are never deleted
);

CREATE TABLE site_members (
    id               BIGSERIAL PRIMARY KEY,
    site_id          BIGINT NOT NULL REFERENCES sites(id),
    application_id   BIGINT REFERENCES applications(id),
    project_id       BIGINT REFERENCES projects(id),
    joined_via       TEXT NOT NULL,   -- 'project_link' | 'family' | 'spatial' | 'singleton'
    materialised_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at       TIMESTAMPTZ,
    CHECK (application_id IS NOT NULL OR project_id IS NOT NULL)
);

-- NULLs are distinct under a plain UNIQUE constraint, so enforce
-- one-membership-per-node with partial unique indexes instead.
CREATE UNIQUE INDEX uq_site_members_app ON site_members(site_id, application_id)
    WHERE application_id IS NOT NULL;
CREATE UNIQUE INDEX uq_site_members_project ON site_members(site_id, project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX idx_site_members_site ON site_members(site_id);
CREATE INDEX idx_site_members_application ON site_members(application_id);
CREATE INDEX idx_site_members_project ON site_members(project_id);
