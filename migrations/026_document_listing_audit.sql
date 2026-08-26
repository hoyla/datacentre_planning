-- What the register offered, beside what we stored.
--
-- A fetch that retrieved some of an application's documents used to be
-- recorded as complete. `fetch_outstanding.py` has caught that since the
-- `partial` outcome landed — it compares `links_found` against what
-- arrived and re-queues the shortfall — but only for fetches run after
-- it. Everything collected before is unmeasurable from what we kept:
-- `_manifest.json` and the `documents` table both record what was
-- *stored*, and neither records what was *offered*. An application that
-- lost 300 of its 375 documents to a rate-limit cascade in June looks,
-- from every artefact we publish, like an application with 50 documents.
--
-- Per-site document counts are reporter-facing (the reader shows them on
-- every site page), so the roadmap puts this before anyone quotes one.
--
-- This table holds the comparison. One row per (application, listing
-- source, listing content): what the register listed, what we hold, and
-- the set difference between them — with the listing's own URL, hash and
-- capture time so the number can be walked back to the page it came from.
--
-- **It records a measurement, not a repair.** Nothing here downloads
-- anything or touches `documents`; the deliverable is a prioritised list
-- a human decides to act on. Per principle 3 the original records are
-- untouched, and per principle 4 a re-list adds a row rather than
-- replacing one — a register that has grown since the last check is a
-- fact worth keeping both halves of.
--
-- Two listing sources, deliberately distinguished:
--
--   snapshot — the documents-tab HTML already in `source_snapshots`,
--              captured by the fetch run itself before it started
--              downloading. Costs no portal traffic at all, and is the
--              exact page the short fetch was working from, which makes
--              it the sharpest available evidence of a short fetch.
--   live     — re-listed now. Catches applications with no snapshot, and
--              documents the register has published since. A live
--              listing also writes its body to `source_snapshots`, so
--              the audit's evidence is preserved on the same terms as
--              every other fetch.
--   harvest  — a browser-harvested listing held on disk (Salesforce
--              registers, which refuse scripted listing).
--
-- Idempotency follows `source_snapshots`: the content key is the hash of
-- the listing body, so re-auditing an unchanged page is a no-op. Rows
-- that carry no listing (skips, errors, portals with no adapter) hash
-- their status and detail instead, so a re-run does not accumulate
-- copies of the same refusal.

CREATE TABLE IF NOT EXISTS document_listing_audit (
    id                     BIGSERIAL PRIMARY KEY,
    application_id         BIGINT      NOT NULL REFERENCES applications(id),

    adapter                TEXT        NOT NULL,
        -- Which listing code path answered: idox | ocella | agile |
        -- arcus | aifusion | salesforce_pr, or the portal family we have
        -- no listing path for.

    listing_source         TEXT        NOT NULL,   -- snapshot | live | harvest | none
    listing_url            TEXT,                   -- the page or endpoint asked for
    listing_sha256         TEXT,                   -- hash of the listing body used
    listing_captured_at    TIMESTAMPTZ,            -- when that body was captured

    status                 TEXT        NOT NULL,
        -- audited          - a listing was obtained and compared
        -- empty_listing    - listing obtained, offered nothing (a real
        --                    fact about the register, not a failure)
        -- withdrawn        - portal answers "no longer available for viewing"
        -- host_skipped     - host deliberately not touched (see detail)
        -- no_adapter       - no listing-only path for this portal type
        -- no_listing       - adapter exists, no listing available (e.g. a
        --                    Salesforce register with nothing harvested)
        -- rate_limited     - portal throttled us; retry later
        -- error            - transient or unknown failure

    detail                 TEXT,

    offered_count          INTEGER,    -- documents the register listed
    stored_count           INTEGER,    -- documents rows we hold for this application
    matched_count          INTEGER,    -- offered documents we hold
    missing_count          INTEGER,    -- offered_count - matched_count (the shortfall)
    unmatched_stored_count INTEGER,    -- held but not in this listing (see below)

    -- The full offered set, and the subset we do not hold. Provenance,
    -- not convenience: a shortfall of 325 is a claim about 325 specific
    -- URLs, and the refetch pass reads them from here rather than
    -- re-listing everything a second time.
    offered                JSONB,
    missing                JSONB,

    content_key            TEXT        NOT NULL,
    tool                   TEXT        NOT NULL,   -- what produced the row
    checked_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `unmatched_stored_count` is diagnostic, not a defect count. A document
-- we hold that the current listing does not offer usually means the
-- register withdrew or re-published it, or that the portal changed its
-- URL scheme under us (Wiltshire moved /pr/ to /pr3/). It is recorded so
-- a large value can be read as "the URL join broke" rather than silently
-- inflating the shortfall.

CREATE UNIQUE INDEX IF NOT EXISTS document_listing_audit_content_key
    ON document_listing_audit (application_id, listing_source, content_key);

CREATE INDEX IF NOT EXISTS document_listing_audit_missing_idx
    ON document_listing_audit (missing_count DESC)
    WHERE missing_count > 0;

-- Current state: the newest audit per application, by insertion order —
-- matching `application_acquisition`, where a backdated correction must
-- not lose to the wrong row it was written to correct.
CREATE OR REPLACE VIEW document_listing_audit_current AS
SELECT a.id                       AS application_id,
       a.application_ref,
       l.adapter,
       l.listing_source,
       l.status,
       l.detail,
       l.offered_count,
       l.stored_count,
       l.matched_count,
       l.missing_count,
       l.unmatched_stored_count,
       l.listing_url,
       l.listing_captured_at,
       l.checked_at
FROM applications a
JOIN LATERAL (
    SELECT * FROM document_listing_audit la
    WHERE la.application_id = a.id
    ORDER BY la.id DESC LIMIT 1) l ON true;
