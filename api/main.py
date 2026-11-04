from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.auth.nonce import SqliteNonceCache
from api.auth.ratelimit import RateLimiter
from api.backends.registry import Registry, lazy
from api.db import default_url, init_db
from api.errors import ApiError
from api.obs.requestlog import RequestLogger, purge_older_than
from api.routes import (
    admin_keys,
    admin_session,
    admin_settings,
    health,
    languages,
    lemmatize,
)

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
            items.append(LemmaItem(surface=surface, lemma=surface.lower(), start=start, end=end))
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


async def _flush_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            app.state.request_log.flush()
        except Exception:  # noqa: BLE001 - logging must never kill the app
            log.warning("request_log flush failed", exc_info=True)


def create_app(
    registry: Registry | None = None,
    *,
    registry_fakes: bool = False,
    db_url: str | None = None,
    auth_enabled: bool | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_flush_loop(app))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            app.state.request_log.flush_all()

    app = FastAPI(title="Lemma API", version="0.3.0", lifespan=lifespan)
    app.state.registry = (
        registry if registry is not None else build_registry(use_fakes=registry_fakes)
    )
    app.state.db_url = db_url or default_url()
    init_db(app.state.db_url)
    app.state.limiter = RateLimiter()
    app.state.nonces = SqliteNonceCache(app.state.db_url)
    app.state.request_log = RequestLogger(app.state.db_url)
    app.state.burst = 60
    purge_older_than(app.state.db_url)

    if auth_enabled is None:
        auth_enabled = os.environ.get("LEMMA_AUTH_ENABLED", "0") == "1"
    if not auth_enabled and os.environ.get("LEMMA_REQUIRE_AUTH") == "1":
        raise RuntimeError("LEMMA_REQUIRE_AUTH=1 but authentication is disabled; refusing to start")
    app.state.auth_enabled = auth_enabled
    if auth_enabled:
        # Fail at boot rather than at the first login attempt: a mangled
        # argon2 hash otherwise looks like "everyone's password is wrong".
        from api.auth.admin import validate_config

        validate_config()

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        headers: dict[str, str] = {}
        # 429 is only actionable if the client knows how long to wait; RFC 6585
        # makes Retry-After optional, but a bare 429 that says nothing forces
        # blind backoff.
        if exc.status == 429 and "retry_after" in exc.details:
            headers["Retry-After"] = str(exc.details["retry_after"])
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_json(getattr(request.state, "request_id", None)),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic failures default to HTTP 422 with a `detail` list.

        That envelope is not ours: spec section 4.4 requires error.code on every
        failure, so a client parsing error.code would break here. Collapse it
        into INVALID_REQUEST / 400 and keep the first field path for diagnosis.
        """
        errors = exc.errors()
        first = errors[0] if errors else {}
        message = str(first.get("msg", "request validation failed"))
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        error = ApiError("INVALID_REQUEST", 400, message, {"field": list(first.get("loc", []))})
        return JSONResponse(
            status_code=400,
            content=error.to_json(getattr(request.state, "request_id", None)),
        )

    @app.middleware("http")
    async def _request_log_middleware(request: Request, call_next):
        started = time.perf_counter()

        # Assign the id here, not in the route. Authentication runs as a
        # dependency before the handler, so a 401 raised by auth would
        # otherwise carry request_id=null and could not be correlated with its
        # own log row.
        request.state.request_id = f"req_{uuid.uuid4().hex[:20]}"

        # HMAC verification needs the exact bytes the client sent, and Starlette
        # discards the stream once the body is parsed. Cache it here, before any
        # route or dependency reads it, so the auth dependency can re-hash it.
        # Skipped for bodies above the limit: those are rejected anyway, and
        # buffering them would be a memory amplification vector.
        if request.headers.get("X-Signature"):
            raw = await request.body()
            request.state.body_bytes = raw

        try:
            response = await call_next(request)
        except Exception:
            request.app.state.request_log.record(
                request_id=getattr(request.state, "request_id", "-"),
                key_id=getattr(getattr(request.state, "key", None), "key_id", None),
                lang=None,
                n_tokens=None,
                bytes_in=len(getattr(request.state, "body_bytes", b"") or b""),
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=500,
                error_code="INTERNAL",
                ip=request.client.host if request.client else None,
            )
            raise

        key = getattr(request.state, "key", None)
        request.app.state.request_log.record(
            request_id=getattr(request.state, "request_id", "-"),
            key_id=key.key_id if key else None,
            lang=getattr(request.state, "lang", None),
            n_tokens=getattr(request.state, "n_tokens", None),
            bytes_in=len(getattr(request.state, "body_bytes", b"") or b""),
            latency_ms=int((time.perf_counter() - started) * 1000),
            status=response.status_code,
            error_code=getattr(request.state, "error_code", None),
            ip=request.client.host if request.client else None,
        )
        response.headers["X-Request-Id"] = getattr(request.state, "request_id", "-")
        return response

    app.include_router(health.router)
    app.include_router(languages.router)
    app.include_router(admin_session.router)
    app.include_router(admin_keys.router)
    app.include_router(admin_settings.router)
    app.include_router(lemmatize.router)
    return app


app = create_app()
