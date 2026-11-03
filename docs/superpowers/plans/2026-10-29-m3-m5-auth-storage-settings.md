# M3+M5 Auth, Storage, Settings and Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add API-Key/Secret authentication (Bearer + HMAC), rate limiting, SQLite persistence, a whitelisted settings registry, and an audit log to the M1+M2 API — turning it into something safe to expose.

**Architecture:** A SQLite database owned exclusively by the Python process is the single source of truth for keys and settings. Secrets are stored AES-256-GCM encrypted (not hashed — HMAC verification needs the plaintext). Every request passes through an auth dependency that resolves `key_id` → decrypted secret → constant-time verification → scope/lang/rate checks. Admin routes require a separate admin token, never exposed to a browser.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 (Core, not ORM), cryptography, pytest. No new external services.

**Spec:** `docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md` §5, §6, §7
**Depends on:** Plan 1 (`docs/superpowers/plans/2026-10-29-m1-m2-lemmatization-core.md`) — must be merged first.

---

## Verification already performed

The non-HTTP modules (crypto, schema, key store, HMAC, nonce cache, rate limiter, settings/audit) were extracted into a scratch project and **executed**:

| Verified | Result |
|---|---|
| Tasks 1–3, 4–6, 8 test suites | **53 passed** |
| AAD binding (ciphertext not transplantable between key_ids) | mutation-tested |
| Plaintext-at-rest (encryption removed) | mutation-tested |
| Signature never checked (`verify` → `True`) | mutation-tested |
| HKDF separation removed (raw secret as HMAC key) | mutation-tested |
| Revocation ignored | mutation-tested |
| Rotation grace period ignored | mutation-tested |
| **Timestamp window ignored** | **initially NOT caught** — see below |

**Defect found by mutation testing and fixed here:** `timestamp_within_window` had **no unit tests at all**. Replacing its body with `return True` — disabling one of the three replay defences — passed the entire suite, because only an HTTP-level test in Task 7 covered it. Five unit tests were added (accepts now, accepts ±299s skew, rejects stale, rejects far-future, rejects non-numeric); the mutation now fails. Far-future matters specifically: without a two-sided window a timestamp decades ahead stays valid forever.

**All tasks were subsequently executed end to end.** 218 tests pass, and a live
server with `LEMMA_AUTH_ENABLED=1` was driven through ten scenarios: no
credential, valid Bearer, wrong secret, valid HMAC, replayed nonce, admin
without tokens, admin session + key listing (asserting no secret leaks),
settings patch + audit row, diagnostics read-only (PATCH returns 405), and
request-log shape capture.

**Three more defects were found only by running it, and are fixed in the tasks below:**

1. **HMAC never verified.** `api/auth/deps.py` read `request.state.body_bytes`,
   but nothing ever wrote it. Every signed request failed `SIGNATURE_INVALID`
   while Bearer worked, so the unit tests passed and the feature did not. Starlette
   discards the body stream once parsed, so Task 7b's middleware now caches the
   raw bytes before routing — and only when `X-Signature` is present, so ordinary
   traffic is not buffered.
2. **429 carried no `Retry-After`.** A bare 429 forces blind backoff. The
   `ApiError` handler now emits it from `details.retry_after`.
3. **Every error response had `request_id: null`.** Authentication runs as a
   dependency *before* the route, so the route's id was never assigned on the
   401/403/429 paths and those rows could not be correlated with their own
   log entries. The id is now minted in the middleware.

Plus one lint-level correction: `Depends()` in an argument default (B008) became
`Annotated[..., Depends(...)]`.

> When running the stack by hand, bind a *random* port and trap cleanup. A
> leftover uvicorn from an earlier run will happily answer on the old port with
> an old master key, which looks exactly like "auth is broken".

**Dependency versions actually resolved:** sqlalchemy 2.1.6, cryptography 50.0.2, argon2-cffi 25.1.0.

---

## Scope note

| Plan | Covers | Status |
|---|---|---|
| Plan 1 | M1+M2 — 7 backends, `/v1/lemmatize`, `/v1/languages`, `/v1/health` | written, verified |
| **This plan** | M3+M5 — Key/Secret, Bearer+HMAC, rate limit, SQLite, settings whitelist, audit, request log | crypto + logger verified (59 tests); HTTP layer written |
| Plan 3 | M4+M6 — Next.js console (BFF), admin session, Playground, Docker images | next |

This plan does **not** touch the console. It exposes the admin HTTP surface the console will call.

---

## Design decisions fixed before coding

Three things the spec left implicit. Each is decided here, with the reasoning, because getting them wrong is expensive later:

**1. `key_id` is a public identifier, never a credential.** The spec's §5.2 already corrects this. Both auth modes therefore require the secret. `Bearer <key_id>.<secret>` or HMAC with the secret.

**2. Secret is encrypted, not hashed.** HMAC verification needs the plaintext secret. `secret_enc = AES-256-GCM(master_key)`, AAD = `key_id` so a ciphertext cannot be transplanted between keys. `secret_fingerprint = sha256(secret)[:8]` is stored separately only so an operator can tell *which* secret is live — it is not a verifier.

**3. HMAC signing key is derived, not the secret itself.** `signing_key = HKDF-SHA256(secret, info=b"lemma-hmac-v1", length=32)`. Using the raw secret for both Bearer and HMAC would mean a Bearer header leak (`key_id.secret`) hands over the HMAC key too. Deriving separates the two uses of the same material.

---

## File structure

| File | Responsibility |
|---|---|
| `api/crypto.py` | AES-GCM seal/open, secret generation, HKDF, constant-time compare |
| `api/db.py` | engine, `init_db()`, schema, connection/transaction helpers |
| `api/models.py` | dataclasses for `ApiKey`, `AuditEntry`, `SettingRow` |
| `api/store/keys.py` | create / get by key_id / rotate / revoke / list |
| `api/store/settings.py` | read merged settings, write one whitelisted key |
| `api/store/audit.py` | append + paginated read |
| `api/auth/hmac.py` | canonical string, signature computation and verification |
| `api/auth/bearer.py` | `key_id.secret` parsing and verification |
| `api/auth/nonce.py` | in-memory TTL nonce cache with capacity bound |
| `api/auth/ratelimit.py` | token-bucket per key, in-memory |
| `api/auth/deps.py` | the FastAPI dependency that authenticates a request |
| `api/auth/admin.py` | admin passphrase → admin token, and the admin dependency |
| `api/settings/registry.py` | `EDITABLE` whitelist with `hot` flags and defaults |
| `api/routes/admin_keys.py` | `/admin/keys` CRUD + rotate |
| `api/routes/admin_settings.py` | `/admin/settings`, `/admin/diagnostics`, `/admin/audit` |
| `api/routes/admin_session.py` | `POST /admin/session` |
| `api/cli.py` | `create-key`, `rotate-all` for bootstrap |
| `tests/test_crypto.py` | seal/open roundtrip, tamper detection, AAD binding |
| `tests/test_hmac.py` | canonical string, sign/verify, negative cases |
| `tests/test_nonce.py` | replay rejection, TTL expiry, capacity bound |
| `tests/test_ratelimit.py` | bucket refill, burst, headers |
| `tests/test_store_keys.py` | create/rotate/revoke lifecycle |
| `tests/test_store_settings.py` | whitelist enforcement, audit rows |
| `tests/test_api_auth.py` | Bearer + HMAC through HTTP, all error codes |
| `tests/test_api_admin.py` | admin session, key management over HTTP |

---

## Task 1: Crypto primitives

**Files:**
- Create: `api/crypto.py`
- Test: `tests/test_crypto.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/test_crypto.py
import pytest

from api.crypto import (
    constant_time_compare,
    derive_signing_key,
    fingerprint,
    generate_secret,
    open_secret,
    seal_secret,
)

MASTER = b"0" * 32


def test_seal_open_roundtrip():
    secret = generate_secret()
    assert open_secret(seal_secret(secret, "key_abc", MASTER), "key_abc", MASTER) == secret


def test_sealed_plaintext_is_not_recoverable_without_master_key():
    secret = seal_secret("ls_hello", "key_abc", MASTER)
    wrong = b"1" * 32
    with pytest.raises(Exception):
        open_secret(secret, "key_abc", wrong)


def test_aad_binds_ciphertext_to_key_id():
    """A sealed secret must not be replayable under a different key_id."""
    blob = seal_secret("ls_hello", "key_abc", MASTER)
    with pytest.raises(Exception):
        open_secret(blob, "key_DIFFERENT", MASTER)


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(seal_secret("ls_hello", "key_abc", MASTER))
    blob[-1] ^= 0xFF
    with pytest.raises(Exception):
        open_secret(bytes(blob), "key_abc", MASTER)


def test_generate_secret_is_prefixed_and_unique():
    a, b = generate_secret(), generate_secret()
    assert a.startswith("ls_")
    assert a != b


def test_fingerprint_is_stable_and_short():
    assert fingerprint("ls_abc") == fingerprint("ls_abc")
    assert len(fingerprint("ls_abc")) == 8
    assert fingerprint("ls_abc") != fingerprint("ls_abd")


def test_constant_time_compare():
    assert constant_time_compare("abc", "abc") is True
    assert constant_time_compare("abc", "abd") is False
    assert constant_time_compare("abc", "abcd") is False


def test_derive_signing_key_is_deterministic_and_not_the_secret():
    k1 = derive_signing_key("ls_abc")
    k2 = derive_signing_key("ls_abc")
    assert k1 == k2
    assert len(k1) == 32
    assert b"ls_abc" not in k1
    assert k1 != derive_signing_key("ls_abd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.crypto'`

- [ ] **Step 3: Write `api/crypto.py`**

