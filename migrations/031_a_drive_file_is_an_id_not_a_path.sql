-- Where our copy of a document lives on Drive, recorded rather than derived.
--
-- The reader and the workbook link a cited document to the copy this
-- project holds, because a council register can withdraw a document,
-- renumber it, move the portal or put it behind a session, and all four
-- have happened during this investigation. 512 documents carry a
-- `file://` URL besides, naming a path on the machine that ingested
-- them, and 401 of those reached the published 2.8 reader as anchors
-- that resolved on nobody's machine.
--
-- ## The problem this table exists to remove
--
-- The Drive *link* was already an id — `/file/d/{id}/view`, which
-- survives the file being moved or renamed on Drive, and that is the
-- whole reason the project addresses Drive by id and never by name
-- (`dcp/drive.py`, and the duplicate archive that a name lookup once
-- silently created).
--
-- But *finding* that id went the long way round. The sync ledger keys on
-- the local staging path, so the export rebuilt each document's expected
-- path — site stem, application ref, and a number counting the
-- application's documents in `fetched_at, id` order — and looked the
-- path up. Correct today: 120 of 120 sampled links were verified
-- content-addressed, the bytes on disk matching the md5 the ledger
-- recorded for the Drive copy.
--
-- Correct today is the problem. Every input to that derivation can move.
-- Renumber the documents of an application, rename a site, change the
-- staging layout, and the lookup either finds nothing — a document
-- silently loses its link — or finds the neighbouring file, which is a
-- live link to the wrong document under a citation that says otherwise.
-- The second failure is invisible and would put a real quote against a
-- real but different source, which principle 7 exists to prevent.
--
-- So: record the id at the moment it is known, and never derive it
-- again.
--
-- ## Shape
--
-- Append-only, like every other interpretation store here. A document
-- re-uploaded under a new path gets a second row rather than an
-- overwrite, so the history of where a copy has lived is preserved and
-- the older link keeps resolving — a Drive id stays valid after a move,
-- which is exactly the property being relied on.
--
-- `md5` is the ledger's own hash of the uploaded bytes, kept so a link
-- can be verified against the local file without calling Drive.
-- `staged_path` is kept for provenance only: it records where the copy
-- was when the id was captured. Nothing reads it to find a file.

CREATE TABLE IF NOT EXISTS document_drive_files (
  id            bigserial PRIMARY KEY,
  document_id   bigint NOT NULL REFERENCES documents(id),
  file_id       text   NOT NULL,
  md5           text,
  staged_path   text,
  recorded_at   timestamptz NOT NULL DEFAULT now()
);

-- Idempotency contract: re-running the recorder over an unchanged
-- ledger inserts nothing.
CREATE UNIQUE INDEX IF NOT EXISTS document_drive_files_unique
  ON document_drive_files (document_id, file_id);

CREATE INDEX IF NOT EXISTS document_drive_files_document
  ON document_drive_files (document_id, recorded_at DESC);

COMMENT ON TABLE document_drive_files IS
  'Our copy of a document on Drive, addressed by file id. Written by '
  'scripts/record_drive_ids.py after a sync; read by the reader and the '
  'workbook to link a cited document to a copy that cannot be withdrawn '
  'from a council register. Append-only: a re-upload adds a row, and '
  'older ids keep resolving because a Drive id survives a move.';

COMMENT ON COLUMN document_drive_files.file_id IS
  'Google Drive file id. The link is https://drive.google.com/file/d/'
  '{file_id}/view. Never a name or a path — a name lookup under the '
  'drive.file scope finds nothing and silently creates a duplicate.';

COMMENT ON COLUMN document_drive_files.staged_path IS
  'Where the local copy was when this id was captured. Provenance only. '
  'Nothing resolves a file through it, which is the point of the table.';
