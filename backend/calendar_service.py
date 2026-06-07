"""Calendar service with a pluggable source, selected by CALENDAR_SOURCE:

    none   nothing configured (default); the UI shows "not connected"
    demo   built-in placeholder events, handy for testing the UI
    ics    one or more local .ics files, or an https URL (CALENDAR_ICS_PATH /
           CALENDAR_ICS_PATHS)
    apple  Apple Calendar. Uses EventKit (fast) when pyobjc-framework-EventKit
           is installed, otherwise falls back to osascript/JXA (slow). Reads
           every accessible calendar; needs Calendar access permission.

Apple Calendar is read one month at a time and cached, so the first view only
loads the month(s) it touches and navigating to another month fetches just
that month. demo/ics load all their events at once (parsing is cheap). Within a
cached month, day/week navigation filters in memory. Event details are never
logged.
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

# Metadata from the most recent load (connected / source / error / message).
_meta = {"connected": False, "source": "none", "error": None, "message": None}
# "Full" sources (none / demo / ics) are cheap, so they load every event at once.
_full = {"events": None, "ts": 0.0}
# Apple Calendar is fetched one month at a time, on demand, and kept cached.
_months = {}          # "YYYY-MM" -> {"events": [...], "ts": float}
_MAX_MONTHS = 12      # cap on months held in memory
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
        desc = (ev.get("description") or ev.get("notes") or "").strip()
        if len(desc) > 600:   # keep the payload (and the popover) small
            desc = desc[:600].rstrip() + "..."
        cleaned.append(
            {
                "id": eid,
                "title": title,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "all_day": bool(ev.get("all_day") or ev.get("allday")),
                "location": (ev.get("location") or "").strip(),
                "description": desc,
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


def _ics_unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n")
                 .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\").strip())


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
            elif name == "DESCRIPTION":
                cur["description"] = _ics_unescape(val)
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
#
# Each property is fetched in a single bulk call per calendar (e.g. one
# `summary()` for the whole filtered set), not once per event. Per-event reads
# cost an Apple Event round-trip each and make the query time out on real
# calendars; the bulk form is far faster.

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
    try {
      const f = cals[i].events.whose({ _and: [
        { startDate: { _lessThan: end } },
        { endDate: { _greaterThan: start } }
      ]});
      const titles = f.summary();
      const starts = f.startDate();
      const ends = f.endDate();
      const allday = f.alldayEvent();
      let locs = [], uids = [];
      try { locs = f.location(); } catch (e) {}
      try { uids = f.uid(); } catch (e) {}
      for (let j = 0; j < titles.length; j++) {
        out.push({
          uid: uids[j] || null,
          title: titles[j],
          start: starts[j] ? starts[j].toISOString() : null,
          end: ends[j] ? ends[j].toISOString() : null,
          allday: allday[j],
          location: locs[j] || "",
          calendar: name
        });
      }
    } catch (e) { continue; }
  }
  return JSON.stringify(out);
})()
"""

# A real Mac with several calendars can still need a few seconds on the first
# (uncached) read; keep this generous since results are cached afterwards.
_APPLE_TIMEOUT_SECONDS = 45


def _query_apple_calendar(start_dt: datetime, end_dt: datetime) -> list:
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    script = _JXA_TEMPLATE.replace("__START__", str(start_ms)).replace("__END__", str(end_ms))
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        timeout=_APPLE_TIMEOUT_SECONDS,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("apple_calendar_unavailable")  # usually a missing permission
    return json.loads(proc.stdout)


# EventKit (PyObjC) is the fast path: it skips Calendar.app's very slow
# AppleScript "whose" queries. Optional, macOS only:
#     pip install pyobjc-framework-EventKit
_eventkit = {"checked": False, "ok": False}

# EKAuthorizationStatus values
_EK_DENIED = 2
_EK_AUTHORIZED = 3   # also "full access" on macOS 14+


def _eventkit_available() -> bool:
    if not _eventkit["checked"]:
        _eventkit["checked"] = True
        try:
            import EventKit  # noqa: F401
            from Foundation import NSDate  # noqa: F401
            _eventkit["ok"] = True
        except Exception:
            _eventkit["ok"] = False
    return _eventkit["ok"]


