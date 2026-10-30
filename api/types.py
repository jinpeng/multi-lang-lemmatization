"""Shared vocabulary for every backend. No backend may invent its own shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# How a lemma was produced. Clients use this to tell a real dictionary hit
# from a passthrough, which matters for downstream confidence.
Prov = Literal["dict", "rule", "model", "identity", "candidates"]


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually deliver for its language.

    `pos` vs `pos_accepted` are genuinely different questions and the
    difference is load-bearing for English:

    - pos          the backend PRODUCES a tag in its output (ru, ja, ko)
    - pos_accepted the backend USES a caller-supplied tag to improve output (en)

    LemmInflect accepts `upos` and materially changes its answer based on it
    ("left" -> "leave" as a verb, "left" as a noun) but never returns a tag.
    Modelling only `pos` would tell a client that English ignores POS, and
    they would silently lose accuracy on every ambiguous word.
    """

    pos: bool = False
    pos_accepted: bool = False
    pos_required: bool = False
    candidates: bool = False
    reading: bool = False
    mwt: bool = False
    tokenizes: bool = False

    def to_json(self) -> dict[str, bool]:
        return {
            "pos": self.pos,
            "pos_accepted": self.pos_accepted,
            "pos_required": self.pos_required,
            "candidates": self.candidates,
            "reading": self.reading,
            "mwt": self.mwt,
            "tokenizes": self.tokenizes,
        }


@dataclass(frozen=True)
class LemmaItem:
    surface: str
    lemma: str
    pos: str | None = None
    prov: Prov = "dict"
    reading: str | None = None
    candidates: tuple[str, ...] = ()
    start: int | None = None
    end: int | None = None

    def to_json(self) -> dict:
        out: dict = {
            "surface": self.surface,
            "lemma": self.lemma,
            "pos": self.pos,
            "prov": self.prov,
        }
        if self.reading is not None:
            out["reading"] = self.reading
        if self.candidates:
            out["candidates"] = list(self.candidates)
        # Offsets are omitted only when genuinely unavailable (caller sent
        # `tokens`, so there is no source string to point into).
        if self.start is not None and self.end is not None:
            out["start"] = self.start
            out["end"] = self.end
        return out
