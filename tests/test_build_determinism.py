"""A build has to be a function of its inputs — asserted, not assumed.

Diffing a build against the last release is how regressions are caught
here (`scripts/release_diff.py`), and that instrument is only as good as
the build's determinism: until 2026-08-22 two builds of one database
differed on 42 lines, and before that on 80 rows across 69 sites. Each
cause was fixed and the fix is held by `tests/test_export_ordering.py`,
which reads the query — but nothing held the *artefact*. This does.

It builds the reader twice and asserts the two files are identical apart
from the generation stamp. Two things it is careful about, both learned
the hard way:

**It has to be at scale.** ROADMAP records the trap: a small fixture does
not catch this, because Postgres returns a handful of tied rows in
insertion order regardless. So this runs against the real corpus, which
is why it is an integration test and takes about twenty seconds.

**The corpus moves.** The Phase 3 corroboration read writes a row every
few seconds, so two builds ten seconds apart are snapshots of different
inputs and their diff proves nothing. The first version of this test
fingerprinted the tables and skipped when they moved — and skipped on
its first run, on one new `deepread_log` row, which would have made it
skip for the weeks the read has left. So instead the test exports a
Postgres snapshot and both builds import it (`DCP_PG_SNAPSHOT`, honoured
by `dcp.db.connect`): every connection either build opens sees the
corpus as it stood at one instant, whatever lands meanwhile. The
fingerprint survives as a check that the snapshot actually held.

The adjudication gate can refuse a build outright while corrections are
outstanding. That is a skip rather than a failure: a build that was
refused was not built twice.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

from dcp import db

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export_reader.py"

# The one line that is allowed to differ between two builds of one corpus.
#
# The pattern has to track the masthead. It was written for an ISO stamp,
# the redesign moved the masthead to the handoff's "generated 21 Aug 2026
# 18:32 UTC", and from then on the regex matched nothing — so the line it
# exists to normalise stopped being normalised, and the test failed only
# when two builds happened to straddle a minute. A guard that fails on
# the clock is a guard nobody trusts.
_STAMP_RE = re.compile(
    r"generated (?:\d{4}-\d{2}-\d{2}|\d{1,2} [A-Z][a-z]{2} \d{4}) "
    r"\d{2}:\d{2} UTC")

# Tables the reader reads. Under the snapshot these cannot move between
# the two builds; if they do, the snapshot was not honoured and the
# comparison is void.
_FINGERPRINT_SQL = """
SELECT (SELECT count(*) FROM findings),
       (SELECT max(id) FROM findings),
       (SELECT count(*) FROM power_adjudication),
       (SELECT count(*) FROM deepread_log),
       (SELECT count(*) FROM documents),
       (SELECT count(*) FROM capacity_claim_matches),
       (SELECT count(*) FROM sites WHERE retired_at IS NULL)
