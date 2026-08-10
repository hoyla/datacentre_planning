-- A battery is not a generator, and thermal input is not electrical output.
--
-- The adjudication rubric asks two questions: is this figure about this
-- development, and if so what kind of quantity is it. The first was
-- answered correctly in every case below. The second had no vocabulary
-- for two things this corpus actually contains, so they were filed under
-- `onsite_generation`, which is the second most important figure in the
-- project and now the one most diluted.
--
-- **Energy storage.** Rover Way, Splott is an energy park with a
-- 1,000 MW battery system beside a data centre: "The Tremorfa project is
-- a 1,000 MW Battery Energy Storage System (BESS)." That rating is how
-- fast the battery can discharge, not what the site generates or draws.
-- Recorded as generation it made a 10 MW data centre look like it had a
-- hundred times its own consumption in on-site plant.
--
-- **Thermal input.** Camilla Road, Auchtertool: "would appear to require
-- a Thermal Input of around 1.2GW to maintain operation of such a
-- facility." Thermal input is fuel energy entering a plant, typically
-- two to three times the electrical capacity leaving it. As the site's
-- headline it overstated a defensible 800 MW by half.
--
-- Neither figure is deleted and neither verdict changes: both genuinely
-- describe their development, which is what `site_capacity` asserts. Only
-- the quantity type is corrected, to values no headline column consumes
-- (the exports filter on exact names — see export_handover.py and
-- export_reader.py). The facts stay in the record, queryable and
-- quotable; they simply stop being counted as something they are not.
--
-- This is the third member of a family found today. Migration 015 was
-- energy recorded as power. This is storage and heat recorded as
-- generation. All three are the same failure: a pipeline that reads the
-- unit and the subject but never asks what kind of quantity it is
-- holding.

BEGIN;

UPDATE power_adjudication pa
   SET quantity_type = 'energy_storage',
       unit_note = coalesce(unit_note || ' ', '')
                   || '[016] battery/storage discharge rating, not '
                      'generation or demand'
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND pa.quantity_type = 'onsite_generation'
   AND (f.evidence_text ~* 'batter|bess|energy storage|storage system'
        OR f.signal_type ~* 'batter|storage');

UPDATE power_adjudication pa
   SET quantity_type = 'thermal_input',
       unit_note = coalesce(unit_note || ' ', '')
                   || '[016] thermal/fuel input, not electrical capacity'
  FROM findings f
 WHERE f.id = pa.finding_id
   AND pa.verdict = 'site_capacity'
   AND pa.quantity_type IN ('onsite_generation', 'it_load', 'total_site')
   AND (f.evidence_text ~* 'thermal input|heat input|calorific|fuel input'
        OR f.signal_type ~* 'thermal_input|heat_input');

COMMIT;
