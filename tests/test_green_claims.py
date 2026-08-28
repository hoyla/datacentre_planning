"""The green-claims table's rules, which exist to stop a cheap reading.

Putting "100% renewable" beside an operator's on-site combustion is
worth reporting and easy to get wrong. These tests pin the four things
that keep it honest: the quote is the unit rather than a boolean, our
silence never renders as theirs, counts are floors, and a missing
permit is not a clean site.
"""

from __future__ import annotations

import pytest

from dcp import green_claims as gc


def _claim(op="Op", kind="powered", quote="100% renewable energy powered"):
    return gc.GreenClaim(op, "snap", kind, quote)


def test_the_committed_file_loads_and_every_quote_still_verifies():
    """The whole point of the snapshot contract: a page that changes
    fails the build rather than drifting. CyrusOne's LON1 capacity moved
    under us on 2026-08-28, so this is not hypothetical."""
    assert gc.validate() == []


def test_the_wording_is_carried_not_flattened():
    """'procurement' and 'powered' are different claims. A boolean
    column would delete the only thing worth reporting."""
    claims = {c.operator: c for c in gc.load_claims()}
    assert claims["Pulsant"].kind == "procurement"
    assert claims["CyrusOne"].kind == "powered"
    assert claims["VIRTUS Data Centres"].kind == "goal"
    for c in claims.values():
        assert len(c.quote) > 15, c.operator


def test_an_unknown_kind_fails_rather_than_defaulting(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text("claims:\n  - operator: X\n    snapshot: s\n"
                 "    kind: greenwashing\n    quote: something\n")
    with pytest.raises(gc.GreenClaimError, match="kind"):
        gc.load_claims(p)


def test_a_duplicate_operator_fails(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text("claims:\n"
                 "  - operator: X\n    snapshot: s\n    kind: powered\n    quote: aaaaaaaaaaaaaaaaaa\n"
                 "  - operator: X\n    snapshot: s\n    kind: goal\n    quote: bbbbbbbbbbbbbbbbbb\n")
    with pytest.raises(gc.GreenClaimError, match="duplicate"):
        gc.load_claims(p)


def test_a_moved_quote_is_reported_not_silently_dropped(tmp_path):
    (tmp_path / "snap.txt").write_text("the page now says something else")
    problems = gc.verify_quotes([_claim()], snapshot_dir=tmp_path)
    assert len(problems) == 1 and "quote not found" in problems[0]


def test_a_missing_snapshot_is_reported(tmp_path):
    problems = gc.verify_quotes([_claim()], snapshot_dir=tmp_path)
    assert len(problems) == 1 and "missing" in problems[0]


def test_our_silence_never_renders_as_theirs():
    """The row that matters most. 'No site matched' is a gap in this
    project's matching; 'none disclosed' is a statement about their
    documents. Rendering both as 'none' would let a reader take our
    coverage for their cleanliness."""
    unmatched = gc.OperatorRow(claim=_claim(), sites=())
    matched = gc.OperatorRow(claim=_claim(), sites=("SITE-A",))
    assert "no site matched" in unmatched.generation_use
    assert "none disclosed" in matched.generation_use
    assert unmatched.generation_use != matched.generation_use
    assert unmatched.evidence_is_thin and matched.evidence_is_thin


def test_chp_is_named_separately_from_standby():
    """CHP implies permanent generation with a heat offtake, which is a
    different emissions picture from standby plant."""
    standby = gc.OperatorRow(claim=_claim(), sites=("A",), fuels=(("Diesel", 1),))
    both = gc.OperatorRow(claim=_claim(), sites=("A",), fuels=(("Gas", 1),), chp_sites=2)
    only = gc.OperatorRow(claim=_claim(), sites=("A",), chp_sites=1)
    assert standby.generation_use == "standby / backup"
    assert "CHP at 2 sites" in both.generation_use
    assert only.generation_use == "CHP (permanent generation)"


def test_a_missing_permit_is_not_a_clean_site():
    """The 50 MWth threshold means an operator can hold generators and
    no permit. The caveat has to say so in the reader's own words."""
    row = gc.OperatorRow(claim=_claim(), sites=("A",), fuels=(("Diesel", 1),))
    assert not row.has_permit
    assert "50 MWth" in gc.PERMIT_THRESHOLD_CAVEAT
    assert "not evidence of a cleaner site" in gc.PERMIT_THRESHOLD_CAVEAT


def test_the_regulatory_caveat_states_the_500_hour_threshold():
    assert "500 hours" in gc.REGULATORY_CAVEAT
    assert "Emission limit values" in gc.REGULATORY_CAVEAT
    assert "not standby generators running" in gc.REGULATORY_CAVEAT


def test_counts_are_described_as_floors():
    assert "floors" in gc.COUNT_CAVEAT
    assert "not added" in gc.COUNT_CAVEAT
