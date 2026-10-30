"""Single error envelope used by every route (spec section 4.4)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApiError(Exception):
    code: str
    status: int
    message: str
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_json(self, request_id: str | None) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }
