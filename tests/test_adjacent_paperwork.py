"""An adjacent-power scheme's own paperwork belongs beside the scheme.

`dcp.adjacent_power.staged_applications` decides what sits under
`adjacent_power/` on Drive: the schemes #252 took out of site membership,
and their discharges, amendments and variations — which the rubric calls
`not_dc`, correctly, because they are not data centres and their text
ties them only to their parent. Until 2026-09-02 that verdict put them in
the shortfall's "excluded by decision" while their parent had a folder.
"""

from __future__ import annotations

import pytest

from dcp import adjacent_power as ap
from dcp import repo, sites

PARENT = "Testing/24/2001/FUL"
CHILD = "Testing/24/2002/DISCON"
STRAY = "Testing/24/2003/FUL"
DC = "Testing/24/2004/FUL"


def _seed(conn, ref, verdict, *, description="x", lat=None, lon=None, doc=True):
    source_id = repo.ensure_source(conn, name="planit", kind="aggregator",
                                   base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": description,
             "location_y": lat, "location_x": lon},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO triage (application_id, model, verdict, raw_response) "
            "VALUES (%s, 'fake', %s, '{\"rubric\": \"dc_build\"}')",
            (app_id, verdict))
    if doc:
        repo.record_document(conn, application_id=app_id,
                             url=f"https://x/{ref}.pdf",
                             content_sha256=("%064x" % abs(hash(ref))),
                             bytes_path=f"data/raw/test/{ref}.pdf", kind="Decision")
    conn.commit()
    return app_id


@pytest.mark.integration
def test_a_schemes_discharge_is_staged_with_it_and_a_stray_not_dc_is_not(db_conn):
    parent = _seed(db_conn, PARENT, "adjacent_power", description="Substation")
    child = _seed(db_conn, CHILD, "not_dc",
                  description=f"Details pursuant to condition 3 of {PARENT}")
    stray = _seed(db_conn, STRAY, "not_dc", description="A warehouse")
    with db_conn.cursor() as cur:
        got = ap.staged_applications(cur)
    assert got[parent]["why"] == "verdict"
    assert got[child]["why"] == "paperwork" and got[child]["parent_ref"] == PARENT
    assert stray not in got, "a not_dc application with no adjacent parent stays out"


@pytest.mark.integration
def test_a_member_of_a_live_site_is_never_staged_under_adjacent_power(db_conn, tmp_path):
    """Membership decides sites/; only what is in no live site can be
    adjacent power's — a procedural discharge that clusters into a data
    centre site stays in that site's folder even if its parent is a
    substation."""
    dc = _seed(db_conn, DC, "new_build", description="data centre", lat=51.5, lon=-0.4)
    parent = _seed(db_conn, PARENT, "adjacent_power", description="Substation", lat=51.5, lon=-0.4)
    child = _seed(db_conn, CHILD, "procedural",
                  description=f"Details pursuant to condition 3 of {PARENT}", lat=51.5, lon=-0.4)
    clusters = sites.build_clusters(db_conn, data_dir=tmp_path)
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    members = {a["id"] for c in clusters for a in c["apps"]}
    assert child in members and parent not in members, "the veto keeps the substation out; the discharge is a member"
    with db_conn.cursor() as cur:
        got = ap.staged_applications(cur)
    assert parent in got and child not in got


@pytest.mark.integration
def test_an_application_holding_no_documents_is_not_listed(db_conn):
    parent = _seed(db_conn, PARENT, "adjacent_power", doc=False)
    with db_conn.cursor() as cur:
        assert parent not in ap.staged_applications(cur)
