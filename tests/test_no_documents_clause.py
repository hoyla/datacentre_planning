"""A site's coverage says what was never there to read.

The coverage fraction is documents read over documents held, so an
application that yielded no documents contributes to neither side and
cannot lower it: a site reads 10 of 10 whether its second application
was checked and found empty, refused, behind a login, on a portal
nothing here can read, or never tried. Measured 2026-09-06: nine sites
read 100% complete while holding such an application, five of them in
the published "Read in full, and silent on capacity" cohort, whose claim
inherited the gap. LD14 was the worked case — 10 of 10 read, and its
EIA screening request settled empty on an adapter's coerced list until
the legacy store said so itself. The number was right; nothing on the
page could have said why.

The fraction stays as it is. Beside it, a clause names the document-less
applications by the kind of not-knowing each is.
"""

from __future__ import annotations

from pathlib import Path

from dcp import site_profile as sp

ROOT = Path(__file__).resolve().parent.parent


class TestTheClause:
    def test_nothing_to_say_when_every_application_holds_something(self):
        assert sp.no_documents_clause([]) == ""

    def test_one_application_checked_and_empty(self):
        assert sp.no_documents_clause(["none_published"]) == \
            "1 application holds no documents: 1 checked and empty"

    def test_classes_are_named_separately_and_in_a_fixed_order(self):
        """Never one number: a refusal and a council that publishes
        nothing are different things to chase. Fixed order so two builds
        of one corpus say it the same way."""
        got = sp.no_documents_clause(["no_adapter", "none_published", "login_required",
                                      "none_published", None, "portal_blocked", "error"])
        assert got == ("7 applications hold no documents: 2 checked and empty, "
                       "1 refused by the portal, 1 behind a login, "
                       "1 on a portal not yet readable, 1 retrieval failed, will retry, "
                       "1 not yet retrieved")

    def test_no_recorded_outcome_reads_as_not_yet_retrieved(self):
        """Nobody looked is not nothing there."""
        assert sp.no_documents_clause([None, "something_unknown"]) == \
            "2 applications hold no documents: 2 not yet retrieved"

    def test_every_settled_class_has_a_phrase(self):
        from dcp.acquisition_outcome import SETTLED
        for cls in SETTLED:
            assert cls in sp.NO_DOCUMENTS_PHRASE, cls


class TestItReachesTheSurfaces:
    def test_the_site_page_renders_it_beside_the_fraction(self):
        src = (ROOT / "scripts" / "export_reader.py").read_text()
        assert "site_profile.no_documents_clause(" in src

    def test_the_cohort_limits_carry_the_same_clause(self):
        from dcp import site_cohorts as sc
        c = next(c for c in sc.REGISTRY if c.key == "read_in_full_silent")
        assert "never obtained" in c.limits and "The site page names them" in c.limits
        assert c.rule_version == "2026-08-23.1", "limits prose is not the rule"
