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

import json
import platform
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta

from backend import calendar_service
from backend.config_loader import (
    TASK_DEFAULT_CALENDAR,
    TASK_REGULAR_DURATION_MINUTES,
    TASK_IMPORTANT_DURATION_MINUTES,
    TASK_INPUT_LOCATION,
)

REGULAR = "regular"
IMPORTANT = "important"
VALID_INPUT_LOCATIONS = ("dashboard", "mac_prompt")

_NO_EVENTKIT = ("Task creation needs the EventKit reader. Install it with: "
                "pip install pyobjc-framework-EventKit")

# Runtime override for where Add Task collects input. Starts from the env
# default; Settings can flip it for the running server (set TASK_INPUT_LOCATION
# in .env for a persistent default).
_input_location = TASK_INPUT_LOCATION if TASK_INPUT_LOCATION in VALID_INPUT_LOCATIONS else "dashboard"


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
    """Durations, the input-location setting, and whether tasks are available."""
    durations = _durations()
    available = _is_macos() and calendar_service.is_eventkit_available()
    return {
        "available": available,
        "regular_minutes": durations[REGULAR],
        "important_minutes": durations[IMPORTANT],
        "default_calendar": (TASK_DEFAULT_CALENDAR or "").strip(),
        "input_location": _input_location,
        "mac_prompt_supported": available and shutil.which("osascript") is not None,
    }


def set_input_location(value: str) -> dict:
    """Flip where Add Task collects input for the running server."""
    global _input_location
    value = (value or "").strip().lower()
    if value not in VALID_INPUT_LOCATIONS:
        return _fail("invalid_location", "Input location must be dashboard or mac_prompt.")
    if value == "mac_prompt" and not _is_macos():
        return _fail("not_macos", "Mac prompt mode is available on macOS only.")
    _input_location = value
    return {"success": True, "input_location": _input_location}


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

    limit = max(0, min(int(limit), 50))
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
        "tasks": events[:limit],
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


def _task_calendar_names() -> set:
    """Lowercased names of calendars FireFrame treats as task calendars — the
    allowlist for delete/reschedule, so events in other calendars are untouched."""
    names = set()
    info = get_calendars()
    if info.get("available"):
        suggested_id = info.get("suggested_id")
        for cal in info["calendars"]:
            if _looks_like_task_calendar(cal["name"]) or cal["id"] == suggested_id:
                names.add(cal["name"].strip().lower())
    configured = (TASK_DEFAULT_CALENDAR or "").strip().lower()
    if configured:
        names.add(configured)
    return names


def delete_task(event_id: str) -> dict:
    if not _is_macos():
        return _fail("not_macos", "Tasks can only be managed on macOS.")
    if not calendar_service.is_eventkit_available():
        return _fail("no_eventkit", _NO_EVENTKIT)
    event_id = (event_id or "").strip()
    if not event_id:
        return _fail("invalid_id", "Missing task id.")
    names = _task_calendar_names()
    if not names:
        return _fail("unavailable", "Could not read your task calendars. Try again.")
    try:
        calendar_service.delete_event(event_id, names)
    except PermissionError:
        return _fail("permission", calendar_service.PERMISSION_HINT)
    except calendar_service.CalendarWriteError as exc:
        return _fail("delete_failed", str(exc))
    except Exception:
        return _fail("delete_failed", "Could not delete the task.")
    return {"success": True, "message": "Task deleted."}


def reschedule_task(event_id: str, date_str: str, time_str: str,
                    importance: str = REGULAR) -> dict:
    if not _is_macos():
        return _fail("not_macos", "Tasks can only be managed on macOS.")
    if not calendar_service.is_eventkit_available():
        return _fail("no_eventkit", _NO_EVENTKIT)
    event_id = (event_id or "").strip()
    if not event_id:
        return _fail("invalid_id", "Missing task id.")
    importance = (importance or REGULAR).strip().lower()
    if importance not in (REGULAR, IMPORTANT):
        return _fail("invalid_importance", "Importance must be Regular or Important.")
    start = _parse_start(date_str, time_str)
    if start is None:
        return _fail("invalid_datetime", "Enter a valid date and start time.")
    minutes = _durations()[importance]
    end = start + timedelta(minutes=minutes)
    names = _task_calendar_names()
    if not names:
        return _fail("unavailable", "Could not read your task calendars. Try again.")
    try:
        calendar_service.reschedule_event(event_id, start, end, names)
    except PermissionError:
        return _fail("permission", calendar_service.PERMISSION_HINT)
    except calendar_service.CalendarWriteError as exc:
        return _fail("reschedule_failed", str(exc))
    except Exception:
        return _fail("reschedule_failed", "Could not reschedule the task.")
    return {"success": True, "message": f"Rescheduled ({minutes} min).",
            "start": start.isoformat(), "end": end.isoformat(), "importance": importance}


