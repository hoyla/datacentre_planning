# Audit of the 2026-08-10 validation rules

Run 2026-08-11, against the audit ROADMAP asked for and by the method it
prescribed: for each rule, write down the domain fact it asserts, then
check that fact against HISTORY, against ROADMAP, and against the corpus.

The reason for it is in ROADMAP: several dozen rules were written in one
evening, and one of them asserted that a site's IT load cannot exceed its
stated total — which this repository had already recorded as false, with
four correct counter-examples. A rule that contradicts a hard-won
negative result is a regression wearing the clothes of an improvement,
and these rules are not advisory: `dcp/adjudication_gate.py` blocks the
exports until the corrections have run, so a wrong rule changes what a
release ships.

**One rule failed.** Four passed, one is inert, and one item in ROADMAP's
own instructions turned out to be wrong.

---

## 1. The 3 GW implausibility ceiling — PASSES

`correct_adjudications.py`, rule `energy_not_power`: `pa.value_mw > 3000`
demotes a figure to `unclear` on the grounds that it must be annual
energy rather than power.

**The fact it asserts:** no data-centre development in or plausibly
arriving in this corpus has an electrical capacity above 3 GW.

**Corroborated.** HISTORY states it independently — "What detects it is
magnitude: nothing is 3 GW" — so the premise was recorded before the rule
was written rather than invented alongside it.

**Measured.** No adjudicated figure now exceeds 3,000 MW. The largest is
1,200 MW, and there is nothing at all between 1,200 and 3,000: the 87
rows at or above 1,000 MW all sit in the 1,000–1,200 band. The ceiling
therefore has a 2.5× margin over the largest genuine figure in the
corpus, and only 3 rows have ever carried its correction note.

**ROADMAP's specific worry — "an energy park's generation might be" above
it — does not apply**, for a reason worth recording. Adjudication runs
over applications in the data-centre site universe: 14,632 from PlanIt
and 39 from NSIP. All 39 NSIP rows belong to `EN0110030`, a data-centre
campus with a gas energy centre. The 197-project energy layer is an
adjacency layer and is not adjudicated, so a 4 GW offshore wind farm
cannot reach this rule.

**Residual risk, stated rather than fixed.** If a gigawatt-scale
generation scheme ever enters the site universe in its own right — an
energy park co-located with a campus, which is exactly the pattern this
investigation is looking for — the ceiling would silently demote its
generation figure and attribute it to "annual energy". The margin is
comfortable today and the rule is right today. It is worth re-running
this check whenever the universe grows a new class of member.

## 2. The consumption and generation corroboration bands — FAILS

`consumption_integrity.py` (`GRID_SHORTFALL` 0.8, `GEN_CORROBORATES`
0.8–1.5, `GEN_PARTIAL` 0.5) and the band labels in
`generation_integrity.py`.

**The fact they asserted:** generation between 0.8 and 1.5 times stated
load means plant "sized to carry the load", described in the code as the
classic full-redundancy pattern; below 0.5 means "life-safety only; site
is grid-dependent".

**The premise cited for it does not exist.** ROADMAP says to check these
against "HISTORY's note that standby is 'normally sized to carry full
load'". There is no such note in HISTORY — no occurrence of "standby",
"full load" or "redundancy" anywhere in it. The instruction to audit
against a recorded fact cited a fact that was not recorded.

**Measured, and the corpus does not support it.** Across the 47 sites
disclosing both a consumption and a generation figure:

| Ratio | Sites | Band label as written |
|---|---|---|
| below 0.5 | **20** | life-safety only; grid-dependent |
| 0.5–0.8 | 4 | partial — load-carrying uncertain |
| 0.8–1.5 | 13 | sized to carry the load |
| above 1.5 | 10 | generation exceeds load (energy park?) |

Median ratio **0.75**, which falls in the band the code calls
"uncertain". The "classic" pattern holds 13 of 47 sites; the modal case,
20 sites, is below half. Whatever the industry norm may be, this corpus's
disclosures do not show it, and a band that calls itself classic on
28% of the evidence is asserting a design intent it cannot see.

**Changed.** The bands are kept — they are useful buckets, and the
thresholds are not obviously wrong as *divisions* — but the labels now
describe the ratio rather than diagnose the engineering: "generation
below half of stated load" rather than "life-safety only; site is
grid-dependent". Why a site is in a band is for a reader who can open the
documents.

**Not changed, and worth a decision.** The ratios are noisy: the extremes
run from 0.00 to 100.00, which means some pairs compare a single
building's generation against a whole campus's load or the reverse. This
is the same cross-application scope trap ROADMAP already documents for
IT-load-exceeds-total. A ratio computed across applications at a
multi-building site may not be comparing like with like, and neither
script says so.

## 3. Count × rating arithmetic — PASSES

`generation_integrity.py` reads "150 x 2MW", "4No. 60MW" and similar as
a fleet count times a unit rating.

**ROADMAP's worry** was that "26 no. 28000kW generators" more likely
means 26 units totalling 28 MW. Sampled against real quotes, the
convention holds and the documents corroborate it themselves: "The site
shall be developed as a 240 MW(IT) campus, comprising 4No. 60MW(IT) DC
buildings" states both the total and the breakdown, and the stored figure
matches the document's own total. The report flags rather than
multiplies, which ROADMAP already judged correct.

## 4. The decimal-slip heuristic — INERT

`review_large_capacities.py` flags a figure that is exactly 10×, 100× or
1000× another on the same site.

**ROADMAP's worry** was that phased schemes legitimately state figures in
that relationship. Currently moot: **the heuristic fires zero times** on
the whole corpus. Of 957 verdicts at or above 100 MW across 41 sites, 78
are flagged, and every flag comes from the storage, thermal-input or
energy-unit families rather than this one.

It costs nothing and catches nothing. Worth keeping as a tripwire,
provided nobody mistakes its silence for evidence that no decimal slips
exist — it has never had the chance to be wrong.

## 5. The gate's duplicated predicates — PASSES, with the gap named

`dcp/adjudication_gate.py` carries its own copy of the six predicates.
ROADMAP: "Tests assert the copies stay in step; nothing asserts either
copy is *right*."

That is still true, and this audit is the missing check rather than a
replacement for it. The one predicate with a numeric threshold, the 3 GW
ceiling, is verified in §1 above. The rest are pattern matches over
evidence text whose premises are recorded in the migration comments
(015–018) and were each found by hand against real documents.

## 6. `dcp/site_scale.py` — UNDISTURBED

ROADMAP asked only whether the evening's changes disturbed the
preference order or the 1.71 kW/m² floor-area factor, both of which
predate it and were measured.

They did not. `site_scale.py` was touched once on 2026-08-10, by
`fdc43e6` ("Stop the capacity caveat hedging on sites whose prose is
fully read"), and that commit changes no threshold, no band and no
constant. The factor's own provenance is stated in the module: median
1.71 kW/m² across the 53 sites disclosing both a capacity and a
floorspace figure, interquartile range 1.29–3.26, land parcels excluded
because including them produced 117 km² of "floor area".

---

## What this audit did not cover

The pattern-matching predicates in rules 2–6 of `correct_adjudications.py`
were read but not measured against the corpus one by one; §5 explains why
they are lower-risk than the numeric ones, and their premises are
recorded in migrations 015–018 with the documents that produced them.
Anyone leaning hard on those specific corrections should measure them
before quoting, in the same way.

The 47-site sample behind §2 is small, and the scope caveat at the end of
it is unresolved.