def _query_apple_eventkit(start_dt: datetime, end_dt: datetime) -> list:
    import threading
    from EventKit import EKEventStore
    from Foundation import NSDate

    status = EKEventStore.authorizationStatusForEntityType_(0)  # 0 = events
    if status == _EK_DENIED:
        raise PermissionError("calendar_access_denied")

    store = EKEventStore.alloc().init()
    if status != _EK_AUTHORIZED:
        granted = {"ok": False}
        done = threading.Event()

        def handler(ok, err):
            granted["ok"] = bool(ok)
            done.set()

        if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
            store.requestFullAccessToEventsWithCompletion_(handler)   # macOS 14+
        else:
            store.requestAccessToEntityType_completion_(0, handler)
        done.wait(timeout=20)
        if not granted["ok"]:
            raise PermissionError("calendar_access_denied")

    ns_start = NSDate.dateWithTimeIntervalSince1970_(start_dt.timestamp())
    ns_end = NSDate.dateWithTimeIntervalSince1970_(end_dt.timestamp())
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(ns_start, ns_end, None)

    out = []
    for ev in (store.eventsMatchingPredicate_(predicate) or []):
        try:
            sd, ed = ev.startDate(), ev.endDate()
            cal = ev.calendar()
            out.append({
                "uid": ev.calendarItemIdentifier(),
                "title": ev.title(),
                "start": datetime.fromtimestamp(sd.timeIntervalSince1970()).isoformat() if sd else None,
                "end": datetime.fromtimestamp(ed.timeIntervalSince1970()).isoformat() if ed else None,
                "allday": bool(ev.isAllDay()),
                "location": ev.location() or "",
                "description": ev.notes() or "",
                "calendar": cal.title() if cal else "",
            })
        except Exception:
            pass
    return out


def _apple_fetch(start_dt: datetime, end_dt: datetime) -> list:
    """Read a date range from Apple Calendar: EventKit if available, else JXA."""
    if _eventkit_available():
        return _query_apple_eventkit(start_dt, end_dt)
    return _query_apple_calendar(start_dt, end_dt)


# --- load + cache ---

def _set_meta(data: dict) -> None:
    _meta.update(connected=data.get("connected", False), source=data.get("source", "none"),
                 error=data.get("error"), message=data.get("message"))


def _overlap(events: list, a: datetime, b: datetime) -> list:
    return [e for e in events if e["_start_dt"] < b and e["_end_dt"] > a]


def _public(events: list) -> list:
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]


def _load_full(source: str) -> dict:
    """Load every event for a 'full' (cheap) source: demo, ics, or none."""
    if source == "demo":
        evs = get_placeholder_events()
        for e in evs:
            e["calendar"] = "Demo"
        return {"connected": True, "source": "demo", "error": None, "events": _shape(evs)}

    if source == "ics":
        srcs = _ics_sources()
        if not srcs:
            return {"connected": False, "source": "ics", "error": "no_path",
                    "events": [], "message": "No ICS path configured (set CALENDAR_ICS_PATH)."}
        try:
            collected = []
            for src in srcs:
                label = _source_label(src)
                for ev in _parse_ics(src):
                    ev["calendar"] = label
                    collected.append(ev)
            return {"connected": True, "source": "ics", "error": None, "events": _shape(collected)}
        except FileNotFoundError:
            return {"connected": False, "source": "ics", "error": "file_not_found",
                    "events": [], "message": "An ICS file was not found."}
        except urllib.error.URLError:
            return {"connected": False, "source": "ics", "error": "fetch_failed",
                    "events": [], "message": "Could not fetch the calendar URL."}
        except Exception:
            return {"connected": False, "source": "ics", "error": "parse_failed",
                    "events": [], "message": "Could not read an ICS source."}

    return {"connected": False, "source": "none", "error": None, "events": [],
            "message": "Calendar not connected. Set CALENDAR_SOURCE to enable it."}


def _ensure_full(source: str) -> None:
    now = time.time()
    if _full["events"] is not None and (now - _full["ts"]) < _ttl():
        return
    with _fetch_lock:
        if _full["events"] is not None and (time.time() - _full["ts"]) < _ttl():
            return
        data = _load_full(source)
        _full["events"] = data["events"]
        _full["ts"] = time.time()
        _set_meta(data)


# Apple Calendar: fetched and cached one month at a time.

