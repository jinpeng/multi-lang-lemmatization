import time

import pytest
from fastapi.testclient import TestClient

from api.auth.hmac import sign
from api.db import init_db
from api.main import create_app
from api.store import keys

MASTER = b"0" * 32


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 't.db'}"
    init_db(url)
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    app = create_app(registry_fakes=True, db_url=url, auth_enabled=True)
    client = TestClient(app)
    created = keys.create(url, name="t", created_by="test", master_key=MASTER, allow_hmac=True)
    return client, created, url


def test_missing_credentials_is_401(app_client):
    client, _, _ = app_client
    resp = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_valid_bearer_succeeds(app_client):
    client, created, _ = app_client
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {created.key_id}.{created.secret}"},
    )
    assert resp.status_code == 200


def test_bearer_with_only_key_id_is_rejected(app_client):
    """key_id is an identifier, not a credential. This must never authenticate."""
    client, created, _ = app_client
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {created.key_id}"},
    )
    assert resp.status_code == 401


def test_valid_hmac_succeeds(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "nonce-1", body)
    resp = client.post(
        "/v1/lemmatize",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Api-Key": created.key_id,
            "X-Timestamp": ts,
            "X-Nonce": "nonce-1",
            "X-Signature": sig,
        },
    )
    assert resp.status_code == 200


def test_hmac_replay_is_rejected(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "nonce-r", body)
    headers = {
        "content-type": "application/json",
        "X-Api-Key": created.key_id,
        "X-Timestamp": ts,
        "X-Nonce": "nonce-r",
        "X-Signature": sig,
    }
    assert client.post("/v1/lemmatize", content=body, headers=headers).status_code == 200
    second = client.post("/v1/lemmatize", content=body, headers=headers)
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "NONCE_REPLAYED"


def test_unauthenticated_hmac_attempt_does_not_touch_the_nonce_store(app_client):
    """The nonce table is a write, so it must be unreachable without credentials.

    Timestamp and nonce used to be checked before the signature, which was
    harmless against a bounded in-memory dict. Once nonces moved to SQLite that
    ordering let anyone append a row per request just by sending X-Signature and
    a current X-Timestamp, with no key and no valid signature at all.
    """
    client, _, url = app_client
    ts = str(int(time.time()))
    for i in range(5):
        resp = client.post(
            "/v1/lemmatize",
            content=b'{"lang":"de","tokens":["x"]}',
            headers={
                "content-type": "application/json",
                "X-Api-Key": "no-such-key",
                "X-Timestamp": ts,
                "X-Nonce": f"junk-{i}",
                "X-Signature": "not-a-signature",
            },
        )
        assert resp.status_code == 401
    assert client.app.state.nonces.size() == 0


def test_hmac_stale_timestamp_is_rejected(app_client):
    client, created, _ = app_client
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()) - 10_000)
    sig = sign(created.secret, "POST", "/v1/lemmatize", ts, "n-old", body)
    resp = client.post(
        "/v1/lemmatize",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Api-Key": created.key_id,
            "X-Timestamp": ts,
            "X-Nonce": "n-old",
            "X-Signature": sig,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TIMESTAMP_OUT_OF_WINDOW"


def test_hmac_when_key_disallows_it_is_rejected(app_client):
    client, _, url = app_client
    no_hmac = keys.create(url, name="nh", created_by="t", master_key=MASTER, allow_hmac=False)
    body = b'{"lang":"de","tokens":["x"]}'
    ts = str(int(time.time()))
    sig = sign(no_hmac.secret, "POST", "/v1/lemmatize", ts, "n-x", body)
    resp = client.post(
        "/v1/lemmatize",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Api-Key": no_hmac.key_id,
            "X-Timestamp": ts,
            "X-Nonce": "n-x",
            "X-Signature": sig,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "HMAC_NOT_ALLOWED"


def test_lang_restriction_is_enforced(app_client):
    client, _, url = app_client
    restricted = keys.create(url, name="r", created_by="t", master_key=MASTER, langs=["fr"])
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {restricted.key_id}.{restricted.secret}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "LANG_FORBIDDEN"


def test_rate_limit_headers_and_429(app_client):
    client, _, url = app_client
    tiny = keys.create(url, name="tiny", created_by="t", master_key=MASTER, rate_limit_rpm=1)
    auth = {"Authorization": f"Bearer {tiny.key_id}.{tiny.secret}"}
    first = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}, headers=auth)
    assert first.status_code == 200
    assert "X-RateLimit-Limit" in first.headers
    assert "X-RateLimit-Remaining" in first.headers

    limited = None
    for _ in range(60):
        r = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}, headers=auth)
        if r.status_code == 429:
            limited = r
            break
    assert limited is not None
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in limited.headers


def test_health_stays_open_without_credentials(app_client):
    client, _, _ = app_client
    assert client.get("/v1/health").status_code == 200


def test_languages_stays_open_without_credentials(app_client):
    client, _, _ = app_client
    assert client.get("/v1/languages").status_code == 200


def test_auth_failure_still_carries_a_request_id(app_client):
    """A 401 must be correlatable with its log row, so the id is minted by the
    middleware, not the route (which never runs when auth rejects)."""
    client, _, _ = app_client
    resp = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]})
    assert resp.status_code == 401
    rid = resp.json()["error"]["request_id"]
    assert rid and rid.startswith("req_")


def test_successful_call_echoes_request_id_in_header(app_client):
    client, created, _ = app_client
    resp = client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"]},
        headers={"Authorization": f"Bearer {created.key_id}.{created.secret}"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Request-Id"] == resp.json()["request_id"]
