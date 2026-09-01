"""The release diff's own guards, which nothing tested until now.

`scripts/release_diff.py` is the instrument the "diff against the
previous release" discipline rests on — it found four regressions in
2.2 that panel-by-panel review had missed. Three test modules named it
in their prose and none exercised it, so its own failure modes were
unwatched.

These cover the one that mattered: the dangling-site-key check read two
committed priors files by working-directory-relative path and opened
with `if not path.exists(): continue`, so from anywhere but the
repository root it found neither, checked nothing, and printed a report
indistinguishable from one where every site key resolved. A guard that
stops guarding is worse than none, because the report still reads as
reassurance.

The paths now resolve against the package root, and an absent file is
reported and exits 2 instead of being skipped.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_diff.py"
_spec = importlib.util.spec_from_file_location("release_diff", _SCRIPT)
rd = importlib.util.module_from_spec(_spec)
# Registered before execution because `Report` is a dataclass, and the
# decorator resolves its annotations through `sys.modules`. Same shape
# as tests/test_chunking.py.
sys.modules["release_diff"] = rd
_spec.loader.exec_module(rd)


def test_the_priors_paths_are_absolute_and_are_files_this_repo_holds():
    """The mechanism, not the file count, which may grow.

    Both are committed, which is what makes an absent one a fact about
    the checkout rather than about the corpus.
    """
    assert rd.PRIORS_WITH_SITE_KEYS
    for path in rd.PRIORS_WITH_SITE_KEYS:
        assert path.is_absolute(), path
        assert path.exists(), path


def test_the_priors_check_runs_from_another_working_directory(
        tmp_path, monkeypatch):
    """The failure this is for: the diff run from anywhere else.

    Nothing raised, nothing skipped visibly, and the site keys the
    priors name went unchecked while the report said so nowhere.
    """
    from_root = rd.Report()
    rd.check_priors(from_root, set())
    assert not from_root.broke, "the committed priors are readable from the root"
    named_at_root = [ln for ln in from_root.lines if "site keys named" in ln]
    assert named_at_root, "the check reports what it examined"

    monkeypatch.chdir(tmp_path)
    elsewhere = rd.Report()
    rd.check_priors(elsewhere, set())
    assert not elsewhere.broke
    assert [ln for ln in elsewhere.lines if "site keys named" in ln] == named_at_root


def test_an_absent_priors_file_is_stated_rather_than_skipped(tmp_path, monkeypatch):
    """The `continue` was the deeper defect, and it is the one to pin.

    Absolute paths stop the file going missing by accident; this stops
    the silence if it goes missing any other way.
    """
    monkeypatch.setattr(rd, "PRIORS_WITH_SITE_KEYS", (tmp_path / "gone.yaml",))
    rep = rd.Report()
    rd.check_priors(rep, {"PTNO-1"})

    assert rep.broke, "a check that did not run is recorded"
    assert "gone.yaml" in rep.broke[0]
    assert any("NOT FOUND" in ln for ln in rep.lines), "and it is in the report"


def test_a_check_that_did_not_run_exits_two_even_with_allow_fewer(
        tmp_path, monkeypatch, capsys):
    """`--allow-fewer` declares a removal deliberate.

    It cannot declare a check nobody ran deliberate, so the two verdicts
    are kept apart: `fell` is about the build, `broke` about this
    instrument, and only the first is waivable.
    """
    before, after = tmp_path / "before", tmp_path / "after"
    for d in (before, after):
        d.mkdir()
        (d / "reader.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(rd, "PRIORS_WITH_SITE_KEYS", (tmp_path / "gone.yaml",))
    monkeypatch.setattr(rd.sys, "argv", [
        "release_diff.py", str(after), "--against", str(before), "--allow-fewer"])

    assert rd.main() == 2
    out = capsys.readouterr().out
    assert "CHECKS THAT DID NOT RUN:" in out


def test_the_script_reads_nothing_else_by_a_relative_path():
    """The sweep the fix was made under, kept as an assertion.

    Every other `Path("…")` literal in the script would be the same
    defect in a different place, and prose cannot stop one being
    reintroduced.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    assert 'Path("data/priors/cohort_checks.yaml")' not in source
    assert 'Path("data/priors/organisation_aliases.yaml")' not in source
    assert 'Path("data' not in source
