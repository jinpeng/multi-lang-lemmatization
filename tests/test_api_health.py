def test_health_is_reachable_without_auth(fake_client):
    resp = fake_client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "backends" in body


def test_health_lists_every_registered_language(fake_client):
    body = fake_client.get("/v1/health").json()
    assert set(body["backends"]) == {"en", "de", "fr", "es", "ru", "ja", "ko"}
