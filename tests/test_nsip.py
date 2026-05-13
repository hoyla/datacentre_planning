"""NSIP CSV adapter unit tests. No live API."""

from __future__ import annotations

import csv
import io

import pytest

from dcp.sources import nsip


def test_parse_gps_apostrophe_prefix():
    """The NSIP CSV prepends an apostrophe to GPS coords to preserve the negative
    sign when viewed in Excel — strip and parse correctly."""
    lng, lat = nsip._parse_gps("'-0.5945505216141749, 51.58726008957555")
    assert lng == pytest.approx(-0.5945505216141749)
    assert lat == pytest.approx(51.58726008957555)


def test_parse_gps_empty_and_invalid():
    assert nsip._parse_gps(None) == (None, None)
    assert nsip._parse_gps("") == (None, None)
    assert nsip._parse_gps("garbage") == (None, None)


def test_is_dc_relevant_matches_description_or_name():
    assert nsip._is_dc_relevant({"Project name": "SDC M40 Campus", "Description": "data centre campus..."})
    assert nsip._is_dc_relevant({"Project name": "Data Centre Project", "Description": ""})
    # Wapseys Wood description includes "data centre campus"
    assert nsip._is_dc_relevant({
        "Project name": "SDC M40 Campus",
        "Description": "The overall scheme comprises a data centre campus...",
    })


def test_is_dc_relevant_rejects_unrelated_generating_station():
    assert not nsip._is_dc_relevant({
        "Project name": "Net Zero Teesside",
        "Description": "Gas-fired generating station with carbon capture",
    })
    assert not nsip._is_dc_relevant({
        "Project name": "East Anglia ONE Offshore Wind",
        "Description": "Offshore wind farm with onshore substation",
    })


def test_csv_row_to_app_maps_wapseys_wood_correctly():
    row = {
        "Project reference": "EN0110030",
        "Project name": "SDC M40 Campus",
        "Applicant name": "Slough Holdings UK Limited",
        "Application type": "EN01 - Generating Stations",
        "Region": "South East",
        "Location": "Buckinghamshire, England",
        "Grid reference - Easting": "497467",
        "Grid reference - Northing:": "188536",
        "GPS co-ordinates": "'-0.5945505216141749, 51.58726008957555",
        "Stage": "Pre-application",
        "Description": "data centre campus of up to three units",
        "Anticipated submission period": "January 2027",
        "Date of application": "",
        "Date application accepted": "",
        "Date Examination started": "",
        "Examining Authority's anticipated close of examination": "",
        "Date Examination closed": "",
        "Date of recommendation": "",
        "Date of decision": "",
        "Date withdrawn": "",
    }
    app = nsip._csv_row_to_app(row)
    assert app["name"] == "EN0110030"
    assert app["uid"] == "EN0110030"
    assert app["description"] == "data centre campus of up to three units"
    assert app["address"] == "Buckinghamshire, England"
    assert app["app_state"] == "Pre-application"
    assert app["app_type"] == "EN01 - Generating Stations"
    assert app["start_date"] is None  # empty string → None
    assert app["location_x"] == pytest.approx(-0.5945505216141749)
    assert app["location_y"] == pytest.approx(51.58726008957555)
    assert app["url"].endswith("/projects/EN0110030")
    assert app["other_fields"]["applicant_name"] == "Slough Holdings UK Limited"
    assert app["other_fields"]["anticipated_submission_period"] == "January 2027"
