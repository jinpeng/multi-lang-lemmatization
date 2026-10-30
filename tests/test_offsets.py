"""Character offsets (spec open item 2).

`start`/`end` are CODE POINT offsets into the request's `text`. They are omitted
when the caller supplied `tokens`, because there is no source string to point
into. `offset_unit` at the top level says which unit is in use.
"""
import pytest


def _body(client, payload):
    return client.post("/v1/lemmatize", json=payload).json()


def test_offsets_present_when_text_is_tokenized(real_client):
    body = _body(real_client, {"lang": "de", "text": "Hier sind Häuser."})
    assert body["offset_unit"] == "unicode_code_point"
    for item in body["items"]:
        assert "start" in item and "end" in item


def test_offsets_slice_back_to_the_surface(real_client):
    text = "Hier sind Häuser."
    body = _body(real_client, {"lang": "de", "text": text})
    for item in body["items"]:
        assert text[item["start"]:item["end"]] == item["surface"]


def test_offsets_absent_for_token_input(real_client):
    body = _body(real_client, {"lang": "de", "tokens": ["Häuser"]})
    assert body["offset_unit"] is None
    assert "start" not in body["items"][0]


@pytest.mark.parametrize("lang,text", [
    ("ru", "Он шёл домой."),
    ("ja", "東京都へ行きました"),
    ("ko", "먹었습니다"),
])
def test_offsets_are_ordered_and_within_bounds(real_client, lang, text):
    body = _body(real_client, {"lang": lang, "text": text})
    assert body["offset_unit"] == "unicode_code_point"
    previous_end = 0
    for item in body["items"]:
        assert 0 <= item["start"] <= item["end"] <= len(text)
        assert item["start"] >= previous_end or item["start"] == item["end"] - 1
        previous_end = item["end"]


def test_japanese_offsets_slice_exactly(real_client):
    text = "東京都へ行きました"
    body = _body(real_client, {"lang": "ja", "text": text})
    for item in body["items"]:
        assert text[item["start"]:item["end"]] == item["surface"]


def test_korean_offsets_are_spans_not_surfaces(real_client):
    """A contracted form is decomposed, so several morphemes share one span.

    갔 is analysed as 가 + 었, both spanning the single character. Offsets still
    point at the right place in the original text; `surface` is the morpheme,
    not the substring. Consumers must not assume text[start:end] == surface.
    """
    text = "갔다"
    body = _body(real_client, {"lang": "ko", "text": text})
    verb = [i for i in body["items"] if i["pos"] == "VV"]
    assert verb, "expected a verb stem"
    assert (verb[0]["start"], verb[0]["end"]) == (0, 1)
    assert text[0:1] == "갔"
    assert verb[0]["surface"] != text[0:1]


def test_offsets_survive_non_bmp_text(real_client):
    """Code-point offsets must not be confused with UTF-16 indices."""
    text = "𝕏東京"
    body = _body(real_client, {"lang": "ja", "text": text})
    tokyo = next(i for i in body["items"] if i["surface"] == "東京")
    assert (tokyo["start"], tokyo["end"]) == (1, 3)
    assert text[1:3] == "東京"
