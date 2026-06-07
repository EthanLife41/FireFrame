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

# --- Buttons tab ---
# "Prepare" opens these apps and links. Keep them generic in a public repo.
PREPARE_APPS = ["Spotify", "Discord"]
PREPARE_URLS = ["https://www.google.com"]

# The Buttons tab registry. The frontend only sends one of these keys; the
# backend looks it up here, so the browser can never run an arbitrary command.
# Edit the Shortcut/app names below to match your own setup. Supported types:
#   shortcut         run a macOS Shortcut by name (`shortcuts run "<name>"`)
#   open_app         launch an app  (`open -a "<app>"`)
#   open_url         open a URL or System Settings pane
#   open_app_or_url  try the app, fall back to the URL
#   mute             toggle system mute       sleep_mac  sleep this Mac (confirmed)
#   prepare          open PREPARE_APPS + PREPARE_URLS
#
# Shortcuts to create in the macOS Shortcuts app for the focus modes:
#   FireFrame DND, FireFrame Locked In, FireFrame Presentation Mode,
#   FireFrame Break Mode, FireFrame Sleep Mode, FireFrame Quick Note
SHORTCUT_ACTIONS = {
    "dnd":              {"type": "shortcut", "shortcut": "FireFrame DND"},
    "locked_in":        {"type": "shortcut", "shortcut": "FireFrame Locked In"},
    "presentation":     {"type": "shortcut", "shortcut": "FireFrame Presentation Mode"},
    "break_mode":       {"type": "shortcut", "shortcut": "FireFrame Break Mode"},
    "sleep_focus":      {"type": "shortcut", "shortcut": "FireFrame Sleep Mode"},
    "sleep_mac":        {"type": "sleep_mac"},
    "mute":             {"type": "mute"},
    "display_settings": {"type": "open_url",
                         "url": "x-apple.systempreferences:com.apple.Displays-Settings.extension",
                         "label": "Display Settings"},
    "open_spotify":     {"type": "open_app", "app": "Spotify"},
    "quick_note":       {"type": "shortcut", "shortcut": "FireFrame Quick Note"},
    "gpt":              {"type": "open_app_or_url", "app": "ChatGPT",
                         "url": "https://chatgpt.com/", "label": "ChatGPT"},
    "wallpapers":       {"type": "open_app", "app": "iWallpaper"},
    "prepare":          {"type": "prepare"},
}

# Optional legacy Bluetooth shortcut actions (the Bluetooth tab handles
# connect/disconnect directly; these only matter if you add custom buttons).
ACTION_CONFIG = {
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
