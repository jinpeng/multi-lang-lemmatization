"""Admin authentication.

Two factors are required on every admin route:
  X-Service-Token - proves the caller is the console, not a browser
  X-Admin-Token   - proves a human supplied the passphrase

Requiring both means a stolen admin token is useless without the service token,
and the service token never leaves the server-to-server hop.

Admin tokens are STATELESS: `<expiry>.<nonce>.<hmac>`, signed with a key derived
from LEMMA_MASTER_KEY. They were originally held in a per-process dict, which
silently broke under `--workers 2`: a login stored the token in worker A's
memory, and any later request routed to worker B was rejected as invalid. No
shared store is needed if the token carries its own proof.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
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
ARGON2_PREFIX = "$argon2"


@dataclass
class AdminSession:
    token: str
    expires_at: float


def hash_passphrase(passphrase: str) -> str:
    return _HASHER.hash(passphrase)


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


def _signing_key() -> bytes:
    """Derive an admin-token key from the master key.

    Separate from the API-key HMAC derivation so that a token issued for one
    purpose can never validate for the other.
    """
    raw = os.environ.get("LEMMA_MASTER_KEY", "")
    if not raw:
        raise ApiError("INTERNAL", 500, "LEMMA_MASTER_KEY is not configured")
    try:
        master = bytes.fromhex(raw)
    except ValueError as exc:
        raise ApiError("INTERNAL", 500, "LEMMA_MASTER_KEY must be 32 hex bytes") from exc
    return hmac_mod.new(master, b"lemma-admin-token-v1", hashlib.sha256).digest()


def _sign(payload: str) -> str:
    digest = hmac_mod.new(_signing_key(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def issue_token() -> AdminSession:
    expires = int(datetime.now(UTC).timestamp()) + ADMIN_TTL_SECONDS
    payload = f"{expires}.{secrets.token_urlsafe(16)}"
    token = f"{payload}.{_sign(payload)}"
    return AdminSession(token=token, expires_at=float(expires))


def _valid_admin_token(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False
    expires_raw, _nonce, signature = parts
    payload = f"{expires_raw}.{_nonce}"

    # compare_digest raises TypeError on non-ASCII str, and an ASGI header is
    # latin-1 decoded, so a byte such as 0xE4 would turn a bad token into a 500
    # instead of a 401. Compare the ASCII bytes explicitly.
    try:
        presented = signature.encode("ascii")
    except UnicodeEncodeError:
        return False
    if not hmac_mod.compare_digest(presented, _sign(payload).encode("ascii")):
        return False
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    return expires >= datetime.now(UTC).timestamp()


async def require_admin(request: Request) -> str:
    service_token = request.headers.get("X-Service-Token", "")
    expected_service = os.environ.get("LEMMA_SERVICE_TOKEN", "")
    if not expected_service or not secrets.compare_digest(service_token, expected_service):
        raise ApiError("UNAUTHORIZED", 401, "invalid or missing X-Service-Token")

    admin_token = request.headers.get("X-Admin-Token", "")
    if not _valid_admin_token(admin_token):
        raise ApiError("UNAUTHORIZED", 401, "invalid or expired X-Admin-Token")

    return "admin"
