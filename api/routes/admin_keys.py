from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.auth.admin import require_admin
from api.auth.deps import master_key
from api.errors import ApiError
from api.store import audit, keys

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] | None = None
    langs: list[str] | None = None
    allow_hmac: bool = False
    rate_limit_rpm: int = Field(default=600, ge=1, le=100_000)
    expires_at: str | None = None


@router.get("/keys")
def list_keys(request: Request) -> dict:
    return {"keys": keys.list_all(request.app.state.db_url)}


@router.post("/keys", status_code=201)
def create_key(payload: CreateKeyRequest, request: Request) -> dict:
    url = request.app.state.db_url
    created = keys.create(
        url,
        name=payload.name,
        created_by="admin",
        master_key=master_key(),
        scopes=payload.scopes,
        langs=payload.langs,
        allow_hmac=payload.allow_hmac,
        rate_limit_rpm=payload.rate_limit_rpm,
        expires_at=payload.expires_at,
    )
    audit.append(
        url,
        actor="admin",
        action="key.create",
        target=created.key_id,
        after={"name": payload.name, "langs": payload.langs},
    )
    return {
        "key_id": created.key_id,
        "secret": created.secret,
        "secret_fingerprint": created.secret_fingerprint,
        "name": created.name,
    }


@router.post("/keys/{key_id}/rotate")
def rotate_key(key_id: str, request: Request) -> dict:
    url = request.app.state.db_url
    try:
        rotated = keys.rotate(url, key_id, master_key=master_key())
    except KeyError as exc:
        raise ApiError("NOT_FOUND", 404, f"no such key {key_id!r}") from exc
    audit.append(url, actor="admin", action="key.rotate", target=key_id)
    return {
        "key_id": rotated.key_id,
        "secret": rotated.secret,
        "secret_fingerprint": rotated.secret_fingerprint,
    }


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(key_id: str, request: Request) -> None:
    url = request.app.state.db_url
    if not keys.revoke(url, key_id, reason="admin revoke", actor="admin"):
        raise ApiError("NOT_FOUND", 404, f"no active key {key_id!r}")
    audit.append(url, actor="admin", action="key.revoke", target=key_id)
