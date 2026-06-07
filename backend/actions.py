"""Buttons-tab actions.

Every action is looked up in the SHORTCUT_ACTIONS registry (config), so the
browser only ever sends a known key, never a command. macOS Shortcuts are run
by name; apps/URLs are opened with `open`; a few direct controls (mute, sleep,
prepare) are small fixed commands. shell=True is never used.
"""

import subprocess

from backend.config_loader import SHORTCUT_ACTIONS, PREPARE_APPS, PREPARE_URLS


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


def handle_action(action_id: str, params: dict) -> dict:
    spec = SHORTCUT_ACTIONS.get(action_id)
    if not spec:
        # Unknown here; main.py falls back to the Bluetooth handler for its keys.
        return {"success": False, "message": f"Handler for '{action_id}' not found."}

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
