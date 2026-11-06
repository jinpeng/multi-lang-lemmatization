"""Morpheme-analyser backend for Japanese.

dictionary_form() is the lemma; normalized_form() is a different thing and must
not be substituted. reading_form() gives katakana, which we expose as `reading`.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from sudachipy import dictionary, tokenizer

from api.backends.base import BaseBackend
from api.types import Capabilities, LemmaItem

SPLIT_MODES = {
    "A": tokenizer.Tokenizer.SplitMode.A,
    "B": tokenizer.Tokenizer.SplitMode.B,
    "C": tokenizer.Tokenizer.SplitMode.C,
}


class SudachiBackend(BaseBackend):
    lang = "ja"
    name = "sudachipy"
    pos_scheme = "sudachi"
    capabilities = Capabilities(
        pos=True, pos_required=False, reading=True, mwt=False, tokenizes=True
    )

    def __init__(self) -> None:
        self._tokenizer = dictionary.Dictionary(dict="core").tokenizer()
        self.version = md.version("sudachipy")
        try:
            self.dictionary_id = md.version("sudachidict_core")
        except md.PackageNotFoundError:
            self.dictionary_id = "unknown"

    def option_specs(self) -> dict[str, dict]:
        return {"split_mode": {"type": "enum", "values": ["A", "B", "C"], "default": "C"}}

    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        mode_key = str(options.get("split_mode", "C"))
        mode = SPLIT_MODES.get(mode_key.upper())
        if mode is None:
            raise ValueError(f"invalid split_mode: {mode_key!r}")

        source = text if text is not None else "".join(tokens or [])
        morphemes = self._tokenizer.tokenize(source, mode)

        items: list[LemmaItem] = []
        for m in morphemes:
            surface = m.surface()
            lemma = m.dictionary_form()
            pos = ",".join(m.part_of_speech()) if m.part_of_speech() else None
            reading = m.reading_form() or None
            prov = "dict" if lemma != surface else "identity"
            items.append(
                LemmaItem(
                    surface=surface,
                    lemma=lemma,
                    pos=pos,
                    prov=prov,
                    reading=reading,
                    start=m.begin(),
                    end=m.end(),
                )
            )
        return items


def build() -> SudachiBackend:
    return SudachiBackend()
