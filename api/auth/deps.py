"""The single place a request becomes an authenticated key.

Order matters. Timestamp and nonce are checked BEFORE the signature so a
replayed request is rejected without an expensive decrypt, and a stale request
never reaches key lookup at all.
"""

from __future__ import annotations

import os

from fastapi import Request

from api.auth.hmac import timestamp_within_window
from api.auth.hmac import verify as verify_hmac
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
            "UNAUTHORIZED",
            401,
            "Bearer credential must be '<key_id>.<secret>'",
        )
    key_id, _, secret = token.partition(".")
    return key_id, secret


async def authenticate(request: Request) -> ResolvedKey | None:
    app = request.app
    if not getattr(app.state, "auth_enabled", True):
        return None

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
            "UNAUTHORIZED",
            401,
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
            "RATE_LIMITED",
            429,
            "rate limit exceeded",
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
            "UNAUTHORIZED",
            401,
            "HMAC auth requires X-Api-Key, X-Timestamp, X-Nonce and X-Signature",
        )

    if not timestamp_within_window(timestamp):
        raise ApiError(
            "TIMESTAMP_OUT_OF_WINDOW",
            401,
            "X-Timestamp is outside the allowed window",
        )

    if not request.app.state.nonces.consume(nonce):
        raise ApiError("NONCE_REPLAYED", 401, "X-Nonce has already been used")

    resolved = keys.resolve_active(url, key_id)
    if resolved is None:
        raise ApiError("UNAUTHORIZED", 401, "invalid key")

    if not resolved.allow_hmac:
        raise ApiError("HMAC_NOT_ALLOWED", 401, "this key is not permitted to use HMAC auth")

    secret = keys.get_secret(url, key_id, secret_key)
    if secret is None:
        raise ApiError("UNAUTHORIZED", 401, "invalid key")

    body = getattr(request.state, "body_bytes", b"")
    if not verify_hmac(secret, request.method, request.url.path, timestamp, nonce, body, signature):
        raise ApiError("SIGNATURE_INVALID", 401, "HMAC signature does not match")

    return resolved


def require_lang(resolved: ResolvedKey, lang: str) -> None:
    if not resolved.allows_lang(lang):
        raise ApiError(
            "LANG_FORBIDDEN",
            403,
            f"this key may not use language {lang!r}",
            {"allowed": resolved.langs},
        )
