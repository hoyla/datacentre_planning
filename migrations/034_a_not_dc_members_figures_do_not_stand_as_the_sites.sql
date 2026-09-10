-- A not_dc member's figures do not stand as the site's capacity.
--
-- A site holds every application the clusterer admits, and the family
-- door admits an application whatever triage said, because a reserved
-- matters on a data-centre outline reads `not_dc` by construction: the
-- description does not say, and the documents are the only fix. That
-- door is doing useful work — vetoing `not_dc` there would eject Google's
-- Waltham Cross reserved matters (ROADMAP, the `not_dc` item, resolved
-- with Luke 2026-09-02, the veto left `off`).
--
-- But nothing downstream distinguished the two kinds of `not_dc` member,
-- and every site-level rollup took the largest figure across every
-- member. Measured 2026-09-10: 185 live members carry a latest dc_build
-- verdict of `not_dc`; 32 of them carry 301 figures adjudicated
-- `site_capacity` — correctly, for the application each belongs to —
-- and those figures stood as the site's. The Eggborough power station's
-- own 2,500 MW rendered as a data-centre site's on-site generation;
-- West Burton's 500 MW battery, the British Museum energy centre and
-- Bristol's Gardiner Haskins energy centre gave their sites' headline
-- figures; ten Selby discharges put 500 MW `other` on PTNO-12784626.
-- Only three of the 32 hold documents naming a data centre, and 80 of
-- their 85 figures sit on one application: Kingsnorth's outline, the
-- parent permission of its data-centre applications.
--
-- ## What this records
--
-- `figure_standing` on each membership row says whether the member's
-- adjudicated figures may stand as the site's:
--
--   `counts`          — every member the universe rule admits.
--   `not_dc_excluded` — the latest dc_build verdict is `not_dc` and no
--                       person has said otherwise; or the member is
--                       `procedural` paperwork whose every family parent in
--                       the site is excluded (a discharge is in the universe
--                       on the premise that its parent is a data centre's
--                       permission, and Eggborough's second discharge
--                       carried the station's 2,500 MW exactly as the first
--                       did). The member stays; its documents stay on
--                       Drive; its figures render on its own application
--                       panel with their adjudication; no site-level rollup
--                       — the sites table, the ladder, the cohorts, the
--                       workbook columns, the DuckDB view, the reading
--                       input — takes them. `standing_reason` names the
--                       parents for the inherited case.
--   `not_dc_admitted` — `not_dc` by verdict, admitted for figures by an
--                       entry in data/priors/not_dc_standing.yaml with the
--                       evidence that the application is the data centre's
--                       own paperwork. `standing_reason` carries that
--                       entry's reason.
--
-- Set at materialise from the verdict fold `build_clusters` already
-- performs and the prior it already loads beside the partitions, so the
-- standing is as current as membership and no more. A membership row is
-- retired and revived by the materialise, never deleted, and the upsert
-- path already rewrites `joined_via` in place; these two columns follow
-- the same contract. The verdict itself is untouched (principle 3): this
-- is a statement about what a figure may stand for, not a re-triage.
--
-- ## Why the dc_build verdict and not the fold the universe rule uses
--
-- The universe rule admits on either rubric (v1 `DC` or dc_build not
-- `not_dc`). Standing keys on the dc_build verdict alone, the rubric
-- that has the concept and the one `dcp/site_class.py` folds first.
-- Measured 2026-09-10: two live members are `not_dc` under dc_build and
-- `DC` under v1, and neither carries a figure.
--
-- ## What this migration does not do
--
-- It does not change site keys. Eighteen `SITE-` keys derive from a
-- `not_dc` application (Kingsnorth's among them, with ten readings and
-- two matched claims behind it), and re-keying them renames Drive
-- folders, orphans readings and breaks the Sheet's annotations by key.
-- That is measured in ROADMAP and is a decision, not a column.

ALTER TABLE site_members
    ADD COLUMN figure_standing TEXT NOT NULL DEFAULT 'counts'
        CHECK (figure_standing IN ('counts', 'not_dc_excluded',
                                   'not_dc_admitted')),
    ADD COLUMN standing_reason TEXT;

COMMENT ON COLUMN site_members.figure_standing IS
    'Whether this member''s adjudicated figures may stand as the site''s: '
    'counts | not_dc_excluded | not_dc_admitted. Set at materialise from '
    'the latest dc_build verdict and data/priors/not_dc_standing.yaml.';
COMMENT ON COLUMN site_members.standing_reason IS
    'For not_dc_admitted: the prior entry''s reason, verbatim. For a '
    'procedural member excluded because its family parents are: the '
    'parents named.';
