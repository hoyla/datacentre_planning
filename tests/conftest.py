"""Shared pytest fixtures.

Loads .env so DATABASE_URL is available, and provides per-test Postgres connections
for integration tests against a separate `dcp_test` database. Tests are marked
`@pytest.mark.integration` and skipped automatically if Postgres is unreachable.
"""

from __future__ import annotations

import os
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


def _ensure_test_database() -> None:
    """Create dcp_test if missing and apply migration if schema not yet present."""
    conn = psycopg2.connect(_admin_url())
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    finally:
        conn.close()

    conn = psycopg2.connect(_test_db_url())
    try:
        with conn.cursor() as cur:
            # Migration 001 — initial schema
            cur.execute("SELECT to_regclass('public.applications')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "001_initial.sql").read_text())
                conn.commit()
            # Migration 002 — discovery_via column + colocated_candidates table
            cur.execute("SELECT to_regclass('public.colocated_candidates')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "002_discovery_tracking.sql").read_text())
                conn.commit()
            # Migration 003 — triage columns refresh (worth_deep_read, signals, why,
            # confidence → TEXT). Probe via information_schema since this migration
            # adds a column rather than a new relation.
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'triage' AND column_name = 'worth_deep_read'"
            )
            if cur.fetchone() is None:
                cur.execute((MIGRATIONS_DIR / "003_triage_columns.sql").read_text())
                conn.commit()
            # Migration 004 — councils.notes → JSONB + council_aliases table.
            cur.execute("SELECT to_regclass('public.council_aliases')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "004_council_aliases.sql").read_text())
                conn.commit()
            # Migration 005 — projects + project_applications (Barbour ABI).
            cur.execute("SELECT to_regclass('public.projects')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "005_projects.sql").read_text())
                conn.commit()
            # Migration 006 — sites + site_members.
            cur.execute("SELECT to_regclass('public.sites')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "006_sites.sql").read_text())
                conn.commit()
            # Migration 008 — power_adjudication, and 009's signal_family
            # on findings. Both are read by the reader's per-site findings
            # query, so tests/test_export_ordering.py cannot exercise the
            # real SQL without them. 007 comes along because it is the
            # deep-read bookkeeping the other two are written against.
            cur.execute("SELECT to_regclass('public.deepread_log')")
            if cur.fetchone()[0] is None:
                cur.execute((MIGRATIONS_DIR / "007_deepread.sql").read_text())
                conn.commit()
            cur.execute("SELECT to_regclass('public.power_adjudication')")
            if cur.fetchone()[0] is None:
                cur.execute(
                    (MIGRATIONS_DIR / "008_power_adjudication.sql").read_text())
                conn.commit()
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'findings' AND column_name = 'signal_family'"
            )
            if cur.fetchone() is None:
                cur.execute(
                    (MIGRATIONS_DIR / "009_signal_family.sql").read_text())
                conn.commit()
            # Migration 021 — capacity_claims + capacity_claim_matches.
            cur.execute("SELECT to_regclass('public.capacity_claims')")
            if cur.fetchone()[0] is None:
                cur.execute(
                    (MIGRATIONS_DIR / "021_capacity_claims.sql").read_text())
                conn.commit()
    finally:
        conn.close()


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
    out = tmp_path_factory.mktemp("reader") / "reader.html"
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "export_reader.py"),
         "--out", str(out), "--phase", "test"],
        cwd=root, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0:
        combined = proc.stdout + proc.stderr
        tail = combined.strip().splitlines()[-8:]
        if "uncorrected" in combined:
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
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE project_applications, projects, "
                "colocated_candidates, findings, triage, documents, "
                "applications, source_snapshots, council_aliases, "
                "capacity_claim_matches, capacity_claims, site_members, "
                "power_adjudication, deepread_log, "
                "sites RESTART IDENTITY CASCADE"
            )
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
