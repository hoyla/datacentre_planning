-- The column header a transcribed cell sits under, and the wider
-- uniqueness that splitting cells makes necessary.
--
-- The pilot (drawings-pilot-1.0) read FG Wilson's generator output
-- ratings table and returned one item per ROW: `kVA 135 150`, with a
-- free-text note saying the two numbers "appear under Prime and
-- Standby respectively". Prime and standby are different quantities --
-- a continuous rating and an emergency one, and this investigation
-- turns on which is which -- so the only thing separating them lived in
-- a note no consumer reads, on a value_text that reads as a single
-- figure. drawings-1.1 splits the row into one item per CELL and makes
-- the column heading a required field of the transcription.
--
-- Splitting cells is also why the unique key has to widen. `135` under
-- Prime and `135` under Standby are two different facts with the same
-- value_text on the same tile, and the 027 key
-- (document_id, page_index, tile_index, model, prompt_version,
--  item_kind, value_text) cannot tell them apart -- the second would be
-- swallowed by ON CONFLICT DO NOTHING and never appear. That is a
-- silent loss of exactly the distinction this migration exists to
-- record. So the key gains the column header and the location on the
-- sheet (which carries the row's own label: `kVA`, `400V, 50 Hz`,
-- item number). Both are nullable, and NULLs do not collide in a
-- Postgres unique constraint, so it is a unique INDEX over
-- coalesce(...,'') rather than a constraint.
--
-- The new key is strictly finer than the old one: every pair of rows
-- the old key separated, the new one separates too. So the 110 pilot
-- rows already stored cannot conflict, and dropping the old constraint
-- loses no protection.

ALTER TABLE drawing_transcriptions
    ADD COLUMN IF NOT EXISTS column_header TEXT;

COMMENT ON COLUMN drawing_transcriptions.column_header IS
    'Verbatim heading of the table column this cell sits under (''Prime'', '
    '''Standby'', ''400V 50Hz''). Empty or NULL when the value is not '
    'tabulated. Never inferred: the prompt requires the model to say '
    '''[unreadable]'' rather than guess which column a number is under.';

ALTER TABLE drawing_transcriptions
    DROP CONSTRAINT IF EXISTS
        drawing_transcriptions_document_id_page_index_tile_index_mo_key;

CREATE UNIQUE INDEX IF NOT EXISTS drawing_transcriptions_content_key
    ON drawing_transcriptions (
        document_id, page_index, tile_index, model, prompt_version,
        item_kind, value_text,
        coalesce(column_header, ''), coalesce(location_on_sheet, ''));