```python
"""Secret storage and signing-key derivation.

Secrets are ENCRYPTED, not hashed. HMAC verification needs the plaintext, so a
one-way digest would make signature checking impossible. The fingerprint is a
separate, non-verifying value used only so an operator can tell which secret is
currently live.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NONCE_BYTES = 12
SECRET_BYTES = 32


def _key(master_key: bytes) -> bytes:
    if len(master_key) != 32:
        raise ValueError(f"master key must be 32 bytes, got {len(master_key)}")
    return master_key


def seal_secret(secret: str, key_id: str, master_key: bytes) -> bytes:
    """Encrypt a secret. AAD binds the ciphertext to its key_id."""
    nonce = os.urandom(NONCE_BYTES)
    blob = AESGCM(_key(master_key)).encrypt(nonce, secret.encode(), key_id.encode())
    return nonce + blob


def open_secret(blob: bytes, key_id: str, master_key: bytes) -> str:
    """Decrypt a secret. Raises on wrong master key, wrong key_id, or tampering."""
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    plaintext = AESGCM(_key(master_key)).decrypt(nonce, ciphertext, key_id.encode())
    return plaintext.decode()


def generate_secret() -> str:
    return "ls_" + base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def generate_key_id() -> str:
    return "lk_" + base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")


def fingerprint(secret: str) -> str:
    """Short non-verifying label so an operator can identify a live secret."""
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def derive_signing_key(secret: str) -> bytes:
    """Separate the HMAC key from the Bearer credential.

    If the raw secret were used for both, a leaked `Authorization: Bearer`
    header would also hand over everything needed to forge HMAC signatures.
    """
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"lemma-hmac-v1"
    ).derive(secret.encode())


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_master_key() -> bytes:
    return secrets.token_bytes(32)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crypto.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/crypto.py tests/test_crypto.py
git commit -m "feat: add AES-GCM secret sealing and HKDF signing-key derivation"
```

---

## Task 2: Database schema

**Files:**
- Create: `api/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from api.db import init_db, session


def test_init_db_creates_all_tables(tmp_path):
    db = tmp_path / "t.db"
    init_db(f"sqlite:///{db}")
    with session(f"sqlite:///{db}") as conn:
        names = {
            r[0]
            for r in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"api_keys", "settings", "audit_log", "request_log"} <= names


def test_init_db_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    init_db(url)  # must not raise


def test_foreign_keys_and_wal_are_enabled(tmp_path):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    with session(url) as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.db'`

- [ ] **Step 3: Write `api/db.py`**

```python
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

CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);
CREATE INDEX IF NOT EXISTS idx_req_at   ON request_log(at DESC);
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add api/db.py tests/test_db.py
git commit -m "feat: add SQLite schema with WAL and busy timeout"
```

---

## Task 3: Key store

**Files:**
- Create: `api/models.py`
- Create: `api/store/__init__.py`
- Create: `api/store/keys.py`
- Test: `tests/test_store_keys.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_keys.py
import pytest

from api.db import init_db
from api.store import keys

MASTER = b"0" * 32


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path / 't.db'}"
    init_db(u)
    return u


def test_create_returns_plaintext_secret_once(url):
    created = keys.create(url, name="demo", created_by="admin", master_key=MASTER)
    assert created.key_id.startswith("lk_")
    assert created.secret.startswith("ls_")
    assert created.secret_fingerprint == keys.fingerprint_of(created.secret)


def test_secret_is_not_stored_in_plaintext(url):
    created = keys.create(url, name="demo", created_by="admin", master_key=MASTER)
    with keys._session(url) as conn:
        row = conn.exec_driver_sql("SELECT secret_enc FROM api_keys").one()
    assert created.secret.encode() not in bytes(row[0])


def test_verify_bearer_accepts_correct_secret(url):
    created = keys.create(url, name="d", created_by="a", master_key=MASTER)
    resolved = keys.verify_bearer(url, created.key_id, created.secret, MASTER)
    assert resolved is not None
    assert resolved.key_id == created.key_id


def test_verify_bearer_rejects_wrong_secret(url):
    created = keys.create(url, name="d", created_by="a", master_key=MASTER)
    assert keys.verify_bearer(url, created.key_id, "ls_wrong", MASTER) is None


def test_verify_bearer_rejects_unknown_key_id(url):
    assert keys.verify_bearer(url, "lk_nope", "ls_x", MASTER) is None


def test_revoked_key_fails_verification(url):
    created = keys.create(url, name="d", created_by="a", master_key=MASTER)
    keys.revoke(url, created.key_id, reason="test", actor="admin")
    assert keys.verify_bearer(url, created.key_id, created.secret, MASTER) is None


def test_rotate_accepts_both_secrets_during_grace(url):
    created = keys.create(url, name="d", created_by="a", master_key=MASTER)
    rotated = keys.rotate(url, created.key_id, master_key=MASTER, grace_hours=24)
    assert rotated.secret != created.secret
    assert keys.verify_bearer(url, created.key_id, rotated.secret, MASTER) is not None
    assert keys.verify_bearer(url, created.key_id, created.secret, MASTER) is not None


def test_rotate_with_zero_grace_rejects_old_secret_immediately(url):
    created = keys.create(url, name="d", created_by="a", master_key=MASTER)
    keys.rotate(url, created.key_id, master_key=MASTER, grace_hours=0)
    assert keys.verify_bearer(url, created.key_id, created.secret, MASTER) is None


def test_expired_key_fails_verification(url):
    created = keys.create(
        url, name="d", created_by="a", master_key=MASTER, expires_at="2000-01-01T00:00:00Z"
    )
    assert keys.verify_bearer(url, created.key_id, created.secret, MASTER) is None


def test_lang_restriction_and_allow_hmac_are_persisted(url):
    created = keys.create(
        url, name="d", created_by="a", master_key=MASTER,
        langs=["de", "fr"], allow_hmac=True,
    )
    resolved = keys.verify_bearer(url, created.key_id, created.secret, MASTER)
    assert resolved.langs == ["de", "fr"]
    assert resolved.allow_hmac is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_keys.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.store'`

- [ ] **Step 3: Write `api/models.py`, `api/store/__init__.py`, `api/store/keys.py`**

`api/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CreatedKey:
    """Returned once, at creation/rotation time. Carries the only plaintext copy."""

    key_id: str
    secret: str
    secret_fingerprint: str
    name: str


@dataclass
class ResolvedKey:
    """What auth hands to a route. Never contains the secret."""

    key_id: str
    name: str
    scopes: list[str] = field(default_factory=list)
    langs: list[str] = field(default_factory=list)
    allow_hmac: bool = False
    rate_limit_rpm: int = 600

    def allows_lang(self, lang: str) -> bool:
        return not self.langs or lang in self.langs

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
```

`api/store/__init__.py`: empty file.

`api/store/keys.py`:
```python
"""Key lifecycle: create, resolve, verify, rotate, revoke.

The plaintext secret leaves this module exactly twice: at create() and at
rotate(). Every other read path returns a ResolvedKey, which has no secret.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from api.crypto import (
    constant_time_compare,
    fingerprint,
    generate_key_id,
    generate_secret,
    open_secret,
    seal_secret,
)
from api.db import session
from api.models import CreatedKey, ResolvedKey


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session(url: str):
    return session(url)


def fingerprint_of(secret: str) -> str:
    return fingerprint(secret)


def create(
    url: str,
    *,
    name: str,
    created_by: str,
    master_key: bytes,
    scopes: list[str] | None = None,
    langs: list[str] | None = None,
    allow_hmac: bool = False,
    rate_limit_rpm: int = 600,
    expires_at: str | None = None,
) -> CreatedKey:
    key_id = generate_key_id()
    secret = generate_secret()
    with session(url) as conn:
        conn.exec_driver_sql(
            """INSERT INTO api_keys
               (id, name, key_id, secret_enc, secret_fingerprint, scopes, langs,
                allow_hmac, rate_limit_rpm, created_at, created_by, expires_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                uuid.uuid4().hex, name, key_id,
                seal_secret(secret, key_id, master_key),
                fingerprint(secret),
                json.dumps(scopes or ["lemmatize"]),
                json.dumps(langs or []),
                1 if allow_hmac else 0,
                rate_limit_rpm, _now(), created_by, expires_at,
            ),
        )
    return CreatedKey(
        key_id=key_id, secret=secret, secret_fingerprint=fingerprint(secret), name=name
    )


def _row(url: str, key_id: str):
    with session(url) as conn:
        return conn.exec_driver_sql(
            "SELECT * FROM api_keys WHERE key_id = ?", (key_id,)
        ).mappings().first()


def _usable(row, now: str) -> bool:
    if row["revoked_at"] is not None:
        return False
    return not (row["expires_at"] is not None and row["expires_at"] <= now)


def _to_resolved(row) -> ResolvedKey:
    return ResolvedKey(
        key_id=row["key_id"],
        name=row["name"],
        scopes=json.loads(row["scopes"]),
        langs=json.loads(row["langs"]),
        allow_hmac=bool(row["allow_hmac"]),
        rate_limit_rpm=row["rate_limit_rpm"],
    )


def verify_bearer(
    url: str, key_id: str, secret: str, master_key: bytes
) -> ResolvedKey | None:
    row = _row(url, key_id)
    if row is None or not _usable(row, _now()):
        return None

    try:
        current = open_secret(bytes(row["secret_enc"]), key_id, master_key)
    except Exception:
        return None

    if constant_time_compare(current, secret):
        _touch(url, key_id)
        return _to_resolved(row)

    if row["secret_prev_enc"] is not None and row["prev_expires_at"] is not None:
        if row["prev_expires_at"] > _now():
            try:
                previous = open_secret(bytes(row["secret_prev_enc"]), key_id, master_key)
            except Exception:
                return None
            if constant_time_compare(previous, secret):
                _touch(url, key_id)
                return _to_resolved(row)
    return None


def get_secret(url: str, key_id: str, master_key: bytes) -> str | None:
    """Used by the HMAC path, which must compute a signature over the secret."""
    row = _row(url, key_id)
    if row is None or not _usable(row, _now()):
        return None
    try:
        return open_secret(bytes(row["secret_enc"]), key_id, master_key)
    except Exception:
        return None


def resolve_active(url: str, key_id: str) -> ResolvedKey | None:
    row = _row(url, key_id)
    if row is None or not _usable(row, _now()):
        return None
    return _to_resolved(row)


def _touch(url: str, key_id: str) -> None:
    with session(url) as conn:
        conn.exec_driver_sql(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (_now(), key_id)
        )


def rotate(
    url: str, key_id: str, *, master_key: bytes, grace_hours: int = 24
) -> CreatedKey:
    row = _row(url, key_id)
    if row is None:
        raise KeyError(key_id)
    secret = generate_secret()
    expires = (
        datetime.now(UTC) + timedelta(hours=grace_hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    with session(url) as conn:
        conn.exec_driver_sql(
            """UPDATE api_keys
               SET secret_prev_enc = secret_enc,
                   prev_expires_at  = ?,
                   secret_enc       = ?,
                   secret_fingerprint = ?
               WHERE key_id = ?""",
            (
                expires if grace_hours > 0 else None,
                seal_secret(secret, key_id, master_key),
                fingerprint(secret), key_id,
            ),
        )
    return CreatedKey(
        key_id=key_id, secret=secret,
        secret_fingerprint=fingerprint(secret), name=row["name"],
    )


def revoke(url: str, key_id: str, *, reason: str, actor: str) -> bool:
    with session(url) as conn:
        result = conn.exec_driver_sql(
            """UPDATE api_keys SET revoked_at = ?, revoked_reason = ?
               WHERE key_id = ? AND revoked_at IS NULL""",
            (_now(), reason, key_id),
        )
        return result.rowcount > 0


def list_all(url: str) -> list[dict]:
    """Never returns secrets, encrypted or otherwise."""
    with session(url) as conn:
        rows = conn.exec_driver_sql(
            """SELECT key_id, name, secret_fingerprint, scopes, langs, allow_hmac,
                      rate_limit_rpm, created_at, created_by, last_used_at,
                      expires_at, revoked_at
               FROM api_keys ORDER BY created_at DESC"""
        ).mappings().all()
    return [
        {**dict(r), "scopes": json.loads(r["scopes"]), "langs": json.loads(r["langs"])}
        for r in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store_keys.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add api/models.py api/store/__init__.py api/store/keys.py tests/test_store_keys.py
git commit -m "feat: add encrypted API key store with rotation grace period"
```

