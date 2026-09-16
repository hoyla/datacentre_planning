"""Shared pytest fixtures.

Loads .env so DATABASE_URL is available, and provides per-test Postgres connections
for integration tests against a separate `dcp_test` database. Tests are marked
`@pytest.mark.integration` and skipped automatically if Postgres is unreachable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
TEST_DB_NAME = "dcp_test"


def _admin_url() -> str:
    parsed = urlparse(os.environ["DATABASE_URL"])
    return parsed._replace(path="/postgres").geturl()


def _test_db_url() -> str:
    parsed = urlparse(os.environ["DATABASE_URL"])
    return parsed._replace(path=f"/{TEST_DB_NAME}").geturl()


def _is_data_only(sql: str) -> bool:
    """A migration that changes rows and not the schema.

    Two of the thirty-five (017 and 018) demote rows and then refuse to
    commit unless the count they expected is the count they found, which
    on an empty database is never. They carry no CREATE, ALTER or DROP,
    so skipping them leaves the test schema identical to production's;
    a migration that carried schema *and* refused would leave it
    different, which is why that case fails the session instead.
    """
    return not re.search(r"^\s*(CREATE|ALTER|DROP)\s", sql, re.I | re.M)


def _ensure_test_database() -> None:
    """Recreate dcp_test and apply every migration, in order.

    Until 2026-09-16 this applied fourteen of the migrations by hand,
    probing for one object each, so the integration tests ran on a
    schema without `findings_content_key` (012), the readings store
    (023), the audit stores (025-027), the Drive file table (031) and
    the adjacency table (032) — and no test could assert the contracts
    those hold. Now the database is dropped and rebuilt once per session
    from `migrations/*.sql`, so the schema the tests run on is the
    schema production has, and a migration that cannot run from scratch
    is found here rather than at restore time.
    """
    conn = psycopg2.connect(_admin_url())
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)")
            cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    finally:
        conn.close()

    conn = psycopg2.connect(_test_db_url())
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            sql = path.read_text()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                if _is_data_only(sql):
                    continue
                raise RuntimeError(
                    f"{path.name} cannot be applied to an empty database: "
                    f"{str(e).splitlines()[0]}") from e
    finally:
        conn.close()


def _state_tables(conn) -> list[str]:
    """Every base table except the reference data (`sources`, `councils`)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename NOT IN ('sources', 'councils') ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


@pytest.fixture(scope="session")
def built_reader(tmp_path_factory) -> str:
    """One reader, built from the live database once, as a file:// URI.

    Both suites that drive the artefact — the behaviour smoke test and
    the design-conformance test — need a real build, and a build is
    fifty seconds. Session-scoped so it happens once.
    """
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent

    # A reader that already exists, driven as-is. Without this the suite
    # can only test a page it built itself from the live database, so in
    # any environment without one — CI, most obviously — all seventeen
    # tests skip and report green while asserting nothing. Pointed at
    # the committed index.html it drives the exact bytes about to be
    # served, which is the only version whose behaviour anybody cares
    # about at the moment of deploying it.
    prebuilt = os.environ.get("READER_HTML")
    if prebuilt:
        path = Path(prebuilt)
        if not path.exists():
            pytest.fail(f"READER_HTML is set to {prebuilt}, which does not exist")
        if path.stat().st_size < 1_000_000:
            pytest.fail(f"READER_HTML at {prebuilt} is {path.stat().st_size} bytes; "
                        f"a reader is tens of megabytes, so this is a stub or a "
                        f"truncated write")
        return path.resolve().as_uri()

    out = tmp_path_factory.mktemp("reader") / "reader.html"
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set and READER_HTML not given")
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "export_reader.py"),
         "--out", str(out), "--phase", "test"],
        cwd=root, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0:
        combined = proc.stdout + proc.stderr
        tail = combined.strip().splitlines()[-8:]
        # The gate's own refusal, matched on the words it actually
        # prints. This looked for "uncorrected" alone, which is the word
        # in the *override flag* rather than in the message — so on
        # 2026-08-26 a correctly-refused build was reported to a reader
        # as "build failed", and the tail shown was the tail of the
        # remedy instructions rather than the reason. A test that cannot
        # recognise a guard doing its job will be silenced the first
        # time the guard fires.
        if ("uncorrected" in combined
                or "Refusing to build" in combined
                or "quantity-type corrections" in combined):
            pytest.skip("adjudication gate refused the build: " + " / ".join(tail))
        if "could not connect" in combined or "OperationalError" in combined:
            pytest.skip("live database unreachable: " + " / ".join(tail))
        pytest.fail("build failed:\n" + "\n".join(tail))
    assert out.exists() and out.stat().st_size > 1_000_000, "build wrote no reader"
    return out.as_uri()


@pytest.fixture(scope="session")
def integration_db() -> str:
    """Ensure dcp_test exists and is migrated. Skip the test if Postgres is unreachable."""
    try:
        _ensure_test_database()
    except psycopg2.OperationalError as e:
        pytest.skip(f"Postgres unavailable for integration tests: {e}")
    return _test_db_url()


@pytest.fixture
def db_conn(integration_db: str):
    """Per-test connection. Rolls back at teardown so the test DB stays clean.

    Also truncates the mutable tables at start-of-test so contamination from
    any prior test that erroneously committed (or from a previous interrupted
    run) doesn't bleed into the next test's preconditions. `sources` and
    `councils` are reference data; the rest is per-test state.
    """
    conn = psycopg2.connect(integration_db)
    try:
        tables = _state_tables(conn)
        with conn.cursor() as cur:
            # Every state table, read from the catalogue: a hand-kept
            # list missed each table a later migration added, so a test
            # writing to one of those started from whatever the previous
            # test left.
            cur.execute("TRUNCATE TABLE " + ", ".join(tables)
                        + " RESTART IDENTITY CASCADE")
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
