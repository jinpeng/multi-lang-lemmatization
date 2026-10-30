from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/health")
def health(request: Request) -> dict:
    registry = request.app.state.registry
    entries = registry.all()
    return {
        "status": "ok" if any(e.status == "ok" for e in entries) else "degraded",
        "backends": {
            e.lang: {
                "status": e.status,
                "backend": e.backend.name if e.backend else None,
                "reason": e.reason,
            }
            for e in entries
        },
    }
