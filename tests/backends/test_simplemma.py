import pytest

from api.backends import simplemma_backend


@pytest.mark.parametrize("lang", ["de", "fr", "es"])
def test_build_covers_supported_languages(lang):
    backend = simplemma_backend.build(lang)
    assert backend.lang == lang
    assert backend.name == "simplemma"
    assert backend.capabilities.pos is False
    assert backend.capabilities.tokenizes is False


def test_build_rejects_unsupported_language():
    with pytest.raises(ValueError, match="does not cover"):
        simplemma_backend.build("ja")


def test_greedy_defaults_follow_survey():
    assert simplemma_backend.build("de").greedy is True
    assert simplemma_backend.build("fr").greedy is False
    assert simplemma_backend.build("es").greedy is False


def test_lemmatizes_german_plural_noun():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(tokens=["Häuser"], text=None, pos=None, options={})
    assert len(items) == 1
    assert items[0].surface == "Häuser"
    assert items[0].lemma == "Haus"
    assert items[0].pos is None


def test_lemmatizes_french_participle():
    backend = simplemma_backend.build("fr")
    items = backend.lemmatize(tokens=["mangées"], text=None, pos=None, options={})
    assert items[0].lemma == "manger"


def test_lemmatizes_spanish_gerund():
    backend = simplemma_backend.build("es")
    items = backend.lemmatize(tokens=["corriendo"], text=None, pos=None, options={})
    assert items[0].lemma == "correr"


def test_tokenizes_text_when_tokens_absent():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(text="Hier sind Häuser.", tokens=None, pos=None, options={})
    assert [i.surface for i in items] == ["Hier", "sind", "Häuser", "."]


def test_unknown_word_falls_back_to_identity_not_exception():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(tokens=["Xylophonwort"], text=None, pos=None, options={})
    assert items[0].lemma == "Xylophonwort"
    assert items[0].prov == "identity"


def test_greedy_option_overrides_default_per_request():
    backend = simplemma_backend.build("de")
    items = backend.lemmatize(
        tokens=["ausgezeichneten"], text=None, pos=None, options={"greedy": False}
    )
    assert items[0].lemma == "ausgezeichnet"


def test_option_specs_exposes_greedy():
    specs = simplemma_backend.build("de").option_specs()
    assert specs["greedy"]["type"] == "bool"
    assert specs["greedy"]["default"] is True


def test_offsets_present_for_text_but_absent_for_tokens():
    backend = simplemma_backend.build("de")
    from_text = backend.lemmatize(text="Häuser Haus", tokens=None, pos=None, options={})
    assert [(i.start, i.end) for i in from_text] == [(0, 6), (7, 11)]
    from_tokens = backend.lemmatize(tokens=["Häuser"], text=None, pos=None, options={})
    assert from_tokens[0].start is None