"""


# The reader does not read the database alone. `_drive_folder_map`,
# `_drive_application_map` and `_drive_findings_map` in
# export_handover all read this JSON ledger from disk, and every Drive
# link in the built page comes from it. `drive_sync` rewrites it once
# per file while it runs, and a Postgres snapshot cannot pin a file —
# so two builds either side of a sync read different ledgers and differ
# for a reason that has nothing to do with query determinism.
#
# This is the best candidate for the single 2026-08-26 failure, which
# the ROADMAP records as arriving "immediately after the Drive-id
# work". Rather than assume, the test measures: if the ledger moves
# between the two builds the comparison is void and says so, exactly as
# the fingerprint above voids a comparison whose snapshot did not hold.
DRIVE_LEDGER = ROOT / "data" / "exports" / ".drive_sync_state.json"


def _ledger_fingerprint() -> str:
    """What the ledger looked like, or 'absent'. Content, not mtime: a
    sync that rewrites the file with the same bytes has not changed
    what either build reads."""
    if not DRIVE_LEDGER.exists():
        return "absent"
    return hashlib.sha256(DRIVE_LEDGER.read_bytes()).hexdigest()


def _live_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    try:
        return psycopg2.connect(url, connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"live database unreachable: {e}")


def _build(out: Path, env: dict) -> None:
    proc = subprocess.run(
        [sys.executable, str(EXPORT), "--out", str(out), "--phase", "test"],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=env, check=False)
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
        if "uncorrected" in (proc.stdout + proc.stderr):
            pytest.skip("adjudication gate refused the build: " + " / ".join(tail))
        pytest.fail("build failed:\n" + "\n".join(tail))
    assert out.exists() and out.stat().st_size > 1_000_000, "build wrote no reader"


def _normalise(text: str) -> str:
    return _STAMP_RE.sub("generated <stamp>", text)


# Where a failing run leaves its evidence. Under data/, so git ignores
# it; a fixed path rather than a timestamped one, because the thing that
# matters is that the next person knows where to look without having to
# find a pytest tmp directory before it is recycled.
FAILURE_DIR = ROOT / "data" / "exports" / "determinism_failure"


def _keep_the_evidence(a: Path, b: Path, ta: str, tb: str) -> Path:
    """Save both builds and their diff, and return where.

    This test failed once, on 2026-08-26, and has passed every run
    since. The detail of *which* lines differed was never captured,
    because the failure message named a line and the builds went out
    with pytest's tmp directory — so a rare failure taught us nothing
    and we are still waiting for the next one. One reproduction has to
    be enough (ROADMAP, the determinism item).
    """
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(a, FAILURE_DIR / "a.html")
    shutil.copy2(b, FAILURE_DIR / "b.html")
    # The normalised text is what was actually compared, so it is what a
    # person should diff; the raw builds are kept beside it because the
    # stamp regex itself has been the bug before (see _STAMP_RE).
    (FAILURE_DIR / "a.normalised.html").write_text(ta, encoding="utf-8")
    (FAILURE_DIR / "b.normalised.html").write_text(tb, encoding="utf-8")
    diff = difflib.unified_diff(ta.splitlines(), tb.splitlines(),
                                "a.normalised.html", "b.normalised.html",
                                n=2, lineterm="")
    # Capped: a build is 27 MB and a diff of two of them can be most of
    # that. The first few thousand lines have always been enough to see
    # the shape, and an unbounded write here would be its own incident.
    kept, truncated = [], False
    for i, line in enumerate(diff):
        if i >= 4000:
            truncated = True
            break
        kept.append(line)
    if truncated:
        kept.append("… diff truncated at 4000 lines; "
                    "diff the two .normalised.html files for the rest")
    (FAILURE_DIR / "diff.txt").write_text("\n".join(kept), encoding="utf-8")
    return FAILURE_DIR


@pytest.mark.integration
def test_two_builds_of_one_snapshot_are_identical(tmp_path):
    # The exporting transaction must stay open for as long as anyone
    # imports its snapshot, so it lives for the whole test.
    holder = _live_connection()
    try:
        holder.set_session(
            isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
            readonly=True)
        with holder.cursor() as cur:
            cur.execute("SELECT pg_export_snapshot()")
            snapshot = cur.fetchone()[0]
            cur.execute(_FINGERPRINT_SQL)
            expected = cur.fetchone()

        env = {**os.environ, db.SNAPSHOT_ENV: snapshot}
        a, b = tmp_path / "a.html", tmp_path / "b.html"
        ledger_before = _ledger_fingerprint()
        _build(a, env)
        _build(b, env)
        ledger_after = _ledger_fingerprint()
        if ledger_before != ledger_after:
            pytest.skip(
                "the Drive ledger changed between the two builds "
                f"({DRIVE_LEDGER}) — every Drive link in the page comes "
                "from it, so the two builds had different inputs and "
                "their diff proves nothing. Re-run when no drive_sync "
                "is in flight.")

        # Seen through the snapshot from a fresh connection, the corpus
        # must read exactly as the holder saw it — or the import is not
        # doing what the docstring says.
        os.environ[db.SNAPSHOT_ENV] = snapshot
        try:
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute(_FINGERPRINT_SQL)
                seen = cur.fetchone()
        finally:
            os.environ.pop(db.SNAPSHOT_ENV, None)
        assert seen == expected, f"snapshot not honoured: {expected} vs {seen}"
    finally:
        holder.close()

    ta = _normalise(a.read_text(encoding="utf-8"))
    tb = _normalise(b.read_text(encoding="utf-8"))
    if ta == tb:
        return
    # Say where, in the terms a person fixing it needs: the first
    # differing line and how many lines differ in all.
    la, lb = ta.splitlines(), tb.splitlines()
    differing = [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]
    first = differing[0] if differing else min(len(la), len(lb))
    where = _keep_the_evidence(a, b, ta, tb)
    # Both builds and their diff are on disk before this message is
    # composed: the message can be read once and lost, the files cannot.
    shown = []
    for i in differing[:3]:
        shown.append(f"  line {i + 1}:\n"
                     f"    a: {la[i][:200]}\n"
                     f"    b: {lb[i][:200]}")
    pytest.fail(
        f"two builds of one snapshot differ on {len(differing)} line(s) "
        f"(lengths {len(la)} vs {len(lb)}); first at line {first + 1}.\n"
        + "\n".join(shown)
        + f"\n  both builds and a unified diff kept in: {where}"
        + "\n  (a.html / b.html as built, *.normalised.html as compared, "
          "diff.txt)"
        # Said explicitly so a future failure is not mis-diagnosed as
        # the ledger when the ledger has been ruled out.
        + "\n  the Drive ledger did NOT move between the builds, so the "
          "difference is in the build itself.")


@pytest.mark.integration
def test_snapshot_env_freezes_what_a_connection_sees():
    """The mechanism on its own, without a 9-second build either side.

    A connection opened with `DCP_PG_SNAPSHOT` set must see the counts
    the exporting transaction saw, and must refuse to write.
    """
    holder = _live_connection()
    try:
        holder.set_session(
            isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
            readonly=True)
        with holder.cursor() as cur:
            cur.execute("SELECT pg_export_snapshot()")
            snapshot = cur.fetchone()[0]
            cur.execute(_FINGERPRINT_SQL)
            expected = cur.fetchone()
        os.environ[db.SNAPSHOT_ENV] = snapshot
        try:
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute(_FINGERPRINT_SQL)
                assert cur.fetchone() == expected
                with pytest.raises(psycopg2.Error):
                    cur.execute("CREATE TEMP TABLE should_not_happen (x int)")
        finally:
            os.environ.pop(db.SNAPSHOT_ENV, None)
    finally:
        holder.close()


def test_only_the_stamp_is_time_dependent():
    """The generator may print the clock once, in the stamp, and nowhere else.

    A second `now()` anywhere in the template would make two builds differ
    for a reason the normaliser does not know about, and the integration
    test above would report non-determinism that is not there.
    """
    src = EXPORT.read_text(encoding="utf-8")
    uses = [m.start() for m in re.finditer(r"\.now\(|today\(\)", src)]
    assert len(uses) == 1, f"expected exactly one clock read in the generator, found {len(uses)}"
    line = src[:uses[0]].count("\n") + 1
    context = src.splitlines()[line - 1]
    assert "generated" in context, f"the clock read at line {line} is not the stamp: {context!r}"


def test_the_failure_path_keeps_what_the_next_person_needs(tmp_path, monkeypatch):
    """The evidence-keeping runs on the rare failure, so it cannot wait
    for the rare failure to be tested. A handler that has never run is
    the same trap as a guard that cannot see: this test exercises it
    with two builds that differ by one line.
    """
    dest = tmp_path / "kept"
    monkeypatch.setattr(
        sys.modules[__name__], "FAILURE_DIR", dest, raising=True)
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    ta = "<p>one</p>\n<p>two</p>\n<p>three</p>\n"
    tb = "<p>one</p>\n<p>TWO</p>\n<p>three</p>\n"
    a.write_text(ta, encoding="utf-8")
    b.write_text(tb, encoding="utf-8")

    where = _keep_the_evidence(a, b, ta, tb)

    assert where == dest
    for name in ("a.html", "b.html", "a.normalised.html",
                 "b.normalised.html", "diff.txt"):
        assert (dest / name).exists(), f"{name} was not kept"
    assert (dest / "a.html").read_text(encoding="utf-8") == ta
    diff = (dest / "diff.txt").read_text(encoding="utf-8")
    assert "-<p>two</p>" in diff and "+<p>TWO</p>" in diff, diff


def test_a_vast_diff_is_capped_rather_than_written_whole(tmp_path, monkeypatch):
    """A reader build is ~27 MB. Writing an unbounded diff of two of them
    would be its own incident, so the cap is asserted rather than
    trusted."""
    dest = tmp_path / "kept"
    monkeypatch.setattr(
        sys.modules[__name__], "FAILURE_DIR", dest, raising=True)
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    ta = "\n".join(f"<p>{i}</p>" for i in range(9000))
    tb = "\n".join(f"<p>x{i}</p>" for i in range(9000))
    a.write_text(ta, encoding="utf-8")
    b.write_text(tb, encoding="utf-8")

    _keep_the_evidence(a, b, ta, tb)

    lines = (dest / "diff.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 4001, len(lines)
    assert "truncated" in lines[-1]
    # The whole builds are still there, so nothing is actually lost.
    assert (dest / "a.normalised.html").read_text(encoding="utf-8") == ta


def test_the_ledger_fingerprint_is_content_not_mtime(tmp_path, monkeypatch):
    """A sync that rewrites the ledger with identical bytes has not
    changed what either build reads, and must not void a comparison —
    otherwise the guard turns every concurrent sync into a skip and the
    determinism check quietly stops running at all.
    """
    import time
    led = tmp_path / ".drive_sync_state.json"
    monkeypatch.setattr(sys.modules[__name__], "DRIVE_LEDGER", led,
                        raising=True)

    assert _ledger_fingerprint() == "absent"

    led.write_text('{"folders": {"a/sites": "ID1"}}', encoding="utf-8")
    first = _ledger_fingerprint()
    assert first != "absent"

    time.sleep(0.01)
    led.write_text('{"folders": {"a/sites": "ID1"}}', encoding="utf-8")
    assert _ledger_fingerprint() == first, "same bytes must fingerprint the same"

    led.write_text('{"folders": {"a/sites": "ID2"}}', encoding="utf-8")
    assert _ledger_fingerprint() != first, "changed bytes must be seen"
