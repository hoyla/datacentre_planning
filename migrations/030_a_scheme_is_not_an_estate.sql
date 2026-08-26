-- The capacity a scheme is valued on, and the value it is valued at.
--
-- Two additions to `capacity_claims.quantity_type`, both from the same
-- sentence in the same kind of document, and neither expressible in the
-- vocabulary the table has.
--
-- ## Why the existing types cannot carry this
--
-- UK Court Lane DC Ltd (14045228) holds one asset — a freehold at Court
-- Lane Industrial Estate, Iver — and its FRS 102 accounts to 30 April
-- 2026 state, in the critical-judgements note, that the £205,000,000
-- valuation of it assumes "successful delivery of a 103.3 MW hyperscale
-- data centre".
--
-- Every existing type would misdescribe that figure:
--
--   * `built_capacity` is what exists. Nothing is built here.
--   * `announced_capacity` is what an operator markets. This is not
--     marketing; it is what an external valuer priced and an auditor
--     signed, and it is *lower* than the developer's own public number.
--   * `grid_connection` is a ceiling contracted with the network. The
--     same scheme's planning documents state a reserved 140 MW grid
--     connection, four times over. A reserved connection is headroom; a
--     valuation assumption is deliverable capacity. Filing 103.3 as a
--     grid connection would assert that 103.3 and 140 measure the same
--     thing and disagree — when in fact they measure different things
--     and both may be right.
--   * `it_load` and `total_site` are planning-document quantities with a
--     technical definition. The accounts do not say which one 103.3 is.
--
-- So `scheme_capacity`: **the capacity a single-asset SPV's investment
-- property is valued on the assumption of delivering.** It is peculiar
-- to this class of filer and it exists by construction rather than by
-- choice — the scheme IS the investment property, so FRS 102 requires
-- the directors to state the assumptions the fair value rests on. That
-- is what makes it different in kind from Ark's per-campus megawatts,
-- which are a narrative choice in a business review and generalise to
-- nobody (docs/EXTERNAL_DATA_SOURCES.md §6).
--
-- ## And the money, because the megawatts are load-bearing for it
--
-- `investment_property_fair_value` is not a power quantity at all, which
-- is the point. The capacity assumption exists *because* it underpins a
-- number — remove the £205m and the sentence has no reason to state a
-- megawatt figure. Recording the valuation beside the capacity is what
-- lets a reader see what the assumption is holding up, and what a
-- shortfall against it would be a shortfall in. `value_mw` is null on
-- these rows for the same reason it is null on `metered_consumption`:
-- pounds are not megawatts, and the column that would like them to be
-- is exactly the column this table exists to avoid.
--
-- ## What this unblocks
--
-- Both types are already used by claims committed in
-- `data/external_sources/companies-house-claims.yaml`, which is why
-- `scripts/load_capacity_claims.py` has been aborting and rolling back
-- **every batch from every source** — NESO, operator websites and
-- Environment Agency permits included — since the SPV work landed. The
-- loader validates and inserts as one transaction by design, so a single
-- unknown quantity type takes the whole store's refresh with it.

ALTER TABLE capacity_claims DROP CONSTRAINT IF EXISTS capacity_claims_quantity_known;
ALTER TABLE capacity_claims ADD CONSTRAINT capacity_claims_quantity_known
  CHECK (quantity_type IN (
    'it_load', 'grid_connection', 'total_site', 'onsite_generation',
    'cooling', 'energy_storage', 'thermal_input',
    'built_capacity', 'metered_consumption', 'announced_capacity',
    'let_capacity',
    'scheme_capacity', 'investment_property_fair_value'));

COMMENT ON COLUMN capacity_claims.quantity_type IS
  'What the figure measures, in the source''s own terms. Shared with '
  'power_adjudication.quantity_type where the quantities coincide. '
  '`scheme_capacity` and `investment_property_fair_value` are peculiar '
  'to single-asset scheme SPVs, whose investment property IS the scheme '
  'and whose fair-value note must therefore state what the valuation '
  'assumes. Never collapsed into a site capacity column.';
