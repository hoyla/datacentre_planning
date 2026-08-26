"""Tests for the offered-versus-stored audit.

The audit exists because a short fetch used to be recorded as complete,
so the failure mode it guards against is a *quiet* one: a number that
looks finished. These cases pin the three places it could go quiet
again — an absent listing reported as an empty one, a comparison that
counts the wrong side of the set difference, and a re-run that either
duplicates rows or refuses to record a changed listing.
"""

from __future__ import annotations

from dcp import relist_audit as ra

IDOX = ("https://publicaccess.glasgow.gov.uk/online-applications/"
        "applicationDetails.do?keyVal=ABC&activeTab=summary")
OCELLA = ("https://planning.hillingdon.gov.uk/OcellaWeb/planningDetails"
          "?reference=1331/APP/2017/1883&module=pl")
AGILE = ("https://planning.agileapplications.co.uk/islington/"
         "application-details/123456")
AIFUSION = ("https://plantech.centralbedfordshire.gov.uk/PLANTECH/DCWebPages/"
            "acolnetcgi.gov?ACTION=UNWRAP&TheSystemkey=618331")
SALESFORCE = ("https://development.wiltshire.gov.uk/pr/s/planning-application/"
              "a0i3z0000154iovAAA")


def test_listing_family_dispatches_on_the_adapters_own_predicates():
    assert ra.listing_family(IDOX) == "idox"
    assert ra.listing_family(OCELLA) == "ocella"
    assert ra.listing_family(AGILE) == "agile"
    assert ra.listing_family(AIFUSION) == "aifusion"
    assert ra.listing_family(SALESFORCE) == "salesforce_pr"
    assert ra.listing_family(
        "https://data.whitehorsedc.gov.uk/java/support/Main.jsp") is None
    assert ra.listing_family(None) is None


def test_newport_is_not_audited_as_idox():
    """Newport's URL is Idox-shaped and its documents tab serves an
    error page; its documents come from a separate store. Auditing it as
    Idox reported an empty register over 42 applications holding 700-odd
    documents — a measured zero where the listing is simply elsewhere."""
    newport = ("https://publicaccess.newport.gov.uk/online-applications/"
               "applicationDetails.do?keyVal=XYZ&activeTab=summary")
    assert ra.listing_family(newport) == "newport_docstore"
    # And it must not offer a documents-tab snapshot key, or the free
    # pass would re-file it as an empty Idox listing.
    assert ra.listing_key(newport, "newport_docstore") is None


def test_listing_key_is_the_documents_tab_not_the_summary_tab():
    """Auditing the summary tab would find no documents at all and file
    every Idox application as an empty register."""
    key = ra.listing_key(IDOX, "idox")
    assert "activeTab=documents" in key
    assert "activeTab=summary" not in key
    assert ra.listing_key(OCELLA, "ocella").endswith(
        "showDocuments?reference=1331/APP/2017/1883&module=pl")
    # Families whose listing is an API call have no snapshot key.
    assert ra.listing_key(AGILE, "agile") is None


def test_compare_counts_the_shortfall_not_the_overlap():
    listing = ra.Listing(offered=[{"url": "a"}, {"url": "b"}, {"url": "c"}])
    got = ra.compare(listing, {"a", "b", "z"})
    assert got["offered_count"] == 3
    assert got["stored_count"] == 3
    assert got["matched_count"] == 2
    assert got["missing_count"] == 1
    # "z" is held and not offered — diagnostic, never counted as missing.
    assert got["unmatched_stored_count"] == 1
    assert [m["url"] for m in got["missing"]] == ["c"]


def test_an_application_holding_nothing_is_all_shortfall():
    listing = ra.Listing(offered=[{"url": "a"}, {"url": "b"}])
    got = ra.compare(listing, set())
    assert got["missing_count"] == 2
    assert got["matched_count"] == 0


def test_absent_listing_is_not_an_empty_listing():
    """`no_listing` and `empty_listing` are opposite facts: one says
    nobody could look, the other says the register published nothing.
    Collapsing them is the mistake HISTORY records in six costumes."""
    absent = ra.listing_from_harvest("Some/Ref", {})
    assert absent.status == "no_listing"
    assert absent.offered == []

    empty = ra.listing_from_harvest("Some/Ref", {"Some/Ref": []})
    assert empty.status == "empty_listing"

    real = ra.listing_from_harvest(
        "Some/Ref", {"Some/Ref": [{"url": "https://x/1", "description": "Plan"}]})
    assert real.status == "audited"
    assert real.offered == [{"url": "https://x/1", "filename": "Plan",
                             "kind": "Plan"}]
    assert real.sha256


def test_content_key_is_the_body_hash_and_survives_a_missing_body():
    """Idempotency rests on this: the same listing re-read must produce
    the same key, and a repeated refusal must not accumulate rows."""
    body = ra.Listing(sha256="deadbeef", status="audited")
    assert ra._content_key(body) == "deadbeef"

    refusal = ra.Listing(status="host_skipped", detail="AWS WAF")
    again = ra.Listing(status="host_skipped", detail="AWS WAF")
    assert ra._content_key(refusal) == ra._content_key(again)
    # A different refusal is a different row.
    assert ra._content_key(refusal) != ra._content_key(
        ra.Listing(status="error", detail="AWS WAF"))


