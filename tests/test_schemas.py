import pytest
from pydantic import ValidationError

from api.schemas import LemmatizeRequest, normalize_pos


def test_accepts_text_only():
    req = LemmatizeRequest(lang="de", text="Häuser")
    assert req.tokens is None


def test_accepts_tokens_only():
    req = LemmatizeRequest(lang="de", tokens=["Häuser"])
    assert req.text is None


def test_rejects_both_text_and_tokens():
    with pytest.raises(ValidationError, match="exactly one"):
        LemmatizeRequest(lang="de", text="x", tokens=["x"])


def test_rejects_neither_text_nor_tokens():
    with pytest.raises(ValidationError, match="exactly one"):
        LemmatizeRequest(lang="de")


def test_normalize_pos_string_becomes_single_element_list():
    assert normalize_pos("VERB", 1) == ["VERB"]


def test_normalize_pos_none_stays_none():
    assert normalize_pos(None, 3) is None


def test_normalize_pos_list_passes_through():
    assert normalize_pos(["VERB", "NOUN"], 2) == ["VERB", "NOUN"]


def test_normalize_pos_list_length_mismatch_raises():
    with pytest.raises(ValueError, match="length"):
        normalize_pos(["VERB"], 2)


def test_normalize_pos_scalar_with_text_input_is_accepted():
    """token_count is None when the caller sent `text`; no length check applies."""
    assert normalize_pos("VERB", None) == ["VERB"]


def test_normalize_pos_list_with_unknown_token_count_raises():
    """A per-token list cannot be matched against a whole-text input."""
    with pytest.raises(ValueError, match="tokens"):
        normalize_pos(["VERB"], None)