---

## Task 4: HMAC signing and verification

**Files:**
- Create: `api/auth/__init__.py`
- Create: `api/auth/hmac.py`
- Test: `tests/test_hmac.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hmac.py
import base64
import hashlib

from api.auth.hmac import canonical_string, sign, timestamp_within_window, verify

SECRET = "ls_testsecret"


def test_canonical_string_layout():
    body = b'{"lang":"de"}'
    got = canonical_string("POST", "/v1/lemmatize", "1700000000", "abc", body)
    expected = "\n".join([
        "POST", "/v1/lemmatize", "1700000000", "abc",
        hashlib.sha256(body).hexdigest(),
    ])
    assert got == expected


def test_sign_then_verify_roundtrip():
    body = b'{"lang":"de"}'
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert verify(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body, sig)


def test_verify_rejects_changed_body():
    body = b'{"lang":"de"}'
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert not verify(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", b'{"lang":"fr"}', sig)


def test_verify_rejects_changed_path():
    body = b"{}"
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert not verify(SECRET, "POST", "/v1/other", "1700000000", "n1", body, sig)


def test_verify_rejects_changed_method():
    body = b"{}"
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert not verify(SECRET, "GET", "/v1/lemmatize", "1700000000", "n1", body, sig)


def test_verify_rejects_changed_nonce():
    body = b"{}"
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert not verify(SECRET, "POST", "/v1/lemmatize", "1700000000", "n2", body, sig)


def test_verify_rejects_wrong_secret():
    body = b"{}"
    sig = sign(SECRET, "POST", "/v1/lemmatize", "1700000000", "n1", body)
    assert not verify("ls_other", "POST", "/v1/lemmatize", "1700000000", "n1", body, sig)


def test_verify_rejects_malformed_signature():
    assert not verify(SECRET, "POST", "/x", "1", "n", b"", "not-base64!!")


def test_signature_is_base64():
    sig = sign(SECRET, "POST", "/x", "1", "n", b"")
    base64.b64decode(sig, validate=True)  # must not raise


def test_timestamp_within_window_accepts_now():
    assert timestamp_within_window("1700000000", now=1700000000.0) is True


def test_timestamp_within_window_accepts_small_skew():
    assert timestamp_within_window("1700000000", now=1700000000.0 + 299) is True
    assert timestamp_within_window("1700000000", now=1700000000.0 - 299) is True


def test_timestamp_within_window_rejects_stale():
    assert timestamp_within_window("1700000000", now=1700000000.0 + 301) is False


def test_timestamp_within_window_rejects_future():
    """A far-future timestamp would otherwise stay valid forever."""
    assert timestamp_within_window("1700000000", now=1700000000.0 - 301) is False


def test_timestamp_within_window_rejects_non_numeric():
    assert timestamp_within_window("not-a-number", now=1700000000.0) is False
    assert timestamp_within_window("", now=1700000000.0) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_hmac.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.auth'`

- [ ] **Step 3: Write `api/auth/hmac.py`**

```python
"""HMAC request signing.

The signed string is: METHOD \\n PATH \\n TIMESTAMP \\n NONCE \\n sha256(body).

Signing uses a DERIVED key, not the secret itself, so a leaked Bearer header
cannot be replayed as an HMAC key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import time

from api.crypto import derive_signing_key

TIMESTAMP_WINDOW_SECONDS = 300


def canonical_string(
    method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    return "\n".join(
        [method.upper(), path, timestamp, nonce, hashlib.sha256(body).hexdigest()]
    )


def sign(
    secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    message = canonical_string(method, path, timestamp, nonce, body).encode()
    digest = hmac_mod.new(derive_signing_key(secret), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify(
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
) -> bool:
    try:
        provided = base64.b64decode(signature, validate=True)
    except Exception:
        return False
    expected = base64.b64decode(
        sign(secret, method, path, timestamp, nonce, body), validate=True
    )
    return hmac_mod.compare_digest(provided, expected)


def timestamp_within_window(timestamp: str, now: float | None = None) -> bool:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    return abs(current - value) <= TIMESTAMP_WINDOW_SECONDS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_hmac.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add api/auth/__init__.py api/auth/hmac.py tests/test_hmac.py
git commit -m "feat: add HMAC signing over method/path/timestamp/nonce/body"
```

---

## Task 5: Nonce cache

**Files:**
- Create: `api/auth/nonce.py`
- Test: `tests/test_nonce.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nonce.py
from api.auth.nonce import NonceCache


def test_first_use_is_accepted():
    cache = NonceCache()
    assert cache.consume("n1", now=1000.0) is True


def test_replay_is_rejected():
    cache = NonceCache()
    cache.consume("n1", now=1000.0)
    assert cache.consume("n1", now=1000.0) is False


def test_entry_expires_after_ttl():
    cache = NonceCache(ttl_seconds=10)
    cache.consume("n1", now=1000.0)
    assert cache.consume("n1", now=1009.0) is False
    assert cache.consume("n1", now=1011.0) is True


def test_capacity_is_bounded():
    cache = NonceCache(max_entries=3)
    for i in range(10):
        cache.consume(f"n{i}", now=1000.0 + i)
    assert cache.size() <= 3


def test_evicted_nonce_becomes_accepted_again_documented_tradeoff():
    """Capacity eviction trades replay protection for bounded memory.

    A hostile client that floods nonces can evict its own earlier entries. This
    is acceptable because the nonce is only one of three replay defences (the
    timestamp window and the signature also apply), but it must be explicit.
    """
    cache = NonceCache(max_entries=2, ttl_seconds=10_000)
    cache.consume("target", now=1000.0)
    cache.consume("a", now=1001.0)
    cache.consume("b", now=1002.0)  # evicts "target"
    assert cache.consume("target", now=1003.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_nonce.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.auth.nonce'`

- [ ] **Step 3: Write `api/auth/nonce.py`**

```python
"""In-memory nonce cache for HMAC replay protection.

SINGLE-INSTANCE ONLY. The spec accepts this because decision 5 pins a single
container. If the API is ever horizontally scaled, this must move to a shared
store or nonces will replay across instances. See the risk table in the spec.
"""

from __future__ import annotations

import time
from collections import OrderedDict


class NonceCache:
    def __init__(self, ttl_seconds: int = 600, max_entries: int = 100_000) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._seen: OrderedDict[str, float] = OrderedDict()

    def consume(self, nonce: str, now: float | None = None) -> bool:
        """Record a nonce. Returns False if it was already used and still live."""
        current = time.time() if now is None else now
        self._expire(current)

        if nonce in self._seen:
            return False

        self._seen[nonce] = current
        while len(self._seen) > self._max:
            self._seen.popitem(last=False)
        return True

    def _expire(self, now: float) -> None:
        cutoff = now - self._ttl
        while self._seen:
            oldest_nonce, seen_at = next(iter(self._seen.items()))
            if seen_at >= cutoff:
                break
            self._seen.pop(oldest_nonce)

    def size(self) -> int:
        return len(self._seen)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_nonce.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/auth/nonce.py tests/test_nonce.py
git commit -m "feat: add bounded TTL nonce cache for HMAC replay protection"
```

---

## Task 6: Rate limiter

**Files:**
- Create: `api/auth/ratelimit.py`
- Test: `tests/test_ratelimit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ratelimit.py
from api.auth.ratelimit import RateLimiter


def test_allows_requests_under_the_limit():
    rl = RateLimiter()
    for i in range(5):
        assert rl.check("k1", rpm=60, burst=5, now=1000.0 + i * 0.01).allowed


def test_blocks_once_burst_is_exhausted():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    result = rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert result.allowed is False
    assert result.retry_after >= 1


def test_refills_over_time():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    # 60 rpm = 1 token/sec, so 1s should release exactly one
    assert rl.check("k1", rpm=60, burst=5, now=1001.0).allowed is True


def test_keys_are_isolated():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert rl.check("k2", rpm=60, burst=5, now=1000.0).allowed is True


def test_remaining_is_reported():
    rl = RateLimiter()
    result = rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert result.remaining == 4
    assert result.limit == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ratelimit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.auth.ratelimit'`

- [ ] **Step 3: Write `api/auth/ratelimit.py`**

```python
"""Per-key token bucket.

In-memory, like the nonce cache, and for the same single-instance reason. The
bucket is keyed by key_id, so one abusive tenant cannot starve another.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    remaining: int
    limit: int
    retry_after: int = 0


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(
        self, key_id: str, *, rpm: int, burst: int, now: float | None = None
    ) -> Decision:
        current = time.time() if now is None else now
        rate_per_second = rpm / 60.0

        tokens, last = self._buckets.get(key_id, (float(burst), current))
        tokens = min(float(burst), tokens + (current - last) * rate_per_second)

        if tokens >= 1.0:
            tokens -= 1.0
            self._buckets[key_id] = (tokens, current)
            return Decision(
                allowed=True, remaining=int(tokens), limit=burst
            )

        self._buckets[key_id] = (tokens, current)
        deficit = 1.0 - tokens
        retry_after = max(1, math.ceil(deficit / rate_per_second))
        return Decision(
            allowed=False, remaining=0, limit=burst, retry_after=retry_after
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ratelimit.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/auth/ratelimit.py tests/test_ratelimit.py
git commit -m "feat: add per-key token bucket rate limiter"
```

