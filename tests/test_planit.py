"""PlanIt adapter unit tests. No live API; uses httpx MockTransport replaying a cached sample."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dcp.sources import planit


SAMPLE = Path(__file__).parent.parent / "data/planit_exploration/sample_data_centre.json"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Return the cached sample for any /api/applics/* request; small fixture for /api/areas/."""
    if "/applics/" in request.url.path:
        body = SAMPLE.read_bytes()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})
    if "/areas/" in request.url.path:
        # Minimal one-area fixture; mark as last page (records < pg_sz).
        fixture = {
            "from": 1, "to": 1, "total": 1, "secs_taken": 0.0,
            "records": [
                {
                    "area_name": "Northumberland (County)",
                    "long_name": "Northumberland County Council",
                    "gss_code": "E06000057",
                    "parent_name": "North East",
                    "in_region": "North East",
                    "scraper_type": "Idox",
                    "scraper_name": "Northumberland",
                    "planning_url": "https://publicaccess.northumberland.gov.uk/online-applications/",
                    "total": 104972,
                    "min_date": "2000-01-05",
                    "max_date": "2026-05-11",
                    "is_planning": True,
                    "has_planning": True,
                }
            ],
        }
        return httpx.Response(200, content=json.dumps(fixture).encode())
    return httpx.Response(404)


@pytest.fixture
def mock_client() -> planit.PlanItClient:
    client = planit.PlanItClient(delay_seconds=0.0)
    client.client = httpx.Client(transport=httpx.MockTransport(_mock_handler), timeout=30.0)
    return client


def test_iter_areas_yields_pages_until_partial(mock_client):
    pages = list(mock_client.iter_areas(pg_sz=100))
    assert len(pages) == 1
    assert pages[0].data["records"][0]["gss_code"] == "E06000057"


def test_iter_applications_yields_first_page(mock_client):
    pages = list(mock_client.iter_applications(start_date="2018-01-01", pg_sz=100))
    # Sample fixture has 5 records < pg_sz=100, so one page.
    assert len(pages) == 1
    recs = pages[0].data["records"]
    assert len(recs) == 5
    first = recs[0]
    # Spot-check we still have the Cambois/Blyth variation
    assert "Cambois" in first["address"]
    assert first["associated_id"] == "24/04112/OUTES"


def test_client_enforces_delay(monkeypatch):
    """A second call after a no-op delay should not sleep beyond the configured interval."""
    sleeps: list[float] = []
    monkeypatch.setattr(planit.time, "sleep", lambda s: sleeps.append(s))

    c = planit.PlanItClient(delay_seconds=0.5)
    c.client = httpx.Client(transport=httpx.MockTransport(_mock_handler), timeout=30.0)
    c.get("/areas/json", {"pg_sz": 1, "page": 1})
    c.get("/areas/json", {"pg_sz": 1, "page": 2})

    # The second call should have slept ~the configured delay; first call has none.
    assert any(s > 0 for s in sleeps), "expected at least one sleep between calls"


def test_cache_get_short_circuits_fetch():
    """When cache_get returns bytes for a URL, the HTTP client is never invoked."""
    cached_body = SAMPLE.read_bytes()
    transport_calls = []

    def boom_handler(request):
        transport_calls.append(request.url)
        return httpx.Response(500, content=b"should not be reached")

    c = planit.PlanItClient(
        delay_seconds=0.0,
        cache_get=lambda url: cached_body if "/applics/" in url else None,
    )
    c.client = httpx.Client(transport=httpx.MockTransport(boom_handler), timeout=30.0)

    resp = c.get("/applics/json", {"search": '"data centre"', "pg_sz": 100, "page": 1})
    assert resp.cached is True
    assert resp.raw == cached_body
    assert resp.data["records"][0]["associated_id"] == "24/04112/OUTES"
    assert transport_calls == [], "transport must not be invoked on cache hit"


def test_cache_get_falls_through_on_miss():
    """When cache_get returns None, the HTTP client handles the request normally."""
    c = planit.PlanItClient(
        delay_seconds=0.0,
        cache_get=lambda url: None,
    )
    c.client = httpx.Client(transport=httpx.MockTransport(_mock_handler), timeout=30.0)
    resp = c.get("/applics/json", {"search": "x", "pg_sz": 100, "page": 1})
    assert resp.cached is False
    assert len(resp.data["records"]) == 5
