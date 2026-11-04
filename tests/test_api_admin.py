import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from api.auth.admin import hash_passphrase
from api.db import init_db
from api.main import create_app

MASTER = b"0" * 32
PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.setenv("LEMMA_SERVICE_TOKEN", "svc-token")
    monkeypatch.setenv("LEMMA_ADMIN_PASSPHRASE_HASH", hash_passphrase(PASSPHRASE))
    app = create_app(registry_fakes=True, db_url=url, auth_enabled=True)
    return TestClient(app)


def _session(client, passphrase=PASSPHRASE):
    return client.post("/admin/session", json={"passphrase": passphrase})


def test_wrong_passphrase_is_rejected(client):
    resp = _session(client, "nope")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_correct_passphrase_returns_admin_token(client):
    resp = _session(client)
    assert resp.status_code == 200
    assert resp.json()["admin_token"]


def test_admin_route_requires_both_tokens(client):
    resp = client.get("/admin/keys")
    assert resp.status_code == 401


def test_admin_route_rejects_wrong_service_token(client):
    token = _session(client).json()["admin_token"]
    resp = client.get(
        "/admin/keys",
        headers={"X-Service-Token": "wrong", "X-Admin-Token": token},
    )
    assert resp.status_code == 401


def test_create_key_returns_secret_exactly_once(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    created = client.post("/admin/keys", json={"name": "demo"}, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("ls_")

    listed = client.get("/admin/keys", headers=headers).json()
    assert all("secret" not in k for k in listed["keys"])
    assert all("secret_enc" not in k for k in listed["keys"])


def test_rotate_returns_a_new_secret(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    key_id = client.post("/admin/keys", json={"name": "d"}, headers=headers).json()["key_id"]
    rotated = client.post(f"/admin/keys/{key_id}/rotate", headers=headers)
    assert rotated.status_code == 200
    assert rotated.json()["secret"].startswith("ls_")


def test_delete_revokes(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    key_id = client.post("/admin/keys", json={"name": "d"}, headers=headers).json()["key_id"]
    assert client.delete(f"/admin/keys/{key_id}", headers=headers).status_code == 204
    keys_now = client.get("/admin/keys", headers=headers).json()["keys"]
    assert keys_now[0]["revoked_at"] is not None


def test_patch_settings_writes_audit(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    resp = client.patch(
        "/admin/settings",
        json={"key": "langs.de.greedy", "value": False},
        headers=headers,
    )
    assert resp.status_code == 200
    rows = client.get("/admin/audit", headers=headers).json()["entries"]
    assert rows[0]["target"] == "langs.de.greedy"


def test_patch_settings_rejects_non_whitelisted_key(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    resp = client.patch("/admin/settings", json={"key": "db.dsn", "value": "x"}, headers=headers)
    assert resp.status_code == 400


def test_diagnostics_is_read_only(client):
    token = _session(client).json()["admin_token"]
    headers = {"X-Service-Token": "svc-token", "X-Admin-Token": token}
    body = client.get("/admin/diagnostics", headers=headers).json()
    assert "backends" in body
    assert "master_key" in body
    assert body["master_key"] == "set"
    assert client.patch("/admin/diagnostics", headers=headers).status_code == 405


def test_malformed_hash_is_rejected_loudly(client, monkeypatch):
    """A '$'-interpolated hash must fail as corrupt, not as a wrong password."""
    from api.auth.admin import verify_passphrase
    from api.errors import ApiError

    monkeypatch.setenv("LEMMA_ADMIN_PASSPHRASE_HASH", "=19=65536,t=3,p=4")
    with pytest.raises(ApiError, match="malformed"):
        verify_passphrase("anything")


def test_startup_refuses_a_malformed_hash(tmp_path, monkeypatch):
    from api.db import init_db
    from api.main import create_app

    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.setenv("LEMMA_ADMIN_PASSPHRASE_HASH", "=19=broken")
    with pytest.raises(Exception, match="malformed"):
        create_app(registry_fakes=True, db_url=url, auth_enabled=True)


def test_headless_deployment_without_admin_hash_is_allowed(tmp_path, monkeypatch):
    """API-key auth must not require an admin passphrase (no console case)."""
    from api.db import init_db
    from api.main import create_app

    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    monkeypatch.delenv("LEMMA_ADMIN_PASSPHRASE_HASH", raising=False)
    app = create_app(registry_fakes=True, db_url=url, auth_enabled=True)
    assert app.state.auth_enabled is True


def test_admin_token_is_stateless_across_processes(monkeypatch):
    """A token must verify from any worker, not just the one that issued it.

    Regression: tokens lived in a per-process dict, so under --workers 2 a login
    on worker A was rejected by worker B -- roughly 1 request in 3 failed.
    Verified in a real second interpreter: an in-process check would pass even
    for a dict-backed store.
    """
    from api.auth.admin import issue_token

    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    token = issue_token().token

    probe = (
        "import sys; from api.auth.admin import _valid_admin_token; "
        "sys.exit(0 if _valid_admin_token(sys.argv[1]) else 1)"
    )
    other_worker = subprocess.run(
        [sys.executable, "-c", probe, token],
        env={**os.environ, "LEMMA_MASTER_KEY": MASTER.hex()},
        capture_output=True,
        check=False,
    )
    assert other_worker.returncode == 0, other_worker.stderr.decode()


def test_forged_admin_token_is_rejected(monkeypatch):
    from api.auth.admin import _valid_admin_token, issue_token

    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    token = issue_token().token
    expiry, nonce, sig = token.split(".")
    # Extend the expiry without re-signing: signature no longer matches.
    assert _valid_admin_token(f"{int(expiry) + 999999}.{nonce}.{sig}") is False


def test_admin_token_from_a_different_master_key_is_rejected(monkeypatch):
    from api.auth.admin import _valid_admin_token, issue_token

    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    token = issue_token().token
    monkeypatch.setenv("LEMMA_MASTER_KEY", (b"1" * 32).hex())
    assert _valid_admin_token(token) is False


def test_expired_admin_token_is_rejected(monkeypatch):
    from datetime import UTC, datetime

    from api.auth import admin as admin_mod

    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    past = int(datetime.now(UTC).timestamp()) - 10
    payload = f"{past}.nonce"
    token = f"{payload}.{admin_mod._sign(payload)}"
    assert admin_mod._valid_admin_token(token) is False


def test_non_ascii_admin_token_is_rejected_not_crashed(monkeypatch):
    """A latin-1 header byte must yield 401, not an uncaught TypeError.

    ASGI decodes header bytes as latin-1, so X-Admin-Token can arrive holding
    non-ASCII str. hmac.compare_digest raises TypeError on those, which escaped
    as a 500 from a route whose whole job is to answer 401.
    """
    from api.auth.admin import _valid_admin_token, issue_token

    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    token = issue_token().token
    expiry, nonce, sig = token.split(".")
    assert _valid_admin_token(f"{expiry}.{nonce}.\xe4") is False
    assert _valid_admin_token(f"{expiry}.{nonce}.\u00ff\u00fe") is False
