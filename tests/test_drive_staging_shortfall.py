"""A tool that assembles a corpus must state what it left out.

On 2026-08-21 the Drive sync reported 50,406 candidates, 0 failed and 0
skipped. It was complete and correct over the tree it was given, and the
tree was missing 3,679 documents held for 143 applications discovered on
2026-08-07 — they had no `site_members` row until the materialise of
2026-08-25, and `build_drive_staging.py` stages a document only if its
application has one. Nothing in the sync could have said so: a document
that never entered the candidate set can be neither skipped nor failed.

Two consequences are pinned here, and both are rules over the whole
shape rather than assertions about that one episode:

- **Only a verdict that means "out of scope on purpose" excuses an
  unstaged document.** Every other verdict, and the absence of one above
  all, has to fail the build. Tested over the verdict vocabulary, not
  over the one verdict that happened to be involved.
- **A check may not draw its sample from the thing it is checking.**
  `verify_drive_sample.py` sampled the upload ledger, which is derived
  from the staging tree, so no sample it could ever draw contained a
  document that never reached the tree. Its frame is now `documents`.

Plus the rebuild rule: anything not written by this build leaves the
tree, so a re-partition cannot leave an application directory behind
under the site it moved away from — except a released artefact at the
root, which accumulates on purpose so a citation of it keeps resolving.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bds = _load("build_drive_staging")


class FakeCursor:
    """Enough of a cursor to exercise a query's contract, not its SQL."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.answers.pop(0)

    def fetchall(self):
        return self.answers.pop(0)


# ---------------------------------------------------------------------------
# The shortfall rule
# ---------------------------------------------------------------------------

# Everything a triage verdict has been or could be, plus the absence of
# one. Exactly one of these means "left out on purpose".
VERDICTS = ["dc_build", "data_centre", "adjacent", "adjacent_power",
            "unrelated", "unknown", "not_dc", "unclear", "", bds.UNTRIAGED]


@pytest.mark.parametrize("verdict", VERDICTS, ids=lambda v: v or "(empty)")
def test_only_not_dc_excuses_an_unstaged_document(verdict):
    rows = [(verdict, "Council/25/00001/FUL", 12)]
    lines, failed = bds.shortfall_lines(rows)
    tolerated = verdict == bds.TOLERATED_VERDICT
    assert failed is not tolerated, (
        f"an unstaged document whose application is triaged {verdict!r} "
        f"{'must not' if tolerated else 'must'} fail the build — only "
        f"{bds.TOLERATED_VERDICT!r} means a document was left out on purpose")
    # Whatever the verdict, the count is stated. A shortfall that is
    # tolerated is still a shortfall and still gets printed.
    assert any("12" in l for l in lines)


def test_an_untriaged_application_is_named_not_silently_tolerated():
    """The failure has to say which application, or nobody can act on it."""
    rows = [("not_dc", "Council/25/00002/FUL", 3808),
            (bds.UNTRIAGED, "Slough/P/00348/011", 6)]
    lines, failed = bds.shortfall_lines(rows)
    assert failed
    blob = "\n".join(lines)
    assert "Slough/P/00348/011" in blob
    assert "6 documents held for 1 in-universe application" in blob
    # ... and the tolerated bulk is still reported beside it, so the
    # reader can see the shortfall is mostly deliberate.
    assert "3,808" in blob


def test_a_complete_tree_says_so_rather_than_saying_nothing():
    lines, failed = bds.shortfall_lines([])
    assert not failed
    assert lines and "none" in lines[0]


def test_the_headline_counts_only_what_was_not_meant_to_be_left_out():
    """3,808 deliberate omissions must not inflate the failure's number."""
    rows = [("not_dc", f"C/25/{i:05d}/FUL", 50) for i in range(70)]
    rows.append((bds.UNTRIAGED, "Slough/P/00348/011", 6))
    lines, failed = bds.shortfall_lines(rows)
    assert failed
    headline = next(l for l in lines if "not in this tree" in l)
    assert headline.strip().startswith("6 documents")


def test_the_shortfall_is_computed_from_the_universe_not_from_the_tree():
    """The query starts at `documents` and asks whether a site exists.

    Reversed — walking the tree and asking what is in it — the answer is
    always "everything", which is what every counter on 2026-08-21 said.
    """
    sql = bds.UNSTAGED_SQL
    assert "FROM documents" in sql
    assert "NOT EXISTS" in sql and "site_members" in sql
    assert "retired_at IS NULL" in sql


