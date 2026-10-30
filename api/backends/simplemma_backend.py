"""Dictionary-lookup backend for de/fr/es.

simplemma needs no morphosyntactic information - that is precisely why these
three languages get no `pos` (spec section 3.2).
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

import simplemma

from api.backends.base import BaseBackend
from api.textutil import tokenize_with_offsets
from api.types import Capabilities, LemmaItem

# Language -> greedy default. `de` needs the second reduction for compound and
# derived nouns; `fr`/`es` get closer to stemming if greedier, so leave it off.
GREEDY_DEFAULTS: dict[str, bool] = {"de": True, "fr": False, "es": False}


class SimplemmaBackend(BaseBackend):
    name = "simplemma"
    pos_scheme = None
    capabilities = Capabilities(pos=False, pos_required=False, tokenizes=False)

    def __init__(self, lang: str, greedy: bool) -> None:
        if lang not in GREEDY_DEFAULTS:
            raise ValueError(f"simplemma backend does not cover {lang!r}")
        self.lang = lang
        self.greedy = greedy
        self.version = md.version("simplemma")

    def option_specs(self) -> dict[str, dict]:
        return {"greedy": {"type": "bool", "default": self.greedy}}

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        greedy = bool(options.get("greedy", self.greedy))

        # Offsets exist only when we tokenized the text ourselves. With
        # caller-supplied tokens there is no source string to point into.
        if tokens is not None:
            spans: list[tuple[str, int | None, int | None]] = [
                (t, None, None) for t in tokens
            ]
        else:
            spans = list(tokenize_with_offsets(text or ""))

        items: list[LemmaItem] = []
        for surface, start, end in spans:
            lemma = simplemma.lemmatize(surface, lang=self.lang, greedy=greedy)
            prov = "dict" if lemma != surface else "identity"
            items.append(
                LemmaItem(
                    surface=surface, lemma=lemma, pos=None, prov=prov,
                    start=start, end=end,
                )
            )
        return items


def build(lang: str) -> SimplemmaBackend:
    if lang not in GREEDY_DEFAULTS:
        raise ValueError(f"simplemma backend does not cover {lang!r}")
    return SimplemmaBackend(lang, greedy=GREEDY_DEFAULTS[lang])
