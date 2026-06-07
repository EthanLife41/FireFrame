import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Server Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8765))

# --- Calendar (macOS-first) ---
# CALENDAR_SOURCE: none | demo | ics | apple
#   none  - nothing configured (UI shows "not connected")
#   demo  - built-in placeholder events
#   ics   - parse a local .ics file at CALENDAR_ICS_PATH
#   apple - read Apple Calendar via osascript/JXA (needs Automation permission)
CALENDAR_SOURCE = os.getenv("CALENDAR_SOURCE", "none")
# For CALENDAR_SOURCE=ics: a single .ics path or https URL. Keep it out of the repo.
CALENDAR_ICS_PATH = os.getenv("CALENDAR_ICS_PATH", "")
# Optional: several .ics files at once, separated by the OS path separator
# (":" on macOS/Linux), e.g. /path/one.ics:/path/two.ics
CALENDAR_ICS_PATHS = os.getenv("CALENDAR_ICS_PATHS", "")
CALENDAR_UPCOMING_DAYS = int(os.getenv("CALENDAR_UPCOMING_DAYS", "7"))
# How long fetched events are cached before a read is allowed again (seconds).
CALENDAR_REFRESH_SECONDS = int(os.getenv("CALENDAR_REFRESH_SECONDS", "300"))

# --- Photos ---
# Optional: keep your pictures outside the repo by setting PHOTOS_DIR.
PHOTOS_DIR_OVERRIDE = os.getenv("PHOTOS_DIR", "")
PHOTO_INTERVAL_SECONDS = int(os.getenv("PHOTO_INTERVAL_SECONDS", "30"))

# --- Bluetooth ---
# Connect/disconnect needs the optional 'blueutil' tool. Set to 0 to disable
# those actions entirely (listing/status still work).
BLUETOOTH_ALLOW_CONNECT = os.getenv("BLUETOOTH_ALLOW_CONNECT", "1") not in ("0", "false", "False", "")
# Optional explicit path to the blueutil binary. Leave empty to auto-detect
# (project-local ./bin/blueutil, then anything on PATH).
BLUEUTIL_PATH = os.getenv("BLUEUTIL_PATH", "")

# Security Settings
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "change-me")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-random-string")

# General Settings
# Allowed URLs for "Prepare Laptop" action
PREPARE_LAPTOP_URLS = [
    "https://calendar.google.com",
    "https://mail.google.com",
    "https://outlook.com",
    "https://github.com",
    "https://chatgpt.com"
]

# Action registry overrides
# Set 'enabled': False to easily disable an action.
ACTION_CONFIG = {
    "toggle_dnd": {"enabled": True},
    "toggle_locked_in": {"enabled": True},
    "sleep_mode_alarm": {"enabled": True},
    "open_calendar": {"enabled": True},
    "prepare_laptop": {"enabled": True},
    "open_assistant": {"enabled": True},
    "bluetooth_toggle": {"enabled": True},
    "bluetooth_connect_headphones": {"enabled": True},
    "bluetooth_disconnect_headphones": {"enabled": True},
    "bluetooth_connect_speaker": {"enabled": True},
    "bluetooth_disconnect_speaker": {"enabled": True},
    "open_bluetooth_settings": {"enabled": True},
}

# Bluetooth Devices
# Friendly identifiers used to prevent exposing real Bluetooth MAC addresses to the frontend
BLUETOOTH_DEVICES = {
    "headphones": {
        "label": "Headphones",
        "enabled": True,
        "identifier": "PLACEHOLDER_HEADPHONES_ID" # e.g. a MAC address if direct tools used later
    },
    "speaker": {
        "label": "Speaker",
        "enabled": True,
        "identifier": "PLACEHOLDER_SPEAKER_ID"
    }
}
