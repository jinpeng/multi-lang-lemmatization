"""The single lemmatize endpoint (spec section 4.1)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Request

from api.errors import ApiError
from api.schemas import LemmatizeRequest, normalize_pos

router = APIRouter()


@router.post("/v1/lemmatize")
def lemmatize(payload: LemmatizeRequest, request: Request) -> dict:
    request_id = f"req_{uuid.uuid4().hex[:20]}"
    request.state.request_id = request_id

    registry = request.app.state.registry
    entry = registry.get(payload.lang)
    if entry is None:
        raise ApiError(
            "UNKNOWN_LANGUAGE",
            400,
            f"unsupported language {payload.lang!r}",
            {"supported": [e.lang for e in registry.all()]},
        )
    if entry.status != "ok" or entry.backend is None:
        raise ApiError(
            "LANGUAGE_UNAVAILABLE",
            503,
            f"backend for {payload.lang!r} failed to initialize",
            {"reason": entry.reason},
        )

    backend = entry.backend

    unknown = set(payload.options) - set(backend.option_specs())
    if unknown:
        raise ApiError(
            "UNKNOWN_OPTION",
            400,
            "unknown option(s) for this language",
            {"unknown": sorted(unknown), "allowed": sorted(backend.option_specs())},
        )

    token_count = len(payload.tokens) if payload.tokens is not None else None
    try:
        pos_list = normalize_pos(payload.pos, token_count)
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc

    if backend.capabilities.pos_required and pos_list is None:
        raise ApiError(
            "INVALID_REQUEST",
            400,
            f"language {payload.lang!r} requires 'pos'",
        )

    started = time.perf_counter()
    try:
        items = backend.lemmatize(
            text=payload.text,
            tokens=payload.tokens,
            pos=pos_list,
            options=payload.options,
        )
    except ValueError as exc:
        raise ApiError("INVALID_REQUEST", 400, str(exc)) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000

    if payload.tokens is not None and not backend.capabilities.tokenizes:
        segmented_by = "input"
    else:
        segmented_by = "backend"

    warnings = [
        {"code": "UNRESOLVED", "surface": item.surface}
        for item in items
        if item.prov == "identity"
    ]

    has_offsets = any(i.start is not None for i in items)

    return {
        "request_id": request_id,
        "offset_unit": "unicode_code_point" if has_offsets else None,
        "lang": payload.lang,
        "backend": {"name": backend.name, "version": backend.version},
        "segmented_by": segmented_by,
        "capabilities": backend.capabilities.to_json(),
        "items": [item.to_json() for item in items],
        "warnings": warnings,
        "elapsed_ms": round(elapsed_ms, 2),
    }
