-- Capacity sold, as distinct from capacity built or announced.
--
-- VIRTUS's property company reports a quantity none of the other
-- sources has: "181.8MW of the total design capacity was contracted to
-- customers, with 179.8MW billable to customers as of the year-end".
-- That is neither built capacity (what exists) nor announced capacity
-- (what is marketed) nor a contracted grid connection (what the network
-- agreed to supply). It is how much of the estate has been let.
--
-- It matters because it is the denominator the utilisation argument
-- actually wants. Against 233,133 MWh of energy consumed in the same
-- year — an average draw of about 26.5 MW — 179.8 MW of billable
-- capacity is running at roughly 15%. Built-capacity comparisons say
-- something about the operator; this one says something about the
-- customers, who are paying for capacity they are not drawing.
--
-- Kept as its own type rather than folded into built_capacity, for the
-- same reason every other quantity is kept apart: a column that mixed
-- "exists" with "is sold" would answer neither question.

ALTER TABLE capacity_claims DROP CONSTRAINT IF EXISTS capacity_claims_quantity_known;
ALTER TABLE capacity_claims ADD CONSTRAINT capacity_claims_quantity_known
  CHECK (quantity_type IN (
    'it_load', 'grid_connection', 'total_site', 'onsite_generation',
    'cooling', 'energy_storage', 'thermal_input',
    'built_capacity', 'metered_consumption', 'announced_capacity',
    'let_capacity'));
