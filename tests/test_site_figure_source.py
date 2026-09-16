"""The figure a site shows and the application it is attributed to come
from one fold of `power_adjudication`.

The table is append-only: a re-adjudication adds a row. `SITE_FIGURE_SQL`
folds it to each finding's latest row before picking the largest
standing figure per quantity, and since 2026-09-16 the reader reads the
source application off the same rows. Until then a second query ranked
`power_adjudication` raw, so a finding re-adjudicated away from
`site_capacity`, or down to a smaller value, could still name its
application as the source of the headline figure. This seeds that case
and runs the real query on the rebuilt test schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import export_reader  # noqa: E402

pytestmark = pytest.mark.integration


def _seed(cur):
    cur.execute("INSERT INTO sources (name, kind, base_url) VALUES ('t', 'planning_portal', "
                "'http://t') ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url "
                "RETURNING id")
    src = cur.fetchone()[0]
    cur.execute("INSERT INTO sites (site_key, classification, radius_km) VALUES "
                "('SITE-1', 'dc', 1.0) RETURNING id")
    site = cur.fetchone()[0]
    apps, findings = {}, {}
    for ref in ("T/A", "T/B"):
        cur.execute("INSERT INTO applications (source_id, application_ref) VALUES (%s, %s) "
                    "RETURNING id", (src, ref))
        apps[ref] = cur.fetchone()[0]
        cur.execute("INSERT INTO site_members (site_id, application_id, joined_via) "
                    "VALUES (%s, %s, 'test')", (site, apps[ref]))
        cur.execute("INSERT INTO findings (application_id, signal_type, model, value_text, "
                    "evidence_text, evidence_page) VALUES (%s, 'power_capacity', 'test', "
                    "'x MW', 'a quote', 1) RETURNING id", (apps[ref],))
        findings[ref] = cur.fetchone()[0]
    return apps, findings


def _adjudicate(cur, app_id, finding_id, verdict, mw, when, version="v0"):
    """A re-adjudication is a new row under a new prompt version: the
    table is unique on (finding_id, model, prompt_version), which is what
    makes it append-only rather than overwritten."""
    cur.execute("INSERT INTO power_adjudication (application_id, finding_id, verdict, "
                "quantity_type, value_mw, reasoning, model, prompt_version, inserted_at) "
                "VALUES (%s, %s, %s, 'total_site', %s, 'seeded', 'test', %s, %s)",
                (app_id, finding_id, verdict, mw, version, when))


def _figures(cur) -> dict[tuple[str, str], tuple[float, str]]:
    cur.execute(export_reader.SITE_FIGURE_SQL)
    return {(r[0], r[1]): (float(r[2]), r[10]) for r in cur.fetchall()}


def test_a_figure_adjudicated_down_no_longer_wins_or_names_its_application(db_conn):
    with db_conn.cursor() as cur:
        apps, f = _seed(cur)
        _adjudicate(cur, apps["T/A"], f["T/A"], "site_capacity", 500, "2026-09-01T10:00Z")
        _adjudicate(cur, apps["T/A"], f["T/A"], "site_capacity", 100, "2026-09-02T10:00Z", "v1")
        _adjudicate(cur, apps["T/B"], f["T/B"], "site_capacity", 200, "2026-09-01T10:00Z")
        got = _figures(cur)
    assert got[("SITE-1", "total_site")] == (200.0, "T/B"), (
        "the superseded 500 MW row must neither be the figure nor name T/A as its source")


def test_a_finding_re_adjudicated_away_from_site_capacity_drops_out(db_conn):
    with db_conn.cursor() as cur:
        apps, f = _seed(cur)
        _adjudicate(cur, apps["T/A"], f["T/A"], "site_capacity", 500, "2026-09-01T10:00Z")
        _adjudicate(cur, apps["T/A"], f["T/A"], "not_this_site", None, "2026-09-02T10:00Z", "v1")
        _adjudicate(cur, apps["T/B"], f["T/B"], "site_capacity", 200, "2026-09-01T10:00Z")
        got = _figures(cur)
    assert got[("SITE-1", "total_site")] == (200.0, "T/B")


def test_the_reader_attributes_from_the_same_rows_it_takes_the_figure_from():
    """The second query is gone: the attribution dict is built from the
    provenance dict, so the two cannot disagree."""
    src = Path(export_reader.__file__).read_text()
    assert 'power_src = {kq: p["ref"] for kq, p in fig_prov.items()}' in src
    assert "row_number() OVER (PARTITION BY s.site_key, pa.quantity_type" not in src
