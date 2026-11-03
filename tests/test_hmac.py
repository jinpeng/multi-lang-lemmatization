import base64
import hashlib

from api.auth.hmac import canonical_string, sign, timestamp_within_window, verify

SECRET = "ls_testsecret"


def test_canonical_string_layout():
    body = b'{"lang":"de"}'
    got = canonical_string("POST", "/v1/lemmatize", "1700000000", "abc", body)
    expected = "\n".join(
        [
            "POST",
            "/v1/lemmatize",
            "1700000000",
            "abc",
            hashlib.sha256(body).hexdigest(),
        ]
    )
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
