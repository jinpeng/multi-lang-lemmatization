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


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    return "\n".join([method.upper(), path, timestamp, nonce, hashlib.sha256(body).hexdigest()])


def sign(secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
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
    expected = base64.b64decode(sign(secret, method, path, timestamp, nonce, body), validate=True)
    return hmac_mod.compare_digest(provided, expected)


def timestamp_within_window(timestamp: str, now: float | None = None) -> bool:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    return abs(current - value) <= TIMESTAMP_WINDOW_SECONDS
