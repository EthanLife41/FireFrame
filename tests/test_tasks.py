"""Task service: calendar selection and input validation (no macOS needed)."""
import backend.tasks as tasks


def test_looks_like_task_calendar():
    assert tasks._looks_like_task_calendar("Tasks")
    assert tasks._looks_like_task_calendar("My Tasks")
    assert tasks._looks_like_task_calendar("Google Tasks")
    assert not tasks._looks_like_task_calendar("Work")
    assert not tasks._looks_like_task_calendar("")


def test_suggest_prefers_task_like_over_default():
    cals = [
        {"id": "w", "name": "Work", "is_default": True},
        {"id": "t", "name": "My Tasks", "is_default": False},
    ]
    assert tasks._suggest_calendar(cals)["id"] == "t"


def test_suggest_falls_back_to_default_then_first():
    cals = [
        {"id": "a", "name": "Personal", "is_default": False},
        {"id": "b", "name": "Work", "is_default": True},
    ]
    assert tasks._suggest_calendar(cals)["id"] == "b"
    assert tasks._suggest_calendar([{"id": "a", "name": "Personal", "is_default": False}])["id"] == "a"
    assert tasks._suggest_calendar([]) is None


def test_configured_default_calendar_wins(monkeypatch):
    monkeypatch.setattr(tasks, "TASK_DEFAULT_CALENDAR", "Work")
    cals = [
        {"id": "t", "name": "Tasks", "is_default": False},
        {"id": "w", "name": "work", "is_default": False},   # case-insensitive match
    ]
    assert tasks._suggest_calendar(cals)["id"] == "w"


def test_durations_from_config():
    d = tasks._durations()
    assert d[tasks.REGULAR] == 60
    assert d[tasks.IMPORTANT] == 240


def test_parse_start_valid_and_invalid():
    dt = tasks._parse_start("2026-06-23", "14:30")
    assert dt is not None and dt.hour == 14 and dt.minute == 30
    assert tasks._parse_start("not-a-date", "14:30") is None
    assert tasks._parse_start("2026-06-23", "99:99") is None
    assert tasks._parse_start("", "") is None


def _force_available(monkeypatch):
    # Bypass the macOS/EventKit gate so validation runs on any platform.
    monkeypatch.setattr(tasks, "_is_macos", lambda: True)
    monkeypatch.setattr(tasks.calendar_service, "is_eventkit_available", lambda: True)


def test_create_task_rejects_blank_title(monkeypatch):
    _force_available(monkeypatch)
    res = tasks.create_task("   ", "2026-06-23", "14:00", "regular")
    assert res["success"] is False and res["error"] == "invalid_title"


def test_create_task_rejects_bad_importance(monkeypatch):
    _force_available(monkeypatch)
    res = tasks.create_task("Plan", "2026-06-23", "14:00", "urgent")
    assert res["success"] is False and res["error"] == "invalid_importance"


def test_create_task_rejects_bad_datetime(monkeypatch):
    _force_available(monkeypatch)
    res = tasks.create_task("Plan", "nope", "14:00", "regular")
    assert res["success"] is False and res["error"] == "invalid_datetime"


def test_create_task_sizes_block_by_importance(monkeypatch):
    _force_available(monkeypatch)
    captured = {}

    def fake_create(title, start, end, notes, calendar_id):
        captured.update(title=title, start=start, end=end, notes=notes, calendar_id=calendar_id)
        return "EVENT-123"

    monkeypatch.setattr(tasks.calendar_service, "create_event", fake_create)
    res = tasks.create_task("Plan week", "2026-06-23", "14:00", "important",
                            notes="outline", calendar_id="cal-1")
    assert res["success"] is True
    assert res["event_id"] == "EVENT-123"
    assert captured["calendar_id"] == "cal-1"
    # Important = 240 minutes -> a 4-hour block (14:00 to 18:00).
    assert (captured["end"] - captured["start"]).total_seconds() == 240 * 60
