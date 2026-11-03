from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.auth.admin import issue_token, verify_passphrase
from api.errors import ApiError

router = APIRouter()


class SessionRequest(BaseModel):
    passphrase: str


@router.post("/admin/session")
def create_session(payload: SessionRequest, request: Request) -> dict:
    if not verify_passphrase(payload.passphrase):
        raise ApiError("UNAUTHORIZED", 401, "invalid passphrase")
    session = issue_token(request.app)
    return {"admin_token": session.token, "expires_at": session.expires_at}