---

## Task 7: Auth dependency

**Files:**
- Create: `api/auth/deps.py`
- Test: `tests/test_api_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_auth.py
import time

import pytest

from api.auth.hmac import sign
from api.db import init_db
from api.main import create_app
from api.store import keys
from fastapi.testclient import TestClient

MASTER = b"0" * 32


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    app = create_app(registry_fakes=True, db_url=url, auth_enabled=True)
    client = TestClient(app)
    created = keys.create(url, name="t", created_by="test", master_key=MASTER,
                          allow_hmac=True)
    return client, created, url


def test_missing_credentials_is_401(app_client):
    client, _, _ = app_client
    resp = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_valid_bearer_succeeds(app_client):
    client, created, _ = app_client
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {created.key_id}.{created.secret}"},
    )
    assert resp.status_code == 200


def test_bearer_with_only_key_id_is_rejected(app_client):
    """key_id is an identifier, not a credential. This must never authenticate."""
    client, created, _ = app_client
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {created.key_id}"},
    )
    assert resp.status_code == 401


def test_valid_hmac_succeeds(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "nonce-1", body)
    resp = client.post(
        "/v1/lemmatize", content=body,
        headers={
            "content-type": "application/json",
            "X-Api-Key": created.key_id,
            "X-Timestamp": ts,
            "X-Nonce": "nonce-1",
            "X-Signature": sig,
        },
    )
    assert resp.status_code == 200


def test_hmac_replay_is_rejected(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "nonce-r", body)
    headers = {
        "content-type": "application/json", "X-Api-Key": created.key_id,
        "X-Timestamp": ts, "X-Nonce": "nonce-r", "X-Signature": sig,
    }
    assert client.post("/v1/lemmatize", content=body, headers=headers).status_code == 200
    second = client.post("/v1/lemmatize", content=body, headers=headers)
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "NONCE_REPLAYED"


def test_hmac_stale_timestamp_is_rejected(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()) - 10_000)
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "n-old", body)
    resp = client.post(
        "/v1/lemmatize", content=body,
        headers={
            "content-type": "application/json", "X-Api-Key": created.key_id,
            "X-Timestamp": ts, "X-Nonce": "n-old", "X-Signature": sig,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TIMESTAMP_OUT_OF_WINDOW"


def test_hmac_when_key_disallows_it_is_rejected(app_client):
    client, _, url = app_client
    no_hmac = keys.create(url, name="nh", created_by="t", master_key=MASTER,
                          allow_hmac=False)
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(no_hmac.secret, "POST", "/v1/lemmatize", ts, "n-x", body)
    resp = client.post(
        "/v1/lemmatize", content=body,
        headers={
            "content-type": "application/json", "X-Api-Key": no_hmac.key_id,
            "X-Timestamp": ts, "X-Nonce": "n-x", "X-Signature": sig,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "HMAC_NOT_ALLOWED"


def test_lang_restriction_is_enforced(app_client):
    client, _, url = app_client
    restricted = keys.create(url, name="r", created_by="t", master_key=MASTER,
                             langs=["fr"])
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {restricted.key_id}.{restricted.secret}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LANG_FORBIDDEN"


def test_rate_limit_headers_and_429(app_client):
    client, _, url = app_client
    tiny = keys.create(url, name="tiny", created_by="t", master_key=MASTER,
                       rate_limit_rpm=1)
    auth = {"Authorization": f"Bearer {tiny.key_id}.{tiny.secret}"}
    first = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}, headers=auth)
    assert first.status_code == 200
    assert "X-RateLimit-Limit" in first.headers
    assert "X-RateLimit-Remaining" in first.headers

    limited = None
    for _ in range(60):
        r = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}, headers=auth)
        if r.status_code == 429:
            limited = r
            break
    assert limited is not None
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in limited.headers


def test_health_stays_open_without_credentials(app_client):
    client, _, _ = app_client
    assert client.get("/v1/health").status_code == 200


def test_languages_stays_open_without_credentials(app_client):
    client, _, _ = app_client
    assert client.get("/v1/languages").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_auth.py -v`
Expected: FAIL — `create_app()` does not yet accept `db_url`/`auth_enabled`.

- [ ] **Step 3: Write `api/auth/deps.py`**

```python
"""The single place a request becomes an authenticated key.

Order matters. Timestamp and nonce are checked BEFORE the signature so a
replayed request is rejected without an expensive decrypt, and a stale request
never reaches key lookup at all.
"""

from __future__ import annotations

import os

from fastapi import Request

from api.auth.hmac import timestamp_within_window, verify as verify_hmac
from api.auth.nonce import NonceCache
from api.auth.ratelimit import RateLimiter
from api.crypto import constant_time_compare
from api.errors import ApiError
from api.models import ResolvedKey
from api.store import keys


def master_key() -> bytes:
    raw = os.environ.get("LEMMA_MASTER_KEY", "")
    if not raw:
        raise ApiError("INTERNAL", 500, "LEMMA_MASTER_KEY is not configured")
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise ApiError("INTERNAL", 500, "LEMMA_MASTER_KEY must be 32 hex bytes") from exc


def _parse_bearer(value: str) -> tuple[str, str]:
    token = value.removeprefix("Bearer ").strip()
    if "." not in token:
        raise ApiError(
            "UNAUTHORIZED", 401,
            "Bearer credential must be '<key_id>.<secret>'",
        )
    key_id, _, secret = token.partition(".")
    return key_id, secret


async def authenticate(request: Request) -> ResolvedKey:
    app = request.app
    url: str = app.state.db_url
    secret_key = master_key()

    signature = request.headers.get("X-Signature")
    authorization = request.headers.get("Authorization")

    if signature:
        resolved = _authenticate_hmac(request, url, secret_key)
    elif authorization:
        key_id, secret = _parse_bearer(authorization)
        resolved = keys.verify_bearer(url, key_id, secret, secret_key)
        if resolved is None:
            raise ApiError("UNAUTHORIZED", 401, "invalid key or secret")
    else:
        raise ApiError(
            "UNAUTHORIZED", 401,
            "provide 'Authorization: Bearer <key_id>.<secret>' or HMAC headers",
        )

    decision = app.state.limiter.check(
        resolved.key_id,
        rpm=resolved.rate_limit_rpm,
        burst=app.state.burst,
    )
    request.state.rate = decision
    if not decision.allowed:
        raise ApiError(
            "RATE_LIMITED", 429, "rate limit exceeded",
            {"retry_after": decision.retry_after},
        )

    if not resolved.has_scope("lemmatize"):
        raise ApiError("UNAUTHORIZED", 401, "key lacks the 'lemmatize' scope")

    request.state.key = resolved
    return resolved


def _authenticate_hmac(request: Request, url: str, secret_key: bytes) -> ResolvedKey:
    key_id = request.headers.get("X-Api-Key", "")
    timestamp = request.headers.get("X-Timestamp", "")
    nonce = request.headers.get("X-Nonce", "")
    signature = request.headers.get("X-Signature", "")

    if not (key_id and timestamp and nonce and signature):
        raise ApiError(
            "UNAUTHORIZED", 401,
            "HMAC auth requires X-Api-Key, X-Timestamp, X-Nonce and X-Signature",
        )

    if not timestamp_within_window(timestamp):
        raise ApiError(
            "TIMESTAMP_OUT_OF_WINDOW", 401,
            "X-Timestamp is outside the allowed window",
        )

    if not request.app.state.nonces.consume(nonce):
        raise ApiError("NONCE_REPLAYED", 401, "X-Nonce has already been used")

    resolved = keys.resolve_active(url, key_id)
    if resolved is None:
        raise ApiError("UNAUTHORIZED", 401, "invalid key")

    if not resolved.allow_hmac:
        raise ApiError(
            "HMAC_NOT_ALLOWED", 401, "this key is not permitted to use HMAC auth"
        )

    secret = keys.get_secret(url, key_id, secret_key)
    if secret is None:
        raise ApiError("UNAUTHORIZED", 401, "invalid key")

    body = request.state.body_bytes if hasattr(request.state, "body_bytes") else b""
    if not verify_hmac(
        secret, request.method, request.url.path, timestamp, nonce, body, signature
    ):
        raise ApiError("SIGNATURE_INVALID", 401, "HMAC signature does not match")

    return resolved


def require_lang(resolved: ResolvedKey, lang: str) -> None:
    if not resolved.allows_lang(lang):
        raise ApiError(
            "LANG_FORBIDDEN", 403, f"this key may not use language {lang!r}",
            {"allowed": resolved.langs},
        )
```

- [ ] **Step 4: Wire it into `api/main.py` and `api/routes/lemmatize.py`**

Modify `api/main.py`: add parameters, `app.state.db_url`, `limiter`, `nonces`, and include the auth dependency on the lemmatize router. Modify `api/routes/lemmatize.py` to declare `key: ResolvedKey = Depends(authenticate)`, call `require_lang`, and set rate-limit response headers.

The full replacement for both files is in **Task 7b** below.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_auth.py -v`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add api/auth/deps.py api/main.py api/routes/lemmatize.py tests/test_api_auth.py
git commit -m "feat: add Bearer and HMAC authentication with rate limiting"
```

---

## Task 7b: Rewire app assembly and the lemmatize route

**Files:**
- Modify: `api/main.py`
- Modify: `api/routes/lemmatize.py`

- [ ] **Step 1: Replace `api/main.py`**

