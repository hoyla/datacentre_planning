-- Separate "nobody looked" from "nothing to see".
--
-- The deep-read runner logged `no_text` in two opposite situations: the
-- text cache was missing, meaning the document had never been through
-- the extractor; or the cache existed and held no words. The first is a
-- gap in our processing, the second is a fact about the document, and
-- recording them identically made the gap invisible — the cohort query
-- excludes anything already logged, so those documents were never
-- revisited.
--
-- It mattered. Of 5,073 `no_text` rows, 4,836 were the missing-cache
-- case, and a sample of the supporting statements among them found every
-- one carried a full text layer — thousands of characters in the first
-- few pages, one of them 86 pages long. Supporting Information is where
-- capacity figures live, so these were not marginal documents.
--
-- The two cases are distinguishable after the fact: the missing-cache
-- branch recorded no page count, the empty-layer branch recorded one.
-- That is what this migration keys on.
--
-- Rows are updated rather than deleted. The append-only rule protects
-- *interpretations* — verdicts, findings, classifications — and this is
-- none of those: it is a processing record that stated the wrong reason,
-- and correcting it in place keeps one row per document per model, which
-- is what the unique constraint expects.

BEGIN;

UPDATE deepread_log
   SET read_state = 'not_extracted'
 WHERE read_state = 'no_text'
   AND pages_total IS NULL;

-- Leaves `no_text` meaning exactly one thing from here on: the extractor
-- ran and the document genuinely holds no words. Those stay settled;
-- `not_extracted` re-enters the deep-read cohort once the text exists.

COMMIT;
