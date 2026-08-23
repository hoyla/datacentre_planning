"""Postgres connection helpers. Raw psycopg2, no ORM."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import cursor as PgCursor
from psycopg2.extras import RealDictCursor


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set (cp .env.example .env and edit)")
    return url


# Without this, `psycopg2.connect` waits on the operating system's TCP
# timeout, which is minutes and on a dropped-packet outage is
# indefinite. It is only a problem when the database is across a
# network, which is exactly the arrangement the deep read runs in: the
# Studio reads, Postgres is on the laptop.
#
# Measured 2026-08-11: a transient outage left the reader blocked inside
# connect() for over 40 minutes, on a connection that succeeded the
# moment it was tried by hand. It had already exhausted its retry ladder
# and printed nothing since — a live process, an idle CPU and a log that
# had stopped, which reads exactly like a machine quietly working.
#
# It also defeats the offline spool, which is the more serious half: that
# path triggers on OperationalError, and a hang never raises one. A
# bounded timeout is what turns an unreachable database into an error the
# reader can act on instead of a wait it cannot see the end of.
CONNECT_TIMEOUT = int(os.environ.get("DCP_CONNECT_TIMEOUT", "10"))

# A build is supposed to be a function of its inputs, and the check for
# that builds twice and diffs. But the corpus moves: the corroboration
# read writes a row every few seconds, so two builds started ten seconds
# apart are two snapshots of different inputs, and the diff proves
# nothing either way. Postgres can hand out one snapshot to many
# connections (`pg_export_snapshot()` in a transaction that stays open;
# `SET TRANSACTION SNAPSHOT` in the others), which is exactly the fix:
# every connection a build opens sees the corpus as it was at one
# instant, whatever is being written meanwhile.
#
# Set this to an exported snapshot id and every connection opened here
# imports it, read-only, at REPEATABLE READ. Nothing else changes. It is
# for builds and checks; a process that needs to write must not set it.
SNAPSHOT_ENV = "DCP_PG_SNAPSHOT"


@contextmanager
def connect() -> Iterator[PgConnection]:
    conn = psycopg2.connect(database_url(), connect_timeout=CONNECT_TIMEOUT)
    snapshot = os.environ.get(SNAPSHOT_ENV)
    if snapshot:
        # Must precede the transaction's first query, and the isolation
        # level must be set before the transaction opens; psycopg2 sends
        # BEGIN with the first execute, so this is that execute.
        conn.set_session(
            isolation_level=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ,
            readonly=True)
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION SNAPSHOT %s", (snapshot,))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def cursor(dict_rows: bool = True) -> Iterator[PgCursor]:
    with connect() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor if dict_rows else None)
        try:
            yield cur
        finally:
            cur.close()