def test_a_withdrawn_application_is_not_an_empty_register():
    html = ("<html><body>This application is no longer available for "
            "viewing.</body></html>")
    listing = ra._parse_html_listing(
        html, key="https://x/docs", family="idox", source="snapshot",
        sha="abc", captured_at=None)
    assert listing.status == "withdrawn"
    assert listing.offered == []


def test_a_permission_denied_page_is_not_an_empty_register():
    """Idox serves "Permission Denied" with HTTP 200 and the council's
    full chrome, so nothing about the response says it is not a listing.
    Parsed, it yields no links — and no links reads as a register that
    publishes nothing. 66 rows in the audit store were this page.
    """
    html = ("<html><body><h1>Error</h1><p>Permission Denied</p>"
            "<p>You do not have permission to view the page. This could be "
            "because it is restricted to specific users.</p>"
            + "<p>chrome</p>" * 200 + "</body></html>")
    listing = ra._parse_html_listing(
        html, key="https://x/docs", family="idox", source="snapshot",
        sha="abc", captured_at=None)
    assert listing.status == "blocked"
    assert listing.offered == []
    assert "refusal" in (listing.detail or "")


def test_an_empty_body_is_not_an_empty_register():
    """Three Brighton snapshots are 212-byte bodies stored with a 200."""
    listing = ra._parse_html_listing(
        "<html><head></head><body></body></html>", key="https://x/docs",
        family="idox", source="snapshot", sha="abc", captured_at=None)
    assert listing.status == "blocked"


def test_length_never_overrules_links_that_parsed():
    """The length floor is weak evidence and must not beat the strong
    kind: a short body that yielded document links is a listing."""
    html = ("<table><tr><th>Document Type</th><th>Description</th></tr>"
            "<tr><td>1 Jan</td><td>Report</td><td>Energy statement</td>"
            "<td><a href='files/BB/pdf/energy.pdf'>View</a></td></tr>"
            "</table>")
    assert len(html) < ra.MIN_LISTING_BYTES
    listing = ra._parse_html_listing(
        html, key="https://x/online-applications/applicationDetails.do",
        family="idox", source="snapshot", sha="abc", captured_at=None)
    assert listing.status == "audited"
    assert len(listing.offered) == 1


def test_a_corrected_reading_can_land_beside_the_row_it_corrects():
    """The 66 refusal pages were already recorded `empty_listing`, keyed
    on the body hash. A `blocked` row for the same body must not be
    deduplicated away by the row it exists to supersede."""
    body_sha = "deadbeef"
    wrong = ra.Listing(sha256=body_sha, status="empty_listing")
    right = ra.Listing(sha256=body_sha, status="blocked",
                       detail="portal served a refusal page")
    assert ra._content_key(wrong) != ra._content_key(right)
    # ...and re-reading the same refusal is still a no-op.
    assert ra._content_key(right) == ra._content_key(
        ra.Listing(sha256=body_sha, status="blocked", detail="anything"))


def test_newport_distinguishes_an_unread_store_from_an_empty_one():
    """`fetch_doc_list` returns [] both when the docstore page carries no
    model and when the folder is genuinely empty — right for a
    downloader, and the seventh costume of the same mistake for a
    measurement. The parse now says which."""
    newport = ra._newport_module()
    assert newport.parse_doc_list("<html>session timed out</html>") is None
    assert newport.parse_doc_list('var model = {"rows": []}') == []
    assert newport.parse_doc_list(
        'var model = {"d":[{"Guid":"G1","Doc_Type":"Plan"}]}') == [
            ("G1", "Plan")]
    # The download path keeps its old shape: either way there is nothing
    # to fetch, so it must not start caring about the difference.
    assert newport.fetch_doc_list.__doc__


def test_coventry_is_skipped_by_name_with_a_reason():
    """A host we deliberately do not touch must record why, or its
    applications read as measured zeroes."""
    reason = ra.skip_reason(
        "https://planandregulatory.coventry.gov.uk/planning/index.html?id=1")
    assert reason and "WAF" in reason
    assert ra.skip_reason(IDOX) is None


def test_parsed_idox_listing_carries_every_direct_link():
    html = """
    <table>
      <tr><th>Date Published</th><th>Document Type</th><th>Description</th></tr>
      <tr><td>1 Jan</td><td>Plans</td><td>Site plan</td>
          <td><a href="/omt-server/omt.html#docKey=99">Measure</a>
              <a href="files/AA/pdf/site.pdf">View</a></td></tr>
      <tr><td>2 Jan</td><td>Report</td><td>Energy statement</td>
          <td><a href="files/BB/pdf/energy.pdf">View</a></td></tr>
    </table>
    """
    listing = ra._parse_html_listing(
        html, key="https://x/online-applications/applicationDetails.do",
        family="idox", source="snapshot", sha="abc", captured_at=None)
    assert listing.status == "audited"
    assert [d["kind"] for d in listing.offered] == ["Plans", "Report"]
    # The OMT viewer anchor must not become the document URL.
    assert all("docKey" not in d["url"] for d in listing.offered)
