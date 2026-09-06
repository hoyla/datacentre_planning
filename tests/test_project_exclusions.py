"""A Barbour project a person has excluded anchors nothing and joins nothing.

Exeter College's "Digital & Data Centre" is a teaching block (Use Class
D1, F1 today). Triage called its applications `not_dc`; the site existed
only because Barbour project 12425966 anchored it and the project-link
door admitted the paperwork whatever triage said, and the title rule
then settled its class as a data centre. Seven Barbour-anchored sites
hold nothing but `not_dc`/`procedural` applications, and some of them
are data centres, so this is decided by exception — one entry, its
evidence — never by rule (Luke, 2026-09-06).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dcp import repo, sites

ROOT = Path(__file__).resolve().parent.parent


def _priors(tmp_path, yaml_text: str | None) -> Path:
    d = tmp_path / "data"; (d / "priors").mkdir(parents=True, exist_ok=True)
    if yaml_text is not None:
        (d / "priors" / "project_exclusions.yaml").write_text(textwrap.dedent(yaml_text))
    return d


class TestTheFile:
    def test_absent_means_nothing_excluded(self, tmp_path):
        assert sites._load_project_exclusions(_priors(tmp_path, None)) == {}

    def test_an_entry_needs_its_reason_evidence_and_date(self, tmp_path):
        with pytest.raises(ValueError, match="no evidence"):
            sites._load_project_exclusions(_priors(tmp_path, """
                exclusions:
                  - ptno: "1"
                    reason: "a teaching building"
                    date: 2026-09-06
            """))

    def test_the_committed_file_loads_and_names_exeter_college(self):
        got = sites._load_project_exclusions(ROOT / "data")
        assert "12425966" in got and "teaching" in got["12425966"].lower()


def _app(conn, ref, *, verdict, assoc=None):
    source_id = repo.ensure_source(conn, name="planit", kind="aggregator", base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": "extension to the Hele Building",
             "location_y": 50.72, "location_x": -3.52, "associated_id": assoc},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute("INSERT INTO triage (application_id, model, verdict, raw_response) "
                    "VALUES (%s, 'fake', %s, '{\"rubric\": \"dc_build\"}')", (app_id, verdict))
    conn.commit()
    return app_id


def _project(conn, ptno, title, *apps):
    with conn.cursor() as cur:
        barbour = repo.ensure_source(conn, name="barbour", kind="aggregator", base_url="https://b")
        cur.execute("INSERT INTO projects (source_id, external_ref, title, latitude, longitude) "
                    "VALUES (%s, %s, %s, 50.72, -3.52) RETURNING id", (barbour, ptno, title))
        pid = cur.fetchone()[0]
        for a in apps:
            cur.execute("INSERT INTO project_applications (project_id, application_id, match_method) "
                        "VALUES (%s, %s, 'test')", (pid, a))
    conn.commit()


@pytest.mark.integration
def test_an_excluded_project_anchors_no_site_and_its_not_dc_paperwork_leaves(db_conn, tmp_path):
    a = _app(db_conn, "Testing/19/0330/FUL", verdict="not_dc")
    d = _app(db_conn, "Testing/20/0366/DIS", verdict="procedural", assoc="19/0330/FUL")
    # Only the parent is linked, as at Exeter: the discharge reaches the
    # site through its family reference, and must leave the same way.
    _project(db_conn, "99001", "A COLLEGE - DIGITAL & DATA CENTRE", a)
    without = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, None))
    assert any(p["ptno"] == "99001" for c in without for p in c["projects"]), \
        "the project anchors a site, and the door admits the not_dc application"
    assert any(x["id"] == a for c in without for x in c["apps"])

    with_excl = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, """
        exclusions:
          - ptno: "99001"
            title: "A COLLEGE - DIGITAL & DATA CENTRE"
            reason: "a teaching building"
            evidence: "Use Class D1"
            date: 2026-09-06
    """))
    assert not any(p["ptno"] == "99001" for c in with_excl for p in c["projects"])
    assert not any(x["id"] in (a, d) for c in with_excl for x in c["apps"]), \
        ("the paperwork leaves with the project: the procedural discharge would "
         "otherwise re-anchor the not_dc parent as a new site keyed on it")


@pytest.mark.integration
def test_an_unknown_project_fails_the_run(db_conn, tmp_path):
    with pytest.raises(ValueError, match="not in the corpus"):
        sites.build_clusters(db_conn, data_dir=_priors(tmp_path, """
            exclusions:
              - ptno: "00000000"
                title: "typo"
                reason: "r"
                evidence: "e"
                date: 2026-09-06
        """))
