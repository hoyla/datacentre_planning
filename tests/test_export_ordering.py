"""A build has to be a function of its inputs.

Diffing a build against the last release is how regressions are caught
in this project. That only works if two builds of one database are the
same build, and until 2026-08-22 they were not. Measured by running the
reader's per-site findings query twice inside a single `REPEATABLE READ`
transaction, so the corpus could not move underneath it: 2,503 of 10,425
rows came back in a different position, and **80 rows in a different
set, across 69 sites**. Those sites rendered a different selection of
findings on two builds of the same data — not diff noise, different
output.

Three orderings caused it, all the same mistake. A `row_number()` window
ranked on a boolean and a string length with nothing unique after them,
so which rows survived `rn <= N` was arbitrary among ties. The outer
select had no `ORDER BY` at all. And a `DISTINCT ON` broke ties on a
timestamp, which two rows can share.

Which test does what, stated because it is easy to assume otherwise.
**The static assertion is the one that catches this** — it reads the
query and fails if the two clauses go missing again. The two integration
tests build a tie deliberately, four findings identical in every column
the ranking looks at, and lock in the contract: the order is by id
ascending, and the `rn <= N` cut keeps the same members twice running.

They do **not** reproduce the original fault. Checked by reverting the
fix: with a handful of rows Postgres returns them in insertion order
anyway, so the tests pass against the broken query. Undefined behaviour
is not reliably reproducible in a small fixture, which is exactly why
the fault survived a 560-test suite in the first place. They earn their
place by pinning the intended behaviour, not by having caught it.

The DuckDB test at the end is the exception, and it is the model to copy
for the rest: DuckDB does not preserve insertion order through a
`row_number()`, so feeding it two rows tied on the ordering column picks
a different winner depending on the order they went in. Reverting the
tiebreak there and running it six times returns both rows as the
"latest"; with the tiebreak it returns the same one every time. That is
a test that fails on the bug rather than one that documents the fix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_the_findings_query_states_a_total_order():
    """Cheap and specific: the two clauses that were missing. A parser
    general enough to check every query in the export path was tried and
    was more fragile than the thing it checked."""
    import export_reader

    sql = re.sub(r"\s+", " ", export_reader.FINDINGS_SQL).strip()
    assert sql.endswith("ORDER BY site_key, rn"), sql[-90:]
    window = sql[sql.index("row_number()"):sql.index(") AS rn")]
    assert window.rstrip().endswith("f.id"), window[-90:]
    assert "inserted_at DESC, id DESC)" in sql


def test_the_parties_query_states_a_total_order():
    """The same clause, on the query that went without one until
    2026-09-01. Its rows are accumulated into dictionaries, and a
    dictionary keeps the order its keys first arrived in, so the row
    order reached the panel and two builds of one snapshot disagreed
    about who two sites were applied for by. `f.id` last because two
    findings can agree on every other column."""
    from dcp import site_profile

    sql = re.sub(r"\s+", " ", site_profile.PARTIES_SQL).strip()
    assert sql.endswith(
        "ORDER BY s.site_key, f.signal_family, f.value_text, f.id"), sql[-90:]


@pytest.mark.integration
def test_tied_findings_rank_the_same_way_every_time(db_conn):
    """Four findings a site's ranking cannot tell apart, twice."""
    import export_reader

    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM sources LIMIT 1")
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO sources (name) VALUES ('test') "
                        "RETURNING id")
            row = cur.fetchone()
        source_id = row[0]
        cur.execute(
            "INSERT INTO applications (source_id, application_ref, "
            "discovered_via) VALUES (%s, 'Order/1', '{test}') RETURNING id",
            (source_id,))
        app_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO sites (site_key, classification, radius_km) "
            "VALUES ('order-site', 'ours_only', 0.5) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO site_members (site_id, application_id, joined_via) "
            "VALUES (%s, %s, 'test')", (site_id, app_id))

        # Same family class, same value_text length, same everything the
        # window orders on. Only the ids differ, which is the point.
        ids = []
        for text in ("aaaa", "bbbb", "cccc", "dddd"):
            cur.execute(
                "INSERT INTO findings (application_id, signal_type, "
                "value_text, model, signal_family) "
                "VALUES (%s, 'generator_count', %s, 'test', 'power_demand') "
                "RETURNING id", (app_id, text))
            ids.append(cur.fetchone()[0])

        cur.execute(export_reader.FINDINGS_SQL, (export_reader.FINDINGS_PER_SITE,))
        first = cur.fetchall()
        cur.execute(export_reader.FINDINGS_SQL, (export_reader.FINDINGS_PER_SITE,))
        second = cur.fetchall()

    assert len(first) == 4, first
    assert first == second, "two runs of one query disagreed"
    # The documented rule: ties break on the finding's own id, ascending,
    # so the order is stable across builds and explicable to a reader.
    assert [r[2] for r in first] == ["aaaa", "bbbb", "cccc", "dddd"]


