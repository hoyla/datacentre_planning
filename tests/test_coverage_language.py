"""Tests for the sentences that tell a reader what is and is not known.

These strings are the difference between "we looked and found nothing"
and "we have not looked", which is the distinction this dataset is most
often going to be misread on. They are also the sort of thing that rots
quietly, so the tests assert the distinctions rather than the wording.
"""

from __future__ import annotations

from dcp import origin, site_profile, site_scale


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


class TestPowerEstimateCoverage:
    """The no-capacity caveat may only claim "read in full" when the
    coverage numbers say so. The published reader once asserted it on 173
    sites whose own banner said reading was incomplete.
    """

    def _est(self, **kw):
        return site_scale.power_estimate(has_documents=True, **kw)

    def test_fully_read_site_keeps_the_null_result(self):
        est = self._est(prose_held=12, prose_read=12)
        assert "read in full" in est.caveat
        assert "notable" in est.caveat

    def test_unread_site_reports_the_reading_gap_not_a_null_result(self):
        est = self._est(prose_held=12, prose_read=0)
        assert "read in full" not in est.caveat
        assert "notable" not in est.caveat
        assert est.basis == "Not yet analysed"
        assert "reading gap" in est.caveat

    def test_partly_read_site_states_its_fraction_and_stays_provisional(self):
        est = self._est(prose_held=2614, prose_read=1927)
        assert "read in full" not in est.caveat
        assert "notable" not in est.caveat
        assert "1,927" in est.caveat and "2,614" in est.caveat
        assert "provisional" in est.caveat

    def test_unknown_coverage_never_claims_a_full_reading(self):
        """A caller that cannot say how much was read must not let the
        caveat claim everything was."""
        est = self._est()
        assert "read in full" not in est.caveat
        assert "notable" not in est.caveat

    def test_no_documents_branch_is_unchanged_by_coverage(self):
        est = site_scale.power_estimate(has_documents=False,
                                        prose_held=0, prose_read=0)
        assert est.basis == "No documents held"

    def test_a_disclosed_figure_is_untouched_by_coverage(self):
        est = site_scale.power_estimate(it_load_mw=45, has_documents=True,
                                        prose_held=10, prose_read=1)
        assert est.value_mw == 45.0
        assert est.basis == "Disclosed IT load"


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


class TestCoverageArgsAreProseCounts:
    """Three functions decide how much of a site has been read, and all
    three must be given prose counts rather than every document held.

    Passed totals, each one describes a site as partly read because it
    holds drawings the deep read skips by design. That was shipped once:
    the reader said 78% and 201 of 302 sites, the workbook hedged the
    capacity caveat on 78 sites whose prose was complete, and the null
    result those sites actually represent — a consented data centre
    disclosing no power figure — was displaced by "reading is
    incomplete". The parameters on power_estimate are named prose_held
    and prose_read so that passing the wrong quantity is visible at the
    call site; this test is the same guard for the other two.
    """

    def test_power_estimate_takes_prose_named_arguments(self):
        import inspect
        params = inspect.signature(site_scale.power_estimate).parameters
        assert "prose_held" in params and "prose_read" in params
        assert "docs_held" not in params and "docs_read" not in params

    def test_call_sites_pass_prose_counts(self):
        import pathlib
        import re
        for name in ("scripts/export_reader.py", "scripts/export_handover.py"):
            src = pathlib.Path(name).read_text()
            for fn, args in (("power_estimate", ("prose_held=p_held",
                                                 "prose_read=p_read")),
                             ("provisional", ("(p_held, p_read)",)),
                             ("capacity_status", ("docs_held=p_held",
                                                  "docs_read=p_read"))):
                if fn not in src:
                    continue
                for frag in args:
                    assert frag in re.sub(r"\s+", " ", src) or frag in src, (
                        f"{name}: {fn} is not being given prose counts "
                        f"({frag!r} missing)")


