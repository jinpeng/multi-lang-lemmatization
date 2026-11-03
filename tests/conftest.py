from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.db import init_db
from api.main import build_registry, create_app
from api.store import keys

MASTER = b"0" * 32


@pytest.fixture
def fake_client(tmp_path):
    """Fake backends, auth disabled - exercises routing only."""
    url = f"sqlite:///{tmp_path / 'authless.db'}"
    init_db(url)
    app = create_app(registry=build_registry(use_fakes=True), db_url=url, auth_enabled=False)
    return TestClient(app)


@pytest.fixture(scope="session")
def real_client(tmp_path_factory):
    """Real 7-language registry, auth disabled. Session-scoped: dictionaries load once."""
    url = f"sqlite:///{tmp_path_factory.mktemp('db') / 'authless.db'}"
    init_db(url)
    app = create_app(db_url=url, auth_enabled=False)
    with TestClient(app) as client:
        return client


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    """Real registry, auth ENABLED, with one freshly created key."""
    monkeypatch.setenv("LEMMA_MASTER_KEY", MASTER.hex())
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    init_db(url)
    app = create_app(db_url=url, auth_enabled=True)
    created = keys.create(url, name="test", created_by="test", master_key=MASTER)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {created.key_id}.{created.secret}"
    return client, created
