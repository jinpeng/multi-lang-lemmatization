from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CreatedKey:
    """Returned once, at creation/rotation time. Carries the only plaintext copy."""

    key_id: str
    secret: str
    secret_fingerprint: str
    name: str


@dataclass
class ResolvedKey:
    """What auth hands to a route. Never contains the secret."""

    key_id: str
    name: str
    scopes: list[str] = field(default_factory=list)
    langs: list[str] = field(default_factory=list)
    allow_hmac: bool = False
    rate_limit_rpm: int = 600

    def allows_lang(self, lang: str) -> bool:
        return not self.langs or lang in self.langs

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
