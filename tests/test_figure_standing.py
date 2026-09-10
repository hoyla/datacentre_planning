"""A not_dc member's figures do not stand as the site's.

Migration 034 and ROADMAP's `not_dc` item. The family door admits an
application whatever triage said, because a reserved matters on a
data-centre outline reads `not_dc` by construction and the documents
are the only fix — and until 2026-09-10 every site-level rollup then
took the largest figure across every member, so the Eggborough power
station's own 2,500 MW rendered as a data-centre site's on-site
generation and West Burton's battery gave its site a 500 MW headline
(32 members, 301 figures, measured that day).

The fix is a standing on the membership row, set at materialise from
the dc_build verdict and `data/priors/not_dc_standing.yaml`, and one
predicate — `figure_standing <> 'not_dc_excluded'` — in every SQL
statement that rolls adjudicated figures up to a site. Three things are
pinned here:

- **The rule holds over the whole tree.** Every triple-quoted SQL in
  `dcp/` and `scripts/` that joins `site_members` to an adjudication
  table has to name `figure_standing`. A statement that deliberately
  reads every member — one that adjudicates the figure itself, or
  lists every figure a site's documents hold — says so in a SQL
  comment that carries the token, beside the query, so the reason sits
  where the next reader looks. The pattern is `test_release_defaults`:
  assert the rule, not the instance, and the test was watched failing
  on all twenty-five statements before the predicates went in.
- **The prior fails the run rather than silently not applying** — an
  unknown reference, a site the application is not a member of, an
  application whose verdict is not `not_dc`.
- **The clusterer sets the standing and the rollups honour it**: a
  `not_dc` member with the largest figure on a site contributes
  nothing to the cohorts' inputs; admitted by the prior, it
  contributes; the preflight names the change.
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

from dcp import repo, sites

ROOT = Path(__file__).resolve().parent.parent
PREDICATE = "figure_standing"
ADJUDICATION_TABLES = ("power_adjudication", "generation_adjudication")


# ---------------------------------------------------------------------------
# The rule, over the tree
# ---------------------------------------------------------------------------

def _sql_strings(path: Path):
    """Every string literal in the module that reads like SQL over
    site_members, with the line it starts on."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "site_members" in node.value:
                yield node.lineno, node.value


def _statements_needing_the_predicate():
    out = []
    for folder in ("dcp", "scripts"):
        for path in sorted((ROOT / folder).glob("*.py")):
            for line, body in _sql_strings(path):
                if any(t in body for t in ADJUDICATION_TABLES):
                    out.append((str(path.relative_to(ROOT)), line, body))
    return out


def test_the_tree_has_statements_to_check():
    """A guard that finds nothing to guard is the guard skipping itself
    (test_release_defaults learned this on 2026-09-02)."""
    assert len(_statements_needing_the_predicate()) >= 20


@pytest.mark.parametrize(
    "where,body",
    [(f"{p}:{line}", body) for p, line, body in _statements_needing_the_predicate()],
    ids=lambda x: x if isinstance(x, str) and ":" in x else "sql")
def test_every_site_rollup_over_adjudications_names_the_standing(where, body):
    assert PREDICATE in body, (
        f"{where}: joins site_members to an adjudication table without "
        f"naming figure_standing. Either add "
        f"`AND <alias>.figure_standing <> 'not_dc_excluded'` — a not_dc "
        f"member's figures do not stand as the site's (migration 034) — or, "
        f"if this statement must read every member, say why in a SQL comment "
        f"that names figure_standing, beside the query.")


# The two rollups that reach a site's capacity through findings rather
# than through an adjudication table: generator counts and fuels, and
# the floorspace behind the `w-modelled` estimate. Named, because the
# rule above cannot see them and a B8 outline's floorspace was in the
# median before this.
def test_the_findings_based_capacity_rollups_name_the_standing():
    from dcp import site_cohorts, site_profile, site_scale
    import inspect
    assert PREDICATE in site_profile.GENERATOR_SQL
    assert PREDICATE in site_cohorts.PENDING_FIGURES_SQL
    assert PREDICATE in inspect.getsource(site_scale.load_site_floorspace)


# ---------------------------------------------------------------------------
# The prior
# ---------------------------------------------------------------------------

def _priors(tmp_path, yaml_text: str | None) -> Path:
    d = tmp_path / "data"; (d / "priors").mkdir(parents=True, exist_ok=True)
    if yaml_text is not None:
        (d / "priors" / "not_dc_standing.yaml").write_text(textwrap.dedent(yaml_text))
    return d


ENTRY = """
    admissions:
      - application_ref: "{ref}"
        site_key: "{key}"
        reason: "the outline the data-centre applications cite as parent"
        evidence: "its documents name a data centre; the children cite it"
        date: 2026-09-10
        decided_by: "test"
"""


