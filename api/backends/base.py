"""The one interface every language adapter implements (spec section 3.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from api.types import Capabilities, LemmaItem


class BaseBackend(ABC):
    lang: str
    name: str
    version: str
    pos_scheme: str | None
    capabilities: Capabilities

    def option_specs(self) -> dict[str, dict]:
        """Request-level options this backend accepts, for /v1/languages."""
        return {}

    @abstractmethod
    def lemmatize(
        self,
        text: str | None,
        tokens: list[str] | None,
        pos: list[str | None] | None,
        options: dict[str, Any],
    ) -> list[LemmaItem]:
        """Return one LemmaItem per output token.

        Always returns a list. Unresolved words come back as
        prov="identity" with lemma == surface - never an exception, because
        one rare word must not fail the whole request.
        """