# --- Mac prompt mode: collect a task via native dialogs on the Mac ----------
# The only value placed into the script is a server-generated timestamp (the
# prefilled start time). The user's answers come back over stdout and are
# validated before reaching EventKit; no user input is interpolated into the
# script or a shell.

_MAC_PROMPT_JXA = """
(() => {
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  let title;
  try {
    title = app.displayDialog("New task — title:", {
      defaultAnswer: "", buttons: ["Cancel", "Next"], defaultButton: "Next"
    }).textReturned;
  } catch (e) { return "CANCEL"; }
  title = (title || "").trim();
  if (!title) return "CANCEL";
  let importance;
  try {
    const r = app.chooseFromList(["Regular", "Important"], {
      defaultItems: ["Regular"], withPrompt: "Importance:"
    });
    if (r === false) return "CANCEL";
    importance = r[0];
  } catch (e) { return "CANCEL"; }
  let when;
  try {
    when = app.displayDialog("Start time (YYYY-MM-DD HH:MM):", {
      defaultAnswer: "__PREFILL__", buttons: ["Cancel", "Next"], defaultButton: "Next"
    }).textReturned;
  } catch (e) { return "CANCEL"; }
  let notes = "";
  try {
    notes = app.displayDialog("Notes (optional):", {
      defaultAnswer: "", buttons: ["Skip", "Add"], defaultButton: "Add"
    }).textReturned;
  } catch (e) { notes = ""; }
  return JSON.stringify({ title: title, importance: importance, when: when, notes: notes });
})()
"""

_NOTIFY_RE = re.compile(r"[^A-Za-z0-9 .:,_-]+")


def prompt_on_mac() -> dict:
    """Start the native Mac dialog flow in a background thread, so the request
    returns immediately and the server never blocks while the dialogs are open."""
    if not _is_macos():
        return _fail("not_macos", "Mac prompt is available on macOS only.")
    if not calendar_service.is_eventkit_available():
        return _fail("no_eventkit", _NO_EVENTKIT)
    if shutil.which("osascript") is None:
        return _fail("no_osascript", "osascript is not available on this Mac.")
    threading.Thread(target=_run_mac_prompt, daemon=True).start()
    return {"success": True, "message": "Finish adding the task on your Mac."}


def _run_mac_prompt() -> None:
    try:
        data = _ask_mac_for_task()
    except Exception:
        return
    if data is None:
        return   # cancelled, or a dialog already reported the problem
    try:
        calendar_service.create_event(title=data["title"], start=data["start"],
                                      end=data["end"], notes=data["notes"], calendar_id="")
        _notify_mac("Task added.")
    except Exception:
        _notify_mac("Could not add the task. Check Calendar access.")


def _ask_mac_for_task():
    # Default to 7 PM today; the user can edit it in the prompt.
    prefill = datetime.now().replace(hour=19, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
    script = _MAC_PROMPT_JXA.replace("__PREFILL__", prefill)
    proc = subprocess.run(["osascript", "-l", "JavaScript", "-e", script],
                          capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out or out == "CANCEL":
        return None
    try:
        raw = json.loads(out)
    except ValueError:
        return None
    title = (raw.get("title") or "").strip()[:200]
    if not title:
        return None
    importance = (raw.get("importance") or REGULAR).strip().lower()
    if importance not in (REGULAR, IMPORTANT):
        importance = REGULAR
    try:
        start = datetime.strptime((raw.get("when") or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        _notify_mac("Task not added: couldn't read the date and time.")
        return None
    minutes = _durations()[importance]
    return {"title": title, "start": start, "end": start + timedelta(minutes=minutes),
            "notes": (raw.get("notes") or "").strip()[:2000]}


def _notify_mac(message: str) -> None:
    msg = _NOTIFY_RE.sub("", message)[:120]
    script = ("on run argv\n"
              '  display notification (item 1 of argv) with title "FireFrame"\n'
              "end run")
    try:
        subprocess.run(["osascript", "-e", script, msg], capture_output=True, timeout=6)
    except Exception:
        pass
