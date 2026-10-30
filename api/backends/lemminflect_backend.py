"""Dictionary + neural-OOV backend for English (LemmInflect).

Two library entry points, and the difference matters:

- getLemma(word, upos) REQUIRES a POS tag. There is no default.
- getAllLemmas(word) is the POS-agnostic path; it returns {UPOS: (lemmas,)}.

Calling getLemma(surface) without upos raises TypeError, and because the
adapter catches exceptions, every POS-less request would silently degrade to
identity - English would "work" but never actually lemmatize. Use getAllLemmas
for the no-tag path instead.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

from lemminflect import getAllLemmas, getLemma

from api.backends.base import BaseBackend
from api.textutil import tokenize_with_offsets
from api.types import Capabilities, LemmaItem


def _merge(by_pos: dict[str, tuple[str, ...]]) -> list[str]:
    """Flatten {UPOS: lemmas} into one ordered, de-duplicated list."""
    merged: list[str] = []
    for lemmas in by_pos.values():
        for lemma in lemmas:
            if lemma not in merged:
                merged.append(lemma)
    return merged


class LemmInflectBackend(BaseBackend):
    lang = "en"
    name = "lemminflect"
    pos_scheme = "ud"
    capabilities = Capabilities(
        pos=False, pos_accepted=True, pos_required=False, candidates=True, tokenizes=False
    )

    def __init__(self) -> None:
        self.version = md.version("lemminflect")

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
        for index, (surface, start, end) in enumerate(spans):
            tag = pos[index] if pos is not None and index < len(pos) else None
            try:
                if tag:
                    found = list(getLemma(surface, upos=tag))
                else:
                    found = _merge(getAllLemmas(surface))
            except Exception:  # noqa: BLE001 - an odd tag must not fail the request
                found = []

            if not found or found[0] == surface:
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

            items.append(
                LemmaItem(
                    surface=surface,
                    lemma=found[0],
                    pos=None,
                    prov="dict",
                    candidates=tuple(found) if len(found) > 1 else (),
                    start=start,
                    end=end,
                )
            )
        return items


def build() -> LemmInflectBackend:
    return LemmInflectBackend()
