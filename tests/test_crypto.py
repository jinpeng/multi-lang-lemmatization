import pytest
from cryptography.exceptions import InvalidTag

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
    with pytest.raises(InvalidTag):
        open_secret(secret, "key_abc", wrong)


def test_aad_binds_ciphertext_to_key_id():
    """A sealed secret must not be replayable under a different key_id."""
    blob = seal_secret("ls_hello", "key_abc", MASTER)
    with pytest.raises(InvalidTag):
        open_secret(blob, "key_DIFFERENT", MASTER)


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(seal_secret("ls_hello", "key_abc", MASTER))
    blob[-1] ^= 0xFF
    with pytest.raises(InvalidTag):
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
