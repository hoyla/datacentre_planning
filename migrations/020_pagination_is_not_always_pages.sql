-- Only a PDF has pages.
--
-- Every finding carries an `evidence_page`, and every artefact that
-- shows one calls it a page. For 1,471 documents that is false: a .docx
-- has no pages until something renders it, so the extractor records the
-- index of a *section*; a workbook's is a sheet; a deck's is a slide.
-- dcp/extract.py has known this since the format loaders landed and
-- writes the right word into the text cache — `pagination` — but the
-- caches are files on disk and every export is SQL, so the distinction
-- has never reached a reader.
--
-- It is a provenance claim, which is why it matters more than it looks.
-- The page number is the thing a reporter uses to find the sentence in
-- the source document before quoting it. Told "page 3" of a spreadsheet
-- they open it, find no page 3, and are left doubting the quote rather
-- than the label. Sheet 3 is where it actually is.
--
-- Nullable and unset by default. Null means "not recorded", not
-- "pages" — the backfill below sets what it can prove and leaves the
-- rest alone, and consumers must treat an unknown as unknown rather
-- than assuming the common case. 34,329 legacy caches predate the field
-- entirely.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS pagination text;

COMMENT ON COLUMN documents.pagination IS
  'Whose division evidence_page indexes: pages | sections | sheets | '
  'slides. Null means not recorded. Only "pages" may be shown to a '
  'reader as a page number.';

-- Constrained rather than free text: this is a small closed vocabulary
-- shared with dcp/extract.py's loader table, and a typo in it would be
-- invisible until it reached a citation.
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_pagination_known;
ALTER TABLE documents ADD CONSTRAINT documents_pagination_known
  CHECK (pagination IS NULL
         OR pagination IN ('pages', 'sections', 'sheets', 'slides'));

-- Partial: the overwhelming majority are ordinary PDFs, and the queries
-- that care are the ones looking for the exceptions.
CREATE INDEX IF NOT EXISTS documents_pagination_idx
  ON documents (pagination) WHERE pagination IS NOT NULL AND pagination <> 'pages';
