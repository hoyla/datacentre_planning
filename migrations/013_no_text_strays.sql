-- The rows migration 011 could not see.
--
-- 011 relabelled "nobody looked" rows from `no_text` to `not_extracted`,
-- keyed on `pages_total IS NULL` — the missing-cache branch never
-- recorded a page count. But there was a third branch wearing the same
-- costume: a cache written by an extractor that had no loader for the
-- format. Those caches exist and hold zero pages, so the runner logged
-- them as `no_text` with `pages_total = 0` — not NULL — and 011's
-- predicate passed over them. 227 rows, and among them the Outlook
-- consultee responses and Word supporting statements the format loaders
-- were added for.
--
-- `no_text` is a settled state the cohort query never revisits, so
-- without this relabel those documents stay unread forever: the loaders
-- exist, the re-extraction pass will rebuild their caches, and the
-- cohort would still never offer them.
--
-- Relabelling is safe for any row genuinely empty: `not_extracted`
-- re-enters the cohort, the fixed extractor re-reads the document, and
-- one that truly holds no words settles back as `no_text` — this time
-- with an honest page count. Updated in place for the same reason as
-- 011: this is a processing record that stated the wrong reason, not an
-- interpretation.

BEGIN;

UPDATE deepread_log
   SET read_state = 'not_extracted'
 WHERE read_state = 'no_text'
   AND pages_total = 0;

COMMIT;
