def test_lemmatize_requires_auth_when_enabled(authed_client):
    """Sanity: the fixture authenticates, and dropping the header fails."""
    client, _ = authed_client
    assert client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).status_code == 200
    client.headers.pop("Authorization")
    assert client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).status_code == 401
