"""FireFrame Tasks: create scheduled calendar blocks in Apple Calendar.

A FireFrame "task" is a normal Apple Calendar event sized by importance:
Regular books a short block, Important a longer one (both configurable). Events
are written through EventKit, so the title and notes are passed as native
objects, never interpolated into a shell or AppleScript string.

A task lands in a calendar whose name looks like "Tasks" when one exists (so it
syncs wherever that calendar syncs, including a Google account added to
Calendar.app), otherwise the configured TASK_DEFAULT_CALENDAR, otherwise a
calendar the user picks. Reading upcoming tasks reuses the cached calendar
service, so this adds no extra polling.
"""

import platform
import re
import time
from datetime import datetime, timedelta

from backend import calendar_service
from backend.config_loader import (
    TASK_DEFAULT_CALENDAR,
    TASK_REGULAR_DURATION_MINUTES,
    TASK_IMPORTANT_DURATION_MINUTES,
)

REGULAR = "regular"
IMPORTANT = "important"

_NO_EVENTKIT = ("Task creation needs the EventKit reader. Install it with: "
                "pip install pyobjc-framework-EventKit")


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _durations() -> dict:
    def minutes(value, fallback):
        try:
            return max(5, int(value))
        except (TypeError, ValueError):
            return fallback
    return {
        REGULAR: minutes(TASK_REGULAR_DURATION_MINUTES, 60),
        IMPORTANT: minutes(TASK_IMPORTANT_DURATION_MINUTES, 240),
    }


# "task" at a word boundary matches Tasks, Task, My Tasks, Google Tasks, but
# not unrelated names like "Multitasking".
_TASK_NAME_RE = re.compile(r"\btask", re.IGNORECASE)


def _looks_like_task_calendar(name: str) -> bool:
    return bool(_TASK_NAME_RE.search(name or ""))


def _suggest_calendar(calendars: list):
    """Pick the default target: the configured calendar by name, else a
    Tasks-like calendar, else the system default, else the first available."""
    configured = (TASK_DEFAULT_CALENDAR or "").strip().lower()
    if configured:
        for cal in calendars:
            if cal["name"].strip().lower() == configured:
                return cal
    for cal in calendars:
        if _looks_like_task_calendar(cal["name"]):
            return cal
    for cal in calendars:
        if cal.get("is_default"):
            return cal
    return calendars[0] if calendars else None


def _fail(code: str, message: str) -> dict:
    return {"success": False, "error": code, "message": message}


def _parse_start(date_str: str, time_str: str):
    try:
        d = datetime.strptime((date_str or "").strip(), "%Y-%m-%d").date()
        t = datetime.strptime((time_str or "").strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return None
    return datetime(d.year, d.month, d.day, t.hour, t.minute)


def get_config() -> dict:
    """Durations and whether task creation is available on this machine."""
    durations = _durations()
    return {
        "available": _is_macos() and calendar_service.is_eventkit_available(),
        "regular_minutes": durations[REGULAR],
        "important_minutes": durations[IMPORTANT],
        "default_calendar": (TASK_DEFAULT_CALENDAR or "").strip(),
    }


# The writable-calendar list changes rarely, so cache it briefly. This keeps a
# Home refresh (which resolves the target calendar) from re-enumerating
# Calendar.app every time.
_CALENDARS_TTL = 60
_calendars_cache = {"ts": 0.0, "data": None}


def get_calendars(force: bool = False) -> dict:
    """Writable calendars to file tasks into, with the suggested default
    pre-selected. Cached briefly; never raises (issues become a message)."""
    now = time.time()
    cached = _calendars_cache["data"]
    if not force and cached is not None and (now - _calendars_cache["ts"]) < _CALENDARS_TTL:
        return cached
    result = _read_calendars()
    if result.get("available"):
        _calendars_cache.update(ts=now, data=result)
    return result


def _read_calendars() -> dict:
    if not _is_macos():
        return {"available": False, "calendars": [], "suggested_id": None,
                "message": "Tasks are available on macOS only."}
    if not calendar_service.is_eventkit_available():
        return {"available": False, "calendars": [], "suggested_id": None,
                "message": _NO_EVENTKIT}
    try:
        calendars = calendar_service.writable_calendars()
    except PermissionError:
        return {"available": False, "calendars": [], "suggested_id": None,
                "message": calendar_service.PERMISSION_HINT}
    except Exception:
        return {"available": False, "calendars": [], "suggested_id": None,
                "message": "Could not read your calendars."}
    suggested = _suggest_calendar(calendars)
    return {
        "available": True,
        "calendars": calendars,
        "suggested_id": suggested["id"] if suggested else None,
    }


def get_upcoming(limit: int = 3) -> dict:
    """Upcoming task blocks for the Home card: timed events in the suggested
    Tasks calendar over the calendar's look-ahead window. Reuses the cached
    calendar read, so it reflects the Apple source (CALENDAR_SOURCE=apple)."""
    cal_info = get_calendars()
    if not cal_info.get("available"):
        return {"available": False, "tasks": [], "message": cal_info.get("message")}

    target = next((c for c in cal_info["calendars"]
                   if c["id"] == cal_info.get("suggested_id")), None)
    target_name = target["name"] if target else None

    data = calendar_service.get_upcoming()   # cached; honours CALENDAR_SOURCE
    events = data.get("events", [])
    if target_name:
        events = [e for e in events
                  if e.get("calendar") == target_name and not e.get("all_day")]
    return {
        "available": True,
        "calendar": target_name,
        "source": data.get("source"),
        "tasks": events[:max(0, limit)],
    }


def create_task(title: str, date_str: str, time_str: str,
                importance: str = REGULAR, notes: str = "",
                calendar_id: str = "") -> dict:
    """Validate input and create the calendar block. Returns a JSON-friendly
    dict with success, a user-facing message, and the created event id."""
    if not _is_macos():
        return _fail("not_macos", "Tasks can only be created on macOS.")
    if not calendar_service.is_eventkit_available():
        return _fail("no_eventkit", _NO_EVENTKIT)

    title = (title or "").strip()
    if not title:
        return _fail("invalid_title", "A task needs a title.")
    title = title[:200]

    importance = (importance or REGULAR).strip().lower()
    if importance not in (REGULAR, IMPORTANT):
        return _fail("invalid_importance", "Importance must be Regular or Important.")

    start = _parse_start(date_str, time_str)
    if start is None:
        return _fail("invalid_datetime", "Enter a valid date and start time.")

    minutes = _durations()[importance]
    end = start + timedelta(minutes=minutes)
    notes = (notes or "").strip()[:2000]

    try:
        event_id = calendar_service.create_event(
            title=title, start=start, end=end, notes=notes,
            calendar_id=(calendar_id or "").strip(),
        )
    except PermissionError:
        return _fail("permission", calendar_service.PERMISSION_HINT)
    except calendar_service.CalendarWriteError as exc:
        return _fail("write_failed", str(exc))
    except Exception:
        return _fail("write_failed", "Could not create the task in Apple Calendar.")

    return {
        "success": True,
        "message": f"Added '{title}' ({minutes} min).",
        "event_id": event_id,
        "importance": importance,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