# ---------------------------------------------------------------------------
# The stale-map rule
# ---------------------------------------------------------------------------

import datetime as _dt  # noqa: E402

_WHEN = _dt.datetime(2026, 8, 26, 7, 16, tzinfo=_dt.timezone.utc)
_LATER = _dt.datetime(2026, 8, 26, 9, 55, tzinfo=_dt.timezone.utc)


@pytest.mark.parametrize("apps,projects,refuses", [
    (0, 0, False),
    (1, 0, True),
    (0, 1, True),
    (2, 3, True),
])
def test_a_map_older_than_its_universe_is_refused(apps, projects, refuses):
    state = {"materialised_at": _WHEN, "applications": apps,
             "projects": projects,
             "examples": [("Slough/P/00348/011", _LATER)] * min(apps, 1)}
    lines, refuse = stale = bds.stale_map_lines(state)
    assert refuse is refuses, (
        f"{apps} application(s) and {projects} project(s) newer than the "
        f"materialise should {'refuse' if refuses else 'pass'}")
    assert any("materialised" in l for l in lines), stale


def test_never_materialised_is_refused_rather_than_treated_as_current():
    _, refuse = bds.stale_map_lines(
        {"materialised_at": None, "applications": 0, "projects": 0,
         "examples": []})
    assert refuse


def test_the_staleness_test_does_not_read_document_timestamps():
    """A refetch must not be mistaken for an unmapped universe.

    `documents.fetched_at` moves every time a document is fetched again,
    including for applications mapped weeks ago. Gating on it would fail
    every refetch pass while nothing was wrong, and a guard nobody
    trusts gets passed rather than read. Membership is a property of
    applications and projects; those are what the map has to be newer
    than.
    """
    assert "fetched_at" not in bds.STALE_MAP_SQL
    assert "applications" in bds.STALE_MAP_SQL
    assert "projects" in bds.STALE_MAP_SQL


# ---------------------------------------------------------------------------
# The rebuild rule
# ---------------------------------------------------------------------------

# Every shape of thing the additive build used to leave behind.
STALE_SHAPES = [
    "sites/A site/MovedAwayApp/001 - Doc.pdf",
    "sites/A site/MovedAwayApp/_index.md",
    "sites/A retired site/_site_report — A retired site.md",
    "sites/A site/_findings.csv",
    "stale_note.md",
    "README.md",
]


@pytest.mark.parametrize("relpath", STALE_SHAPES, ids=lambda p: p)
def test_anything_this_build_did_not_write_leaves_the_tree(tmp_path, relpath):
    live = tmp_path / "drive_staging"
    stale = live / relpath
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("x")
    built = tmp_path / "drive_staging.building"
    (built / "sites" / "A site").mkdir(parents=True)
    (built / "sites" / "A site" / "_site_report — A site.md").write_text("y")

    bds.swap_in(built, live)

    assert not (live / relpath).exists(), (
        f"{relpath} survived the rebuild — an additive tree is how the "
        f"Interxion folder came to hold 45 application directories for a "
        f"16-application site")
    assert (live / "sites" / "A site" / "_site_report — A site.md").is_file()
    assert not built.exists()
    assert not live.with_name(live.name + ".superseded").exists()


@pytest.mark.parametrize("name", ["dc_handover_phase1.xlsx",
                                  "dc_handover_phase2.2.xlsx",
                                  "dc_phase2.2.duckdb"])
def test_a_released_artefact_at_the_root_is_carried_forward(tmp_path, name):
    """The root accumulates on purpose: a citation has to keep resolving."""
    live = tmp_path / "drive_staging"
    live.mkdir()
    (live / name).write_text("published")
    built = tmp_path / "drive_staging.building"
    built.mkdir()
    (built / "dc_handover_phase2.7.xlsx").write_text("current")

    carried = bds.carry_forward_released(
        live, built, ["dc_handover_phase2.7.xlsx"])
    assert carried == [name]
    bds.swap_in(built, live)
    assert (live / name).is_file()
    assert (live / "dc_handover_phase2.7.xlsx").is_file()


@pytest.mark.parametrize("name", ["reader.html", "stale_note.md",
                                  "dc_build_handover_2026-06-01.xlsx"])
