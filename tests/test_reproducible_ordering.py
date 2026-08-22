"""Ordering that does not depend on the order the rows arrived in.

A release is checked by diffing it against the one before, so anything
that reorders itself between two builds of an unchanged database is noise
in the one instrument that catches regressions — and worse than noise
when the reordering decides what is *shown* rather than merely where.

Both halves of that had gone wrong. In SQL, a window `ORDER BY` that did
not fully determine its order let the cut at `FINDINGS_PER_SITE` fall in
a different place on each build: two consecutive builds disagreed about
the contents of 32 site panels. In Python, `sorted` is stable, so ranked
labels tied on their counts came out in the order the passages happened
to arrive from an unordered `array_agg` — putting "Air-cooled (11), Free
cooling (11)" on one build and the reverse on the next, in the workbook's
Cooling method column and in the reader panel alike.

The SQL half is enforced by the queries themselves (every ordering that
selects or ranks ends in a unique column) and by
tests/test_export_ordering.py. This is the Python half: the ranked-label
helpers must be indifferent to the order of their input.

Written on 2026-08-21 in a worktree that was never committed, and
recovered from it on 2026-08-22 while clearing that worktree away. The
fix it was written against was independently redone in the meantime;
this test was not, and it is the better one — rotating the input is a
property, where asserting a particular output is an example. It fails on
three of five cases with the tie-break removed, which is three more than
anything written for the Python half the second time round.
"""

from __future__ import annotations

from dcp import site_profile


def _rotations(seq):
    """Every rotation of `seq` — a cheap stand-in for arbitrary row order."""
    return [seq[i:] + seq[:i] for i in range(len(seq))]


class TestRankedLabelsIgnoreInputOrder:
    def test_cooling_methods_tied_on_count_keep_one_order(self):
        """Two methods named once each must not swap between builds."""
        texts = ["the units are air-cooled", "free cooling is used in winter"]
        labels = {site_profile.cooling_profile(t)[0] for t in _rotations(texts)}
        assert len(labels) == 1, labels
        # Both survive the secondary floor, and the tie-break is
        # alphabetical. Asserted by position rather than by the whole
        # string, so the test is about the order and not about how
        # ranked_label happens to word a count.
        label = labels.pop()
        assert label.index("Air-cooled") < label.index("Free cooling")

    def test_a_three_way_cooling_tie_is_also_fixed(self):
        texts = ["adiabatic coolers proposed",
                 "free air cooling considered",
                 "dry cooler array on the roof"]
        labels = {site_profile.cooling_profile(t)[0] for t in _rotations(texts)}
        assert len(labels) == 1, labels

    def test_a_genuine_majority_still_leads(self):
        """The tie-break orders equals; it must not outrank the count."""
        texts = ["chilled water plant", "chiller replacement",
                 "chillers serving the halls", "air-cooled condensers"]
        label, _ = site_profile.cooling_profile(texts)
        assert label.startswith("Water-cooled / chilled water (3 mentions)")

    def test_fuels_tied_on_count_keep_one_order(self):
        texts = ["diesel generators on site", "an HVO alternative was costed"]
        ranked = {tuple(site_profile.fuels_for(t)[0]) for t in _rotations(texts)}
        assert len(ranked) == 1, ranked

    def test_fuel_counts_still_rank_above_the_tie_break(self):
        texts = ["diesel generators", "red diesel storage",
                 "biomass was discounted"]
        ranked, _ = site_profile.fuels_for(texts)
        assert ranked[0] == ("Diesel", 2)
