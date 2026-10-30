from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.backends.registry import Registry, lazy
from api.errors import ApiError
from api.routes import health, languages, lemmatize

log = logging.getLogger(__name__)


class _FakeBackend:
    """Test double used when build_registry(use_fakes=True)."""

    pos_scheme = None

    def __init__(self, lang: str) -> None:
        from api.types import Capabilities

        self.lang = lang
        self.name = "fake"
        self.version = "0.0.0"
        self.capabilities = Capabilities()

    def option_specs(self) -> dict:
        return {}

    def lemmatize(self, text, tokens, pos, options):
        from api.types import LemmaItem

        # Mirrors the real backends' contract: offsets when we tokenized the
        # text ourselves, none when the caller supplied tokens.
        if tokens is not None:
            return [LemmaItem(surface=t, lemma=t.lower()) for t in tokens]

        items = []
        cursor = 0
        for surface in (text or "").split():
            start = (text or "").find(surface, cursor)
            end = start + len(surface)
            cursor = end
            items.append(
                LemmaItem(surface=surface, lemma=surface.lower(), start=start, end=end)
            )
        return items


def build_registry(use_fakes: bool = False) -> Registry:
    registry = Registry()
    if use_fakes:
        for lang in ("en", "de", "fr", "es", "ru", "ja", "ko"):
            registry.register(lang, lambda lang=lang: _FakeBackend(lang))
        return registry

    # Every backend is registered through `lazy` so a missing package degrades
    # one language instead of raising ImportError out of build_registry.
    registry.register("en", lazy("api.backends.lemminflect_backend"))
    for lang in ("de", "fr", "es"):
        registry.register(lang, lazy("api.backends.simplemma_backend", lang))
    registry.register("ru", lazy("api.backends.pymorphy_backend"))
    registry.register("ja", lazy("api.backends.sudachi_backend"))
    registry.register("ko", lazy("api.backends.kiwi_backend"))
    return registry


def create_app(registry: Registry | None = None) -> FastAPI:
    app = FastAPI(title="Lemma API", version="0.1.0")
    app.state.registry = registry if registry is not None else build_registry()

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_json(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic failures default to HTTP 422 with a `detail` list.

        That envelope is not ours: spec section 4.4 requires error.code on every
        failure, so a client parsing error.code would break here. Collapse it
        into INVALID_REQUEST / 400 and keep the first field path for diagnosis.
        """
        errors = exc.errors()
        first = errors[0] if errors else {}
        message = str(first.get("msg", "request validation failed"))
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        error = ApiError(
            "INVALID_REQUEST", 400, message, {"field": list(first.get("loc", []))}
        )
        return JSONResponse(
            status_code=400,
            content=error.to_json(getattr(request.state, "request_id", None)),
        )

    app.include_router(health.router)
    app.include_router(languages.router)
    app.include_router(lemmatize.router)
    return app


app = create_app()
