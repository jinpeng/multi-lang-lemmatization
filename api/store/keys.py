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
                uuid.uuid4().hex,
                name,
                key_id,
                seal_secret(secret, key_id, master_key),
                fingerprint(secret),
                json.dumps(scopes or ["lemmatize"]),
                json.dumps(langs or []),
                1 if allow_hmac else 0,
                rate_limit_rpm,
                _now(),
                created_by,
                expires_at,
            ),
        )
    return CreatedKey(
        key_id=key_id, secret=secret, secret_fingerprint=fingerprint(secret), name=name
    )


def _row(url: str, key_id: str):
    with session(url) as conn:
        return (
            conn.exec_driver_sql("SELECT * FROM api_keys WHERE key_id = ?", (key_id,))
            .mappings()
            .first()
        )


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


def verify_bearer(url: str, key_id: str, secret: str, master_key: bytes) -> ResolvedKey | None:
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


def rotate(url: str, key_id: str, *, master_key: bytes, grace_hours: int = 24) -> CreatedKey:
    row = _row(url, key_id)
    if row is None:
        raise KeyError(key_id)
    secret = generate_secret()
    expires = (datetime.now(UTC) + timedelta(hours=grace_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
                fingerprint(secret),
                key_id,
            ),
        )
    return CreatedKey(
        key_id=key_id,
        secret=secret,
        secret_fingerprint=fingerprint(secret),
        name=row["name"],
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
        rows = (
            conn.exec_driver_sql(
                """SELECT key_id, name, secret_fingerprint, scopes, langs, allow_hmac,
                          rate_limit_rpm, created_at, created_by, last_used_at,
                          expires_at, revoked_at
                   FROM api_keys ORDER BY created_at DESC"""
            )
            .mappings()
            .all()
        )
    return [
        {**dict(r), "scopes": json.loads(r["scopes"]), "langs": json.loads(r["langs"])}
        for r in rows
    ]
