from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.auth.admin import require_admin
from api.errors import ApiError
from api.obs import requestlog
from api.store import audit, settings

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class PatchSettingRequest(BaseModel):
    key: str
    value: object


@router.get("/settings")
def read_settings(request: Request) -> dict:
    return {"settings": settings.get_all(request.app.state.db_url)}


@router.patch("/settings")
def patch_setting(payload: PatchSettingRequest, request: Request) -> dict:
    url = request.app.state.db_url
    try:
        value = settings.set_value(url, payload.key, payload.value, actor="admin")
    except KeyError as exc:
        raise ApiError("INVALID_SETTING", 400, str(exc)) from exc
    except ValueError as exc:
        raise ApiError("INVALID_SETTING", 400, str(exc)) from exc
    return {"key": payload.key, "value": value, "hot": settings.is_hot(payload.key)}


@router.get("/audit")
def read_audit(request: Request, limit: int = 50, offset: int = 0) -> dict:
    return {"entries": audit.list_entries(request.app.state.db_url, limit, offset)}


@router.get("/requests")
def recent_requests(request: Request, limit: int = 100, offset: int = 0) -> dict:
    """Request shapes only - never text. See api/obs/requestlog.py."""
    return {"requests": requestlog.recent(request.app.state.db_url, limit, offset)}


@router.get("/diagnostics")
def diagnostics(request: Request) -> dict:
    """Read-only. Never PATCHable, so the console cannot brick the service."""
    registry = request.app.state.registry
    return {
        "backends": {
            e.lang: {
                "status": e.status,
                "backend": e.backend.name if e.backend else None,
                "version": e.backend.version if e.backend else None,
                "reason": e.reason,
            }
            for e in registry.all()
        },
        "master_key": "set" if os.environ.get("LEMMA_MASTER_KEY") else "unset",
        "service_token": "set" if os.environ.get("LEMMA_SERVICE_TOKEN") else "unset",
        "db_url_kind": "sqlite",
    }
