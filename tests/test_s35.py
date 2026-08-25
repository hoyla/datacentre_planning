"""Section 35 Directions watcher unit tests. No live API."""

from __future__ import annotations

from dcp.sources import s35


def test_is_dc_relevant_accepts_all_three_known_directions():
    # The three real DC directions as of August 2026, by search-result title.
    assert s35._is_dc_relevant(
        "Data Centre Campus, Wapseys Wood, Buckinghamshire: Section 35 Direction, Planning Act 2008",
        None,
    )
    assert s35._is_dc_relevant(
        "Data Centre Campus, Ampthill Road, Bedford in Central Bedfordshire: Section 35 Direction, Planning Act 2008",
        "Direction by the Secretary of State relating to a proposed business or commercial project: application by Questpit Limited.",
    )
    assert s35._is_dc_relevant(
        "Data Centre Campus, New Barn Road, Dartford: Section 35 Direction, Planning Act 2008",
        "Direction by the Secretary of State relating to a proposed business or commercial project: application by Burges Salmon LLP on behalf of CSE52 Limited.",
    )


def test_is_dc_relevant_rejects_non_dc_directions_and_guidance():
    # Real non-DC hits from the same search query.
    assert not s35._is_dc_relevant(
        "Project Union: East Coast - section 35 direction, Planning Act 2008", None)
    assert not s35._is_dc_relevant(
        "Heathrow West Terminal: section 35 direction, Planning Act 2008", None)
    assert not s35._is_dc_relevant(
        "Planning Act 2008: Guidance on powers to direct a project into or out of the NSIP regime",
        "Guidance on powers to direct a project into or out of the Nationally Significant Infrastructure Projects (NSIP) regime",
    )
    assert not s35._is_dc_relevant(
        "Lighthouse Green Fuels Project: section 35 direction, Planning Act 2008", None)


def test_slug_takes_last_path_segment():
    assert s35._slug(
        "/government/publications/data-centre-campus-new-barn-road-dartford-section-35-direction-planning-act-2008"
    ) == "data-centre-campus-new-barn-road-dartford-section-35-direction-planning-act-2008"
    assert s35._slug("/government/publications/foo/") == "foo"


def test_strip_html():
    assert s35._strip_html("<div><p>Direction under\nsection 35</p></div>") == \
        "Direction under section 35"
    assert s35._strip_html(None) == ""
    assert s35._strip_html("") == ""


def test_page_to_app_maps_quest_park_page():
    # Shape and values from the real Content API response for the Ampthill
    # Road (Quest Park) direction, verified 2026-08-25.
    page = {
        "base_path": "/government/publications/data-centre-campus-ampthill-road-bedford-in-central-bedfordshire-section-35-direction-planning-act-2008",
        "content_id": "59fb206c-a5f1-44c9-bc1d-eec34d9935b8",
        "document_type": "decision",
        "title": "Data Centre Campus, Ampthill Road, Bedford in Central Bedfordshire: Section 35 Direction, Planning Act 2008",
        "description": "Direction by the Secretary of State relating to a proposed business or commercial project: application by Questpit Limited.",
        "first_published_at": "2026-06-15T15:30:01+01:00",
        "public_updated_at": "2026-06-15T15:30:01+01:00",
        "details": {
            "document_type_label": "Decision",
            "body": "<div><p>Direction under section 35 of the Planning Act 2008.</p></div>",
            "attachments": [
                {
                    "title": "MHCLG decision letter",
                    "url": "https://assets.publishing.service.gov.uk/media/6a2fca4d1f6fa5c3377e5f27/MHCLG_Decision_Letter.pdf",
                    "content_type": "application/pdf",
                    "file_size": 197228,
                    "attachment_type": "file",
                },
                {
                    "title": "Request statement on behalf of Questpit Limited",
                    "url": "https://assets.publishing.service.gov.uk/media/6a2fc930c39255c595b5084f/Request_Statement_on_behalf_of_Questpit_Limited.pdf",
                    "content_type": "application/pdf",
                    "file_size": 7049969,
                    "attachment_type": "file",
                },
            ],
        },
    }
    app = s35._page_to_app(page)
    assert app["name"] == (
        "data-centre-campus-ampthill-road-bedford-in-central-bedfordshire-"
        "section-35-direction-planning-act-2008"
    )
    assert app["uid"] == app["name"]
    assert app["description"].startswith("Data Centre Campus, Ampthill Road")
    assert "Questpit Limited" in app["description"]
    assert "Direction under section 35" in app["description"]
    assert app["address"] is None
    assert app["app_state"] == "Section 35 Direction"
    assert app["app_type"] == "Decision"
    assert app["start_date"] == "2026-06-15"
    assert app["url"] == (
        "https://www.gov.uk/government/publications/data-centre-campus-"
        "ampthill-road-bedford-in-central-bedfordshire-section-35-direction-"
        "planning-act-2008"
    )
    atts = app["other_fields"]["attachments"]
    assert len(atts) == 2
    assert atts[0]["title"] == "MHCLG decision letter"
    assert atts[1]["file_size"] == 7049969
    assert app["other_fields"]["content_id"] == "59fb206c-a5f1-44c9-bc1d-eec34d9935b8"


def test_page_to_app_without_body_or_attachments():
    app = s35._page_to_app({
        "base_path": "/government/publications/some-direction",
        "title": "Some Data Centre Direction",
        "description": None,
        "first_published_at": "",
        "details": {},
    })
    assert app["name"] == "some-direction"
    assert app["description"] == "Some Data Centre Direction"
    assert app["start_date"] is None
    assert app["other_fields"]["attachments"] == []
