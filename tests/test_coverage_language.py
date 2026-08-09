"""Tests for the sentences that tell a reader what is and is not known.

These strings are the difference between "we looked and found nothing"
and "we have not looked", which is the distinction this dataset is most
often going to be misread on. They are also the sort of thing that rots
quietly, so the tests assert the distinctions rather than the wording.
"""

from __future__ import annotations

from dcp import origin, site_profile


class TestProvisional:
    def test_fully_read_site_is_not_provisional(self):
        assert site_profile.provisional(10, 10) == (False, "")
        assert site_profile.provisional_statement(10, 10) == ""

    def test_partly_read_site_reports_its_fraction(self):
        is_prov, note = site_profile.provisional(2614, 1927)
        assert is_prov
        assert "73%" in note
        statement = site_profile.provisional_statement(2614, 1927)
        assert "1,927" in statement and "2,614" in statement and "73%" in statement

    def test_the_statement_does_not_repeat_the_inline_marker(self):
        """The panel version is a sentence, not a footnote to itself.

        It once rendered as "(prior to complete deep read) — prior to
        complete deep read — from the 73% of documents…".
        """
        statement = site_profile.provisional_statement(2614, 1927)
        assert site_profile.PROVISIONAL_MARK not in statement
        assert "prior to complete deep read" not in statement.lower()

    def test_unread_site_says_absent_rather_than_zero(self):
        is_prov, note = site_profile.provisional(40, 0)
        assert is_prov
        assert "absent" in note
        assert "absent" in site_profile.provisional_statement(40, 0)

    def test_a_site_with_no_documents_is_not_provisional(self):
        """Nothing to be provisional about; the no-documents reason covers it."""
        assert site_profile.provisional(0, 0) == (False, "")


class TestNoDocumentsReason:
    def test_checked_and_empty_is_not_reported_as_a_gap(self):
        label, why = site_profile.no_documents_reason(["none_published"])
        assert "publishes no documents" in label.lower()
        assert "finished check" in why or "not an outstanding" in why

    def test_outstanding_work_outranks_finished_work(self):
        """Part-checked is not checked.

        A site with one register checked and another never attempted must
        report the untried one, or it reads as fully accounted for.
        """
        label, _ = site_profile.no_documents_reason(["none_published", "untried"])
        assert label == "Not yet retrieved"

    def test_missing_outcome_is_treated_as_untried(self):
        assert site_profile.no_documents_reason([])[0] == "Not yet retrieved"
        assert site_profile.no_documents_reason([None])[0] == "Not yet retrieved"

    def test_every_outcome_has_an_explanation(self):
        for key in site_profile.NO_DOCUMENT_REASONS:
            label, why = site_profile.no_documents_reason([key])
            assert label and len(why) > 40, key

    def test_pre_application_says_why_the_blanks_are_blank(self):
        _, why = site_profile.no_documents_reason(["pre_application"])
        assert "not that the scheme is small" in why


class TestOriginRoutes:
    def test_tags_reduce_to_readable_routes(self):
        assert origin.routes_for(["dc_keyword"]) == ["Keyword search"]
        assert origin.routes_for(["barbour:12345"]) == ["Barbour ABI"]
        assert origin.routes_for(
            ["spatial:Northumberland/24/04112/FUL"]) == ["Next to a known site"]

    def test_more_specific_prefixes_win(self):
        """'energy_national:' must not be swallowed by a looser rule."""
        assert origin.routes_for(
            ["energy_national:PTNO-12548129"]) == ["Energy search near a site"]

    def test_repeated_routes_collapse_but_distinct_ones_are_kept(self):
        got = origin.routes_for(["dc_keyword", "dc_keyword", "barbour:1"])
        assert got == ["Keyword search", "Barbour ABI"]

    def test_unknown_tags_are_dropped_rather_than_guessed(self):
        assert origin.routes_for(["something_new:42"]) == []

    def test_explain_covers_the_labels_it_is_given(self):
        note = origin.explain(["Keyword search"])
        assert "data-centre language" in note
        assert origin.explain([]) == ""
