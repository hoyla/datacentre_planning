"""What a fetch attempt may conclude, and what it may never conclude.

`none_published` is settled — it removes an application from the queue
for good — so the failure that matters here is not an exception. It is a
run that finishes quietly having recorded "this register publishes
nothing" about a register that listed five documents and served none of
them. HISTORY calls this mistake's six earlier costumes the same
mistake; these tests assert the rule rather than the instances, so a
seventh cannot be introduced by adding a branch.
"""

from __future__ import annotations

import pytest

from dcp.acquisition_outcome import SETTLED, classify_outcome


def summary(**kw) -> dict:
    base = {"downloaded": 0, "errors": 0, "links_found": 0,
            "skipped_existing": 0, "error_class": None}
    base.update(kw)
    return base


class TestSettledNegativeIsEarned:
    """The rule: a settled negative requires a register that was read
    and listed nothing. Anything else keeps the application queued."""

    @pytest.mark.parametrize("s", [
        # The register listed documents and every one failed.
        summary(links_found=5, errors=5),
        # ... and the listing itself reported no error, which is what
        # made this reachable in the first place.
        summary(links_found=1, errors=1, error_class=None),
        # Nothing listed, but something failed on the way to finding out.
        summary(errors=3),
        # A partial retrieval.
        summary(links_found=5, downloaded=2, errors=3),
        # Nothing listed and the listing fetch itself failed.
        summary(error_class="http_403"),
    ])
    def test_a_failure_is_never_recorded_as_published_nothing(self, s):
        outcome, _ = classify_outcome(s)
        assert outcome != "none_published"
        assert outcome not in SETTLED, (
            f"{outcome!r} would take this application out of the queue")

    @pytest.mark.parametrize("error_class", [None, "no_documents"])
    def test_an_empty_register_read_cleanly_is_settled(self, error_class):
        outcome, detail = classify_outcome(
            summary(error_class=error_class))
        assert outcome == "none_published"
        assert detail == error_class

    def test_everything_already_held_is_success_not_emptiness(self):
        """Nothing downloaded this run because it was all downloaded last
        run. `downloaded == 0` alone must not imply an empty register."""
        outcome, _ = classify_outcome(
            summary(links_found=4, skipped_existing=4))
        assert outcome == "fetched"


class TestUnfinishedWorkStaysQueued:
    @pytest.mark.parametrize("s", [
        summary(links_found=5, downloaded=2),
        summary(links_found=5, downloaded=2, errors=3),
        summary(links_found=5, downloaded=1, skipped_existing=1, errors=3),
        summary(links_found=5, errors=5),
    ])
    def test_a_shortfall_against_the_listing_is_not_finished(self, s):
        outcome, detail = classify_outcome(s)
        assert outcome in ("partial", "error")
        assert outcome not in SETTLED
        if outcome == "partial":
            assert "of 5 listed" in detail

    def test_the_detail_says_how_many_failed(self):
        _, detail = classify_outcome(
            summary(links_found=5, downloaded=2, errors=3))
        assert "3 failed" in detail

    def test_a_complete_fetch_is_finished(self):
        outcome, detail = classify_outcome(
            summary(links_found=3, downloaded=3))
        assert (outcome, detail) == ("fetched", None)


class TestErrorsAreDescribed:
    def test_an_error_without_a_class_still_says_what_happened(self):
        outcome, detail = classify_outcome(summary(errors=4))
        assert outcome == "error"
        assert "4 document failures" in detail
