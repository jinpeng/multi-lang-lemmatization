def test_languages_returns_all_seven(real_client):
    body = real_client.get("/v1/languages").json()
    langs = {entry["lang"] for entry in body["languages"]}
    assert langs == {"en", "de", "fr", "es", "ru", "ja", "ko"}


def test_each_entry_has_full_capability_matrix(real_client):
    body = real_client.get("/v1/languages").json()
    for entry in body["languages"]:
        caps = entry["capabilities"]
        assert set(caps) == {
            "pos", "pos_accepted", "pos_required",
            "candidates", "reading", "mwt", "tokenizes",
        }
        assert "pos_scheme" in entry


def test_english_accepts_pos_but_emits_none(real_client):
    body = real_client.get("/v1/languages").json()
    en = next(e for e in body["languages"] if e["lang"] == "en")
    assert en["capabilities"]["pos"] is False
    assert en["capabilities"]["pos_accepted"] is True


def test_russian_emits_pos_but_does_not_accept_it(real_client):
    body = real_client.get("/v1/languages").json()
    ru = next(e for e in body["languages"] if e["lang"] == "ru")
    assert ru["capabilities"]["pos"] is True
    assert ru["capabilities"]["pos_accepted"] is False


def test_japanese_declares_tokenizes_true_and_reading_true(real_client):
    body = real_client.get("/v1/languages").json()
    ja = next(e for e in body["languages"] if e["lang"] == "ja")
    assert ja["capabilities"]["tokenizes"] is True
    assert ja["capabilities"]["reading"] is True
    assert ja["pos_scheme"] == "sudachi"


def test_german_declares_pos_false(real_client):
    body = real_client.get("/v1/languages").json()
    de = next(e for e in body["languages"] if e["lang"] == "de")
    assert de["capabilities"]["pos"] is False
    assert de["pos_scheme"] is None
    assert de["options"]["greedy"]["default"] is True
