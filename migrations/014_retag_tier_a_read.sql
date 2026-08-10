-- The tier A read, tagged with the model but not its configuration.
--
-- The first bulk OpenAI batch — 4,417 tier A documents, 10,314 requests
-- — was submitted from code that stamps reasoning effort into the model
-- tag, because effort changes what the model does, not just what it
-- costs: at default effort gpt-5 answered nothing at all on 29% of
-- requests; at low effort it out-yields every other reader. Two
-- configurations of one model are two readers, and an append-only
-- findings store must keep them apart.
--
-- The batch was *collected* by the older code on main, after a branch
-- switch for unrelated documentation work left the working tree holding
-- the version without effort tagging. Main's collector — carrying the
-- conflict guard and prompt_version from migration 012 — stored
-- everything correctly except the tag: 122,235 findings and 4,417 log
-- rows say `openai:gpt-5` where the batch state records that the run
-- was `reasoning_effort: low`.
--
-- The two populations are exactly separable without touching a
-- timestamp: every document in the 60-document validation set (whose
-- default-effort rows are correctly tagged `openai:gpt-5`) also carries
-- an `openai:gpt-5:minimal` log row from the minimal-effort run over
-- the same documents; no tier A document does, because the tier A
-- cohort was selected to exclude documents the OpenAI path had already
-- read. Verified before writing this: 692 vs 122,235 findings, 60 vs
-- 4,417 log rows.
--
-- Updated in place for the reason 011 and 013 were: this is a
-- processing record that stated the wrong label, not an interpretation.
-- The batch state file (data/deepread_batches_openai/) remains the
-- provenance for what the run's configuration actually was.

BEGIN;

UPDATE findings
   SET model = 'openai:gpt-5:low'
 WHERE model = 'openai:gpt-5'
   AND document_id NOT IN (SELECT document_id FROM deepread_log
                           WHERE model = 'openai:gpt-5:minimal');

UPDATE deepread_log
   SET model = 'openai:gpt-5:low'
 WHERE model = 'openai:gpt-5'
   AND document_id NOT IN (SELECT document_id FROM deepread_log
                           WHERE model = 'openai:gpt-5:minimal');

COMMIT;
