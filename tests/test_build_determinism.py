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

import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

from dcp import db

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export_reader.py"

# The one line that is allowed to differ between two builds of one corpus.
_STAMP_RE = re.compile(r"generated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC")

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
        _build(a, env)
        _build(b, env)

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
    pytest.fail(
        f"two builds of one snapshot differ on {len(differing)} line(s) "
        f"(lengths {len(la)} vs {len(lb)}); first at line {first + 1}:\n"
        f"  a: {la[first][:240] if first < len(la) else '<eof>'}\n"
        f"  b: {lb[first][:240] if first < len(lb) else '<eof>'}")


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
