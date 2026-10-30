def test_lemmatize_german_tokens(real_client):
    resp = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["lang"] == "de"
    assert body["segmented_by"] == "input"
    assert body["items"][0]["lemma"] == "Haus"


def test_response_carries_backend_identity_and_capabilities(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert body["backend"]["name"] == "simplemma"
    assert "version" in body["backend"]
    assert "capabilities" in body


def test_japanese_reports_segmented_by_backend(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "ja", "text": "食べました"}
    ).json()
    assert body["segmented_by"] == "backend"
    assert {i["surface"] for i in body["items"]} != {"食べました"}


def test_japanese_retokenizes_even_when_given_tokens(real_client):
    """`ja` re-segments, so `segmented_by` is "backend" on both input paths.

    Sending both `text` and `tokens` is rejected by the schema, so this exercises
    the tokens-only path: SudachiPy joins the tokens and analyses the result.
    """
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "ja", "tokens": ["食べました"]}
    ).json()
    assert body["segmented_by"] == "backend"
    surfaces = [i["surface"] for i in body["items"]]
    assert surfaces != ["食べました"], "output must not echo the caller's token 1:1"
    assert any(i["lemma"] == "食べる" for i in body["items"])


def test_request_id_is_present_and_unique(real_client):
    a = real_client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).json()
    b = real_client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]}).json()
    assert a["request_id"].startswith("req_")
    assert a["request_id"] != b["request_id"]


def test_elapsed_ms_is_reported(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert isinstance(body["elapsed_ms"], (int, float))
    assert body["elapsed_ms"] >= 0


def test_greedy_option_is_accepted(real_client):
    resp = real_client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["ausgezeichneten"], "options": {"greedy": False}},
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["lemma"] == "ausgezeichnet"


def test_unknown_option_is_rejected(real_client):
    resp = real_client.post(
        "/v1/lemmatize",
        json={"lang": "de", "tokens": ["x"], "options": {"nonsense": 1}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNKNOWN_OPTION"


def test_unknown_language_is_rejected(real_client):
    resp = real_client.post("/v1/lemmatize", json={"lang": "zz", "tokens": ["x"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNKNOWN_LANGUAGE"


def test_both_text_and_tokens_is_400_with_our_envelope(real_client):
    """Pydantic's default 422/detail envelope must not leak out."""
    resp = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "text": "a", "tokens": ["a"]}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "detail" not in body


def test_missing_input_is_400_with_our_envelope(real_client):
    resp = real_client.post("/v1/lemmatize", json={"lang": "de"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_list_pos_with_text_input_is_rejected(real_client):
    resp = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "text": "Haus", "pos": ["NOUN"]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


def test_unavailable_backend_returns_503():
    from fastapi.testclient import TestClient

    from api.main import build_registry, create_app

    registry = build_registry(use_fakes=True)

    def _boom():
        raise RuntimeError("dict missing")

    registry.register("de", _boom)
    client = TestClient(create_app(registry=registry))
    resp = client.post("/v1/lemmatize", json={"lang": "de", "tokens": ["x"]})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "LANGUAGE_UNAVAILABLE"
    assert "dict missing" in resp.json()["error"]["details"]["reason"]


def test_response_states_the_offset_unit(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "text": "Häuser"}
    ).json()
    assert body["offset_unit"] == "unicode_code_point"


def test_response_offset_unit_is_null_for_tokens(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Häuser"]}
    ).json()
    assert body["offset_unit"] is None
