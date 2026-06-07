"""macOS Bluetooth support.

Two layers, both macOS-first and safe:

1. Listing / status — uses the built-in ``system_profiler SPBluetoothDataType``
   (no third-party tools, no Homebrew). Read-only.
2. Connect / disconnect — uses the OPTIONAL ``blueutil`` CLI if it is installed
   (``brew install blueutil``). If it is missing we degrade gracefully and tell
   the UI that the action is unsupported rather than failing hard.

Privacy: real Bluetooth addresses never leave the backend. The frontend only
ever sees an opaque, stable token per device and acts on that token.

Never uses ``shell=True``; every address is validated before being passed to a
subprocess.
"""

import hashlib
import json
import platform
import re
import shutil
import subprocess
import time

from backend.actions import run_shortcut
from backend.config_loader import ACTION_CONFIG, BLUETOOTH_DEVICES, BLUETOOTH_ALLOW_CONNECT

# Accept colon- or hyphen-separated MAC addresses only.
_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")

# Opaque-token -> real address map, rebuilt on every scan. Keeps addresses off
# the wire while still letting the UI ask us to act on a specific device.
_device_index: dict = {}

# system_profiler is slow (~1-2s). Cache results briefly so the Home tab's
# frequent status polling doesn't spawn overlapping scans. "Rescan" forces fresh.
_SCAN_TTL_SECONDS = 8
_scan_cache = {"ts": 0.0, "data": None}


# ---------------------------------------------------------------------------
# Platform / tool detection
# ---------------------------------------------------------------------------
def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _have_blueutil() -> bool:
    return shutil.which("blueutil") is not None


def _connect_supported() -> bool:
    return _is_macos() and BLUETOOTH_ALLOW_CONNECT and _have_blueutil()


def _token_for(address: str) -> str:
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]


def _normalize_mac(address: str):
    """Return a canonical AA:BB:.. address, or None if it isn't a valid MAC."""
    if not address:
        return None
    norm = address.strip().replace("-", ":").upper()
    return norm if _MAC_RE.match(norm) else None


# ---------------------------------------------------------------------------
# Scanning (system_profiler)
# ---------------------------------------------------------------------------
def _scan(force: bool = False) -> dict:
    """Scan via system_profiler. Returns {powered, devices, error}.

    ``devices`` is a list of {name, address, connected, type}. Defensive about
    the several JSON shapes system_profiler has used across macOS versions.
    Results are cached for a few seconds unless ``force`` is set.
    """
    if not _is_macos():
        return {"powered": None, "devices": [], "error": "not_macos"}

    now = time.time()
    if not force and _scan_cache["data"] is not None and (now - _scan_cache["ts"]) < _SCAN_TTL_SECONDS:
        return _scan_cache["data"]

    result = _scan_uncached()
    # Only cache successful scans so transient failures retry promptly.
    if result.get("error") is None:
        _scan_cache["data"] = result
        _scan_cache["ts"] = now
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

    devices = []
    for key, val in block.items():
        if not key.startswith("device_") or not isinstance(val, list):
            continue
        # "device_connected" => connected; "device_not_connected" => not.
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
    """Replace the token->address map and return UI-safe device dicts."""
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
                "actionable": bool(norm),  # we have a usable address for this one
            }
        )
    # Connected first, then alphabetical — stable and readable in the UI.
    safe.sort(key=lambda x: (not x["connected"], x["name"].lower()))
    return safe


# ---------------------------------------------------------------------------
# Public API (used by routes)
# ---------------------------------------------------------------------------
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
    if not _have_blueutil():
        return {"success": False, "supported": False,
                "message": "Optional 'blueutil' not found. Install with: brew install blueutil"}

    address = _device_index.get(token)
    if not address:
        return {"success": False, "message": "Unknown device — rescan and try again."}
    norm = _normalize_mac(address)
    if not norm:
        return {"success": False, "message": "Device address is invalid."}

    try:
        subprocess.run(
            ["blueutil", "--%s" % verb, norm],
            check=True,
            capture_output=True,
            timeout=25,
        )
        return {"success": True, "message": "%sing…" % verb.capitalize()}
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


# ---------------------------------------------------------------------------
# Legacy Shortcuts-based actions (still used by the static Buttons tab)
# ---------------------------------------------------------------------------
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