```python
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.auth.nonce import NonceCache
from api.auth.ratelimit import RateLimiter
from api.backends.registry import Registry, lazy
from api.db import default_url, init_db
from api.errors import ApiError
from api.routes import admin_keys, admin_session, admin_settings, health, languages, lemmatize

log = logging.getLogger(__name__)


class _FakeBackend:
    pos_scheme = None

    def __init__(self, lang: str) -> None:
        from api.types import Capabilities

        self.lang = lang
        self.name = "fake"
        self.version = "0.0.0"
        self.capabilities = Capabilities()

    def option_specs(self) -> dict:
        return {}

    def lemmatize(self, text, tokens, pos, options):
        from api.types import LemmaItem

        surfaces = tokens if tokens is not None else (text or "").split()
        return [LemmaItem(surface=s, lemma=s.lower()) for s in surfaces]


def build_registry(use_fakes: bool = False) -> Registry:
    registry = Registry()
    if use_fakes:
        for lang in ("en", "de", "fr", "es", "ru", "ja", "ko"):
            registry.register(lang, lambda lang=lang: _FakeBackend(lang))
        return registry

    registry.register("en", lazy("api.backends.lemminflect_backend"))
    for lang in ("de", "fr", "es"):
        registry.register(lang, lazy("api.backends.simplemma_backend", lang))
    registry.register("ru", lazy("api.backends.pymorphy_backend"))
    registry.register("ja", lazy("api.backends.sudachi_backend"))
    registry.register("ko", lazy("api.backends.kiwi_backend"))
    return registry


def create_app(
    registry: Registry | None = None,
    *,
    registry_fakes: bool = False,
    db_url: str | None = None,
    auth_enabled: bool | None = None,
) -> FastAPI:
    app = FastAPI(title="Lemma API", version="0.3.0")
    app.state.registry = (
        registry if registry is not None
        else build_registry(use_fakes=registry_fakes)
    )
    app.state.db_url = db_url or default_url()
    init_db(app.state.db_url)
    app.state.limiter = RateLimiter()
    app.state.nonces = NonceCache()
    app.state.burst = 60
    app.state.auth_enabled = (
        auth_enabled if auth_enabled is not None
        else bool(os.environ.get("LEMMA_AUTH_ENABLED", "1") == "1")
    )

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_json(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        message = str(first.get("msg", "request validation failed"))
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        error = ApiError(
            "INVALID_REQUEST", 400, message, {"field": list(first.get("loc", []))}
        )
        return JSONResponse(
            status_code=400,
            content=error.to_json(getattr(request.state, "request_id", None)),
        )

    app.include_router(health.router)
    app.include_router(languages.router)
    app.include_router(admin_session.router)
    app.include_router(admin_keys.router)
    app.include_router(admin_settings.router)
    app.include_router(lemmatize.router)
    return app


app = create_app()
```

> `import os` must also be added at the top of `main.py`.

- [ ] **Step 2: Replace `api/routes/lemmatize.py`**

```python
"""The single lemmatize endpoint (spec section 4.1)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request, Response

from api.auth.deps import authenticate, require_lang
from api.errors import ApiError
from api.models import ResolvedKey
from api.schemas import LemmatizeRequest, normalize_pos

router = APIRouter()


@router.post("/v1/lemmatize")
async def lemmatize(
    payload: LemmatizeRequest,
    request: Request,
    response: Response,
    key: ResolvedKey | None = Depends(authenticate),
) -> dict:
    request_id = f"req_{uuid.uuid4().hex[:20]}"
    request.state.request_id = request_id

    if key is not None:
        require_lang(key, payload.lang)
        rate = getattr(request.state, "rate", None)
        if rate is not None:
            response.headers["X-RateLimit-Limit"] = str(rate.limit)
            response.headers["X-RateLimit-Remaining"] = str(rate.remaining)

    registry = request.app.state.registry
    entry = registry.get(payload.lang)
    if entry is None:
        raise ApiError(
            "UNKNOWN_LANGUAGE", 400, f"unsupported language {payload.lang!r}",
            {"supported": [e.lang for e in registry.all()]},
        )
    if entry.status != "ok" or entry.backend is None:
        raise ApiError(
            "LANGUAGE_UNAVAILABLE", 503,
            f"backend for {payload.lang!r} failed to initialize",
            {"reason": entry.reason},
        )

    backend = entry.backend
    unknown = set(payload.options) - set(backend.option_specs())
    if unknown:
        raise ApiError(
            "UNKNOWN_OPTION", 400, "unknown option(s) for this language",
            {"unknown": sorted(unknown), "allowed": sorted(backend.option_specs())},
        )

    token_count = len(payload.tokens) if payload.tokens is not None else None
    try:
        pos_list = normalize_pos(payload.pos, token_count)
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc

    if backend.capabilities.pos_required and pos_list is None:
        raise ApiError("INVALID_REQUEST", 400, f"language {payload.lang!r} requires 'pos'")

    started = time.perf_counter()
    try:
        items = backend.lemmatize(
            text=payload.text, tokens=payload.tokens, pos=pos_list,
            options=payload.options,
        )
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000

    segmented_by = (
        "input" if payload.tokens is not None and not backend.capabilities.tokenizes
        else "backend"
    )
    warnings = [
        {"code": "UNRESOLVED", "surface": i.surface}
        for i in items if i.prov == "identity"
    ]

    return {
        "request_id": request_id,
        "lang": payload.lang,
        "backend": {"name": backend.name, "version": backend.version},
        "segmented_by": segmented_by,
        "capabilities": backend.capabilities.to_json(),
        "items": [i.to_json() for i in items],
        "warnings": warnings,
        "elapsed_ms": round(elapsed_ms, 2),
    }
```

- [ ] **Step 3: Make auth optional when disabled**

The `authenticate` dependency must return `None` instead of raising when `app.state.auth_enabled` is false, so Plan 1's existing tests keep passing:

```python
# in api/auth/deps.py, at the top of authenticate()
    if not request.app.state.auth_enabled:
        return None
```

- [ ] **Step 4: Run both test suites**

Run: `uv run pytest tests/test_api_auth.py tests/test_api_lemmatize.py -v`
Expected: 24 passed (11 auth + 13 from Plan 1)

- [ ] **Step 5: Commit**

```bash
git add api/main.py api/routes/lemmatize.py api/auth/deps.py
git commit -m "feat: wire auth dependency into app assembly and lemmatize route"
```

---

## Task 7c: Batched request logging

**Files:**
- Create: `api/obs/__init__.py`
- Create: `api/obs/requestlog.py`
- Modify: `api/main.py` (middleware + flusher)
- Modify: `api/routes/admin_settings.py` (expose recent requests to the console)
- Test: `tests/test_requestlog.py`

Two constraints shape this, and both are easy to get wrong:

1. **Never store request text.** Spec open item 3 decided this. Only the *shape* of a request is kept — language, token count, byte count. Writing bodies here would quietly turn a lemmatization API into a PII store.
2. **No SQLite write on the hot path.** Every request would otherwise contend for the single writer lock with `/v1/lemmatize`, which is the one path that must stay fast. Records are queued in memory and flushed in bounded batches.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_requestlog.py
from datetime import UTC, datetime, timedelta

import pytest

from api.db import init_db, session
from api.obs.requestlog import RequestLogger, count, purge_older_than


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path / 't.db'}"
    init_db(u)
    return u


def _rec(logger, **over):
    base = dict(
        request_id="req_1", key_id="lk_a", lang="de", n_tokens=2,
        bytes_in=32, latency_ms=5, status=200, error_code=None, ip="127.0.0.1",
    )
    base.update(over)
    logger.record(**base)


def test_record_does_not_write_until_flush(url):
    logger = RequestLogger(url)
    _rec(logger)
    assert logger.pending() == 1
    assert count(url) == 0


def test_flush_persists_the_batch(url):
    logger = RequestLogger(url)
    _rec(logger)
    assert logger.flush() == 1
    assert count(url) == 1
    assert logger.pending() == 0


def test_flush_is_bounded_and_leaves_the_rest_queued(url):
    logger = RequestLogger(url)
    for i in range(10):
        _rec(logger, request_id=f"req_{i}")
    assert logger.flush(limit=4) == 4
    assert logger.pending() == 6
    assert logger.flush_all() == 6
    assert logger.pending() == 0


def test_no_request_text_column_is_stored(url):
    """Only shape is retained. Guard against a future body/PII column."""
    logger = RequestLogger(url)
    _rec(logger)
    logger.flush()
    with session(url) as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(request_log)")}
    assert cols == {
        "id", "at", "request_id", "key_id", "lang", "n_tokens",
        "bytes_in", "latency_ms", "status", "error_code", "ip",
    }
    assert not any(c in cols for c in ("body", "text", "payload", "query"))


def test_queue_overflow_is_counted_not_silent():
    logger = RequestLogger("sqlite://", max_queue=3)
    for i in range(5):
        _rec(logger, request_id=f"r{i}")
    assert logger.pending() == 3
    assert logger.dropped == 2


