"""Morphological-analyser backend for Russian.

pymorphy3 returns scored parses; the highest-scoring parse's normal_form is the
lemma. We also surface its POS so clients get more than a bare string.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

import pymorphy3

from api.backends.base import BaseBackend
from api.textutil import tokenize_with_offsets
from api.types import Capabilities, LemmaItem


class PymorphyBackend(BaseBackend):
    lang = "ru"
    name = "pymorphy3"
    pos_scheme = "pymorphy"
    capabilities = Capabilities(pos=True, pos_required=False, tokenizes=False)

    def __init__(self) -> None:
        self._morph = pymorphy3.MorphAnalyzer()
        self.version = md.version("pymorphy3")

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        if tokens is not None:
            spans: list[tuple[str, int | None, int | None]] = [(t, None, None) for t in tokens]
        else:
            spans = list(tokenize_with_offsets(text or ""))

        items: list[LemmaItem] = []
        for surface, start, end in spans:
            parses = self._morph.parse(surface)
            if not parses:
                items.append(
                    LemmaItem(
                        surface=surface,
                        lemma=surface,
                        pos=None,
                        prov="identity",
                        start=start,
                        end=end,
                    )
                )
                continue

            best = parses[0]
            lemma = best.normal_form
            tag = getattr(best.tag, "POS", None)
            prov = "dict" if lemma.lower() != surface.lower() else "identity"
            items.append(
                LemmaItem(
                    surface=surface,
                    lemma=lemma,
                    pos=tag,
                    prov=prov,
                    start=start,
                    end=end,
                )
            )
        return items


def build() -> PymorphyBackend:
    return PymorphyBackend()
