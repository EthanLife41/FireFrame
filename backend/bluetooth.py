"""macOS Bluetooth helpers.

Listing and status come from the built-in `system_profiler` (read-only, no
extra tools). Connect/disconnect use `blueutil` when present and report an
unsupported result otherwise. Device addresses stay server-side; the UI only
ever sees a per-device token.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time

from backend.actions import run_shortcut
from backend.config_loader import (
    ACTION_CONFIG,
    BLUETOOTH_DEVICES,
    BLUETOOTH_ALLOW_CONNECT,
    BLUEUTIL_PATH,
)

# colon- or hyphen-separated MAC
_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")

# token -> address, rebuilt on each scan so real addresses never reach the UI
_device_index: dict = {}

# system_profiler takes a second or two; cache scans briefly. Rescan forces one.
_SCAN_TTL_SECONDS = 15
_scan_cache = {"ts": 0.0, "data": None}
# Keep two requests from launching system_profiler at the same time.
_scan_lock = threading.Lock()


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _blueutil_path():
    """Find blueutil: BLUEUTIL_PATH, then ./bin/blueutil, then PATH."""
    explicit = (BLUEUTIL_PATH or "").strip()
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit
    local = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "blueutil"))
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return shutil.which("blueutil")


def _have_blueutil() -> bool:
    return _blueutil_path() is not None


def _connect_supported() -> bool:
    return _is_macos() and BLUETOOTH_ALLOW_CONNECT and _have_blueutil()


def _token_for(address: str) -> str:
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]


def _normalize_mac(address: str):
    """Canonical AA:BB:.. form, or None if not a valid MAC."""
    if not address:
        return None
    norm = address.strip().replace("-", ":").upper()
    return norm if _MAC_RE.match(norm) else None


def _scan(force: bool = False) -> dict:
    """Return {powered, devices, error}, cached for a few seconds unless forced."""
    if not _is_macos():
        return {"powered": None, "devices": [], "error": "not_macos"}

    now = time.time()
    if not force and _scan_cache["data"] is not None and (now - _scan_cache["ts"]) < _SCAN_TTL_SECONDS:
        return _scan_cache["data"]

    with _scan_lock:
        now = time.time()
        if not force and _scan_cache["data"] is not None and (now - _scan_cache["ts"]) < _SCAN_TTL_SECONDS:
            return _scan_cache["data"]  # filled while we waited
        result = _scan_uncached()
        if result.get("error") is None:  # don't cache failures
            _scan_cache["data"] = result
            _scan_cache["ts"] = time.time()
    return result


def _scan_uncached() -> dict:
    try:
        proc = subprocess.run(
            ["system_profiler", "SPBluetoothDataType", "-json"],
            capture_output=True,
            timeout=20,
            text=True,
        )
    except FileNotFoundError:
        return {"powered": None, "devices": [], "error": "no_system_profiler"}
    except subprocess.TimeoutExpired:
        return {"powered": None, "devices": [], "error": "timeout"}

    if proc.returncode != 0 or not proc.stdout.strip():
        return {"powered": None, "devices": [], "error": "scan_failed"}

    try:
        data = json.loads(proc.stdout)
    except (ValueError, json.JSONDecodeError):
        return {"powered": None, "devices": [], "error": "parse_failed"}

    blocks = data.get("SPBluetoothDataType") or []
    if not blocks:
        return {"powered": None, "devices": [], "error": "empty"}
    block = blocks[0] if isinstance(blocks[0], dict) else {}

    powered = None
    controller = block.get("controller_properties")
    if isinstance(controller, dict):
        state = controller.get("controller_state")
        if state is not None:
            powered = state == "attrib_on"

    # system_profiler groups devices under device_connected / device_not_connected,
    # and the exact shape has shifted between macOS versions, so stay defensive.
    devices = []
    for key, val in block.items():
        if not key.startswith("device_") or not isinstance(val, list):
            continue
        default_connected = "not_connected" not in key
        for entry in val:
            if not isinstance(entry, dict):
                continue
            for name, props in entry.items():
                props = props if isinstance(props, dict) else {}
                address = props.get("device_address") or props.get("device_addr") or ""
                connected = default_connected
                isc = props.get("device_isconnected")
                if isc is not None:
                    connected = str(isc).lower().endswith("yes")
                devices.append(
                    {
                        "name": name or "Unknown device",
                        "address": address,
                        "connected": connected,
                        "type": props.get("device_minorType")
                        or props.get("device_majorType")
                        or "",
                    }
                )

    return {"powered": powered, "devices": devices, "error": None}


def _rebuild_index(devices: list) -> list:
    """Rebuild the token->address map and return UI-safe device dicts."""
    _device_index.clear()
    safe = []
    for d in devices:
        norm = _normalize_mac(d.get("address", ""))
        token = _token_for(norm) if norm else _token_for(d.get("name", "") + "::noaddr")
        if norm:
            _device_index[token] = norm
        safe.append(
            {
                "id": token,
                "name": d.get("name", "Unknown device"),
                "connected": bool(d.get("connected")),
                "type": d.get("type", ""),
                "actionable": bool(norm),
            }
        )
    safe.sort(key=lambda x: (not x["connected"], x["name"].lower()))  # connected first
    return safe


def get_bluetooth_status() -> dict:
    if not _is_macos():
        return {
            "available": False,
            "platform": platform.system().lower(),
            "powered": None,
            "connect_supported": False,
            "connected_count": 0,
            "message": "Bluetooth control is available on macOS only.",
        }

    scan = _scan()
    devices = _rebuild_index(scan["devices"])
    connected = sum(1 for d in devices if d["connected"])
    return {
        "available": scan["error"] is None,
        "platform": "darwin",
        "powered": scan["powered"],
        "connect_supported": _connect_supported(),
        "connected_count": connected,
        "error": scan["error"],
    }


def get_bluetooth_devices(force: bool = False) -> dict:
    if not _is_macos():
        return {
            "available": False,
            "platform": platform.system().lower(),
            "devices": [],
            "connect_supported": False,
            "message": "Bluetooth listing is available on macOS only.",
        }

    scan = _scan(force)
    devices = _rebuild_index(scan["devices"])
    resp = {
        "available": scan["error"] is None,
        "platform": "darwin",
        "powered": scan["powered"],
        "devices": devices,
        "connect_supported": _connect_supported(),
        "error": scan["error"],
    }
    if not _connect_supported() and _is_macos():
        resp["note"] = (
            "Connect/disconnect needs the optional 'blueutil' tool "
            "(install with: brew install blueutil)."
        )
    return resp


def _set_connection(token: str, connect: bool) -> dict:
    verb = "connect" if connect else "disconnect"
    if not _is_macos():
        return {"success": False, "supported": False,
                "message": "Bluetooth control is available on macOS only."}
    if not BLUETOOTH_ALLOW_CONNECT:
        return {"success": False, "supported": False,
                "message": "Bluetooth connect/disconnect is disabled in config."}
    tool = _blueutil_path()
    if not tool:
        return {"success": False, "supported": False,
                "message": "Optional 'blueutil' not found. Install it (brew install blueutil) "
                           "or place the binary in ./bin/blueutil."}

    address = _device_index.get(token)
    if not address:
        return {"success": False, "message": "Unknown device. Rescan and try again."}
    norm = _normalize_mac(address)
    if not norm:
        return {"success": False, "message": "Device address is invalid."}

    try:
        subprocess.run([tool, "--%s" % verb, norm], check=True, capture_output=True, timeout=25)
        return {"success": True, "message": "%sing..." % verb.capitalize()}
    except subprocess.CalledProcessError:
        return {"success": False, "message": "blueutil could not %s that device." % verb}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Bluetooth command timed out."}
    except FileNotFoundError:
        return {"success": False, "supported": False, "message": "blueutil is not available."}


def connect_device(token: str) -> dict:
    return _set_connection(token, True)


def disconnect_device(token: str) -> dict:
    return _set_connection(token, False)


# Shortcuts-based actions used by the fixed Buttons tab.
def handle_bluetooth_action(action_id: str, params: dict) -> dict:
    config = ACTION_CONFIG.get(action_id, {})
    if not config.get("enabled", False):
        return {"success": False, "message": f"Action '{action_id}' is disabled or unknown."}

    if action_id == "bluetooth_toggle":
        return run_shortcut("Desk Bluetooth Toggle")

    elif action_id == "bluetooth_connect_headphones":
        if not BLUETOOTH_DEVICES.get("headphones", {}).get("enabled", False):
            return {"success": False, "message": "Headphones are not enabled in config."}
        return run_shortcut("Desk Connect Headphones")

    elif action_id == "bluetooth_disconnect_headphones":
        if not BLUETOOTH_DEVICES.get("headphones", {}).get("enabled", False):
            return {"success": False, "message": "Headphones are not enabled in config."}
        return run_shortcut("Desk Disconnect Headphones")

    elif action_id == "bluetooth_connect_speaker":
        if not BLUETOOTH_DEVICES.get("speaker", {}).get("enabled", False):
            return {"success": False, "message": "Speaker is not enabled in config."}
        return run_shortcut("Desk Connect Speaker")

    elif action_id == "bluetooth_disconnect_speaker":
        if not BLUETOOTH_DEVICES.get("speaker", {}).get("enabled", False):
            return {"success": False, "message": "Speaker is not enabled in config."}
        return run_shortcut("Desk Disconnect Speaker")

    elif action_id == "open_bluetooth_settings":
        try:
            subprocess.run(
                ["open", "x-apple.systempreferences:com.apple.BluetoothSettings"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            return {"success": True, "message": "Opened Bluetooth Settings."}
        except Exception:
            try:
                subprocess.run(
                    ["open", "-b", "com.apple.systempreferences"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return {"success": True, "message": "Opened System Settings."}
            except Exception:
                return {"success": False, "message": "Could not open Settings."}

    return {"success": False, "message": f"Handler for '{action_id}' not found."}
