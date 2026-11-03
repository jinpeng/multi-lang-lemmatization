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
