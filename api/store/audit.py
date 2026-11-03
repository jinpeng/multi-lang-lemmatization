from __future__ import annotations

import json
from datetime import UTC, datetime

from api.db import session


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(
    url: str,
    *,
    actor: str,
    action: str,
    target: str,
    before: object = None,
    after: object = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> None:
    with session(url) as conn:
        conn.exec_driver_sql(
            """INSERT INTO audit_log
               (at, actor, action, target, before_json, after_json, request_id, ip)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                _now(),
                actor,
                action,
                target,
                None if before is None else json.dumps(before),
                None if after is None else json.dumps(after),
                request_id,
                ip,
            ),
        )


def list_entries(url: str, limit: int = 50, offset: int = 0) -> list[dict]:
    with session(url) as conn:
        rows = (
            conn.exec_driver_sql(
                """SELECT id, at, actor, action, target, before_json, after_json,
                          request_id, ip
                   FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]
