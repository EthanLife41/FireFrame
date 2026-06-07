"""Calendar service — macOS-first, pluggable source.

The source is chosen with the ``CALENDAR_SOURCE`` env var (see config.example.py):

    none   - nothing configured (default). UI shows "Calendar not connected".
    demo   - built-in placeholder events (good for UI testing).
    ics     - parse a local .ics file at CALENDAR_ICS_PATH (no extra deps).
    apple  - read Apple Calendar via osascript/JXA (needs Automation permission).

Real integration is intentionally behind a clean interface so the frontend and
routes are ready for live data. No event details are ever logged, and no
credentials/tokens/paths are stored in the repo.
"""

import json
import platform
import subprocess
import time
from datetime import datetime, timedelta, timezone

from backend.config_loader import (
    CALENDAR_SOURCE,
    CALENDAR_ICS_PATH,
    CALENDAR_UPCOMING_DAYS,
)
from backend.calendar_stub import get_placeholder_events

_CACHE_TTL_SECONDS = 60
_cache = {"ts": 0.0, "payload": None}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_local_naive(dt: datetime) -> datetime:
    """Normalise to naive local time so all comparisons are apples-to-apples."""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _parse_iso(value: str):
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _to_local_naive(datetime.fromisoformat(text))
    except ValueError:
        return None