class TestMentionCountsAreNotPlant:
    """A bracketed count says how often the documents say a thing.

    Nothing else on the same panel does. "Standby generators: 109" beside
    "Diesel (147), HVO (39)" was read by a reporter as 147 diesel engines
    and 39 HVO ones inside a total of 109, which is the natural reading of
    two numbers that look alike and are never told apart. Both figures
    were correct; neither said what it counted.

    These assert the distinction rather than the wording: that the leading
    bracket names its unit, that the plant count carries its own, and that
    the reader passes these fields through the formatter that subdues them.
    """

    def test_the_leading_bracket_names_what_it_counts(self):
        label = site_profile.ranked_label(
            [("Diesel", 147), ("HVO", 39)], site_profile.FUEL_SECONDARY_FLOOR)
        assert label.startswith("Diesel (147 mentions)")
        # Named once, not four times: the noun establishes the kind for the
        # line, and repeating it buries the fuels it exists to qualify.
        assert label.count(site_profile.MENTION_NOUN) == 1
        assert "HVO (39)" in label

    def test_a_minor_entry_is_referenced_rather_than_counted(self):
        label = site_profile.ranked_label(
            [("Diesel", 147), ("HVO", 39), ("Hydrogen / fuel cell", 4)],
            site_profile.FUEL_SECONDARY_FLOOR)
        assert "also referenced: Hydrogen / fuel cell" in label
        assert "(4)" not in label

    def test_empty_ranking_says_nothing(self):
        assert site_profile.ranked_label([], 0.15) == ""

    def test_fuels_cooling_and_parties_all_declare_the_unit(self):
        """One claim, three columns. It has been fixed in two before."""
        fuels = site_profile.GeneratorProfile(
            109, [("Diesel", 147), ("HVO", 39)], False, "").fuel_label
        cooling, _ = site_profile.cooling_profile(
            ["adiabatic cooling", "adiabatic and chilled water"])
        for label in (fuels, cooling):
            assert site_profile.MENTION_NOUN in label

    def test_chp_survives_the_shared_builder(self):
        prof = site_profile.GeneratorProfile(
            5, [("Gas", 20)], True, "")
        assert prof.fuel_label == "Gas (20 mentions) — CHP"

    def test_no_fuels_means_no_chp_suffix(self):
        """The suffix once qualified a label that did not exist."""
        assert site_profile.GeneratorProfile(5, [], True, "").fuel_label == ""

    def test_the_generator_caveat_separates_plant_from_mentions(self):
        prof = site_profile.generator_profile([12, 109], ["diesel generator"])
        assert prof.count == 109
        assert "plant" in prof.caveat
        assert "mention" in prof.caveat or "passages" in prof.caveat

    def test_the_reader_subdues_counts_and_units_its_plant(self):
        import pathlib
        import re
        src = re.sub(r"\s+", " ", pathlib.Path("scripts/export_reader.py").read_text())
        # The plant count says what it is a count of.
        assert "generator_count')) + ' units'" in src
        # Every ranked label goes through the formatter, not bare esc().
        for field in ("generator_fuel", "cooling_method",
                      "applicants", "advisers", "authorities"):
            assert f"counted(prof.get('{field}'))" in src, (
                f"{field} is rendered without subduing its mention counts")
        assert ".mcount{" in src


class TestOneDefinitionOfIntendedToBeRead:
    """Sampled-by-design is not a backlog, and must not be counted as one.

    The repetitive tier — objections, neighbour comments, petitions,
    correspondence — is read at 1-in-5 deliberately. The reader's
    coverage figure filtered on `classify_kind` alone, which knows
    nothing about that, so 4,204 documents policy never intends to read
    were published as prose awaiting analysis: 99% coverage rendered as
    89% and falling. The cohort query had the mirror-image fault, sampling
    a different fifth because it filtered before planning.
    """

    def test_sampling_is_computed_over_the_whole_set_not_a_filtered_one(self):
        """Filter-then-plan and plan-then-filter must agree on the fifth."""
        from dcp import deepread_select as sel
        docs = [{"application_ref": "X/1", "sha": f"s{i}",
                 "kind": "objection"} for i in range(10)]
        full = sel.plan_documents(docs)
        chosen = {d["sha"] for d, p in zip(docs, full) if p.will_read}
        # The same documents, planned after someone dropped the first two.
        subset = docs[2:]
        refiltered = {d["sha"] for d, p in zip(subset,
                                               sel.plan_documents(subset))
                      if p.will_read}
        assert chosen != refiltered, (
            "if these agree the test no longer demonstrates the hazard "
            "universe_plan exists to remove")
        assert chosen == {"s0", "s5"}

    def test_a_sampled_out_document_is_not_will_read(self):
        from dcp import deepread_select as sel
        docs = [{"application_ref": "X/1", "sha": f"s{i}",
                 "kind": "public comment"} for i in range(5)]
        plans = sel.plan_documents(docs)
        assert sum(p.will_read for p in plans) == 1
        assert all(p.tier == "C" for p in plans)
        assert "1-in-5" in [p.reason for p in plans if p.sampled_out][0]

    def test_a_named_drawing_is_skipped_and_a_statement_is_not(self):
        from dcp import deepread_select as sel
        assert sel.classify_kind("Site Location Plan")[0] == "skip"
        assert sel.classify_kind("Supporting Statement")[0] == "A"

    def test_bare_plan_kinds_are_not_recognised_as_drawings(self):
        """Recorded because it is the cause of a live 231-document residue.

        DRAWING_KINDS matches 'location plan' and 'block plan' but not a
        council that files the same thing as 'Plans' or 'OS Extract'.
        Those land in tier B, are counted as prose that ought to be read,
        extract to no words at all, and sit in the outstanding column for
        ever. Widening the pattern is not obviously right — a plan can
        carry an annotation schedule worth reading — so this asserts the
        behaviour rather than asking for it, and fails loudly if someone
        changes it without deciding to.
        """
        from dcp import deepread_select as sel
        for kind in ("Plans", "Site Plan", "OS Extract"):
            assert sel.classify_kind(kind)[0] == "B", kind

    def test_both_consumers_ask_the_same_function(self):
        """The two callers that disagreed now share one definition."""
        import pathlib
        import re
        for name in ("scripts/export_reader.py",
                     "scripts/deepread_escalate_openai.py"):
            src = re.sub(r"\s+", " ", pathlib.Path(name).read_text())
            assert "universe_plan(" in src, (
                f"{name} derives coverage without the shared plan")

    def test_the_batch_builder_counts_what_it_cannot_build(self):
        """245 selected, 3 built, and it used to say nothing about 242."""
        import pathlib
        src = pathlib.Path("scripts/deepread_escalate_openai.py").read_text()
        for reason in ("cache missing", "cache unreadable",
                       "no extractable text"):
            assert f'"{reason}"' in src
        assert "selected documents cannot be " in src


