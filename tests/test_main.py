"""Endpoint auth, login, and lockout behavior via the TestClient."""
import backend.main as main


PROTECTED_GET = ["/api/me", "/api/status", "/api/stats", "/api/settings",
                 "/api/calendar/today", "/api/photos", "/api/bluetooth/status",
                 "/api/tasks/config", "/api/tasks/calendars", "/api/tasks/upcoming"]


def test_protected_endpoints_require_a_session(client):
    for path in PROTECTED_GET:
        assert client.get(path).status_code == 401, f"{path} should require auth"


def test_action_endpoint_requires_a_session(client):
    assert client.post("/api/action", json={"action": "mute"}).status_code == 401


def test_task_create_requires_a_session(client):
    body = {"title": "x", "date": "2026-06-23", "time": "14:00"}
    assert client.post("/api/tasks/create", json=body).status_code == 401


def test_task_management_routes_require_a_session(client):
    assert client.post("/api/tasks/delete", json={"event_id": "x"}).status_code == 401
    assert client.post("/api/tasks/reschedule",
                       json={"event_id": "x", "date": "2026-06-23", "time": "14:00"}).status_code == 401
    assert client.post("/api/tasks/prompt").status_code == 401
    assert client.post("/api/tasks/config", json={"input_location": "dashboard"}).status_code == 401


def test_login_with_wrong_password_is_401_and_counts_down(client):
    resp = client.post("/api/login", json={"password": "wrong"})
    assert resp.status_code == 401
    assert "attempt(s) remaining" in resp.json()["detail"]


def test_login_success_sets_session_and_unlocks_endpoints(client):
    resp = client.post("/api/login", json={"password": "1234"})
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    assert "session" in resp.cookies
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"logged_in": True}


def test_logout_clears_the_session(auth_client):
    assert auth_client.get("/api/me").status_code == 200
    assert auth_client.post("/api/logout").status_code == 200
    assert auth_client.get("/api/me").status_code == 401


def test_repeated_failures_trigger_a_lockout(client):
    for _ in range(main.MAX_ATTEMPTS - 1):
        assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    locked = client.post("/api/login", json={"password": "wrong"})
    assert locked.status_code == 429
    # locked out: even the right password is refused
    assert client.post("/api/login", json={"password": "1234"}).status_code == 429


def test_lockout_clears_after_the_window(client, monkeypatch):
    for _ in range(main.MAX_ATTEMPTS):
        client.post("/api/login", json={"password": "wrong"})
    assert client.post("/api/login", json={"password": "1234"}).status_code == 429

    # skip past the lockout window instead of sleeping
    real_time = main.time.time
    monkeypatch.setattr(main.time, "time",
                        lambda: real_time() + main.LOCKOUT_SECONDS + 1)
    assert client.post("/api/login", json={"password": "1234"}).status_code == 200
