from __future__ import annotations

import json
from datetime import UTC, datetime

from api.db import session
from api.settings.registry import EDITABLE, defaults, validate
from api.store import audit


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stored(url: str) -> dict[str, object]:
    with session(url) as conn:
        rows = conn.exec_driver_sql("SELECT key, value_json FROM settings").all()
    return {k: json.loads(v) for k, v in rows}


def effective(url: str) -> dict[str, object]:
    """Defaults overlaid with whatever has been persisted."""
    merged = defaults()
    for name, value in _stored(url).items():
        if name in EDITABLE:
            merged[name] = value
    return merged


def get_all(url: str) -> list[dict]:
    stored = _stored(url)
    out = []
    for name, spec in EDITABLE.items():
        out.append(
            {
                "key": name,
                "value": stored.get(name, spec.default),
                "default": spec.default,
                "kind": spec.kind,
                "hot": spec.hot,
                "min": spec.min,
                "max": spec.max,
                "values": list(spec.values),
                "overridden": name in stored,
            }
        )
    return out


def set_value(url: str, name: str, value: object, *, actor: str) -> object:
    coerced = validate(name, value)
    before = _stored(url).get(name, EDITABLE[name].default)

    with session(url) as conn:
        conn.exec_driver_sql(
            """INSERT INTO settings (key, value_json, updated_at, updated_by)
               VALUES (?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 value_json = excluded.value_json,
                 updated_at = excluded.updated_at,
                 updated_by = excluded.updated_by""",
            (name, json.dumps(coerced), _now(), actor),
        )
    audit.append(
        url,
        actor=actor,
        action="settings.update",
        target=name,
        before=before,
        after=coerced,
    )
    return coerced


def is_hot(name: str) -> bool:
    return EDITABLE[name].hot
