-- Energy is not power, and one planning document said so in kW.
--
-- An ARK application states: "The Data Centre Load for the LP1
-- development, detailed in Appendix 9.1 - ARK Data Centre Load Schedule,
-- is 251,859,057.50 kW which equates to 94,197.29 kWh/m2". The unit says
-- kW; the cross-reference in the same sentence gives kWh/m2. The figure
-- is annual energy, mislabelled as power *in the source document*.
-- 251,859,057 kWh over 8,760 hours is about 28.7 MW, which is a
-- believable data centre.
--
-- Nothing in the pipeline was wrong, exactly, and that is the point. The
-- extractor quoted the document faithfully and even labelled the signal
-- `it_load_energy`. The adjudicator was asked whose figure it was and
-- answered correctly: this development's. No stage was asked whether a
-- figure denominated in kW is a power figure at all, so a 251,859 MW
-- site capacity -- roughly four times the United Kingdom's entire
-- generating capacity -- reached the adjudication table and would have
-- reached a chart.
--
-- This is a sibling of the finding that produced power adjudication in
-- the first place. That one was "whose quantity is this"; this one is
-- "what kind of quantity is this". Both are invisible to a pipeline that
-- trusts the unit string.
--
-- Two changes:
--
-- 1. The three verdicts are demoted to 'unclear' with the reason
--    recorded. They are not deleted: the finding is real, the quote is
--    accurate, and the document genuinely says what it says. What was
--    wrong was calling it this site's power capacity.
--
-- 2. A view, power_adjudication_suspect, standing for the rest. It flags
--    every site_capacity verdict whose signal_type or evidence quote
--    points at energy rather than power, or whose converted value is
--    implausible for any data centre (no announced campus anywhere
--    approaches 3 GW). 33 rows carry energy-shaped signal types and 17
--    have energy units in the quote; most are small enough that the
--    error is immaterial, but they should be visible rather than
--    assumed harmless.

BEGIN;

UPDATE power_adjudication pa
   SET verdict = 'unclear',
       quantity_type = NULL,
       value_mw = NULL,
       is_maximum = NULL,
       unit_note = 'demoted by migration 015: the source document gives '
                   'this figure in kW but cross-references it as kWh/m2, '
                   'so it is annual energy, not power. Converted it '
                   'implied a site capacity many times the national grid.',
       reasoning = left('[015] ' || reasoning, 600)
 WHERE pa.verdict = 'site_capacity'
   AND pa.value_mw > 3000;

CREATE OR REPLACE VIEW power_adjudication_suspect AS
SELECT pa.id, pa.finding_id, pa.application_id, pa.model,
       pa.value_mw, pa.value_original, pa.unit_original, pa.quantity_type,
       f.signal_type, f.evidence_text,
       (pa.value_mw > 3000)                                  AS implausible,
       (f.signal_type ~* 'energy|consumption|kwh|annual')     AS signal_says_energy,
       (f.evidence_text ~* 'kwh|mwh|gwh|per annum|annually|per year')
                                                             AS quote_says_energy
FROM power_adjudication pa
JOIN findings f ON f.id = pa.finding_id
WHERE pa.verdict = 'site_capacity'
  AND (pa.value_mw > 3000
       OR f.signal_type ~* 'energy|consumption|kwh|annual'
       OR f.evidence_text ~* 'kwh|mwh|gwh|per annum|annually|per year');

COMMIT;
