"""Cross-language golden cases from the design spec section 10."""

import pytest

CASES = [
    # lang, payload, expected lemma, expected pos-ness
    ("en", {"tokens": ["was"], "pos": ["VERB"]}, "be", "present-or-null"),
    ("de", {"tokens": ["Häuser"]}, "Haus", "null"),
    ("fr", {"tokens": ["mangées"]}, "manger", "null"),
    ("es", {"tokens": ["corriendo"]}, "correr", "null"),
    ("ru", {"text": "шёл"}, "идти", "present"),
    ("ja", {"text": "食べました"}, "食べる", "present"),
    ("ko", {"text": "먹었습니다"}, "먹다", "present"),
]


@pytest.mark.parametrize("lang,payload,expected_lemma,_posness", CASES)
def test_golden_lemma(real_client, lang, payload, expected_lemma, _posness):
    body = real_client.post("/v1/lemmatize", json={"lang": lang, **payload}).json()
    lemmas = [i["lemma"] for i in body["items"]]
    assert expected_lemma in lemmas, f"{lang}: {expected_lemma} not in {lemmas}"


@pytest.mark.parametrize("lang,payload,_lemma,posness", CASES)
def test_golden_pos_contract(real_client, lang, payload, _lemma, posness):
    body = real_client.post("/v1/lemmatize", json={"lang": lang, **payload}).json()
    items = body["items"]
    assert all("pos" in i for i in items)
    if posness == "null":
        assert all(i["pos"] is None for i in items)
    elif posness == "present":
        assert any(i["pos"] is not None for i in items)


def test_all_seven_languages_are_healthy(real_client):
    body = real_client.get("/v1/health").json()
    unavailable = {
        lang: info for lang, info in body["backends"].items()
        if info["status"] != "ok"
    }
    assert unavailable == {}, f"unavailable backends: {unavailable}"
