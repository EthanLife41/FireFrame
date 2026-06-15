"""Shared fixtures. Env vars are set before importing backend.* because
config_loader exits when SESSION_SECRET is unset and reads the password at import.
"""
import os

os.environ["SESSION_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ["DASHBOARD_PASSWORD"] = "1234"

import pytest
from starlette.testclient import TestClient

from backend.main import app, _login_attempts


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Clear the global login rate-limiter between tests."""
    _login_attempts.clear()
    yield
    _login_attempts.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """Logged-in client (session cookie set)."""
    resp = client.post("/api/login", json={"password": "1234"})
    assert resp.status_code == 200
    return client
