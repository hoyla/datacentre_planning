-- The Stage-1 triage rubric was refined during the labelling/eval phase
-- (2026-05-13/14) — `dcp/triage.py` and `data/triage_labelling/rubric.md` now
-- produce categorical `confidence` plus three new fields (`worth_deep_read`,
-- `signals`, `why`) that the v0 schema didn't have. The original `confidence
-- REAL` and `est_capacity_mw REAL` columns matched an earlier draft of the
-- rubric; the `triage` table has no rows yet, so this migration reshapes it
-- without touching live data. `est_capacity_mw` is kept (nullable) for a
-- future deep-read pass that may populate it from document text.

ALTER TABLE triage
    ALTER COLUMN confidence TYPE TEXT USING confidence::TEXT,
    ADD COLUMN worth_deep_read TEXT,
    ADD COLUMN signals TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN why TEXT;

CREATE INDEX idx_triage_verdict ON triage(verdict);
CREATE INDEX idx_triage_worth_deep_read ON triage(worth_deep_read);
CREATE INDEX idx_triage_signals ON triage USING gin (signals);
