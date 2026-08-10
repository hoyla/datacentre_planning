-- A number in a table is not a capacity unless something says what it is.
--
-- 116 site-capacity verdicts rest on a quote that is a bare table row
-- stripped of its column headers. The extraction is faithful — the
-- characters really are in the document — and the adjudication answered
-- the question it was asked, which is whether the figure belongs to this
-- development. Neither stage was in a position to notice that the quote
-- contains no unit at all, so nothing in the record establishes that the
-- number is megawatts rather than pounds, metres or a row index.
--
-- What that produced:
--
--   "80% - 480W"                             -> 480 MW total site
--   "Year 1 150 £1,232 £1,109 £847 £1,451"   -> 384 MW IT load
--   "Totals: 74 212.4 607.6"                 -> 212.4 MW generation
--   "Data Centre 150 210 1,839,600 0.20448"  -> 150 MW and 210 MW
--   "Total supply required 163.2 172.2 161.6"-> 163.2 MW and 161.6 MW
--
-- The first is a million-fold error: 480 watts read as 480 megawatts.
-- The second is a financial table in pounds sterling.
--
-- Three sites lose their headline figure to this, and all three were
-- independently flagged as contradicted by a separate check comparing
-- consumption against the grid connection the same documents describe.
-- Cardiff East drops from 210 MW to 70 MW and stops contradicting its
-- own 150 MW connection; Longcross drops from 56.3 MW to 3.8 MW against
-- a 1 MW connection; North Hyde Gardens from 163.2 MW to 89 MW. Two
-- methods built from different evidence agreeing on which figures are
-- wrong is the strongest signal available here that they are.
--
-- Demoted to 'unclear' rather than deleted, and value_mw cleared so no
-- aggregate can pick them up. The finding remains: the document really
-- does contain that table, a reader may want it, and a later pass with
-- the column headers in hand could adjudicate it properly. What goes is
-- only the claim that the number is this site's power capacity.
--
-- The detector is deliberately narrow — a quote is a headerless table row
-- when it is over 30% digits, carries fewer than eight words of three or
-- more letters, and never places a power unit beside a number. Prose that
-- happens to contain figures keeps its verdict.
--
-- One trap, recorded because it cost a restore. The unit test below uses
-- \y, not \b. In PostgreSQL's regular expressions \b is a BACKSPACE
-- character; the word boundary is \y. Written with \b the exclusion
-- silently matches nothing, every row passes the "no unit" test, and the
-- migration demotes 261 rows instead of 116 — including 146 that carry a
-- perfectly good "50 MW" in their quote. That is what happened on the
-- first run of this file. The guard at the end now refuses to commit if
-- the count strays from what the committed detector found.

BEGIN;

UPDATE power_adjudication pa
   SET verdict = 'unclear',
       quantity_type = NULL,
       value_mw = NULL,
       is_maximum = NULL,
       unit_note = coalesce(unit_note || ' ', '')
                   || '[017] quote is a table row with no column headers '
                      'and no unit; nothing establishes that this figure '
                      'is megawatts',
       reasoning = left('[017] ' || coalesce(reasoning, ''), 600)
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND length(f.evidence_text) > 0
   -- mostly numerals
   -- Whitespace-normalised first, so this predicate and the Python
   -- detector in scripts/ compute the same ratio over the same string.
   -- Without it they disagreed by one row, which is exactly how two
   -- copies of one rule start to drift.
   AND (length(regexp_replace(f.evidence_text, '[^0-9]', '', 'g'))::float
        / length(regexp_replace(btrim(f.evidence_text), '\s+', ' ', 'g')))
       > 0.30
   -- almost no prose
   AND (SELECT count(*)
          FROM unnest(regexp_split_to_array(lower(f.evidence_text),
                                            '[^a-z]+')) AS w
         WHERE length(w) >= 3) < 8
   -- and never a unit next to a number
   AND f.evidence_text !~* '\d[\d,.]*\s*(mw|kw|gw|mva|kva|mwe)\y';

-- Refuse to commit a demotion this file did not intend. 116 is what the
-- committed detector (scripts/review_large_capacities.py's sibling logic)
-- finds against this corpus; a materially different number means the
-- predicate has drifted or the regex flavour has bitten again.
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM power_adjudication
   WHERE unit_note LIKE '%[017]%';
  IF n <> 116 THEN
    RAISE EXCEPTION 'migration 017 demoted % rows, expected 116 — '
                    'refusing to commit', n;
  END IF;
END $$;

COMMIT;