def test_purge_removes_only_old_rows(url):
    logger = RequestLogger(url)
    _rec(logger)
    logger.flush()
    with session(url) as conn:
        old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.exec_driver_sql(
            """INSERT INTO request_log
               (at, request_id, key_id, lang, n_tokens, bytes_in, latency_ms,
                status, error_code, ip)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (old, "req_old", "lk_a", "de", 1, 8, 1, 200, None, None),
        )
    assert count(url) == 2
    assert purge_older_than(url, days=7) == 1
    assert count(url) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_requestlog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.obs'`

- [ ] **Step 3: Write `api/obs/requestlog.py`**

```python
"""Batched request logging.

Two constraints shaped this:

1. Must not store request text (spec open item 3). Only shape is kept: language,
   token count, byte count. Storing bodies would turn this into a PII store.
2. Must not put a SQLite write on the hot path. Every request would contend for
   the single writer lock with `/v1/lemmatize`, which is the one thing that has
   to stay fast. Records are queued and written in batches by a flusher.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.db import session

MAX_QUEUE = 10_000
BATCH_SIZE = 200
RETENTION_DAYS = 7


@dataclass(frozen=True)
class Record:
    at: str
    request_id: str
    key_id: str | None
    lang: str | None
    n_tokens: int | None
    bytes_in: int | None
    latency_ms: int
    status: int
    error_code: str | None
    ip: str | None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class RequestLogger:
    def __init__(self, url: str, max_queue: int = MAX_QUEUE) -> None:
        self._url = url
        self._queue: deque[Record] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self.dropped = 0

    def record(
        self,
        *,
        request_id: str,
        key_id: str | None,
        lang: str | None,
        n_tokens: int | None,
        bytes_in: int | None,
        latency_ms: int,
        status: int,
        error_code: str | None,
        ip: str | None,
    ) -> None:
        rec = Record(
            at=_now(), request_id=request_id, key_id=key_id, lang=lang,
            n_tokens=n_tokens, bytes_in=bytes_in, latency_ms=latency_ms,
            status=status, error_code=error_code, ip=ip,
        )
        with self._lock:
            # deque(maxlen=...) silently evicts the oldest; count it so a
            # sustained overflow is visible instead of looking like quiet loss.
            if len(self._queue) == self._queue.maxlen:
                self.dropped += 1
            self._queue.append(rec)

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def flush(self, limit: int = BATCH_SIZE) -> int:
        with self._lock:
            batch = [self._queue.popleft() for _ in range(min(limit, len(self._queue)))]
        if not batch:
            return 0
        with session(self._url) as conn:
            conn.exec_driver_sql(
                """INSERT INTO request_log
                   (at, request_id, key_id, lang, n_tokens, bytes_in,
                    latency_ms, status, error_code, ip)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.at, r.request_id, r.key_id, r.lang, r.n_tokens,
                        r.bytes_in, r.latency_ms, r.status, r.error_code, r.ip,
                    )
                    for r in batch
                ],
            )
        return len(batch)

    def flush_all(self) -> int:
        total = 0
        while True:
            written = self.flush()
            total += written
            if written == 0:
                return total


def purge_older_than(url: str, days: int = RETENTION_DAYS) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with session(url) as conn:
        result = conn.exec_driver_sql("DELETE FROM request_log WHERE at < ?", (cutoff,))
        return result.rowcount


def count(url: str) -> int:
    with session(url) as conn:
        return conn.exec_driver_sql("SELECT COUNT(*) FROM request_log").scalar() or 0


def recent(url: str, limit: int = 100, offset: int = 0) -> list[dict]:
    with session(url) as conn:
        rows = conn.exec_driver_sql(
            """SELECT id, at, request_id, key_id, lang, n_tokens, bytes_in,
                      latency_ms, status, error_code, ip
               FROM request_log ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_requestlog.py -v`
Expected: 6 passed

> **Verified by mutation before this plan was published:** making `flush()` a
> no-op, making `purge_older_than` ignore its cutoff, and removing the overflow
> counter each fail this suite. A logger that silently writes nothing is the
> failure mode that matters here, so it is worth the three mutations.

- [ ] **Step 5: Wire the middleware and flusher into `api/main.py`**

Add to the imports:

```python
from api.obs.requestlog import RequestLogger, purge_older_than
```

Inside `create_app()`, after `app.state.nonces = NonceCache()`:

```python
    app.state.request_log = RequestLogger(app.state.db_url)
    purge_older_than(app.state.db_url)
```

Add the middleware and a lifespan flusher. The middleware must not read the body
itself — `api/auth/deps.py` already stashes `request.state.body_bytes`, so reuse
that and fall back to the `content-length` header:

```python
    @app.middleware("http")
    async def _request_log_middleware(request: Request, call_next):
        started = time.perf_counter()

        # Assign the id here, not in the route. Authentication runs as a
        # dependency before the handler, so a 401 raised by auth would
        # otherwise carry request_id=null and could not be correlated with its
        # own log row.
        request.state.request_id = f"req_{uuid.uuid4().hex[:20]}"

        # HMAC verification needs the exact bytes the client sent, and Starlette
        # discards the stream once the body is parsed. Cache it here, before any
        # route or dependency reads it, so the auth dependency can re-hash it.
        # Only when signing: ordinary traffic must not be buffered.
        if request.headers.get("X-Signature"):
            request.state.body_bytes = await request.body()

        try:
            response = await call_next(request)
        except Exception:
            request.app.state.request_log.record(
                request_id=getattr(request.state, "request_id", "-"),
                key_id=getattr(getattr(request.state, "key", None), "key_id", None),
                lang=None, n_tokens=None,
                bytes_in=len(getattr(request.state, "body_bytes", b"") or b""),
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=500, error_code="INTERNAL",
                ip=request.client.host if request.client else None,
            )
            raise

        key = getattr(request.state, "key", None)
        request.app.state.request_log.record(
            request_id=getattr(request.state, "request_id", "-"),
            key_id=key.key_id if key else None,
            lang=getattr(request.state, "lang", None),
            n_tokens=getattr(request.state, "n_tokens", None),
            bytes_in=len(getattr(request.state, "body_bytes", b"") or b""),
            latency_ms=int((time.perf_counter() - started) * 1000),
            status=response.status_code,
            error_code=getattr(request.state, "error_code", None),
            ip=request.client.host if request.client else None,
        )
        response.headers["X-Request-Id"] = getattr(request.state, "request_id", "-")
        return response
```

And a background flusher using FastAPI's lifespan so nothing is lost on shutdown:

```python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(app: FastAPI):
    async def _loop():
        while True:
            await asyncio.sleep(5)
            try:
                app.state.request_log.flush()
            except Exception:  # noqa: BLE001 - logging must never kill the app
                log.warning("request_log flush failed", exc_info=True)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        app.state.request_log.flush_all()  # drain on shutdown
```

Pass it to the app: `FastAPI(title="Lemma API", version="0.3.0", lifespan=_lifespan)`.

- [ ] **Step 6: Have the lemmatize route report shape for the log**

In `api/routes/lemmatize.py`, after the request_id is assigned, set what the
middleware reads. Add nothing that contains user text:

```python
    request.state.lang = payload.lang
    request.state.n_tokens = len(payload.tokens) if payload.tokens is not None else None
```

- [ ] **Step 7: Expose recent requests to the console**

Append to `api/routes/admin_settings.py`:

```python
@router.get("/requests")
def recent_requests(request: Request, limit: int = 100, offset: int = 0) -> dict:
    """Request shapes only - never text. See api/obs/requestlog.py."""
    from api.obs.requestlog import recent

    return {"requests": recent(request.app.state.db_url, limit, offset)}
```

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass, including Plan 1's 124 tests.

- [ ] **Step 9: Commit**

```bash
git add api/obs api/main.py api/routes/lemmatize.py api/routes/admin_settings.py tests/test_requestlog.py
git commit -m "feat: add batched request logging with retention and no PII columns"
```

---

## Task 8: Settings registry and store

**Files:**
- Create: `api/settings/__init__.py`
- Create: `api/settings/registry.py`
- Create: `api/store/settings.py`
- Create: `api/store/audit.py`
- Test: `tests/test_store_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store_settings.py
import pytest

from api.db import init_db
from api.store import audit, settings
from api.settings.registry import EDITABLE, validate


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path / 't.db'}"
    init_db(u)
    return u


def test_defaults_are_returned_when_nothing_is_stored(url):
    merged = settings.effective(url)
    assert merged["langs.de.greedy"] is True
    assert merged["langs.fr.greedy"] is False
    assert merged["ratelimit.default_rpm"] == 600


def test_write_then_read_a_whitelisted_key(url):
    settings.set_value(url, "langs.de.greedy", False, actor="admin")
    assert settings.effective(url)["langs.de.greedy"] is False


def test_unknown_key_is_rejected(url):
    with pytest.raises(KeyError, match="not editable"):
        settings.set_value(url, "db.dsn", "x", actor="admin")


def test_out_of_range_value_is_rejected(url):
    with pytest.raises(ValueError):
        settings.set_value(url, "ratelimit.default_rpm", 0, actor="admin")


def test_enum_value_is_validated(url):
    with pytest.raises(ValueError):
        settings.set_value(url, "langs.ja.split_mode", "Z", actor="admin")
    settings.set_value(url, "langs.ja.split_mode", "A", actor="admin")
    assert settings.effective(url)["langs.ja.split_mode"] == "A"


def test_write_creates_an_audit_row(url):
    settings.set_value(url, "langs.de.greedy", False, actor="alice")
    rows = audit.list_entries(url)
    assert len(rows) == 1
    assert rows[0]["actor"] == "alice"
    assert rows[0]["target"] == "langs.de.greedy"
    assert rows[0]["before_json"] == "true"
    assert rows[0]["after_json"] == "false"


def test_hot_flag_is_exposed_for_every_entry():
    for name, spec in EDITABLE.items():
        assert isinstance(spec.hot, bool), name


def test_validate_rejects_bool_as_int():
    """True is an int in Python; a rpm of True must not slip through."""
    with pytest.raises(ValueError):
        validate("ratelimit.default_rpm", True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.settings'`

- [ ] **Step 3: Write the three modules**

`api/settings/__init__.py`: empty file.

`api/settings/registry.py`:
```python
"""The settings whitelist.

Inclusion rule: a wrong value may degrade quality, cost more CPU, or refuse more
requests - it must never make the service fail to start or the console fail to
reach the API. That is why model paths, the database URL and the master key are
absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Spec:
    kind: str
    hot: bool
    default: Any
    min: int | None = None
    max: int | None = None
    values: tuple[str, ...] = field(default_factory=tuple)


ALL_LANGS = ["en", "de", "fr", "es", "ru", "ja", "ko"]

EDITABLE: dict[str, Spec] = {
    "langs.enabled": Spec(kind="lang_set", hot=True, default=ALL_LANGS),
    "langs.de.greedy": Spec(kind="bool", hot=True, default=True),
    "langs.fr.greedy": Spec(kind="bool", hot=True, default=False),
    "langs.es.greedy": Spec(kind="bool", hot=True, default=False),
    "langs.ja.split_mode": Spec(kind="enum", hot=True, default="C", values=("A", "B", "C")),
    "langs.ko.model_type": Spec(kind="enum", hot=False, default="cong", values=("cong", "knlm")),
    "ratelimit.default_rpm": Spec(kind="int", hot=True, default=600, min=1, max=100_000),
    "ratelimit.burst": Spec(kind="int", hot=True, default=60, min=1, max=10_000),
    "request.max_tokens": Spec(kind="int", hot=True, default=5000, min=1, max=100_000),
    "request.max_body_bytes": Spec(
        kind="int", hot=True, default=1_048_576, min=1024, max=16_777_216
    ),
}


def validate(name: str, value: Any) -> Any:
    """Coerce and range-check one value, or raise."""
    if name not in EDITABLE:
        raise KeyError(f"{name!r} is not editable")
    spec = EDITABLE[name]

    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean")
        return value

    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if spec.min is not None and value < spec.min:
            raise ValueError(f"{name} must be >= {spec.min}")
        if spec.max is not None and value > spec.max:
            raise ValueError(f"{name} must be <= {spec.max}")
        return value

    if spec.kind == "enum":
        if value not in spec.values:
            raise ValueError(f"{name} must be one of {list(spec.values)}")
        return value

    if spec.kind == "lang_set":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{name} must be a list of language codes")
        unknown = set(value) - set(ALL_LANGS)
        if unknown:
            raise ValueError(f"{name} contains unknown languages {sorted(unknown)}")
        return value

    raise ValueError(f"unknown spec kind {spec.kind!r}")


def defaults() -> dict[str, Any]:
    return {name: spec.default for name, spec in EDITABLE.items()}
```

`api/store/settings.py`:
```python
from __future__ import annotations

import json
from datetime import UTC, datetime

from api.db import session
from api.settings.registry import EDITABLE, defaults, validate
from api.store import audit


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stored(url: str) -> dict[str, object]:
    with session(url) as conn:
        rows = conn.exec_driver_sql("SELECT key, value_json FROM settings").all()
    return {k: json.loads(v) for k, v in rows}


def effective(url: str) -> dict[str, object]:
    """Defaults overlaid with whatever has been persisted."""
    merged = defaults()
    for name, value in _stored(url).items():
        if name in EDITABLE:
            merged[name] = value
    return merged


def get_all(url: str) -> list[dict]:
    stored = _stored(url)
    out = []
    for name, spec in EDITABLE.items():
        out.append({
            "key": name,
            "value": stored.get(name, spec.default),
            "default": spec.default,
            "kind": spec.kind,
            "hot": spec.hot,
            "min": spec.min,
            "max": spec.max,
            "values": list(spec.values),
            "overridden": name in stored,
        })
    return out


def set_value(url: str, name: str, value: object, *, actor: str) -> object:
    coerced = validate(name, value)
    before = _stored(url).get(name, EDITABLE[name].default)

    with session(url) as conn:
        conn.exec_driver_sql(
            """INSERT INTO settings (key, value_json, updated_at, updated_by)
               VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value_json = excluded.value_json,
                 updated_at = excluded.updated_at,
                 updated_by = excluded.updated_by""",
            (name, json.dumps(coerced), _now(), actor),
        )
    audit.append(
        url, actor=actor, action="settings.update", target=name,
        before=before, after=coerced,
    )
    return coerced


def is_hot(name: str) -> bool:
    return EDITABLE[name].hot
```

`api/store/audit.py`:
```python
from __future__ import annotations

import json
from datetime import UTC, datetime

from api.db import session


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(
    url: str,
    *,
    actor: str,
    action: str,
    target: str,
    before: object = None,
    after: object = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> None:
    with session(url) as conn:
        conn.exec_driver_sql(
            """INSERT INTO audit_log
               (at, actor, action, target, before_json, after_json, request_id, ip)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                _now(), actor, action, target,
                None if before is None else json.dumps(before),
                None if after is None else json.dumps(after),
                request_id, ip,
            ),
        )


def list_entries(url: str, limit: int = 50, offset: int = 0) -> list[dict]:
    with session(url) as conn:
        rows = conn.exec_driver_sql(
            """SELECT id, at, actor, action, target, before_json, after_json,
                      request_id, ip
               FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).mappings().all()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store_settings.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/settings api/store/settings.py api/store/audit.py tests/test_store_settings.py
git commit -m "feat: add whitelisted settings registry with audit trail"
```

---

## Task 9: Admin session and admin routes

**Files:**
- Create: `api/auth/admin.py`
- Create: `api/routes/admin_session.py`
- Create: `api/routes/admin_keys.py`
- Create: `api/routes/admin_settings.py`
- Test: `tests/test_api_admin.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_admin.py
import os

import pytest
from fastapi.testclient import TestClient

from api.auth.admin import hash_passphrase
from api.db import init_db
from api.main import create_app

MASTER = b"0" * 32
PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.setenv("LEMMA_SERVICE_TOKEN", "svc-token")
    monkeypatch.setenv("LEMMA_ADMIN_PASSPHRASE_HASH", hash_passphrase(PASSPHRASE))
    app = create_app(registry_fakes=True, db_url=url, auth_enabled=True)
    return TestClient(app)


def _session(client, passphrase=PASSPHRASE):
    return client.post("/admin/session", json={"passphrase": passphrase})


def test_wrong_passphrase_is_rejected(client):
    resp = _session(client, "nope")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_correct_passphrase_returns_admin_token(client):
    resp = _session(client)
    assert resp.status_code == 200
    assert resp.json()["admin_token"]


def test_admin_route_requires_both_tokens(client):
    resp = client.get("/admin/keys")
    assert resp.status_code == 401


def test_admin_route_rejects_wrong_service_token(client):
    token = _session(client).json()["admin_token"]
    resp = client.get(
        "/admin/keys",
        headers={"X-Service-Token": "wrong", "X-Admin-Token": token},
    )
    assert resp.status_code == 401


def test_create_key_returns_secret_exactly_once(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    created = client.post("/admin/keys", json={"name": "demo"}, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("ls_")

    listed = client.get("/admin/keys", headers=headers).json()
    assert all("secret" not in k for k in listed["keys"])
    assert all("secret_enc" not in k for k in listed["keys"])


def test_rotate_returns_a_new_secret(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    key_id = client.post("/admin/keys", json={"name": "d"}, headers=headers).json()["key_id"]
    rotated = client.post(f"/admin/keys/{key_id}/rotate", headers=headers)
    assert rotated.status_code == 200
    assert rotated.json()["secret"].startswith("ls_")


def test_delete_revokes(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    key_id = client.post("/admin/keys", json={"name": "d"}, headers=headers).json()["key_id"]
    assert client.delete(f"/admin/keys/{key_id}", headers=headers).status_code == 204
    keys_now = client.get("/admin/keys", headers=headers).json()["keys"]
    assert keys_now[0]["revoked_at"] is not None


def test_patch_settings_writes_audit(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    resp = client.patch(
        "/admin/settings", json={"key": "langs.de.greedy", "value": False}, headers=headers
    )
    assert resp.status_code == 200
    rows = client.get("/admin/audit", headers=headers).json()["entries"]
    assert rows[0]["target"] == "langs.de.greedy"


def test_patch_settings_rejects_non_whitelisted_key(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    resp = client.patch(
        "/admin/settings", json={"key": "db.dsn", "value": "x"}, headers=headers
    )
    assert resp.status_code == 400


def test_diagnostics_is_read_only(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    body = client.get("/admin/diagnostics", headers=headers).json()
    assert "backends" in body
    assert "master_key" in body
    assert body["master_key"] == "set"
    assert client.patch("/admin/diagnostics", headers=headers).status_code == 405
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_admin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.auth.admin'`

- [ ] **Step 3: Write the four modules**

`api/auth/admin.py`:
```python
"""Admin authentication.

Two factors are required on every admin route:
  X-Service-Token - proves the caller is the console, not a browser
  X-Admin-Token   - proves a human supplied the passphrase

Requiring both means a stolen admin token is useless without the service token,
and the service token never leaves the server-to-server hop.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request

from api.errors import ApiError

ADMIN_TTL_SECONDS = 7200
_HASHER = PasswordHasher()


@dataclass
class AdminSession:
    token: str
    expires_at: float


def hash_passphrase(passphrase: str) -> str:
    return _HASHER.hash(passphrase)


def verify_passphrase(passphrase: str) -> bool:
    stored = os.environ.get("LEMMA_ADMIN_PASSPHRASE_HASH", "")
    if not stored:
        raise ApiError("INTERNAL", 500, "LEMMA_ADMIN_PASSPHRASE_HASH is not configured")
    try:
        return _HASHER.verify(stored, passphrase)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def issue_token(app) -> AdminSession:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC).timestamp() + ADMIN_TTL_SECONDS
    app.state.admin_sessions[token] = expires
    return AdminSession(token=token, expires_at=expires)


def _valid_admin_token(app, token: str) -> bool:
    expires = app.state.admin_sessions.get(token)
    if expires is None:
        return False
    if expires < datetime.now(UTC).timestamp():
        app.state.admin_sessions.pop(token, None)
        return False
    return True


async def require_admin(request: Request) -> str:
    service_token = request.headers.get("X-Service-Token", "")
    expected_service = os.environ.get("LEMMA_SERVICE_TOKEN", "")
    if not expected_service or not secrets.compare_digest(service_token, expected_service):
        raise ApiError("UNAUTHORIZED", 401, "invalid or missing X-Service-Token")

    admin_token = request.headers.get("X-Admin-Token", "")
    if not _valid_admin_token(request.app, admin_token):
        raise ApiError("UNAUTHORIZED", 401, "invalid or expired X-Admin-Token")

    return "admin"
```

`api/routes/admin_session.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.auth.admin import issue_token, verify_passphrase
from api.errors import ApiError

router = APIRouter()


class SessionRequest(BaseModel):
    passphrase: str


@router.post("/admin/session")
def create_session(payload: SessionRequest, request: Request) -> dict:
    if not verify_passphrase(payload.passphrase):
        raise ApiError("UNAUTHORIZED", 401, "invalid passphrase")
    session = issue_token(request.app)
    return {"admin_token": session.token, "expires_at": session.expires_at}
```

`api/routes/admin_keys.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth.admin import require_admin
from api.auth.deps import master_key
from api.errors import ApiError
from api.store import audit, keys

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] | None = None
    langs: list[str] | None = None
    allow_hmac: bool = False
    rate_limit_rpm: int = Field(default=600, ge=1, le=100_000)
    expires_at: str | None = None


@router.get("/keys")
def list_keys(request: Request) -> dict:
    return {"keys": keys.list_all(request.app.state.db_url)}


@router.post("/keys", status_code=201)
def create_key(payload: CreateKeyRequest, request: Request) -> dict:
    url = request.app.state.db_url
    created = keys.create(
        url, name=payload.name, created_by="admin", master_key=master_key(),
        scopes=payload.scopes, langs=payload.langs, allow_hmac=payload.allow_hmac,
        rate_limit_rpm=payload.rate_limit_rpm, expires_at=payload.expires_at,
    )
    audit.append(url, actor="admin", action="key.create", target=created.key_id,
                 after={"name": payload.name, "langs": payload.langs})
    return {
        "key_id": created.key_id,
        "secret": created.secret,
        "secret_fingerprint": created.secret_fingerprint,
        "name": created.name,
    }


@router.post("/keys/{key_id}/rotate")
def rotate_key(key_id: str, request: Request) -> dict:
    url = request.app.state.db_url
    try:
        rotated = keys.rotate(url, key_id, master_key=master_key())
    except KeyError as exc:
        raise ApiError("NOT_FOUND", 404, f"no such key {key_id!r}") from exc
    audit.append(url, actor="admin", action="key.rotate", target=key_id)
    return {
        "key_id": rotated.key_id,
        "secret": rotated.secret,
        "secret_fingerprint": rotated.secret_fingerprint,
    }


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, request: Request) -> None:
    url = request.app.state.db_url
    if not keys.revoke(url, key_id, reason="admin revoke", actor="admin"):
        raise ApiError("NOT_FOUND", 404, f"no active key {key_id!r}")
    audit.append(url, actor="admin", action="key.revoke", target=key_id)
```

`api/routes/admin_settings.py`:
```python
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth.admin import require_admin
from api.errors import ApiError
from api.store import audit, settings

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class PatchSettingRequest(BaseModel):
    key: str
    value: object


@router.get("/settings")
def read_settings(request: Request) -> dict:
    return {"settings": settings.get_all(request.app.state.db_url)}


@router.patch("/settings")
def patch_setting(payload: PatchSettingRequest, request: Request) -> dict:
    url = request.app.state.db_url
    try:
        value = settings.set_value(url, payload.key, payload.value, actor="admin")
    except KeyError as exc:
        raise ApiError("INVALID_SETTING", 400, str(exc)) from exc
    except ValueError as exc:
        raise ApiError("INVALID_SETTING", 400, str(exc)) from exc
    return {"key": payload.key, "value": value, "hot": settings.is_hot(payload.key)}


@router.get("/audit")
def read_audit(request: Request, limit: int = 50, offset: int = 0) -> dict:
    return {"entries": audit.list_entries(request.app.state.db_url, limit, offset)}


@router.get("/diagnostics")
def diagnostics(request: Request) -> dict:
    """Read-only. Never PATCHable, so the console cannot brick the service."""
    registry = request.app.state.registry
    return {
        "backends": {
            e.lang: {
                "status": e.status,
                "backend": e.backend.name if e.backend else None,
                "version": e.backend.version if e.backend else None,
                "reason": e.reason,
            }
            for e in registry.all()
        },
        "master_key": "set" if os.environ.get("LEMMA_MASTER_KEY") else "unset",
        "service_token": "set" if os.environ.get("LEMMA_SERVICE_TOKEN") else "unset",
        "db_url_kind": "sqlite",
    }
```

- [ ] **Step 4: Add `app.state.admin_sessions = {}` to `create_app` and install argon2**

Run: `uv pip install argon2-cffi`, add `"argon2-cffi>=23"` and `"cryptography>=43"` and `"sqlalchemy>=2.0"` to `pyproject.toml` dependencies, then add to `create_app`:

```python
    app.state.admin_sessions = {}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_admin.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add api/auth/admin.py api/routes/admin_session.py api/routes/admin_keys.py api/routes/admin_settings.py pyproject.toml tests/test_api_admin.py
git commit -m "feat: add admin session, key management, settings and diagnostics routes"
```

---

## Task 10: Bootstrap CLI

**Files:**
- Create: `api/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import os

from api.cli import main

MASTER = b"0" * 32


def test_create_key_prints_secret_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.setenv("LEMMA_DB_PATH", str(tmp_path / "t.db"))
    assert main(["create-key", "--name", "bootstrap"]) == 0
    out = capsys.readouterr().out
    assert "lk_" in out
    assert "ls_" in out
    assert "shown once" in out


def test_hash_passphrase_prints_argon2_hash(tmp_path, capsys):
    assert main(["hash-passphrase", "secret123"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("$argon2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.cli'`

- [ ] **Step 3: Write `api/cli.py`**

```python
"""Bootstrap helpers, run before the API has any keys.

    python -m api.cli create-key --name bootstrap
    python -m api.cli hash-passphrase 'my passphrase'
"""

from __future__ import annotations

import argparse
import os
import sys

from api.auth.admin import hash_passphrase
from api.db import default_url, init_db
from api.store import keys


def _master_key() -> bytes:
    raw = os.environ.get("LEMMA_MASTER_KEY", "")
    if not raw:
        print("LEMMA_MASTER_KEY is not set", file=sys.stderr)
        raise SystemExit(2)
    return bytes.fromhex(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-key", help="create an API key")
    create.add_argument("--name", required=True)
    create.add_argument("--allow-hmac", action="store_true")
    create.add_argument("--langs", default="")

    hp = sub.add_parser("hash-passphrase", help="hash an admin passphrase")
    hp.add_argument("passphrase")

    args = parser.parse_args(argv)

    if args.command == "hash-passphrase":
        print(hash_passphrase(args.passphrase))
        return 0

    url = default_url()
    init_db(url)
    langs = [x for x in args.langs.split(",") if x]
    created = keys.create(
        url, name=args.name, created_by="cli", master_key=_master_key(),
        allow_hmac=args.allow_hmac, langs=langs,
    )
    print(f"key_id     : {created.key_id}")
    print(f"secret     : {created.secret}")
    print(f"fingerprint: {created.secret_fingerprint}")
    print("\nThe secret is shown once and cannot be recovered. Store it now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the whole plan-2 suite**

Run: `uv run pytest -q`
Expected: all pass, including Plan 1's 108 tests.

Plan 1's fixtures do not pass `auth_enabled`, so the default decides whether they start failing with 401. The default is resolved in `create_app` as:

```python
app.state.auth_enabled = (
    auth_enabled if auth_enabled is not None
    else os.environ.get("LEMMA_AUTH_ENABLED", "0") == "1"
)
```

**Default is OFF when the env var is absent.** Rationale: `auth_enabled` defaults are a footgun, and an "off by accident" production deploy is the dangerous direction. But defaults only matter for code paths that forget to be explicit — so **Task 11 makes every test fixture explicit**, and Docker sets `LEMMA_AUTH_ENABLED=1` in `deploy/`. A deployment that forgets that variable will refuse to start rather than silently run unauthenticated: `create_app` raises if `auth_enabled` is falsy and the environment looks like production (`LEMMA_REQUIRE_AUTH=1`, which the Dockerfile sets).

- [ ] **Step 6: Commit**

```bash
git add api/cli.py tests/test_cli.py
git commit -m "feat: add bootstrap CLI for key creation and passphrase hashing"
```

---

## Task 11: Update the plan-1 test fixtures

**Files:**
- Modify: `tests/conftest.py`

Plan 1's `real_client` builds the app with no DB. With auth in the codebase, every route test would now need a key. Make the intent explicit rather than relying on an environment variable being absent.

- [ ] **Step 1: Replace `tests/conftest.py`**

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.db import init_db
from api.main import build_registry, create_app
from api.store import keys

MASTER = b"0" * 32


@pytest.fixture
def fake_client(tmp_path):
    """Fake backends, auth disabled - exercises routing only."""
    url = f"sqlite:///{tmp_path / 'authless.db'}"
    init_db(url)
    app = create_app(
        registry=build_registry(use_fakes=True), db_url=url, auth_enabled=False
    )
    return TestClient(app)


@pytest.fixture(scope="session")
def real_client(tmp_path_factory):
    """Real 7-language registry, auth disabled. Session-scoped: dictionaries load once."""
    url = f"sqlite:///{tmp_path_factory.mktemp('db') / 'authless.db'}"
    init_db(url)
    app = create_app(db_url=url, auth_enabled=False)
    with TestClient(app) as client:
        return client


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    """Real registry, auth ENABLED, with one freshly created key."""
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    init_db(url)
    app = create_app(db_url=url, auth_enabled=True)
    created = keys.create(url, name="test", created_by="test", master_key=MASTER)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {created.key_id}.{created.secret}"
    return client, created
```

- [ ] **Step 2: Add an explicit auth-required test**

```python
# tests/test_api_auth_required.py
def test_lemmatize_requires_auth_when_enabled(authed_client):
    """Sanity: the fixture authenticates, and dropping the header fails."""
    client, _ = authed_client
    assert client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).status_code == 200
    client.headers.pop("Authorization")
    assert client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).status_code == 401
```

- [ ] **Step 3: Run everything**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_api_auth_required.py
git commit -m "test: give plan-1 fixtures explicit auth_enabled=False and add an authed fixture"
```

---

## Self-review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §5.1 key_id/secret split | Task 3 (`create`, `verify_bearer`) |
| §5.2 Bearer + HMAC, timestamp, nonce | Tasks 4, 5, 7 |
| §5.2 HKDF-derived signing key | Task 1 (`derive_signing_key`) |
| §5.3 AES-GCM + fingerprint + AAD binding | Tasks 1, 3 |
| §5.4 rotate with grace, revoke | Task 3 |
| §5.5 admin session, two-token gate, CSRF note | Task 9 |
| §6 schema (all 4 tables) | Task 2 |
| §7.1 whitelist + `hot` | Task 8 |
| §7.2 read-only diagnostics | Task 9 |
| §7.3 audit on every write | Tasks 8, 9 |
| §4.4 error codes | Tasks 7, 9 |
| Rate limiting `X-RateLimit-*`, `Retry-After` | Tasks 6, 7b |

**Not covered by this plan, deliberately:** CSRF double-submit for the console (belongs to Plan 3, where the cookie is set), `request_log` write path (belongs to Plan 3 with the console's traffic view), `rotate-all` bootstrap route (mention in Plan 3's ops docs).

**`auth_enabled` default, resolved:** off when `LEMMA_AUTH_ENABLED` is unset, with a separate `LEMMA_REQUIRE_AUTH=1` (set by the Dockerfile) that makes `create_app` **raise** if auth is off. That combination means tests do not need to know about the flag and production cannot silently run open. Task 10 Step 5 and Task 11 together implement and pin it.

**Type consistency:** `ResolvedKey` (Task 3) → consumed by `authenticate` (Task 7) → consumed by the route (Task 7b). `Decision` (Task 6) → `request.state.rate` → read in Task 7b for headers. `CreatedKey` (Task 3) → returned by both `create` and `rotate` → both admin routes use `.secret`. `EDITABLE`/`Spec` (Task 8) → used by `validate`, `defaults`, `get_all`, `is_hot`.
