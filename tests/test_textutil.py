from api.textutil import fallback_tokenize, tokenize_with_offsets


def test_tokenize_latin_sentence():
    assert fallback_tokenize("Hier sind Vaccines.") == ["Hier", "sind", "Vaccines", "."]


def test_tokenize_cyrillic_sentence():
    tokens = fallback_tokenize("Он шёл домой.")
    assert "шёл" in tokens
    assert tokens[-1] == "."


def test_tokenize_empty_string_returns_empty_list():
    assert fallback_tokenize("") == []


def test_tokenize_with_offsets_slices_back_to_each_token():
    text = "Hier sind Häuser."
    spans = tokenize_with_offsets(text)
    assert [t for t, _, _ in spans] == ["Hier", "sind", "Häuser", "."]
    for token, start, end in spans:
        assert text[start:end] == token


def test_tokenize_with_offsets_never_matches_an_earlier_occurrence():
    """The cursor must move forward, so repeated tokens get distinct spans."""
    text = "a a a"
    spans = tokenize_with_offsets(text)
    assert [(s, e) for _, s, e in spans] == [(0, 1), (2, 3), (4, 5)]


def test_tokenize_with_offsets_reports_code_points():
    """Offsets count code points, so a surrogate pair is 1 wide, not 2.

    𝕏 is U+1D54F: one code point, two UTF-16 units. If these were UTF-16
    indices the span would end at 4 instead of 3.
    """
    text = "𝕏東京"
    assert len(text) == 3
    assert len(text.encode("utf-16-le")) // 2 == 4
    spans = tokenize_with_offsets(text)
    assert spans == [("𝕏東京", 0, 3)]


def test_tokenize_with_offsets_empty():
    assert tokenize_with_offsets("") == []
