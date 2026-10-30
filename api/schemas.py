"""Request validation for /v1/lemmatize (spec section 4.1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class LemmatizeRequest(BaseModel):
    lang: str = Field(min_length=2, max_length=8)
    text: str | None = None
    tokens: list[str] | None = None
    pos: list[str | None] | str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> LemmatizeRequest:
        if (self.text is None) == (self.tokens is None):
            raise ValueError("exactly one of 'text' or 'tokens' is required")
        return self


def normalize_pos(
    pos: list[str | None] | str | None, token_count: int | None
) -> list[str | None] | None:
    """Widen a scalar POS to a per-token list, enforcing length agreement.

    `token_count` is None when the caller sent `text` instead of `tokens`: the
    backend may retokenize, so there is nothing to agree against. A scalar is
    then still meaningful ("the whole input is one POS"), but a per-token list
    is not.
    """
    if pos is None:
        return None
    if isinstance(pos, str):
        if token_count == 0:
            raise ValueError("scalar 'pos' requires at least one token")
        return [pos]
    if token_count is None:
        raise ValueError("list 'pos' requires 'tokens'; it cannot be matched against 'text'")
    if len(pos) != token_count:
        raise ValueError(f"'pos' length {len(pos)} does not match token count {token_count}")
    return pos