class TestUnreadableIsNotUnread:
    """A document with no words is not a document awaiting analysis.

    231 documents are held, classified as prose, and contain nothing:
    photographs of site notices, plans filed as JPEGs. Both tesseract and
    Apple Vision read them as blank, so no further pass moves them.
    Counted as "not yet analysed" they were a residue that never cleared
    and implied a backlog that did not exist.
    """

    def test_the_reader_separates_no_text_from_not_yet_read(self):
        import pathlib
        import re
        src = re.sub(r"\s+", " ", pathlib.Path("scripts/export_reader.py").read_text())
        assert "read_state='no_text'" in src
        assert "if no_text and not was_read:" in src
        # ...and says so on the page rather than only in the arithmetic.
        assert "contain no words at all" in src

    def test_recording_a_verdict_is_its_own_action(self):
        """A dry run that quietly wrote rows would be the worse trap."""
        import pathlib
        src = pathlib.Path("scripts/deepread_escalate_openai.py").read_text()
        assert "--record-no-text" in src
        assert "requires --model" in src
        # It must not be reachable from the estimate-only path.
        assert "if args.record_no_text:" in src

    def test_the_log_writer_takes_a_model_rather_than_assuming_one(self):
        """One upsert, many readers. A second copy is how not_extracted
        outlived the extraction that fixed it."""
        import inspect
        import pathlib
        src = pathlib.Path("scripts/deepread_run.py").read_text()
        assert "model: str | None = None" in src
        assert "model or MODEL_TAG" in src
        assert src.count("INSERT INTO deepread_log") == 1, (
            "a second INSERT into deepread_log means a second upsert "
            "policy, which is the bug this guards")
        del inspect


class TestOnlyAPdfHasPages:
    """`evidence_page` is the thing a reporter follows to check a quote.

    A .docx has no pages until something renders it, so the extractor
    records the index of a section; a workbook's is a sheet, a deck's a
    slide. 17,724 findings cite an index that is not a page, and every
    artefact called it one. Told "page 3" of a spreadsheet a reporter
    opens the file, finds no page 3, and doubts the quote rather than the
    label.
    """

    def test_each_kind_is_named_in_the_singular(self):
        from dcp import extract
        assert extract.cite_page(4, "pages") == "page 4"
        assert extract.cite_page(4, "sections") == "section 4"
        assert extract.cite_page(2, "sheets") == "sheet 2"
        assert extract.cite_page(5, "slides") == "slide 5"

    def test_an_unrecorded_pagination_gives_a_bare_number_not_a_guess(self):
        """Most such documents are PDFs. "Most" is not a provenance claim."""
        from dcp import extract
        assert extract.cite_page(4, None) == "4"
        assert extract.cite_page(4, "") == "4"
        assert extract.cite_page(4, "something-new") == "4"

    def test_no_page_cites_nothing(self):
        from dcp import extract
        assert extract.cite_page(None, "pages") == ""
        assert extract.cite_page("", "sections") == ""

    def test_page_zero_is_still_a_citation(self):
        """0 is falsy and is a real index; it must not vanish."""
        from dcp import extract
        assert extract.cite_page(0, "sections") == "section 0"

    def test_the_vocabulary_matches_the_loader_table(self):
        """The nouns and the labels extract.py writes cannot drift apart."""
        from dcp import extract
        written = {p for _loader, p in extract._LOADERS.values()}
        written.add("pages")
        assert written <= set(extract._PAGINATION_NOUN), (
            f"no singular noun for {written - set(extract._PAGINATION_NOUN)}")

    def test_the_csv_and_the_notebook_share_a_header(self):
        """They are one artefact in two renderings, and only a comment
        said so. This is the assertion that comment implied."""
        import pathlib
        import re
        import sys
        sys.path.insert(0, "scripts")
        csv_src = pathlib.Path("scripts/build_drive_staging.py").read_text()
        m = re.search(r"w\.writerow\(\[(.*?)\]\)", csv_src, re.S)
        assert m, "could not find the findings CSV header"
        header = re.findall(r'"([^"]+)"', m.group(1))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "nb", "scripts/export_notebook_bundle.py")
        nb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nb)
        assert header == nb.COLUMNS

    def test_the_exports_carry_the_pagination(self):
        import pathlib
        for name in ("scripts/build_drive_staging.py",
                     "scripts/export_duckdb.py"):
            src = pathlib.Path(name).read_text()
            assert "pagination" in src, name
