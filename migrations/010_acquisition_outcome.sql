-- What happened when we last tried to obtain an application's documents.
--
-- Without this, "no documents" is one state covering two very different
-- facts: material we have not yet gone after, and material a portal has
-- told us does not exist. The second is finished work — 85 applications
-- were fetched successfully and the register returned nothing, which is
-- a disclosure fact about the application, not a gap in ours. Recomputing
-- that from a campaign log means it is lost the moment the log rotates,
-- and those applications drift back into the queue for ever.
--
-- Append-only: each attempt adds a row, and the latest by application is
-- the current state. Re-running an adapter therefore records that it was
-- re-checked rather than overwriting what happened before.
CREATE TABLE IF NOT EXISTS acquisition_outcome (
    id             bigserial PRIMARY KEY,
    application_id bigint      NOT NULL REFERENCES applications(id),
    outcome        text        NOT NULL,   -- see below
    adapter        text,                   -- which fetcher reached the verdict
    detail         text,
    documents_found integer    NOT NULL DEFAULT 0,
    checked_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN acquisition_outcome.outcome IS
  'fetched            - documents obtained
   none_published     - portal reached, register holds no documents
   portal_blocked     - portal refuses automated access
   login_required     - register entry is not public
   no_adapter         - portal type we cannot yet read
   error              - attempt failed for a transient or unknown reason';

CREATE INDEX IF NOT EXISTS acquisition_outcome_app_idx
    ON acquisition_outcome (application_id, checked_at DESC);

-- One row per application: what we last saw, and when we last looked.
--
-- Holding a document is itself proof we looked, so the view falls back to
-- the newest document's fetch time where no outcome row exists. That
-- matters for the councils harvested through a browser, which never went
-- through the campaign that writes these rows.
--
-- Current state follows insertion order, not checked_at: a correction
-- stamped with the moment a check really happened must not lose to a
-- later-written but wrong row. checked_at answers 'how stale is this',
-- id answers 'what do we currently believe'.
--
-- 'last_checked_at' rather than 'last_fetched_at' is the field to plan
-- revisits from: an application whose register held nothing in March may
-- hold an Environmental Statement by August, and what we need to know is
-- how stale our knowledge is, not when we last succeeded.
CREATE OR REPLACE VIEW application_acquisition AS
SELECT a.id                                        AS application_id,
       a.application_ref,
       o.outcome                                   AS last_outcome,
       greatest(o.checked_at, d.newest_doc)        AS last_checked_at,
       d.newest_doc                                AS last_fetched_at,
       coalesce(d.n, 0)                            AS documents_held,
       o.adapter                                   AS last_adapter,
       o.detail                                    AS last_detail
FROM applications a
LEFT JOIN LATERAL (
    SELECT outcome, checked_at, adapter, detail
    FROM acquisition_outcome ao
    WHERE ao.application_id = a.id
    ORDER BY ao.id DESC LIMIT 1) o ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS n, max(fetched_at) AS newest_doc
    FROM documents dd WHERE dd.application_id = a.id) d ON true;