def test_only_a_published_artefact_is_carried_forward(tmp_path, name):
    """Not everything at the root is a release.

    `reader.html` is regenerated under the same name every time, the
    superseded `dc_build_handover_*` naming was dropped on purpose, and
    a stray markdown file is the explanatory material that moved into
    the reader in 2.1.
    """
    live = tmp_path / "drive_staging"
    live.mkdir()
    (live / name).write_text("old")
    built = tmp_path / "drive_staging.building"
    built.mkdir()
    assert bds.carry_forward_released(live, built, []) == []


def test_the_swap_never_loses_the_tree_when_the_rename_fails(tmp_path):
    """A failed swap restores the previous tree rather than leaving a hole."""
    live = tmp_path / "drive_staging"
    (live / "sites").mkdir(parents=True)
    (live / "sites" / "marker").write_text("the previous tree")
    missing = tmp_path / "never_built"
    with pytest.raises(OSError):
        bds.swap_in(missing, live)
    assert (live / "sites" / "marker").read_text() == "the previous tree"


# ---------------------------------------------------------------------------
# One implementation of a document's name
# ---------------------------------------------------------------------------

def _doc(url, kind, sha, path):
    return (url, kind, sha, path, None)


def test_the_number_counts_documents_not_files_present(tmp_path):
    """A document whose bytes have gone still consumes its number.

    Otherwise losing one file silently renumbers every document after it,
    and every citation of those names — the per-site findings CSV, the
    folder's own `_index.md`, the sync ledger — moves by one.
    """
    present = tmp_path / "a.pdf"
    present.write_bytes(b"x")
    rows = [_doc("u1", "Plan", "aa" * 16, str(tmp_path / "gone.pdf")),
            _doc("u2", "Report", "bb" * 16, str(present))]
    named = bds.document_filenames("Council/25/1/FUL", rows)
    assert [n[5] for n in named] == [False, True]
    assert named[1][2] == "Council_25_1_FUL/002 - Report.pdf"


def test_the_verifier_derives_names_from_the_builder():
    """Two implementations of the numbering would drift apart silently.

    The check would then disagree with the build about what a document
    is called, and both would look right.
    """
    src = (ROOT / "scripts" / "verify_drive_sample.py").read_text()
    assert "document_filenames" in src and "site_stem" in src
    assert "build_drive_staging" in src


def test_the_verifier_samples_the_universe_not_the_ledger():
    """The frame must be a database query over `documents`.

    Sampling the ledger — which is written from the tree — cannot
    produce a document that never reached the tree, which is the whole
    class of failure this check exists for.
    """
    vds = _load("verify_drive_sample")
    # The frame first asks the shared rule which applications sit under
    # adjacent_power/ (one query when the verdict class is empty), then
    # samples the universe.
    cur = FakeCursor([[], [(11,), (22,), (33,)]])
    import random
    ids, universe = vds.sample_universe(cur, 2, random.Random(0))
    assert universe == 3 and len(ids) == 2
    assert set(ids) <= {11, 22, 33}
    sql = cur.executed[-1][0]
    assert "FROM documents" in sql
    assert "site_members" in sql, (
        "the frame must be documents the builder is supposed to stage")
    assert "drive_sync_state" not in sql and "ledger" not in sql.lower()


def test_a_document_missing_from_the_tree_fails_the_verifier(tmp_path):
    """The failure the ledger-framed sampler was structurally unable to see."""
    vds = _load("verify_drive_sample")
    item = {"doc_id": 1, "ref": "Council/25/1/FUL", "site_key": "SITE-x",
            "sha": "aa", "kind": "Plan", "source": tmp_path / "raw.pdf",
            "exists": True, "path": tmp_path / "tree" / "001 - Plan.pdf"}
    problems = vds.check_document(item, {}, svc=None)
    assert problems and "NOT IN THE STAGING TREE" in problems[0]


def test_a_staged_document_never_uploaded_fails_the_verifier(tmp_path):
    staged = tmp_path / "tree" / "001 - Plan.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"x")
    vds = _load("verify_drive_sample")
    item = {"doc_id": 1, "ref": "Council/25/1/FUL", "site_key": "SITE-x",
            "sha": "aa", "kind": "Plan", "source": tmp_path / "raw.pdf",
            "exists": True, "path": staged}
    problems = vds.check_document(item, {}, svc=None)
    assert problems and "NOT IN THE UPLOAD LEDGER" in problems[0]


# ---------------------------------------------------------------------------
# Adjacent power: staged beside sites, never excused (2026-09-02)
# ---------------------------------------------------------------------------
#
# Issue #252 removed the `adjacent_power` class from site membership, and
# the first staging build after it found 744 held documents across 28
# applications with nowhere to go. They now sit under `adjacent_power/`
# beside `sites/`. Three properties are pinned: the class is staged, not
# tolerated; the shortfall counts it as staged only when this build wrote
# it; and the recorder and the verifier read the same folder name, so a
# document filed there gets its Drive id recorded and can be sampled.


