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
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"lemma-hmac-v1").derive(
        secret.encode()
    )


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_master_key() -> bytes:
    return secrets.token_bytes(32)
