-- Which gate admitted a finding is part of how that finding came to exist.
--
-- `findings` records the model that read the document and the prompt
-- version it read under. It does not record the gate the extracted quote
-- had to pass to be stored at all — and the gate is not a detail. It is
-- the project's hallucination protection: a quote that does not appear
-- in the cached page text is refused, and the finding with it.
--
-- `site_machine_readings` already carries `gate_version` for exactly this
-- reason, and `_already()` keys on it, so a reading knows which gate
-- admitted it. Findings have had no equivalent, with two consequences.
--
-- ## The gate has changed and the data cannot show it
--
-- On 2026-08-31 the gate gained a whitespace-blind fallback behind a
-- 25-character guard, because pypdf breaks words mid-token — a page
-- reads "d ata centres" or "940 µ g/m 3" — and a model that copies the
-- passage correctly then failed a comparison against the broken text.
-- Measured over every rejection with cached page text, 68.8% were
-- genuinely absent and 29.8% appeared once whitespace was ignored.
--
-- Every finding stored before that change passed a stricter gate than
-- every finding stored after it, and nothing in the table says so.
--
-- ## And 15,042 findings are about to be reinstated
--
-- The rejected quotes were never discarded: `data/deepread_escalations.
-- jsonl` keeps each one beside its document, page and the whole finding
-- payload. Re-gating them offline recovers 15,042, of which 416 carry a
-- numeric value with a power unit.
--
-- Those rows carry the model and prompt version of the read that
-- produced them, recovered from `deepread_log` — which is true, and is
-- what keeps them deduplicable, since both columns sit in the
-- `findings_content_key` index. A synthetic `regate/<reader>` model tag
-- would assert a model that never read the document AND make the row
-- permanently un-deduplicable against a genuine re-read of the same
-- document, which is how 20,377 duplicates happened before that index
-- existed.
--
-- So the cohort needs to be separable on something other than the model,
-- and this is that something. NULL means "admitted before the gate was
-- versioned" — which is every row already stored, and is honest: we do
-- not know which of the pre-2026-08-31 gates admitted them, only that it
-- was stricter than the current one.
--
-- Deliberately not backfilled. A backfill would have to guess a gate
-- version from `inserted_at` against a history nothing recorded, and a
-- guessed provenance is worse than an absent one.

ALTER TABLE findings ADD COLUMN IF NOT EXISTS gate_version TEXT;

COMMENT ON COLUMN findings.gate_version IS
  'The quote gate that admitted this finding. NULL for rows stored '
  'before the gate was versioned (2026-08-31); not backfilled, because '
  'the gate in force at an earlier insert was never recorded and a '
  'guessed value would be worse than an absent one.';

-- The content key is untouched on purpose. `gate_version` must NOT join
-- it: the same finding re-gated under a later gate is the same finding,
-- and adding this column to the key would let one row become several as
-- the gate is revised.
