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
        url,
        name="d",
        created_by="a",
        master_key=MASTER,
        expires_at="2000-01-01T00:00:00Z",
    )
    assert keys.verify_bearer(url, created.key_id, created.secret, MASTER) is None


def test_lang_restriction_and_allow_hmac_are_persisted(url):
    created = keys.create(
        url,
        name="d",
        created_by="a",
        master_key=MASTER,
        langs=["de", "fr"],
        allow_hmac=True,
    )
    resolved = keys.verify_bearer(url, created.key_id, created.secret, MASTER)
    assert resolved.langs == ["de", "fr"]
    assert resolved.allow_hmac is True