def test_adjacent_power_is_not_an_excuse_for_an_unstaged_document():
    """An adjacent-power application that reached the shortfall was NOT
    written under adjacent_power/, and that is a failure, not a class
    the tree leaves out on purpose."""
    lines, failed = bds.shortfall_lines([("adjacent_power", "Leeds/18/00742/FU", 52)])
    assert failed
    assert any("52" in l for l in lines)


def test_the_shortfall_drops_only_the_adjacent_applications_this_build_wrote():
    rows = [("adjacent_power", "Leeds/18/00742/FU", 52),
            ("adjacent_power", "Bradford/24/02647/VOC", 89),
            ("not_dc", "Council/25/00002/FUL", 3)]
    cur = FakeCursor([rows])
    kept = bds.unstaged_documents(cur, staged_adjacent={"Leeds/18/00742/FU"})
    assert ("adjacent_power", "Leeds/18/00742/FU", 52) not in kept
    assert ("adjacent_power", "Bradford/24/02647/VOC", 89) in kept, \
        "an adjacent application the build did not write stays a shortfall"
    assert ("not_dc", "Council/25/00002/FUL", 3) in kept
    # And with nothing written, nothing is dropped.
    assert bds.unstaged_documents(FakeCursor([rows])) == rows


def test_adjacent_power_is_staged_beside_sites_with_its_relationships(tmp_path):
    src = tmp_path / "raw"
    src.mkdir()
    (src / "a.pdf").write_bytes(b"%PDF a")
    (src / "b.pdf").write_bytes(b"%PDF b")
    apps = [(7, "Leeds/18/00742/FU", "https://example/leeds", "Decided",
             "2018-02-01", "2018-06-01", "Substation for the park"),
            (8, "Empty/00/0001", None, None, None, None, None)]
    docs_by_app = {7: [("https://example/a", "Decision Notice", "a" * 64, str(src / "a.pdf"), None),
                       ("https://example/b", "Site Plan", "b" * 64, str(src / "b.pdf"), None)]}
    related = {7: [("PTNO-12885139", "SKELTON GRANGE - MICROSOFT", "discovery", 812.0)]}
    out = tmp_path / "staging.building"
    staged, n = bds.stage_adjacent_power(out, apps, docs_by_app, related)
    assert staged == {"Leeds/18/00742/FU"}, "an application with nothing held is not staged"
    assert n == 2
    folder = out / bds.ADJACENT_DIR / bds.app_dir_name("Leeds/18/00742/FU")
    assert (folder / "001 - Decision Notice.pdf").read_bytes() == b"%PDF a"
    assert (folder / "002 - Site Plan.pdf").exists()
    index = (folder / "_index.md").read_text()
    assert "SKELTON GRANGE" in index and "discovery" in index and "812 m" in index
    assert "not a site member" in index
    assert (out / bds.ADJACENT_DIR / "_README.md").exists()
    assert not (out / "sites").exists(), "nothing of this goes under sites/"


def test_the_recorder_and_the_verifier_read_the_adjacent_folder_by_the_builders_name():
    """One folder name, in the module that owns the layout. A recorder
    that could not find the folder would leave 744 documents linking
    the binned copies under the sites they used to belong to."""
    for name in ("record_drive_ids", "verify_drive_sample"):
        src = (ROOT / "scripts" / f"{name}.py").read_text()
        assert "bds.ADJACENT_DIR" in src, f"{name} does not read the folder name from the builder"
        assert "adjacent_power" in src


def test_a_verdict_vocabulary_now_names_the_staged_class():
    assert bds.ADJACENT_VERDICT == "adjacent_power"
    assert bds.ADJACENT_DIR == "adjacent_power"
    assert bds.ADJACENT_VERDICT != bds.TOLERATED_VERDICT


def test_the_verifier_keys_the_ledger_the_way_the_sync_writes_it():
    """The sync keys its ledger repository-relative; the verifier's
    staging default became absolute with R7, and an exact lookup then
    reported 30 of 30 sampled documents as never uploaded while the
    recorder found 55,944 of them (2026-09-01). The verifier must
    resolve an absolute path under the repository to the relative key
    — and leave a path outside the repository as it is."""
    vds = _load("verify_drive_sample")
    rel = "data/exports/drive_staging/sites/S — name/App/001 - Report.pdf"
    assert vds.ledger_key(ROOT / rel) == rel
    assert vds.ledger_key(Path(rel)) == rel
    assert vds.ledger_key(Path("/elsewhere/tree/x.pdf")) == "/elsewhere/tree/x.pdf"


