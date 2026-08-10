-- Make re-deriving a finding different from re-inserting it.
--
-- The findings table had no idempotency: the runner committed findings
-- chunk by chunk and wrote the deepread_log row afterwards, on a
-- separate commit. A document whose run died between the two — or whose
-- parse_failed retry re-read chunks that had already landed — was
-- re-offered by the cohort query and re-inserted everything it had
-- already stored. Measured on 2026-08-10: 20,377 rows were exact
-- duplicates of an earlier row in every content column, 5.6% of the
-- published findings count. 1,504 documents were affected, almost all
-- on the local-model run, with the copies landing hours apart — the
-- signature of restarts, not of versioned re-reads.
--
-- Three changes, one contract:
--
-- 1. `prompt_version` joins the row. The deepread_log has carried it
--    since migration 007; findings did not, so a finding could not name
--    the prompt that produced it. Every deep-read to date ran under
--    prompt 1.0 (the log confirms no other version exists), so the two
--    deep-read models backfill to '1.0'. The v1 read-tool rows predate
--    prompt versioning and stay NULL — that is a fact, not a gap.
--
-- 2. The exact duplicates move to an archive table rather than being
--    deleted outright. The append-only rule protects interpretations;
--    a second identical copy of the same interpretation is not a second
--    interpretation, but the archive keeps the repair auditable and
--    reversible. Rows that share a quote but differ in any value column
--    (7,771 of them) are NOT touched: same evidence, different reading
--    — those are for adjudication, not cleanup.
--
-- 3. A unique index over the content columns makes the database refuse
--    what the code used to permit. The text columns enter as md5() —
--    evidence quotes run to 2,676 characters, past what a btree row can
--    hold. NULLS NOT DISTINCT because two absent units are the same
--    absent unit. Writers insert with ON CONFLICT DO NOTHING against
--    this key, so a re-run is a no-op on unchanged content — which is
--    what principle 5 promised all along.

BEGIN;

ALTER TABLE findings ADD COLUMN prompt_version TEXT;

UPDATE findings
   SET prompt_version = '1.0'
 WHERE model IN ('claude-sonnet-5', 'mlx:Qwen3.6-35B-A3B-4bit');

CREATE TABLE findings_removed_duplicates (
    LIKE findings,
    removed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason      TEXT        NOT NULL
);

WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY application_id, document_id, model,
                            prompt_version, signal_type, value_text,
                            value_number, value_unit, evidence_text,
                            evidence_page
               ORDER BY id) AS rn
    FROM findings
),
surplus AS (
    SELECT id FROM ranked WHERE rn > 1
)
INSERT INTO findings_removed_duplicates
SELECT f.*, now(),
       'exact duplicate of an earlier row in every content column; '
       'inserted by a re-run before migration 012 made findings '
       'idempotent'
FROM findings f
JOIN surplus s ON s.id = f.id;

DELETE FROM findings f
 USING findings_removed_duplicates d
 WHERE f.id = d.id;

-- The earliest copy survives (ORDER BY id): it is the original read,
-- with the timestamp closest to when the document was actually seen.

CREATE UNIQUE INDEX findings_content_key
    ON findings (application_id, document_id, model, prompt_version,
                 signal_type, md5(value_text), value_number, value_unit,
                 md5(evidence_text), evidence_page)
    NULLS NOT DISTINCT;

COMMIT;
