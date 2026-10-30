from api.types import Capabilities, LemmaItem


def test_capabilities_serializes_all_seven_flags():
    caps = Capabilities(pos=True, tokenizes=True)
    assert caps.to_json() == {
        "pos": True,
        "pos_accepted": False,
        "pos_required": False,
        "candidates": False,
        "reading": False,
        "mwt": False,
        "tokenizes": True,
    }


def test_lemma_item_omits_absent_optional_fields():
    item = LemmaItem(surface="was", lemma="be", pos="VERB", prov="dict")
    assert item.to_json() == {
        "surface": "was",
        "lemma": "be",
        "pos": "VERB",
        "prov": "dict",
    }


def test_lemma_item_includes_reading_and_candidates_when_present():
    item = LemmaItem(
        surface="食べ", lemma="食べる", pos="動詞", prov="dict",
        reading="タベ", candidates=("食べる", "食べ"),
    )
    out = item.to_json()
    assert out["reading"] == "タベ"
    assert out["candidates"] == ["食べる", "食べ"]


def test_lemma_item_keeps_explicit_null_pos():
    """pos must serialize as null (not be dropped) - clients rely on the key existing."""
    item = LemmaItem(surface="Häuser", lemma="Haus", pos=None, prov="dict")
    out = item.to_json()
    assert "pos" in out
    assert out["pos"] is None


def test_lemma_item_omits_offsets_when_unknown():
    item = LemmaItem(surface="Haus", lemma="Haus")
    out = item.to_json()
    assert "start" not in out and "end" not in out


def test_lemma_item_includes_offsets_when_known():
    item = LemmaItem(surface="Haus", lemma="Haus", start=9, end=13)
    out = item.to_json()
    assert (out["start"], out["end"]) == (9, 13)


def test_lemma_item_omits_offsets_if_only_one_bound_is_set():
    """A half-open span is meaningless; drop both rather than emit a lie."""
    item = LemmaItem(surface="Haus", lemma="Haus", start=9)
    out = item.to_json()
    assert "start" not in out and "end" not in out


def test_pos_produced_and_pos_accepted_are_independent():
    """English accepts a tag but emits none; Russian emits one but takes none."""
    english = Capabilities(pos=False, pos_accepted=True)
    russian = Capabilities(pos=True, pos_accepted=False)
    assert english.to_json()["pos"] is False
    assert english.to_json()["pos_accepted"] is True
    assert russian.to_json()["pos"] is True
    assert russian.to_json()["pos_accepted"] is False