# ---------------------------------------------------------------------------
# One rule decides what is under adjacent_power/, and three scripts read it
# ---------------------------------------------------------------------------

# Three scripts have to agree on which applications sit under
# `adjacent_power/`: the builder writes the tree, the recorder records
# where each file landed, the verifier's sample frame must cover every
# document the builder stages. On 2026-09-02 each carried its own copy of
# the rule; the copies agreed with each other and disagreed with the
# materialise about what "a member" meant, and four applications'
# documents had no Drive home (#349). The rule now lives once, in
# `dcp.adjacent_power.staged_applications`, and this pins that all three
# read it and none re-derives it from the verdict.


@pytest.mark.parametrize("module", ["build_drive_staging", "record_drive_ids",
                                    "verify_drive_sample"])
def test_the_adjacent_class_is_decided_once_and_read_three_times(module):
    src = (ROOT / "scripts" / f"{module}.py").read_text()
    assert "staged_applications(" in src, \
        f"{module} must read the adjacent class from dcp.adjacent_power"
    body = src[src.index("import"):]
    assert "l.verdict = 'adjacent_power'" not in body, \
        f"{module} re-derives the adjacent class from the verdict instead " \
        f"of reading the shared rule"


def test_the_shared_rule_requires_a_live_site_for_membership():
    from dcp import adjacent_power as ap
    for sql in (ap.STAGED_VERDICT_SQL, ap.UNSITED_SQL):
        assert "JOIN sites s ON s.id = m.site_id" in sql and \
               "s.retired_at IS NULL" in sql, \
            "a membership row on a retired site must not count as a membership"


def test_a_schemes_own_paperwork_is_staged_beside_it_and_names_its_parent(tmp_path):
    src = tmp_path / "raw"
    src.mkdir()
    (src / "p.pdf").write_bytes(b"%PDF parent")
    (src / "c.pdf").write_bytes(b"%PDF child")
    apps = [(7, "Hillingdon/75111/APP/2022/1007", "https://x/parent", "Decided", None, None,
             "Site clearance and substation"),
            (9, "Hillingdon/75111/APP/2023/2544", "https://x/child", "Decided", None, None,
             "Details pursuant to condition 12 of 75111/APP/2022/1007")]
    docs_by_app = {7: [("https://x/p", "Decision Notice", "a" * 64, str(src / "p.pdf"), None)],
                   9: [("https://x/c", "Condition Details", "b" * 64, str(src / "c.pdf"), None)]}
    related = {7: [("PTNO-12511337", "UNION PARK", "discovery", 120.0)]}
    why = {7: {"ref": apps[0][1], "why": "verdict", "parent_id": None, "parent_ref": None},
           9: {"ref": apps[1][1], "why": "paperwork", "parent_id": 7,
               "parent_ref": apps[0][1]}}
    out = tmp_path / "staging.building"
    staged, n = bds.stage_adjacent_power(out, apps, docs_by_app, related, why=why)
    assert staged == {apps[0][1], apps[1][1]} and n == 2
    child = out / bds.ADJACENT_DIR / bds.app_dir_name(apps[1][1])
    index = (child / "_index.md").read_text()
    assert "Paperwork of an adjacent-power scheme" in index
    assert apps[0][1] in index, "the child's index names its parent"
    assert "UNION PARK" in index, "and inherits the sites the parent stands beside"
    assert (child / "001 - Condition Details.pdf").read_bytes() == b"%PDF child"


def test_the_shortfall_drops_whatever_this_build_wrote_under_adjacent_power():
    """A scheme's own discharge is `not_dc`; staged under adjacent_power/
    it must not be reported as held-but-not-staged."""
    rows = [("adjacent_power", "Leeds/18/00742/FU", 52),
            ("not_dc", "Hillingdon/75111/APP/2023/2544", 26),
            ("not_dc", "Council/25/00002/FUL", 3)]
    kept = bds.unstaged_documents(
        FakeCursor([rows]),
        staged_adjacent={"Leeds/18/00742/FU", "Hillingdon/75111/APP/2023/2544"})
    assert kept == [("not_dc", "Council/25/00002/FUL", 3)]