class TestTheFile:
    def test_absent_means_nothing_admitted(self, tmp_path):
        assert sites._load_not_dc_standing(_priors(tmp_path, None)) == {}

    def test_an_entry_needs_every_field(self, tmp_path):
        with pytest.raises(ValueError, match="no evidence"):
            sites._load_not_dc_standing(_priors(tmp_path, """
                admissions:
                  - application_ref: "Testing/1"
                    site_key: "SITE-Testing/1"
                    reason: "r"
                    date: 2026-09-10
                    decided_by: "test"
            """))

    def test_the_committed_file_loads_and_admits_kingsnorths_outline(self):
        got = sites._load_not_dc_standing(ROOT / "data")
        assert "MEDWAY/MC/21/0979" in got
        assert got["MEDWAY/MC/21/0979"]["site_key"] == "SITE-Medway/MC/21/0979"

    def test_the_committed_files_entries_all_name_not_dc_members(self):
        """A committed admission has to be honest about what it admits:
        every entry names an application the prior's own contract can
        reach. The materialise checks liveness against the database;
        this checks the file is well-formed and each entry carries a
        reason a reporter could quote."""
        for key, e in sites._load_not_dc_standing(ROOT / "data").items():
            assert e["reason"].strip(), key
            assert e["site_key"].startswith(("SITE-", "PTNO-")), key


# ---------------------------------------------------------------------------
# The clusterer sets it, the rollups honour it
# ---------------------------------------------------------------------------

def _app(conn, ref, *, verdict, lat=51.5011, lon=-0.4070, assoc=None):
    source_id = repo.ensure_source(conn, name="planit", kind="aggregator",
                                   base_url="https://x")
    app_id = repo.upsert_application(
        conn, source_id=source_id,
        app={"name": ref, "description": "a scheme",
             "location_y": lat, "location_x": lon, "associated_id": assoc},
        discovered_via=["test"])
    with conn.cursor() as cur:
        cur.execute("INSERT INTO triage (application_id, model, verdict, raw_response) "
                    "VALUES (%s, 'fake', %s, '{\"rubric\": \"dc_build\"}')",
                    (app_id, verdict))
    conn.commit()
    return app_id


def _figure(conn, app_id, mw, quantity="it_load"):
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO findings (application_id, signal_type,
                           value_number, value_unit, evidence_text, model)
                       VALUES (%s, 'it_load', %s, 'MW', %s, 'fake')
                       RETURNING id""", (app_id, mw, f"an IT load of {mw} MW"))
        fid = cur.fetchone()[0]
        cur.execute("""INSERT INTO power_adjudication (application_id, finding_id,
                           verdict, quantity_type, value_mw, reasoning, model,
                           prompt_version)
                       VALUES (%s, %s, 'site_capacity', %s, %s, 'test', 'fake',
                               'power-1.0')""", (app_id, fid, quantity, mw))
    conn.commit()


DC = "Testing/24/1001/FUL"
OUTLINE = "Testing/23/0001/OUT"
DISCHARGE = "Testing/24/0002/DISCON"     # procedural paperwork of the outline


@pytest.mark.integration
def test_a_not_dc_members_figure_does_not_stand_as_the_sites(db_conn, tmp_path):
    from dcp import site_cohorts
    dc = _app(db_conn, DC, verdict="new_build", assoc=OUTLINE)
    outline = _app(db_conn, OUTLINE, verdict="not_dc")
    discharge = _app(db_conn, DISCHARGE, verdict="procedural", assoc=OUTLINE)
    _figure(db_conn, dc, 40)
    _figure(db_conn, outline, 500)          # the larger figure, on the not_dc member
    _figure(db_conn, discharge, 500)        # Eggborough's shape: the discharge repeats it
    clusters = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, None))
    assert len(clusters) == 1, "the family edges admit both into one site"
    standing = {a["ref"]: a["figure_standing"] for a in clusters[0]["apps"]}
    assert standing == {DC: "counts", OUTLINE: "not_dc_excluded",
                        DISCHARGE: "not_dc_excluded"}
    reason = {a["ref"]: a["standing_reason"] for a in clusters[0]["apps"]}
    assert reason[DISCHARGE] == (f"procedural paperwork of {OUTLINE}, "
                                 "which triage calls not a data centre")
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    key = clusters[0]["site_key"]
    figures = site_cohorts.load_inputs(db_conn).figures
    assert figures[key]["it_load_mw"] == 40, (
        "the site ranks on its own member's 40 MW, not the outline's 500 "
        "nor its discharge's")


@pytest.mark.integration
def test_a_site_is_not_keyed_on_a_not_dc_member(db_conn, tmp_path):
    """The outline sorts first by reference and would have named the
    site; the key skips it for the data-centre application, and an
    admission gives it back (Kingsnorth keeps its key)."""
    _app(db_conn, DC, verdict="new_build", assoc=OUTLINE)
    _app(db_conn, OUTLINE, verdict="not_dc")
    assert OUTLINE < DC, "the test needs the not_dc member to sort first"
    clusters = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, None))
    assert [c["site_key"] for c in clusters] == [f"SITE-{DC}"]
    data_dir = _priors(tmp_path, ENTRY.format(ref=OUTLINE, key=f"SITE-{OUTLINE}"))
    clusters = sites.build_clusters(db_conn, data_dir=data_dir)
    assert [c["site_key"] for c in clusters] == [f"SITE-{OUTLINE}"]


@pytest.mark.integration
def test_procedural_paperwork_with_a_counting_neighbour_keeps_counting(db_conn, tmp_path):
    """A discharge citing the data-centre permission as well as the
    not_dc outline is not the outline's paperwork alone; it stays."""
    _app(db_conn, DC, verdict="new_build", assoc=OUTLINE)
    _app(db_conn, OUTLINE, verdict="not_dc")
    _app(db_conn, DISCHARGE, verdict="procedural", assoc=f"{OUTLINE} {DC}")
    clusters = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, None))
    standing = {a["ref"]: a["figure_standing"] for a in clusters[0]["apps"]}
    assert standing[DISCHARGE] == "counts"


