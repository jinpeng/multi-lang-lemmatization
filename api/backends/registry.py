"""Builds every backend at startup, degrading per language rather than crashing.

Decision 2 puts all 7 languages in one image, so "unavailable" should be rare.
This exists for real failures: a stripped dictionary, a model that fails to
load, out-of-memory on a constrained host, or a backend package that is not
installed in this environment.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from api.backends.base import BaseBackend

log = logging.getLogger(__name__)


@dataclass
class Entry:
    lang: str
    backend: BaseBackend | None
    status: str  # "ok" | "unavailable"
    reason: str | None = None


def lazy(module_name: str, *args, **kwargs) -> Callable[[], BaseBackend]:
    """Defer both the import and the construction into the factory.

    This must be lazy. A module-level `from api.backends import kiwi_backend`
    would raise ImportError while assembling the language list, which is
    outside every try/except and therefore crashes startup for all seven
    languages instead of degrading one. Import inside the closure so the
    failure lands where Registry.register can catch it.
    """

    def factory() -> BaseBackend:
        module = importlib.import_module(module_name)
        return module.build(*args, **kwargs)

    return factory


class Registry:
    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}

    def register(self, lang: str, factory: Callable[[], BaseBackend]) -> None:
        try:
            backend = factory()
        except Exception as exc:  # noqa: BLE001 - degrade, never propagate
            log.warning("backend %s unavailable: %s", lang, exc)
            self._entries[lang] = Entry(
                lang=lang,
                backend=None,
                status="unavailable",
                reason=f"{type(exc).__name__}: {exc}",
            )
            return
        self._entries[lang] = Entry(lang=lang, backend=backend, status="ok")
        log.info("backend %s ready (%s %s)", lang, backend.name, backend.version)

    def get(self, lang: str) -> Entry | None:
        return self._entries.get(lang)

    def all(self) -> list[Entry]:
        return [self._entries[k] for k in sorted(self._entries)]
