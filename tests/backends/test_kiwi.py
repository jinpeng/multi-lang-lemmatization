import pytest

from api.backends import kiwi_backend

pytestmark = pytest.mark.slow


def test_capabilities():
    backend = kiwi_backend.build()
    assert backend.lang == "ko"
    assert backend.name == "kiwipiepy"
    assert backend.pos_scheme == "sejong-kiwi"
    assert backend.capabilities.pos is True
    assert backend.capabilities.tokenizes is True


def test_noun_lemma_equals_surface():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="학교에 갔습니다", tokens=None, pos=None, options={})
    hakgyo = next(i for i in items if i.surface == "학교")
    assert hakgyo.lemma == "학교"
    assert hakgyo.pos == "NNG"


def test_predicate_stem_gets_dictionary_form():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="먹었습니다", tokens=None, pos=None, options={})
    stem = next(i for i in items if i.pos == "VV")
    assert stem.surface == "먹"
    assert stem.lemma == "먹다"


def test_ignores_callers_tokens_because_it_retokenizes():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="학교", tokens=["WRONG"], pos=None, options={})
    assert all(i.surface != "WRONG" for i in items)


def test_carries_pos_tags_from_sejong_tagset():
    backend = kiwi_backend.build()
    items = backend.lemmatize(text="먹었습니다", tokens=None, pos=None, options={})
    tags = {i.pos for i in items}
    assert "VV" in tags


def test_offsets_are_valid_spans_not_surfaces():
    """A contracted verb decomposes, so several morphemes share one span.

    갔 is analysed as 가 + 었, both over [0:1]. The span is correct; `surface`
    is the morpheme, not the substring. Do not assert equality here.
    """
    backend = kiwi_backend.build()
    text = "갔다"
    items = backend.lemmatize(text=text, tokens=None, pos=None, options={})
    verb = next(i for i in items if i.pos == "VV")
    assert (verb.start, verb.end) == (0, 1)
    assert text[0:1] == "갔"
    assert verb.surface != text[0:1]