def _ym(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_bounds(d: date):
    start = datetime(d.year, d.month, 1)
    nxt = datetime(d.year + 1, 1, 1) if d.month == 12 else datetime(d.year, d.month + 1, 1)
    return start, nxt


def _months_in_range(a: datetime, b: datetime) -> list:
    """First-of-month dates for every month the half-open range [a, b) touches."""
    months = []
    cur = date(a.year, a.month, 1)
    last_dt = b - timedelta(microseconds=1)   # b is exclusive
    last = date(last_dt.year, last_dt.month, 1)
    while cur <= last:
        months.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return months


def _evict_months() -> None:
    while len(_months) > _MAX_MONTHS:
        del _months[min(_months, key=lambda k: _months[k]["ts"])]


def _fetch_month_locked(d: date):
    """Cache one month if missing/stale. Returns (code, message) on failure, else None.
    The caller must hold _fetch_lock."""
    ym = _ym(d)
    entry = _months.get(ym)
    if entry is not None and (time.time() - entry["ts"]) < _ttl():
        return None
    start, nxt = _month_bounds(d)
    try:
        _months[ym] = {"events": _shape(_apple_fetch(start, nxt)), "ts": time.time()}
        _evict_months()
        return None
    except PermissionError:
        return ("permission",
                "FireFrame needs Calendar access. Enable it in System Settings > Privacy & "
                "Security > Calendars (and approve any Automation prompt), then retry.")
    except subprocess.TimeoutExpired:
        return ("timeout",
                "Apple Calendar (AppleScript) is too slow on this Mac. Install the faster "
                "EventKit reader with: ./.venv/bin/pip install pyobjc-framework-EventKit "
                "then restart, or use an ICS source.")
    except FileNotFoundError:
        return ("no_osascript", "osascript is not available.")
    except Exception:
        return ("unavailable",
                "Could not read Apple Calendar. Grant Calendar access (System Settings > "
                "Privacy & Security > Calendars) or use an ICS source.")


def _collect_apple(a: datetime, b: datetime) -> list:
    if platform.system() != "Darwin":
        _meta.update(connected=False, source="apple", error="not_macos",
                     message="Apple Calendar is only available on macOS.")
        return []
    months = _months_in_range(a, b)
    errs = []
    with _fetch_lock:
        for m in months:
            err = _fetch_month_locked(m)
            if err:
                errs.append(err)
    # Combine the months we have (dedupe events that span a month boundary).
    combined = {}
    for m in months:
        entry = _months.get(_ym(m))
        if entry:
            for ev in entry["events"]:
                combined[ev["id"]] = ev
    events = list(combined.values())
    if errs and not events:
        code, msg = errs[0]
        _meta.update(connected=False, source="apple", error=code, message=msg)
    else:
        _meta.update(connected=True, source="apple", error=None, message=None)
    return events


def _collect(a: datetime, b: datetime) -> list:
    """Events overlapping [a, b), loading only what's needed. Updates _meta."""
    source = (CALENDAR_SOURCE or "none").strip().lower()
    if source == "apple":
        events = _collect_apple(a, b)
    elif source in ("demo", "ics"):
        _ensure_full(source)
        events = _full["events"] or []
    else:
        _meta.update(connected=False, source="none", error=None,
                     message="Calendar not connected. Set CALENDAR_SOURCE to enable it.")
        events = []
    return sorted(_overlap(events, a, b), key=lambda e: e["_start_dt"])


# --- public API ---

def get_day(date_str=None) -> dict:
    d = _parse_date(date_str) or date.today()
    a = datetime(d.year, d.month, d.day)
    b = a + timedelta(days=1)
    return {**_meta, "view": "day", "date": d.isoformat(), "events": _public(_collect(a, b))}


def get_week(start_str=None) -> dict:
    d = _parse_date(start_str) or _monday(date.today())
    a = datetime(d.year, d.month, d.day)
    b = a + timedelta(days=7)
    events = _collect(a, b)
    return {**_meta, "view": "week", "start": d.isoformat(),
            "end": (d + timedelta(days=6)).isoformat(), "events": _public(events)}


def get_today() -> dict:
    return get_day(None)


def get_upcoming() -> dict:
    days = max(1, int(CALENDAR_UPCOMING_DAYS))
    a = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    b = a + timedelta(days=days)
    return {**_meta, "events": _public(_collect(a, b)[:25])}


def get_sources() -> dict:
    a = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = _collect(a, a + timedelta(days=max(1, int(CALENDAR_UPCOMING_DAYS))))
    seen, names = set(), []
    for e in events:
        n = e["calendar"]
        if n and n not in seen:
            seen.add(n)
            names.append({"name": n, "id": e["calendar_id"]})
    return {**_meta, "sources": names}


def refresh_calendar() -> dict:
    _full["events"] = None
    _full["ts"] = 0.0
    _months.clear()
    return get_upcoming()
