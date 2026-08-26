-- What a vision model says is written on a drawing. Unverified, and
-- quarantined until a person has looked.
--
-- The deep read skips drawings by design (dcp/deepread_select.py): a
-- location plan carries no prose, 23% of the corpus goes unread on that
-- rule, and the rule is right about location plans. It cannot tell them
-- from an electrical single-line diagram or a manufacturer's transformer
-- general arrangement, and those carry ratings the prose never states.
-- ROADMAP parks a "Multimodal pass over drawings" and reopens it only
-- "for a specific application where both conditions fail". This table
-- holds the pilot that tests whether such applications exist.
--
-- **Nothing here is a finding.** The project's contract for an
-- extracted figure is that its quote verifies character-for-character
-- against the cached text of the document it cites
-- (scripts/verify_findings.py, dcp/adjudication_gate.py). A
-- transcription off an image has no such substrate: there is no text to
-- check it against, and the checkable text that does exist on these
-- sheets is CAD output in drawing order, not reading order -- "1500kVA
-- ELECTRICAL RATINGS" arrives interleaved with the parts list around
-- it. So the round trip cannot run, and every row in this table is
-- unverified by construction.
--
-- The failure mode that makes this matter is specific. A vision model
-- that reads "2 x 3MVA" as "23 MVA" produces a confident figure that is
-- wrong by a factor of four, and a wrong figure travels further than a
-- missing one. `human_verdict` is therefore NULL until somebody has put
-- the transcription beside the rasterised tile it came from, and
-- nothing joins this table to power_adjudication, to the site capacity
-- panels or to any artefact. There is no view that would let it leak.
--
-- Append-only and idempotent on (document_id, page_index, tile_index,
-- model, prompt_version), the same contract as power_adjudication,
-- generation_adjudication and finding_label_audit: a re-run under a
-- better prompt or a higher render DPI adds rows beside the old ones
-- rather than replacing them. render_dpi is recorded but deliberately
-- not in the key -- it is a property of how the tile was made, and two
-- runs at different DPI under the same prompt are the same question
-- asked twice, which is exactly what an append-only table should show
-- side by side.

CREATE TABLE drawing_transcriptions (
    id               BIGSERIAL PRIMARY KEY,
    document_id      BIGINT NOT NULL REFERENCES documents(id),
    application_id   BIGINT NOT NULL REFERENCES applications(id),

    -- Which cohort put this document in the pilot, so a scale-up can be
    -- targeted at whichever one paid off. 1 = follow-on plant
    -- application whose prose yields no figure (the accretion pattern,
    -- ROADMAP item 4); 2 = electrical drawing at a site with no
    -- disclosed capacity, whose published number rides on the 1.71
    -- kW/m2 floor-area factor.
    cohort           SMALLINT NOT NULL,

    -- Where on the sheet. tile_index 0 is the whole-sheet overview.
    page_index       INT NOT NULL,
    tile_index       INT NOT NULL,
    tile_position    TEXT,              -- "row 2 of 3, column 3 of 4, middle-right"
    render_dpi       REAL,

    -- The model's own account of where it read this, in the sheet's
    -- terms rather than ours: the title-block drawing number, the
    -- schedule or view it sits in. This is the provenance a reporter
    -- would quote, and it is the model's claim, not a measurement.
    sheet_ref        TEXT,
    location_on_sheet TEXT,

    -- The transcription itself, verbatim as the model read it, plus the
    -- kind of thing it is. Never parsed into a number by this table:
    -- `value_text` is what is written, and any arithmetic on it is a
    -- later human act.
    item_kind        TEXT NOT NULL,
        -- 'rating'    — a kW/MW/MVA/kVA/V/A figure against equipment
        -- 'schedule'  — a transcribed equipment schedule row
        -- 'count'     — a stated quantity of generators, transformers,
        --               chillers, tanks
        -- 'volume'    — litres/m3 of fuel, oil or water
        -- 'model_no'  — a manufacturer and model designation
        -- 'other'     — anything else the sheet states as a rating
    value_text       TEXT NOT NULL,
    equipment        TEXT,
    quantity         TEXT,

    -- The model's own legibility judgement for this item, so a figure it
    -- half-read is distinguishable from one it read cleanly. A pilot
    -- that could not tell those apart could not say whether a higher
    -- render DPI would help.
    legibility       TEXT,              -- 'clear' | 'partial' | 'illegible'

    -- NULL until a person has checked it against the tile image. This
    -- is the whole quarantine: no consumer of this table may treat a
    -- row with a NULL verdict as a fact.
    human_verdict    TEXT,              -- 'correct' | 'wrong' | 'unclear'
    human_note       TEXT,
    checked_at       TIMESTAMPTZ,

    -- Where the reviewer can see the image. Relative to the repo root.
    tile_image_path  TEXT,

    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (document_id, page_index, tile_index, model, prompt_version,
            item_kind, value_text)
);

CREATE INDEX idx_drawing_transcriptions_doc
    ON drawing_transcriptions (document_id, page_index, tile_index);

CREATE INDEX idx_drawing_transcriptions_unchecked
    ON drawing_transcriptions (cohort, human_verdict)
    WHERE human_verdict IS NULL;

-- One row per tile actually sent, whether or not it yielded anything.
-- Without it a null result is indistinguishable from a tile that was
-- never sent, and null results are the point: "we looked at 28 drawings
-- and 19 carried no rating" is a finding about the corpus, and it only
-- exists if the looking is recorded.
CREATE TABLE drawing_transcription_log (
    id               BIGSERIAL PRIMARY KEY,
    document_id      BIGINT NOT NULL REFERENCES documents(id),
    application_id   BIGINT NOT NULL REFERENCES applications(id),
    cohort           SMALLINT NOT NULL,
    page_index       INT NOT NULL,
    tiles_sent       INT NOT NULL,
    render_dpi       REAL,
    sheet_width_pt   REAL,
    sheet_height_pt  REAL,
    outcome          TEXT NOT NULL,
        -- 'hit'        — at least one item transcribed
        -- 'null'       — the model read the sheet and found no rating
        -- 'illegible'  — the model said it could not read the sheet
        -- 'refused'    — the model declined or returned nothing usable
        -- 'error'      — the request failed
    items_found      INT NOT NULL DEFAULT 0,
    notes            TEXT,
    input_tokens     INT,
    output_tokens    INT,
    elapsed_s        REAL,
    model            TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    inserted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (document_id, page_index, model, prompt_version)
);
