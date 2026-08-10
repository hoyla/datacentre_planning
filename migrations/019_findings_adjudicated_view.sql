-- The default way to read a finding should carry its adjudication.
--
-- Power adjudication lives in its own table, correctly: it is a
-- versioned interpretation over findings, and findings must stay
-- canonical. But that made carrying the verdict an opt-in, and on
-- 2026-08-10 three of four consumers had not opted in.
--
--   the per-site findings CSV   built from `findings` alone
--   the DuckDB export           no reference to power_adjudication at all
--   the reader's site panel     ranked power findings to the top, joined
--                               nothing, and displayed 33 figures
--                               adjudicated as somebody else's
--   the workbook                sound, because its power columns were
--                               designed around the adjudication
--
-- The pattern is clear enough to design against: whatever was built
-- alongside adjudication got it, and everything built afterwards
-- inherited raw findings. The corpus contains a 30 GW national storage
-- target and a 22,700 MW market forecast, so a consumer reading
-- `findings` and sorting by value_number is not making an unusual
-- mistake — it is making the obvious one.
--
-- So this view is the thing to reach for. It is `findings` plus the
-- verdict, and using it costs nothing over querying the table directly.
-- Reaching past it to raw `findings` remains possible and is sometimes
-- right — re-adjudication does exactly that — but it becomes a
-- deliberate act rather than the path of least resistance.
--
-- DISTINCT ON keeps one adjudication per finding: a figure judged by two
-- models would otherwise duplicate its row. Decided verdicts are
-- preferred over 'unclear', and the most recent within that, so a later
-- pass supersedes an earlier one without the older row being destroyed.

CREATE OR REPLACE VIEW findings_adjudicated AS
SELECT f.*,
       adj.verdict        AS adj_verdict,
       adj.quantity_type  AS adj_quantity_type,
       adj.value_mw       AS adj_value_mw,
       adj.is_maximum     AS adj_is_maximum,
       adj.unit_note      AS adj_unit_note,
       adj.reasoning      AS adj_reasoning,
       adj.model          AS adj_model,
       -- The single question most consumers actually need answered.
       -- NULL where the finding never went to adjudication, which is not
       -- the same as having been judged and set aside.
       CASE WHEN adj.verdict IS NULL THEN NULL
            ELSE adj.verdict = 'site_capacity' END AS adj_is_this_site
FROM findings f
LEFT JOIN LATERAL (
  SELECT verdict, quantity_type, value_mw, is_maximum, unit_note,
         reasoning, model
  FROM power_adjudication pa
  WHERE pa.finding_id = f.id
  ORDER BY (pa.verdict = 'unclear'), pa.inserted_at DESC
  LIMIT 1) adj ON true;

COMMENT ON VIEW findings_adjudicated IS
  'findings with its power adjudication attached. Prefer this over the '
  'findings table wherever a consumer might read a megawatt figure: the '
  'largest figures in this corpus describe other people''s schemes, and '
  'three of four exports shipped without the verdict before this existed.';
