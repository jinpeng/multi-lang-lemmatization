"""The settings whitelist.

Inclusion rule: a wrong value may degrade quality, cost more CPU, or refuse more
requests - it must never make the service fail to start or the console fail to
reach the API. That is why model paths, the database URL and the master key are
absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Spec:
    kind: str
    hot: bool
    default: Any
    min: int | None = None
    max: int | None = None
    values: tuple[str, ...] = field(default_factory=tuple)


ALL_LANGS = ["en", "de", "fr", "es", "ru", "ja", "ko"]

EDITABLE: dict[str, Spec] = {
    "langs.enabled": Spec(kind="lang_set", hot=True, default=ALL_LANGS),
    "langs.de.greedy": Spec(kind="bool", hot=True, default=True),
    "langs.fr.greedy": Spec(kind="bool", hot=True, default=False),
    "langs.es.greedy": Spec(kind="bool", hot=True, default=False),
    "langs.ja.split_mode": Spec(kind="enum", hot=True, default="C", values=("A", "B", "C")),
    "langs.ko.model_type": Spec(kind="enum", hot=False, default="cong", values=("cong", "knlm")),
    "ratelimit.default_rpm": Spec(kind="int", hot=True, default=600, min=1, max=100_000),
    "ratelimit.burst": Spec(kind="int", hot=True, default=60, min=1, max=10_000),
    "request.max_tokens": Spec(kind="int", hot=True, default=5000, min=1, max=100_000),
    "request.max_body_bytes": Spec(
        kind="int", hot=True, default=1_048_576, min=1024, max=16_777_216
    ),
}


def validate(name: str, value: Any) -> Any:
    """Coerce and range-check one value, or raise."""
    if name not in EDITABLE:
        raise KeyError(f"{name!r} is not editable")
    spec = EDITABLE[name]

    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean")
        return value

    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if spec.min is not None and value < spec.min:
            raise ValueError(f"{name} must be >= {spec.min}")
        if spec.max is not None and value > spec.max:
            raise ValueError(f"{name} must be <= {spec.max}")
        return value

    if spec.kind == "enum":
        if value not in spec.values:
            raise ValueError(f"{name} must be one of {list(spec.values)}")
        return value

    if spec.kind == "lang_set":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{name} must be a list of language codes")
        unknown = set(value) - set(ALL_LANGS)
        if unknown:
            raise ValueError(f"{name} contains unknown languages {sorted(unknown)}")
        return value

    raise ValueError(f"unknown spec kind {spec.kind!r}")


def defaults() -> dict[str, Any]:
    return {name: spec.default for name, spec in EDITABLE.items()}