@pytest.mark.integration
def test_an_admitted_not_dc_members_figure_counts_and_the_preflight_names_the_change(db_conn, tmp_path):
    from dcp import site_cohorts
    dc = _app(db_conn, DC, verdict="new_build", assoc=OUTLINE)
    outline = _app(db_conn, OUTLINE, verdict="not_dc")
    _figure(db_conn, dc, 40)
    _figure(db_conn, outline, 500)
    # First materialise: excluded.
    clusters = sites.build_clusters(db_conn, data_dir=_priors(tmp_path, None))
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    key = clusters[0]["site_key"]
    # Then a person admits the outline, with evidence — and the admission
    # carries the outline's own discharge with it, and gives the site
    # the outline's key, which sorts first (Kingsnorth's shape).
    _app(db_conn, DISCHARGE, verdict="procedural", assoc=OUTLINE)
    new_key = f"SITE-{OUTLINE}"
    data_dir = _priors(tmp_path, ENTRY.format(ref=OUTLINE, key=new_key))
    clusters = sites.build_clusters(db_conn, data_dir=data_dir)
    assert clusters[0]["site_key"] == new_key
    standing = {a["ref"]: (a["figure_standing"], a["standing_reason"])
                for a in clusters[0]["apps"]}
    assert standing[OUTLINE][0] == "not_dc_admitted"
    assert "parent" in standing[OUTLINE][1]
    assert standing[DISCHARGE][0] == "counts"
    pre = sites.preflight(db_conn, clusters)
    assert pre["retiring"] == [key] and pre["new"] == [new_key]
    # The discharge is new to the site, so it is not a *change* of
    # standing; the outline's is.
    assert pre["standing"] == [
        (OUTLINE, new_key, "not_dc_excluded", "not_dc_admitted")]
    sites.materialise(db_conn, clusters)
    db_conn.commit()
    assert site_cohorts.load_inputs(db_conn).figures[new_key]["it_load_mw"] == 500
    with db_conn.cursor() as cur:
        cur.execute("SELECT figure_standing, standing_reason FROM site_members "
                    "WHERE application_id = %s AND retired_at IS NULL", (outline,))
        assert cur.fetchone() == ("not_dc_admitted",
                                  "the outline the data-centre applications cite as parent")


@pytest.mark.integration
def test_the_prior_fails_the_run_on_a_reference_the_corpus_does_not_hold(db_conn, tmp_path):
    _app(db_conn, DC, verdict="new_build")
    data_dir = _priors(tmp_path, ENTRY.format(ref="Testing/99/9999/OUT",
                                              key="SITE-Testing/24/1001/FUL"))
    with pytest.raises(ValueError, match="not members of any site"):
        sites.build_clusters(db_conn, data_dir=data_dir)


@pytest.mark.integration
def test_the_prior_fails_the_run_on_a_site_the_application_is_not_in(db_conn, tmp_path):
    _app(db_conn, DC, verdict="new_build", assoc=OUTLINE)
    _app(db_conn, OUTLINE, verdict="not_dc")
    data_dir = _priors(tmp_path, ENTRY.format(ref=OUTLINE, key="SITE-Somewhere/Else"))
    with pytest.raises(ValueError, match="site key moved"):
        sites.build_clusters(db_conn, data_dir=data_dir)


@pytest.mark.integration
def test_the_prior_fails_the_run_on_an_application_that_is_not_not_dc(db_conn, tmp_path):
    _app(db_conn, DC, verdict="new_build")
    data_dir = _priors(tmp_path, ENTRY.format(ref=DC, key=f"SITE-{DC}"))
    with pytest.raises(ValueError, match="never asks"):
        sites.build_clusters(db_conn, data_dir=data_dir)
