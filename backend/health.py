"""Read-only configuration and feature status for the Settings page.

Reuses the existing config and feature modules. Everything here is cheap: no
system_profiler scans and no Apple Calendar fetches. Paths are reduced to a safe
basename, and secrets are reported only as "is this still the default", never as
their actual values.
"""

import os
import shutil

from backend.config_loader import (
    HOST,
    PORT,
    SHORTCUT_ACTIONS,
    DASHBOARD_PASSWORD,
    SESSION_SECRET,
    CONFIG_IS_LOCAL,
)
from backend.photos import PHOTOS_DIR, get_photos_payload
from backend.bluetooth import get_bluetooth_support
from backend.calendar_service import get_calendar_status, get_today

# The shipped defaults; matching them means the user hasn't set their own yet.
_DEFAULT_PASSWORD = "change-me"
_DEFAULT_SECRET = "change-this-random-string"


def _calendar() -> dict:
    st = get_calendar_status()
    source = st.get("configured_source", "none")
    # demo/ics load cheaply, so confirm they actually parse even before the
    # Calendar tab is opened. Apple is left to its own (cached) loads.
    if source in ("demo", "ics") and not st.get("connected"):
        try:
            get_today()
        except Exception:
            pass
        st = get_calendar_status()
    return {
        "source": source,
        "configured": source not in ("", "none"),
        "connected": bool(st.get("connected")),
        "message": st.get("message"),
    }


def _photos() -> dict:
    payload = get_photos_payload()
    return {
        "folder": os.path.basename(PHOTOS_DIR.rstrip(os.sep)) or "photos",
        "exists": os.path.isdir(PHOTOS_DIR),
        "count": payload.get("count", 0),
    }


def _shortcuts() -> dict:
    # Count the actions that need a macOS Shortcut created (type "shortcut").
    count = sum(1 for spec in (SHORTCUT_ACTIONS or {}).values()
                if isinstance(spec, dict) and spec.get("type") == "shortcut")
    return {
        "configured": count > 0,
        "count": count,
        "cli_available": shutil.which("shortcuts") is not None,
    }


def get_settings_status() -> dict:
    return {
        "server": {"host": HOST, "port": PORT},
        "config": {
            "local_config": bool(CONFIG_IS_LOCAL),
            "password_is_default": DASHBOARD_PASSWORD == _DEFAULT_PASSWORD,
            "secret_is_default": SESSION_SECRET == _DEFAULT_SECRET,
        },
        "calendar": _calendar(),
        "photos": _photos(),
        "bluetooth": get_bluetooth_support(),
        "shortcuts": _shortcuts(),
    }
