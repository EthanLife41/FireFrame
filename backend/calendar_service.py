"""Calendar service with a pluggable source, selected by CALENDAR_SOURCE:

    none   nothing configured (default); the UI shows "not connected"
    demo   built-in placeholder events, handy for testing the UI
    ics    one or more local .ics files, or an https URL (CALENDAR_ICS_PATH /
           CALENDAR_ICS_PATHS)
    apple  Apple Calendar via osascript/JXA, reading every accessible calendar
           (needs Automation permission)

Events for the surrounding window are fetched once and cached, so day/week
navigation filters in memory instead of re-running osascript. Refreshes are the
only thing that forces a new read. Event details are never logged.
"""

import hashlib
import json
import os
import platform
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from backend.config_loader import (
    CALENDAR_SOURCE,
    CALENDAR_ICS_PATH,
    CALENDAR_ICS_PATHS,
    CALENDAR_UPCOMING_DAYS,
    CALENDAR_REFRESH_SECONDS,
)
from backend.calendar_stub import get_placeholder_events

# One in-memory window of events, plus the metadata for the current source.
_cache = {"start": None, "end": None, "events": None, "ts": 0.0, "meta": {}, "full": False}
# Serialise expensive reads so two requests never spawn osascript at once.
_fetch_lock = threading.Lock()


def _ttl() -> int:
    try:
        return max(30, int(CALENDAR_REFRESH_SECONDS))
    except (TypeError, ValueError):
        return 300


# --- date helpers ---

def _to_local_naive(dt: datetime) -> datetime:
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


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _shape(events: list) -> list:
    """Normalize raw source events into the API model, sorted by start."""
    cleaned = []
    for ev in events:
        start = _parse_iso(ev.get("start", ""))
        if start is None:
            continue
        end = _parse_iso(ev.get("end", "")) or start
        title = (ev.get("title") or "Untitled").strip()
        name = (ev.get("calendar") or "").strip()
        uid = str(ev.get("uid") or ev.get("id") or "").strip()
        eid = uid or hashlib.sha1(f"{title}|{start.isoformat()}".encode("utf-8")).hexdigest()[:12]
        cleaned.append(
            {
                "id": eid,
                "title": title,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "all_day": bool(ev.get("all_day") or ev.get("allday")),
                "location": (ev.get("location") or "").strip(),
                "calendar": name,
                "calendar_id": hashlib.sha1(name.encode("utf-8")).hexdigest()[:8] if name else "",
                "_start_dt": start,
                "_end_dt": end,
            }
        )
    cleaned.sort(key=lambda e: e["_start_dt"])
    return cleaned


# --- ICS source ---

def _ics_sources() -> list:
    paths = []
    for p in (CALENDAR_ICS_PATHS or "").split(os.pathsep):
        p = p.strip()
        if p:
            paths.append(p)
    single = (CALENDAR_ICS_PATH or "").strip()
    if single:
        paths.append(single)
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _source_label(src: str) -> str:
    if src.lower().startswith(("http://", "https://")):
        return "Web"  # don't echo the (secret) URL
    base = os.path.basename(src)
    return os.path.splitext(base)[0] or "ICS"


def _ics_datetime(prop: str, value: str):
    value = value.strip()
    is_date = "VALUE=DATE" in prop.upper() and "T" not in value
    try:
        if is_date:
            return datetime.strptime(value, "%Y%m%d").isoformat(), True
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.isoformat(), False
        return datetime.strptime(value, "%Y%m%dT%H%M%S").isoformat(), False
    except ValueError:
        return None, False


