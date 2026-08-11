"""Postgres connection helpers. Raw psycopg2, no ORM."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

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


@contextmanager
def connect() -> Iterator[PgConnection]:
    conn = psycopg2.connect(database_url(), connect_timeout=CONNECT_TIMEOUT)
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
