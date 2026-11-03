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
