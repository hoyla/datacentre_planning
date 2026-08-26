-- A refusal page is not an empty register.
--
-- Migration 026 gave `document_listing_audit` the status
-- `empty_listing`, meaning "the listing was obtained and offered
-- nothing — a real fact about the register, not a failure". Two kinds of
-- body reached that status without being a listing at all:
--
--   * Idox serves "Permission Denied — You do not have permission to
--     view the page" with **HTTP 200** and the council's full site
--     chrome. Nothing in the response distinguishes it from a documents
--     tab: the status code is a success, the length is ordinary, and the
--     listing parser finds no links in it, exactly as it would in a
--     register that genuinely publishes nothing. 66 of the 107
--     snapshot-sourced `empty_listing` rows in the store were this page.
--   * Three Brighton snapshots are 212-byte bodies stored with a 200 —
--     no content whatsoever, which likewise parses to zero documents.
--
-- Both were recorded as measured zeroes. That is the mistake HISTORY
-- keeps re-filing under new names ("An empty result is not a null
-- finding"; "'Nobody looked' must never be stored as 'nothing there'"),
-- and it is the same mistake `dcp/acquisition_outcome.py` was written to
-- refuse in the acquisition path — arriving here by the other door. Not
-- a failure miscounted as a success, but a refusal parsed as a fact.
--
-- So the vocabulary gains one value:
--
--   blocked — the portal answered, and what it answered was not a
--             listing. The register is UNMEASURED. It must never be
--             counted as a register that publishes nothing, and it must
--             never settle an application.
--
-- `dcp/relist_audit.py` detects it from the pages' own words and from a
-- body-length floor of 1,000 bytes (the smallest listing in the corpus
-- that offered even one document is 7,192 bytes, so the floor cannot
-- catch a real one).
--
-- Nothing is rewritten. Per principle 4 the corrected reading is
-- appended: a `blocked` row's content key is the body hash prefixed with
-- its status, so it lands beside the `empty_listing` row that read the
-- same body and supersedes it by insertion order, with both halves of
-- the history intact. Re-running the snapshot pass with `--recheck`
-- appends the corrections and no-ops on everything else.

COMMENT ON COLUMN document_listing_audit.status IS
  'audited | empty_listing | blocked | withdrawn | host_skipped | '
  'no_adapter | no_listing | rate_limited | error. Only `audited` and '
  '`empty_listing` are measurements of a register. `blocked` means the '
  'portal answered with something that is not a listing (an HTTP 200 '
  'refusal page, or a body too short to be one) and the register is '
  'unmeasured — it must not be read as a register that publishes '
  'nothing.';

-- Finding the corrected rows, and the superseded readings behind them.
CREATE INDEX IF NOT EXISTS document_listing_audit_status_idx
    ON document_listing_audit (status);
