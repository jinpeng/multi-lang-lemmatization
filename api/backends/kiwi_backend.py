"""Morpheme-analyser backend for Korean.

Kiwi has no lemma() API. A predicate stem's dictionary form is reconstructed by
joining the stem with the plain ending 다/하다, which is the same technique the
Kiwi README uses when it strips the past-tense ending to recover 먹다.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from kiwipiepy import Kiwi

from api.backends.base import BaseBackend
from api.types import Capabilities, LemmaItem

# Sejong-derived tags whose dictionary form is "<stem>다".
PREDICATE_TAGS = frozenset({"VV", "VA", "VX", "XSV", "XSA"})


class KiwiBackend(BaseBackend):
    lang = "ko"
    name = "kiwipiepy"
    pos_scheme = "sejong-kiwi"
    capabilities = Capabilities(pos=True, pos_required=False, tokenizes=True)

    def __init__(self) -> None:
        self._kiwi = Kiwi()
        self.version = md.version("kiwipiepy")

    def option_specs(self) -> dict[str, dict]:
        return {}

    def _dictionary_form(self, form: str, tag: str) -> str:
        if tag not in PREDICATE_TAGS:
            return form
        try:
            return self._kiwi.join([(form, tag), ("다", "EF")])
        except Exception:  # noqa: BLE001 - a bad tag must not fail the request
            return form

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        source = text if text is not None else " ".join(tokens or [])
        parsed = self._kiwi.tokenize(source)

        items: list[LemmaItem] = []
        for token in parsed:
            form = token.form
            tag = token.tag
            lemma = self._dictionary_form(form, tag)
            prov = "dict" if lemma != form else "identity"
            items.append(
                LemmaItem(
                    surface=form,
                    lemma=lemma,
                    pos=tag,
                    prov=prov,
                    start=token.start,
                    end=token.start + token.len,
                )
            )
        return items


def build() -> KiwiBackend:
    return KiwiBackend()
