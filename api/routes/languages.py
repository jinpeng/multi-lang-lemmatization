from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/languages")
def languages(request: Request) -> dict:
    registry = request.app.state.registry
    out = []
    for entry in registry.all():
        backend = entry.backend
        out.append(
            {
                "lang": entry.lang,
                "status": entry.status,
                "backend": (
                    {"name": backend.name, "version": backend.version}
                    if backend
                    else None
                ),
                "reason": entry.reason,
                "pos_scheme": backend.pos_scheme if backend else None,
                "capabilities": (
                    backend.capabilities.to_json()
                    if backend
                    else {
                        "pos": False, "pos_accepted": False, "pos_required": False,
                        "candidates": False, "reading": False, "mwt": False,
                        "tokenizes": False,
                    }
                ),
                "options": backend.option_specs() if backend else {},
            }
        )
    return {"languages": out}
