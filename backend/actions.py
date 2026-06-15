"""Buttons-tab actions.

Every action is looked up in the SHORTCUT_ACTIONS registry (config), so the
browser only ever sends a known key, never a command. macOS Shortcuts are run
by name; apps/URLs are opened with `open`; a few direct controls (mute, sleep,
prepare) are small fixed commands. shell=True is never used.
"""

import re
import subprocess
import time

from backend.config_loader import (
    SHORTCUT_ACTIONS,
    PREPARE_APPS,
    PREPARE_URLS,
    TIMER_SOUND,
    WEATHER_ENABLED,
    WEATHER_SHORTCUT,
)

_LABEL_RE = re.compile(r"[^A-Za-z0-9 ]+")   # notification text: letters/digits/spaces only
_SOUND_RE = re.compile(r"[^A-Za-z0-9]+")    # macOS sound name: letters/digits only


def run_shortcut(shortcut_name: str) -> dict:
    if not shortcut_name:
        return {"success": False, "message": "No shortcut name configured."}
    try:
        subprocess.run(["shortcuts", "run", shortcut_name], check=True, capture_output=True, timeout=10)
        return {"success": True, "message": f"Ran '{shortcut_name}'."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": f"Shortcut failed. Create '{shortcut_name}' in the Shortcuts app."}
    except FileNotFoundError:
        return {"success": False, "message": "The 'shortcuts' command is macOS only."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Shortcut timed out."}


def run_open_command(app_name: str) -> dict:
    if not app_name:
        return {"success": False, "message": "No app configured."}
    try:
        subprocess.run(["open", "-a", app_name], check=True, capture_output=True, timeout=8)
        return {"success": True, "message": f"Opened {app_name}."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": f"Could not open {app_name}. Is it installed?"}
    except FileNotFoundError:
        return {"success": False, "message": "The 'open' command is macOS only."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": f"Opening {app_name} timed out."}


def run_open_url(url: str, label: str = None) -> dict:
    if not url:
        return {"success": False, "message": "No URL configured."}
    try:
        subprocess.run(["open", url], check=True, capture_output=True, timeout=8)
        return {"success": True, "message": f"Opened {label}." if label else "Opened."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": f"Could not open {label or 'that item'}."}
    except FileNotFoundError:
        return {"success": False, "message": "The 'open' command is macOS only."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Open timed out."}


def open_urls(urls: list) -> int:
    return sum(1 for url in urls if run_open_url(url)["success"])


def _open_app_or_url(app: str, url: str, label: str = None) -> dict:
    res = run_open_command(app)
    if res["success"]:
        return res
    fallback = run_open_url(url, label)
    if fallback["success"]:
        fallback["message"] = f"{label or app} app not found; opened the website."
    return fallback


def toggle_mute() -> dict:
    # Read the current state and flip it, so one button both mutes and unmutes.
    script = ("set m to output muted of (get volume settings)\n"
              "set volume output muted (not m)\n"
              "return (not m) as text")
    try:
        proc = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=6, text=True)
        muted = proc.stdout.strip().lower() == "true"
        return {"success": True, "message": "Muted." if muted else "Unmuted."}
    except FileNotFoundError:
        return {"success": False, "message": "Volume control is macOS only."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": "Could not change the mute state."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Mute command timed out."}


def sleep_mac() -> dict:
    try:
        subprocess.run(["pmset", "sleepnow"], check=True, capture_output=True, timeout=6)
        return {"success": True, "message": "Putting the Mac to sleep..."}
    except FileNotFoundError:
        return {"success": False, "message": "Sleeping the Mac is macOS only."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": "Could not sleep the Mac (it may need Energy permissions)."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Sleep command timed out."}


def run_prepare() -> dict:
    opened_apps = sum(1 for app in PREPARE_APPS if run_open_command(app)["success"])
    opened_urls = open_urls(PREPARE_URLS)
    return {"success": True, "message": f"Prepared: opened {opened_apps} app(s) and {opened_urls} link(s)."}


def notify_timer_done(minutes, label="") -> dict:
    """Post a passive macOS notification (with a soft sound) when a FireFrame
    timer finishes. It respects Do Not Disturb / Focus, so it won't interrupt
    focused work. The dynamic text is passed as argv, never interpolated into
    the script, so it can't break out; the sound name is sanitised too."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        minutes = 0
    minutes = max(1, min(1440, minutes))
    label = _LABEL_RE.sub("", (label or "")).strip()[:40]
    body = f"{label} finished" if label else f"{minutes}-minute timer finished"
    sound = _SOUND_RE.sub("", (TIMER_SOUND or "")).strip()
    sound_clause = f' sound name "{sound}"' if sound else ""
    script = ("on run argv\n"
              "  display notification (item 1 of argv) with title (item 2 of argv)"
              f"{sound_clause}\n"
              "end run")
    try:
        subprocess.run(["osascript", "-e", script, body, "FireFrame Timer"],
                       check=True, capture_output=True, timeout=6)
        return {"success": True, "message": "Timer notification sent."}
    except FileNotFoundError:
        return {"success": False, "message": "Notifications are macOS only."}
    except subprocess.CalledProcessError:
        return {"success": False, "message": "Could not post the notification."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Notification timed out."}


_weather_cache = {"ts": 0.0, "data": None}


def get_weather() -> dict:
    """Weather for the Home card, sourced from a user-built macOS Shortcut that
    prints a short string. Off unless WEATHER_ENABLED. Cached so the Shortcut
    runs at most a couple of times an hour."""
    if not WEATHER_ENABLED:
        return {"enabled": False}

    cached = _weather_cache["data"]
    if cached is not None:
        ttl = 1800 if cached.get("available") else 300
        if (time.time() - _weather_cache["ts"]) < ttl:
            return cached

    data = {"enabled": True, "available": False,
            "message": f'Create a "{WEATHER_SHORTCUT}" Shortcut that outputs the weather.'}
    try:
        proc = subprocess.run(["shortcuts", "run", WEATHER_SHORTCUT, "--output-path", "-"],
                              capture_output=True, text=True, timeout=15)
        text = (proc.stdout or "").strip()
        if proc.returncode == 0 and text:
            data = {"enabled": True, "available": True, "text": text[:80]}
    except FileNotFoundError:
        data = {"enabled": True, "available": False, "message": "Shortcuts is macOS only."}
    except subprocess.TimeoutExpired:
        data = {"enabled": True, "available": False, "message": "Weather Shortcut timed out."}
    except OSError:
        data = {"enabled": True, "available": False, "message": "Could not run the weather Shortcut."}

    _weather_cache.update(ts=time.time(), data=data)
    return data


def handle_action(action_id: str, params: dict) -> dict:
    spec = SHORTCUT_ACTIONS.get(action_id)
    if not spec:
        return {"success": False, "message": f"Unknown action '{action_id}'."}

    t = spec.get("type")
    if t == "shortcut":
        return run_shortcut(spec.get("shortcut", ""))
    if t == "open_app":
        return run_open_command(spec.get("app", ""))
    if t == "open_url":
        return run_open_url(spec.get("url", ""), spec.get("label"))
    if t == "open_app_or_url":
        return _open_app_or_url(spec.get("app", ""), spec.get("url", ""), spec.get("label"))
    if t == "mute":
        return toggle_mute()
    if t == "sleep_mac":
        return sleep_mac()
    if t == "prepare":
        return run_prepare()
    return {"success": False, "message": f"Action '{action_id}' has an unsupported type."}
