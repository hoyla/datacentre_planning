-- A substation on a drawing is not the site's grid connection.
--
-- Seven sites reported a consumption figure their grid connection could
-- not carry. Reading all seven found only two were what they looked
-- like, and the rest were a sixth kind of quantity error: `grid_connection`
-- had been applied to any electrical infrastructure the documents
-- mentioned.
--
-- What the seven actually were:
--
--   Northumberland   the "30 MW connection" is a battery storage
--                    compound, from a screening opinion for a different
--                    development on the same land.
--   Kenwood Point    "- 6MW Substation 25.4m²" — a drawing-schedule row,
--                    complete with the substation's floor area.
--   Graven Hill      "a new 6MW substation ... as part of the legacy
--                    logistic park planning consent" — infrastructure
--                    from an earlier, unrelated scheme.
--   Longcross        "TEMPORARY 1MW SUBSTATION", fifteen times over: a
--                    construction-phase supply, not the finished site's.
--   Watford Bypass   GENUINE. 218 MW of demand against "a 132kV
--                    dual-circuit connection designed to support a power
--                    transfer capacity of 120 MW". The documents really
--                    do say that.
--   West London      GENUINE, and scope-limited by its own words: 57 MW
--                    reserved, "anticipated to serve the needs of
--                    building 1", on a 155 MW site.
--   Ocean Estates    a clustering artefact — the 5 MW is a Salford
--                    application and the 36 MW a Trafford one.
--
-- So this corrects 26 rows and deliberately leaves the two genuine
-- mismatches standing. A site whose stated demand exceeds its designed
-- connection is not a data error to be smoothed away; it is a fact the
-- documents assert, and arguably the more interesting one.
--
-- Scope is narrow on purpose. Of 459 grid_connection verdicts, 114
-- mention a substation without connection language — but almost all are
-- MVA figures the adjudicator already refuses to convert, so they carry
-- no value_mw and cannot reach a headline. Only rows with a convertible
-- MW value are touched. Legitimate supply capacities survive untouched:
-- "the main substation will be a Grid Supply Point", "2No 150MW 66kV
-- supplies by the IDNO", "Substation 1 (100MW) from Uxbridge Moor".

BEGIN;

-- Batteries are storage, and 016 already established where those belong.
UPDATE power_adjudication pa
   SET quantity_type = 'energy_storage',
       unit_note = coalesce(unit_note || ' ', '')
                   || '[018] battery storage, not a grid connection'
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND pa.quantity_type = 'grid_connection'
   AND pa.value_mw IS NOT NULL
   AND f.evidence_text ~* 'batter|bess|energy storage';

-- A construction-phase supply is not the operating site's connection.
UPDATE power_adjudication pa
   SET verdict = 'unclear', quantity_type = NULL, value_mw = NULL,
       is_maximum = NULL,
       unit_note = coalesce(unit_note || ' ', '')
                   || '[018] temporary construction supply, not the '
                      'completed development''s connection'
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND pa.quantity_type = 'grid_connection'
   AND pa.value_mw IS NOT NULL
   AND f.evidence_text ~* '\ytemporar';

-- Drawing schedules, figure captions and another scheme's legacy plant.
UPDATE power_adjudication pa
   SET verdict = 'unclear', quantity_type = NULL, value_mw = NULL,
       is_maximum = NULL,
       unit_note = coalesce(unit_note || ' ', '')
                   || '[018] equipment label, drawing reference or an '
                      'earlier scheme''s infrastructure, not this '
                      'development''s connection'
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND pa.quantity_type = 'grid_connection'
   AND pa.value_mw IS NOT NULL
   AND f.evidence_text ~* 'floor plan|sections drawing|figure [0-9]|substation\s+[0-9.]+\s*m²|legacy';

-- Note the \s+ in the equipment predicate above, not a literal space.
-- The Kenwood drawing row reads "- 6MW Substation       25.4m²" with
-- seven spaces in it; text lifted out of PDFs and OCR is full of runs of
-- whitespace, and a pattern written with one space silently misses them.
-- That is the third regex trap in this migration series, after \b for a
-- word boundary and summing overlapping predicates instead of counting
-- distinct rows.
--
-- The guard 017 earned. If these predicates ever stop meaning what they
-- meant when they were read by hand, this aborts rather than quietly
-- changing a different number of figures.
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM power_adjudication
   WHERE unit_note LIKE '%[018]%';
  IF n <> 26 THEN
    RAISE EXCEPTION 'migration 018 changed % rows, expected 26 — '
                    'refusing to commit', n;
  END IF;
END $$;

COMMIT;
