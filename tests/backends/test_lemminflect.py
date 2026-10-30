from api.backends import lemminflect_backend


def test_capabilities():
    backend = lemminflect_backend.build()
    assert backend.lang == "en"
    assert backend.name == "lemminflect"
    assert backend.pos_scheme == "ud"
    # English never emits a tag, but it does use one if you supply it.
    assert backend.capabilities.pos is False
    assert backend.capabilities.pos_accepted is True
    assert backend.capabilities.pos_required is False
    assert backend.capabilities.tokenizes is False


def test_lemmatizes_irregular_verb_with_pos():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["was"], text=None, pos=["VERB"], options={})
    assert items[0].lemma == "be"
    assert items[0].prov == "dict"


def test_lemmatizes_plural_noun():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["watches"], text=None, pos=["VERB"], options={})
    assert items[0].lemma == "watch"


def test_works_without_pos():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["watches"], text=None, pos=None, options={})
    assert items[0].lemma == "watch"
    assert items[0].pos is None


def test_tokenizes_text_when_tokens_absent():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(text="The cats were sleeping.", tokens=None, pos=None, options={})
    assert items[0].surface == "The"
    assert any(i.lemma == "cat" for i in items)


def test_unknown_word_is_identity():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(tokens=["zzzzqqq"], text=None, pos=None, options={})
    assert items[0].lemma == "zzzzqqq"
    assert items[0].prov == "identity"


def test_pos_input_changes_the_answer():
    backend = lemminflect_backend.build()
    as_verb = backend.lemmatize(tokens=["left"], text=None, pos=["VERB"], options={})
    as_noun = backend.lemmatize(tokens=["left"], text=None, pos=["NOUN"], options={})
    assert as_verb[0].lemma == "leave"
    assert as_noun[0].lemma == "left"


def test_offsets_present_for_text():
    backend = lemminflect_backend.build()
    items = backend.lemmatize(text="cats dogs", tokens=None, pos=None, options={})
    assert [(i.start, i.end) for i in items] == [(0, 4), (5, 9)]
