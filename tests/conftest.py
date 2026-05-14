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
    finally:
        conn.close()


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
                "TRUNCATE TABLE colocated_candidates, findings, triage, documents, "
                "applications, source_snapshots RESTART IDENTITY CASCADE"
            )
        conn.commit()
        yield conn
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
