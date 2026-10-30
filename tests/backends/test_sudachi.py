import pytest

from api.backends import sudachi_backend

pytestmark = pytest.mark.slow


def test_capabilities():
    backend = sudachi_backend.build()
    assert backend.lang == "ja"
    assert backend.name == "sudachipy"
    assert backend.pos_scheme == "sudachi"
    assert backend.capabilities.pos is True
    assert backend.capabilities.reading is True
    assert backend.capabilities.tokenizes is True


def test_dictionary_form_of_inflected_verb():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    lemmas = {i.surface: i.lemma for i in items}
    assert lemmas["食べ"] == "食べる"


def test_outputs_reading():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    tabe = next(i for i in items if i.surface == "食べ")
    assert tabe.reading == "タベ"


def test_outputs_pos():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="食べました", tokens=None, pos=None, options={})
    tabe = next(i for i in items if i.surface == "食べ")
    assert tabe.pos is not None
    assert "動詞" in tabe.pos


def test_ignores_callers_tokens_because_it_retokenizes():
    backend = sudachi_backend.build()
    items = backend.lemmatize(text="東京都", tokens=["WRONG"], pos=None, options={})
    assert all(i.surface != "WRONG" for i in items)


def test_split_mode_option_changes_segmentation():
    backend = sudachi_backend.build()
    merged = backend.lemmatize(
        text="国家公務員", tokens=None, pos=None, options={"split_mode": "C"}
    )
    split = backend.lemmatize(text="国家公務員", tokens=None, pos=None, options={"split_mode": "A"})
    assert len(split) > len(merged)


def test_option_specs_exposes_split_mode():
    specs = sudachi_backend.build().option_specs()
    assert specs["split_mode"]["values"] == ["A", "B", "C"]
    assert specs["split_mode"]["default"] == "C"


def test_offsets_slice_back_exactly():
    backend = sudachi_backend.build()
    text = "東京都へ行きました"
    items = backend.lemmatize(text=text, tokens=None, pos=None, options={})
    for item in items:
        assert text[item.start : item.end] == item.surface


def test_non_bmp_prefix_gives_code_point_offsets():
    backend = sudachi_backend.build()
    text = "𝕏東京"
    items = backend.lemmatize(text=text, tokens=None, pos=None, options={})
    tokyo = next(i for i in items if i.surface == "東京")
    assert (tokyo.start, tokyo.end) == (1, 3)