def _read_ics_text(source: str) -> str:
    # A URL lets you use the Apple/Google "secret iCal address". Keep it in .env.
    if source.lower().startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "FireFrame"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    with open(source, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _parse_ics(source: str) -> list:
    raw = _read_ics_text(source)

    # Unfold RFC 5545 continuation lines (those starting with a space or tab).
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
                cur["uid"] = val.strip()
            elif name == "DTSTART":
                iso, all_day = _ics_datetime(prop, val)
                cur["start"] = iso
                if all_day:
                    cur["all_day"] = True
            elif name == "DTEND":
                cur["end"], _ = _ics_datetime(prop, val)
    return events


# --- Apple Calendar source (JXA) ---
# Reads every accessible calendar and keeps events that overlap [start, end):
# startDate < end AND endDate > start. That overlap test (instead of a
# startDate-only "greater than") is what lets all-day and ongoing events show.

_JXA_TEMPLATE = """
(() => {
  const Cal = Application("Calendar");
  const start = new Date(__START__);
  const end = new Date(__END__);
  const out = [];
  let cals;
  try { cals = Cal.calendars(); } catch (e) { return "[]"; }
  for (let i = 0; i < cals.length; i++) {
    let name = "";
    try { name = cals[i].name(); } catch (e) {}
    let evs;
    try {
      evs = cals[i].events.whose({ _and: [
        { startDate: { _lessThan: end } },
        { endDate: { _greaterThan: start } }
      ]})();
    } catch (e) { continue; }
    for (let j = 0; j < evs.length; j++) {
      try {
        out.push({
          uid: evs[j].uid(),
          title: evs[j].summary(),
          start: evs[j].startDate().toISOString(),
          end: evs[j].endDate().toISOString(),
          allday: evs[j].alldayEvent(),
          location: evs[j].location() || "",
          calendar: name
        });
      } catch (e) {}
    }
  }
  return JSON.stringify(out);
})()
"""


def _query_apple_calendar(start_dt: datetime, end_dt: datetime) -> list:
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    script = _JXA_TEMPLATE.replace("__START__", str(start_ms)).replace("__END__", str(end_ms))
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        timeout=30,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("apple_calendar_unavailable")  # usually a missing permission
    return json.loads(proc.stdout)


# --- window load + cache ---

def _load_window(win_start: datetime, win_end: datetime) -> dict:
    source = (CALENDAR_SOURCE or "none").strip().lower()

    if source == "demo":
        evs = get_placeholder_events()
        for e in evs:
            e["calendar"] = "Demo"
        return {"connected": True, "source": "demo", "error": None, "full": True,
                "events": _shape(evs)}

    if source == "ics":
        srcs = _ics_sources()
        if not srcs:
            return {"connected": False, "source": "ics", "error": "no_path", "full": True,
                    "events": [], "message": "No ICS path configured (set CALENDAR_ICS_PATH)."}
        try:
            collected = []
            for src in srcs:
                label = _source_label(src)
                for ev in _parse_ics(src):
                    ev["calendar"] = label
                    collected.append(ev)
            return {"connected": True, "source": "ics", "error": None, "full": True,
                    "events": _shape(collected)}
        except FileNotFoundError:
            return {"connected": False, "source": "ics", "error": "file_not_found", "full": True,
                    "events": [], "message": "An ICS file was not found."}
        except urllib.error.URLError:
            return {"connected": False, "source": "ics", "error": "fetch_failed", "full": True,
                    "events": [], "message": "Could not fetch the calendar URL."}
        except Exception:
            return {"connected": False, "source": "ics", "error": "parse_failed", "full": True,
                    "events": [], "message": "Could not read an ICS source."}

    if source == "apple":
        if platform.system() != "Darwin":
            return {"connected": False, "source": "apple", "error": "not_macos", "full": False,
                    "events": [], "message": "Apple Calendar is only available on macOS."}
        try:
            return {"connected": True, "source": "apple", "error": None, "full": False,
                    "events": _shape(_query_apple_calendar(win_start, win_end))}
        except subprocess.TimeoutExpired:
            return {"connected": False, "source": "apple", "error": "timeout", "full": False,
                    "events": [], "message": "Apple Calendar query timed out."}
        except FileNotFoundError:
            return {"connected": False, "source": "apple", "error": "no_osascript", "full": False,
                    "events": [], "message": "osascript is not available."}
        except Exception:
            return {"connected": False, "source": "apple", "error": "unavailable", "full": False,
                    "events": [],
                    "message": "Could not read Apple Calendar. Grant Automation permission "
                               "(System Settings > Privacy & Security > Automation) or use ICS."}

    return {"connected": False, "source": "none", "error": None, "full": True, "events": [],
            "message": "Calendar not connected. Set CALENDAR_SOURCE to enable it."}


def _covers(req_start: datetime, req_end: datetime) -> bool:
    if _cache["full"]:
        return True
    return (_cache["start"] is not None
            and _cache["start"] <= req_start and req_end <= _cache["end"])


def _ensure(req_start: datetime, req_end: datetime) -> None:
    """Make sure the cache holds a fresh window covering [req_start, req_end)."""
    now = time.time()
    if _cache["events"] is not None and (now - _cache["ts"]) < _ttl() and _covers(req_start, req_end):
        return
    with _fetch_lock:
        now = time.time()
        if _cache["events"] is not None and (now - _cache["ts"]) < _ttl() and _covers(req_start, req_end):
            return  # another request filled it while we waited
        pad = timedelta(days=7)  # padding so adjacent day/week navigation stays in cache
        win_start, win_end = req_start - pad, req_end + pad
        data = _load_window(win_start, win_end)
        _cache.update(
            start=win_start, end=win_end, events=data["events"], ts=time.time(),
            full=data.get("full", False),
            meta={k: data.get(k) for k in ("connected", "source", "error", "message")},
        )


def _overlap(events: list, a: datetime, b: datetime) -> list:
    return [e for e in events if e["_start_dt"] < b and e["_end_dt"] > a]


def _public(events: list) -> list:
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]


# --- public API ---

def get_day(date_str=None) -> dict:
    d = _parse_date(date_str) or date.today()
    a = datetime(d.year, d.month, d.day)
    b = a + timedelta(days=1)
    _ensure(a, b)
    events = _overlap(_cache["events"], a, b)
    return {**_cache["meta"], "view": "day", "date": d.isoformat(), "events": _public(events)}


def get_week(start_str=None) -> dict:
    d = _parse_date(start_str) or _monday(date.today())
    a = datetime(d.year, d.month, d.day)
    b = a + timedelta(days=7)
    _ensure(a, b)
    events = _overlap(_cache["events"], a, b)
    return {**_cache["meta"], "view": "week", "start": d.isoformat(),
            "end": (d + timedelta(days=6)).isoformat(), "events": _public(events)}


def get_today() -> dict:
    return get_day(None)


def get_upcoming() -> dict:
    days = max(1, int(CALENDAR_UPCOMING_DAYS))
    a = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    b = a + timedelta(days=days)
    _ensure(a, b)
    events = sorted(_overlap(_cache["events"], a, b), key=lambda e: e["_start_dt"])[:25]
    return {**_cache["meta"], "events": _public(events)}


def get_sources() -> dict:
    a = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    _ensure(a, a + timedelta(days=max(1, int(CALENDAR_UPCOMING_DAYS))))
    seen, names = set(), []
    for e in _cache["events"] or []:
        n = e["calendar"]
        if n and n not in seen:
            seen.add(n)
            names.append({"name": n, "id": e["calendar_id"]})
    return {**_cache["meta"], "sources": names}


def refresh_calendar() -> dict:
    _cache.update(start=None, end=None, events=None, ts=0.0, full=False)
    return get_upcoming()
