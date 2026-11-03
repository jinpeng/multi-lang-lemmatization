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


ARGON2_PREFIX = "$argon2"


def _stored_hash() -> str:
    stored = os.environ.get("LEMMA_ADMIN_PASSPHRASE_HASH", "")
    if not stored:
        raise ApiError("INTERNAL", 500, "LEMMA_ADMIN_PASSPHRASE_HASH is not configured")
    # A hash that does not start with "$argon2" is corrupt, not merely wrong.
    # The usual cause is Docker Compose variable interpolation eating "$argon2id"
    # and "$v": the value silently becomes "=19=65536,t=3,p=4" and every login
    # fails as "wrong passphrase", which looks like a credentials problem.
    # Fail loudly instead.
    if not stored.startswith(ARGON2_PREFIX):
        raise ApiError(
            "INTERNAL",
            500,
            "LEMMA_ADMIN_PASSPHRASE_HASH is malformed (does not start with $argon2). "
            "In a .env file, escape every '$' as '$$'.",
        )
    return stored


def verify_passphrase(passphrase: str) -> bool:
    stored = _stored_hash()
    try:
        return _HASHER.verify(stored, passphrase)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def validate_config() -> None:
    """Called at startup so a broken hash never reaches a login attempt.

    An absent hash is allowed: API-key authentication works without a console,
    so a headless deployment has no reason to configure an admin passphrase.
    A hash that is *present but malformed* is always a configuration error.
    """
    stored = os.environ.get("LEMMA_ADMIN_PASSPHRASE_HASH", "")
    if stored:
        _stored_hash()


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
