"""Tests for portal classification.

This function decides which adapter is sent after an application, and
when it is wrong the failure is quiet: the application is filed as "no
adapter for this portal type" and leaves the queue, so a council we can
in fact read stops being asked. It also drives the outstanding-work
breakdown, which is how the size of the remaining job gets reported.

The cases here are the real URLs that were misfiled.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "fetch_dc_campaign",
    Path(__file__).parent.parent / "scripts" / "fetch_dc_campaign.py")
campaign = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(campaign)


@pytest.mark.parametrize("url,expected", [
    # Salesforce Lightning: each council picks its own object path, so
    # matching only /s/detail/ filed Anglesey as unreadable.
    ("https://ioacc.my.site.com/s/papplication/a1GR5000004uZyTMAU", "salesforce"),
    ("https://publicaccess.bracknell-forest.gov.uk/s/detail/a1DP300000BsBJLMA3",
     "salesforce"),
    # A hostname is not a product. Both of these live on a
    # planningexplorer.* host and neither is Northgate.
    ("https://planningexplorer.barnsley.gov.uk/Home/ApplicationDetails"
     "?planningApplicationNumber=2020%2F0517", "bespoke/other"),
    ("https://planningexplorer.charnwood.gov.uk/Assure/ES/Presentation/Planning/"
     "OnlinePlanning/OnlinePlanningOverview?applicationNumber=P%2F23%2F0050%2F2",
     "nec"),
    # Northgate proper, under either of its two vendor paths.
    ("https://eplanning.birmingham.gov.uk/Northgate/PlanningExplorer/Generic/"
     "StdDetails.aspx?PARAM0=1347654", "northgate"),
    ("https://planningrecords.camden.gov.uk/NECSWS/PlanningExplorer/Generic/"
     "StdDetails.aspx?PARAM0=400024", "northgate"),
    ("https://planningandbuilding.hounslow.gov.uk/lpassure/index.html", "nec"),
    ("https://publicaccess.argyll-bute.gov.uk/online-applications/"
     "applicationDetails.do?keyVal=Q58Q2XCHMZQ00", "idox"),
    ("https://www.example.gov.uk/ocellaweb/planningDetails?ref=1", "ocella"),
    ("https://slough.agileapplications.co.uk/planning/index.html", "agile"),
    (None, "no_url"),
])
def test_portal_family(url, expected):
    assert campaign.portal_family(url) == expected


def test_an_unknown_portal_is_named_rather_than_guessed():
    """Better an honest 'bespoke/other' than the wrong adapter.

    Sending an Idox adapter at a portal that merely looks Idox-shaped
    produces an empty document list, and an empty list is how an access
    failure gets recorded as "this council publishes nothing".
    """
    assert campaign.portal_family(
        "https://planning.example.gov.uk/some/unknown/path") == "bespoke/other"
