"""SQLite engine and schema.

Single-writer by design (decision 5). `session()` yields a connection inside a
transaction; WAL lets the read-heavy `/v1/lemmatize` path avoid blocking on the
rare admin write.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
  id                 TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  key_id             TEXT NOT NULL UNIQUE,
  secret_enc         BLOB NOT NULL,
  secret_fingerprint TEXT NOT NULL,
  secret_prev_enc    BLOB,
  prev_expires_at    TEXT,
  scopes             TEXT NOT NULL DEFAULT '["lemmatize"]',
  langs              TEXT NOT NULL DEFAULT '[]',
  allow_hmac         INTEGER NOT NULL DEFAULT 0,
  rate_limit_rpm     INTEGER NOT NULL DEFAULT 600,
  created_at         TEXT NOT NULL,
  created_by         TEXT NOT NULL,
  last_used_at       TEXT,
  expires_at         TEXT,
  revoked_at         TEXT,
  revoked_reason     TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT NOT NULL,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  target      TEXT NOT NULL,
  before_json TEXT,
  after_json  TEXT,
  request_id  TEXT,
  ip          TEXT
);

CREATE TABLE IF NOT EXISTS request_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  request_id TEXT NOT NULL,
  key_id     TEXT,
  lang       TEXT,
  n_tokens   INTEGER,
  bytes_in   INTEGER,
  latency_ms INTEGER,
  status     INTEGER,
  error_code TEXT,
  ip         TEXT
);

CREATE TABLE IF NOT EXISTS hmac_nonces (
  nonce   TEXT PRIMARY KEY,
  seen_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_at  ON audit_log(at DESC);
CREATE INDEX IF NOT EXISTS idx_nonce_age ON hmac_nonces(seen_at);
CREATE INDEX IF NOT EXISTS idx_req_at    ON request_log(at DESC);
"""

_ENGINES: dict[str, Engine] = {}


def get_engine(url: str) -> Engine:
    engine = _ENGINES.get(url)
    if engine is None:
        engine = create_engine(url, future=True)

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        _ENGINES[url] = engine
    return engine


def init_db(url: str) -> None:
    engine = get_engine(url)
    with engine.begin() as conn:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)


@contextmanager
def session(url: str) -> Iterator[Connection]:
    engine = get_engine(url)
    with engine.begin() as conn:
        yield conn


def default_url() -> str:
    path = os.environ.get("LEMMA_DB_PATH", "./data/lemming.db")
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return f"sqlite:///{path}"
