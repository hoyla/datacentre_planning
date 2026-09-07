"""The reference-list format, and the rule that gives it a point.

`scripts/ingest_planit_refs.py` exists because a scheme can be wholly
absent from a keyword sweep while its neighbour's paperwork names it by
reference (the Hemel Hempstead chain, 2026-09-07). The list is a
person's judgement written down, so the parser's job is to carry that
judgement — which cohort each reference belongs to — without inventing
one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "ingest_planit_refs",
    Path(__file__).parent.parent / "scripts" / "ingest_planit_refs.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_a_label_applies_to_the_refs_that_follow_it_and_no_others():
    parsed = mod.parse_ref_file(
        "# label: first\n"
        "Council/1/A\n"
        "Council/2/B\n"
        "# label: second\n"
        "Council/3/C\n")
    assert parsed == [("Council/1/A", "first"), ("Council/2/B", "first"),
                      ("Council/3/C", "second")]


def test_refs_before_any_label_take_the_default():
    assert mod.parse_ref_file("Council/1/A\n") == [("Council/1/A",
                                                    mod.DEFAULT_LABEL)]


def test_comments_and_blank_lines_are_not_references():
    parsed = mod.parse_ref_file(
        "# The two families the site 11 review found absent.\n"
        "\n"
        "   \n"
        "# label: fam\n"
        "Council/1/A\n"
        "# a trailing note\n")
    assert parsed == [("Council/1/A", "fam")]


def test_an_empty_label_falls_back_rather_than_tagging_with_nothing():
    parsed = mod.parse_ref_file("# label:\nCouncil/1/A\n")
    assert parsed == [("Council/1/A", mod.DEFAULT_LABEL)]


@pytest.mark.parametrize("path", [
    Path("data/priors/site_partitions.yaml"),
])
def test_every_hemel_ref_ingested_is_listed_in_a_partition(path):
    """The maintenance duty this script's docstring hands to the caller.

    A new application with no family edge cannot spatially join a
    partition: it lands in whichever unpartitioned site is in radius.
    So a reference fetched for a partitioned campus and left out of the
    file is a silent misplacement, which is the failure this asserts
    against — for the one cohort where it has already been done, so the
    next one has a shape to copy.
    """
    import yaml
    entries = yaml.safe_load(path.read_text())["partitions"]
    listed = {ref for e in entries for ref in (e.get("applications") or [])}
    # The chain Amazon's own Learning Lab application cites, plus the
    # cross-council screening opinion for its substation.
    for ref in ("Dacorum/4/01922/19/MFA", "Dacorum/22/01067/ROC",
                "Dacorum/24/00914/NMA", "StAlbans/5/2021/3548"):
        assert ref in listed, f"{ref} is ingested but in no partition"