@pytest.mark.integration
def test_a_site_with_more_findings_than_the_cap_keeps_the_same_ones(db_conn):
    """The membership half of the bug: which findings survive `rn <= N`
    was arbitrary among ties, so a site could publish a different
    selection on each build."""
    import export_reader

    cap = export_reader.FINDINGS_PER_SITE
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM sources LIMIT 1")
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO sources (name) VALUES ('test') "
                        "RETURNING id")
            row = cur.fetchone()
        cur.execute(
            "INSERT INTO applications (source_id, application_ref, "
            "discovered_via) VALUES (%s, 'Order/2', '{test}') RETURNING id",
            (row[0],))
        app_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO sites (site_key, classification, radius_km) "
            "VALUES ('cap-site', 'ours_only', 0.5) RETURNING id")
        site_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO site_members (site_id, application_id, joined_via) "
            "VALUES (%s, %s, 'test')", (site_id, app_id))
        for i in range(cap + 6):
            cur.execute(
                "INSERT INTO findings (application_id, signal_type, "
                "value_text, model, signal_family) "
                "VALUES (%s, 'generator_count', %s, 'test', 'power_demand')",
                (app_id, f"{i:04d}"))

        cur.execute(export_reader.FINDINGS_SQL, (cap,))
        first = {r[2] for r in cur.fetchall()}
        cur.execute(export_reader.FINDINGS_SQL, (cap,))
        second = {r[2] for r in cur.fetchall()}

    assert len(first) == cap
    assert first == second, (
        f"{len(first ^ second)} findings differed between two runs of the "
        f"same query — the cut is falling in a different place")


def test_duckdbs_latest_verdict_survives_a_shared_timestamp():
    """`triage_verdicts` is append-only and multi-rubric, and the
    `latest_verdict` view picks one row per application per rubric by
    `inserted_at DESC`. Two verdicts written in the same batch can share
    a timestamp, and DuckDB then returns whichever it saw first — so the
    same database exported twice disagreed about which verdict was the
    latest. `triage_id` breaks the tie.

    Fails on the bug: with the tiebreak removed, the two insertion orders
    below produce two different winners.
    """
    import duckdb
    import export_duckdb

    sql = export_duckdb.VIEWS["latest_verdict"]
    winners = set()
    for reverse in (False, True):
        con = duckdb.connect()
        con.execute("""CREATE TABLE triage_verdicts (
            triage_id BIGINT, application_ref VARCHAR, model VARCHAR,
            verdict VARCHAR, worth_deep_read BOOLEAN, signals VARCHAR,
            why VARCHAR, confidence VARCHAR, rubric VARCHAR,
            prompt_version VARCHAR, enriched BOOLEAN, model_input VARCHAR,
            inserted_at TIMESTAMP)""")
        rows = [
            (1, "A/1", "m", "no", False, "", "", "high", "r", "v1", False, "",
             "2026-01-01 00:00:00"),
            (2, "A/1", "m", "yes", True, "", "", "high", "r", "v1", False, "",
             "2026-01-01 00:00:00"),
        ]
        con.executemany(
            "INSERT INTO triage_verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            list(reversed(rows)) if reverse else rows)
        out = con.execute(sql).fetchall()
        assert len(out) == 1, out
        winners.add(out[0][0])
    assert winners == {2}, (
        f"the view picked {sorted(winners)} depending on insertion order; "
        f"two exports of one database would disagree about the latest "
        f"verdict")