def _shape(events: list) -> list:
    """Sort by start and keep a clean, serialisable shape."""
    cleaned = []
    for ev in events:
        start = _parse_iso(ev.get("start", ""))
        if start is None:
            continue
        end = _parse_iso(ev.get("end", "")) or start
        cleaned.append(
            {
                "id": str(ev.get("id", "")) or None,
                "title": (ev.get("title") or "Untitled").strip(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "location": (ev.get("location") or "").strip(),
                "_start_dt": start,
            }
        )
    cleaned.sort(key=lambda e: e["_start_dt"])
    return cleaned


# ---------------------------------------------------------------------------
# Source: ICS
# ---------------------------------------------------------------------------
def _ics_datetime(prop: str, value: str):
    value = value.strip()
    params = prop.upper()
    try:
        if "VALUE=DATE" in params and "T" not in value:
            return datetime.strptime(value, "%Y%m%d").isoformat()
        if value.endswith("Z"):
            return (
                datetime.strptime(value, "%Y%m%dT%H%M%SZ")
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        return datetime.strptime(value, "%Y%m%dT%H%M%S").isoformat()
    except ValueError:
        return None


def _parse_ics(path: str) -> list:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()

    # Unfold RFC 5545 line continuations (lines beginning with space/tab).
    lines = []
    for line in raw.splitlines():
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)

    events, cur = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            prop, val = line.split(":", 1)
            name = prop.split(";", 1)[0].upper()
            if name == "SUMMARY":
                cur["title"] = val.strip()
            elif name == "LOCATION":
                cur["location"] = val.strip()
            elif name == "UID":
                cur["id"] = val.strip()
            elif name == "DTSTART":
                cur["start"] = _ics_datetime(prop, val)
            elif name == "DTEND":
                cur["end"] = _ics_datetime(prop, val)
    return events


# ---------------------------------------------------------------------------
# Source: Apple Calendar via JXA
# ---------------------------------------------------------------------------
_JXA_TEMPLATE = """
(() => {
  const Cal = Application("Calendar");
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const end = new Date(start.getTime() + %d * 86400000);
  const out = [];
  let cals;
  try { cals = Cal.calendars(); } catch (e) { return "[]"; }
  for (let i = 0; i < cals.length; i++) {
    let evs;
    try {
      evs = cals[i].events.whose({ _and: [
        { startDate: { _greaterThan: start } },
        { startDate: { _lessThan: end } }
      ]})();
    } catch (e) { continue; }
    for (let j = 0; j < evs.length; j++) {
      try {
        out.push({
          title: evs[j].summary(),
          start: evs[j].startDate().toISOString(),
          end: evs[j].endDate().toISOString(),
          location: evs[j].location() || ""
        });
      } catch (e) {}
    }
  }
  return JSON.stringify(out);
})()
"""


def _query_apple_calendar() -> list:
    days = max(1, int(CALENDAR_UPCOMING_DAYS))
    script = _JXA_TEMPLATE % days
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        timeout=30,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        # Most common cause: Automation permission not granted yet.
        raise RuntimeError("apple_calendar_unavailable")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Load + cache
# ---------------------------------------------------------------------------
def _load() -> dict:
    source = (CALENDAR_SOURCE or "none").strip().lower()

    if source == "demo":
        return {"connected": True, "source": "demo", "error": None,
                "events": _shape(get_placeholder_events())}

    if source == "ics":
        if not CALENDAR_ICS_PATH:
            return {"connected": False, "source": "ics", "error": "no_path",
                    "events": [], "message": "CALENDAR_ICS_PATH is not set."}
        try:
            return {"connected": True, "source": "ics", "error": None,
                    "events": _shape(_parse_ics(CALENDAR_ICS_PATH))}
        except FileNotFoundError:
            return {"connected": False, "source": "ics", "error": "file_not_found",
                    "events": [], "message": "ICS file not found."}
        except Exception:
            return {"connected": False, "source": "ics", "error": "parse_failed",
                    "events": [], "message": "Could not read the ICS file."}

    if source == "apple":
        if platform.system() != "Darwin":
            return {"connected": False, "source": "apple", "error": "not_macos",
                    "events": [], "message": "Apple Calendar is only available on macOS."}
        try:
            return {"connected": True, "source": "apple", "error": None,
                    "events": _shape(_query_apple_calendar())}
        except subprocess.TimeoutExpired:
            return {"connected": False, "source": "apple", "error": "timeout",
                    "events": [], "message": "Apple Calendar query timed out."}
        except FileNotFoundError:
            return {"connected": False, "source": "apple", "error": "no_osascript",
                    "events": [], "message": "osascript is not available."}
        except Exception:
            return {"connected": False, "source": "apple", "error": "unavailable",
                    "events": [],
                    "message": "Could not read Apple Calendar. Grant Automation "
                               "permission (System Settings > Privacy & Security > "
                               "Automation) or use an ICS file."}

    # Default: nothing configured.
    return {"connected": False, "source": "none", "error": None, "events": [],
            "message": "Calendar not connected. Set CALENDAR_SOURCE to enable it."}


def _cached() -> dict:
    now = time.time()
    if _cache["payload"] is None or (now - _cache["ts"]) > _CACHE_TTL_SECONDS:
        _cache["payload"] = _load()
        _cache["ts"] = now
    return _cache["payload"]


def _public(events: list) -> list:
    """Strip internal fields before returning to the API."""
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]


# ---------------------------------------------------------------------------
# Public API (used by routes)
# ---------------------------------------------------------------------------
def get_upcoming() -> dict:
    data = _cached()
    days = max(1, int(CALENDAR_UPCOMING_DAYS))
    now = datetime.now()
    horizon = now + timedelta(days=days)
    upcoming = [e for e in data["events"]
                if e["_start_dt"] >= now.replace(hour=0, minute=0, second=0, microsecond=0)
                and e["_start_dt"] <= horizon]
    return {
        "connected": data["connected"],
        "source": data["source"],
        "error": data.get("error"),
        "message": data.get("message"),
        "events": _public(upcoming[:25]),
    }


def get_today() -> dict:
    data = _cached()
    today = datetime.now().date()
    todays = [e for e in data["events"] if e["_start_dt"].date() == today]
    return {
        "connected": data["connected"],
        "source": data["source"],
        "error": data.get("error"),
        "message": data.get("message"),
        "events": _public(todays),
    }


def refresh_calendar() -> dict:
    _cache["payload"] = None
    _cache["ts"] = 0.0
    return get_upcoming()
