from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import build_registry, create_app


@pytest.fixture
def fake_client():
    """Client with fake backends only - no heavy dictionaries loaded."""
    app = create_app(registry=build_registry(use_fakes=True))
    return TestClient(app)


@pytest.fixture(scope="session")
def real_client():
    """Client with the real 7-language registry. Session-scoped: dictionaries load once."""
    app = create_app()
    with TestClient(app) as client:
        return client
