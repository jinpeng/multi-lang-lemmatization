from api.backends import pymorphy_backend


def test_capabilities():
    backend = pymorphy_backend.build()
    assert backend.lang == "ru"
    assert backend.name == "pymorphy3"
    assert backend.pos_scheme == "pymorphy"
    assert backend.capabilities.pos is True
    assert backend.capabilities.tokenizes is False


def test_lemmatizes_past_tense_verb():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["шёл"], text=None, pos=None, options={})
    assert items[0].lemma == "идти"
    assert items[0].pos is not None


def test_lemmatizes_genitive_noun():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["Украины"], text=None, pos=None, options={})
    assert items[0].lemma == "украина"


def test_tokenizes_text_when_tokens_absent():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(text="Он шёл домой.", tokens=None, pos=None, options={})
    assert any(i.lemma == "идти" for i in items)


def test_uppercase_word_is_lowercased_like_pymorphy_normal_form():
    backend = pymorphy_backend.build()
    items = backend.lemmatize(tokens=["Москве"], text=None, pos=None, options={})
    assert items[0].lemma == "москва"


def test_offsets_present_for_text():
    backend = pymorphy_backend.build()
    text = "Он шёл"
    items = backend.lemmatize(text=text, tokens=None, pos=None, options={})
    for item in items:
        assert text[item.start : item.end] == item.surface
