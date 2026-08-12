"""Tests for the external aggregates that sit beside the planning data.

The figures are hand-transcribed from primary documents, which is exactly
the kind of entry that rots or typos silently. The tests assert internal
consistency — the banded table must sum to its own printed totals — and
the banding contract the comparison table depends on.
"""

from __future__ import annotations

from dcp import external_aggregates as ea


def test_ofgem_table_1_sums_to_its_own_totals():
    ea.check()


def test_every_aggregate_names_a_known_source():
    for agg in ea.AGGREGATES:
        assert agg.source_key in ea.SOURCES


def test_bands_partition_cleanly_at_the_edges():
    # A 10 MW site is a 10–50 MW site, not a 0–10 one; 500 MW is Hyper.
    assert ea.band_counts([9.99]) == [
        ("0–10 MW", 1), ("10–50 MW", 0), ("50–100 MW", 0),
        ("100–500 MW", 0), ("500 MW and above", 0)]
    assert ea.band_counts([10.0])[1] == ("10–50 MW", 1)
    assert ea.band_counts([500.0])[4] == ("500 MW and above", 1)
    assert ea.band_counts([None, None]) == [
        ("0–10 MW", 0), ("10–50 MW", 0), ("50–100 MW", 0),
        ("100–500 MW", 0), ("500 MW and above", 0)]


def test_sources_carry_full_provenance():
    for s in ea.SOURCES.values():
        assert s.url.startswith("https://")
        assert s.published and s.accessed and s.note
