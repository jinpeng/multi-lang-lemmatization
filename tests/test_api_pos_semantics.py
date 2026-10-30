import pytest


def _items(client, payload):
    return client.post("/v1/lemmatize", json=payload).json()["items"]


def test_pos_key_always_present_even_when_null(real_client):
    items = _items(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert all("pos" in i for i in items)
    assert items[0]["pos"] is None


@pytest.mark.parametrize("lang,tokens", [
    ("de", ["Häuser"]),
    ("fr", ["mangées"]),
    ("es", ["corriendo"]),
])
def test_lookup_languages_report_null_pos(real_client, lang, tokens):
    items = _items(real_client, {"lang": lang, "tokens": tokens})
    assert items[0]["pos"] is None


@pytest.mark.parametrize("lang,text", [
    ("ru", "шёл"),
    ("ja", "食べました"),
    ("ko", "먹었습니다"),
])
def test_analyser_languages_report_non_null_pos(real_client, lang, text):
    items = _items(real_client, {"lang": lang, "text": text})
    assert any(i["pos"] is not None for i in items)


def test_prov_is_always_present(real_client):
    items = _items(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert all(i["prov"] in {"dict", "rule", "model", "identity", "candidates"} for i in items)


def test_identity_items_appear_in_warnings(real_client):
    body = real_client.post(
        "/v1/lemmatize", json={"lang": "de", "tokens": ["Xylophonwort"]}
    ).json()
    assert any(w["surface"] == "Xylophonwort" for w in body["warnings"])
