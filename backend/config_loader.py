import os
import sys
import importlib.util

from dotenv import load_dotenv

# Load .env first so the defaults below (and any os.getenv() inside a config
# file) can see it.
load_dotenv()

EXAMPLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.example.py")
LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")


def _flag(name, default="1"):
    return os.getenv(name, default) not in ("0", "false", "False", "")


# Declarative registry for the Buttons tab. The frontend only ever sends one of
# these keys; the backend looks it up here (no arbitrary commands). A local
# backend/config.py can override any of this to point at the user's own macOS
# Shortcut names or app names. Supported "type" values:
#   shortcut         run a macOS Shortcut by name (`shortcuts run "<name>"`)
#   open_app         launch an app  (`open -a "<app>"`)
#   open_url         open a URL or settings pane (`open "<url>"`)
#   open_app_or_url  try the app, fall back to the URL
#   mute             toggle system mute (osascript)
#   sleep_mac        sleep this Mac (pmset); the UI asks to confirm first
#   prepare          open the PREPARE_APPS and PREPARE_URLS below
_SHORTCUT_ACTIONS_DEFAULT = {
    # Focus & Modes (macOS Shortcuts you create in the Shortcuts app)
    "dnd":            {"type": "shortcut", "shortcut": "FireFrame DND"},
    "locked_in":      {"type": "shortcut", "shortcut": "FireFrame Locked In"},
    "presentation":   {"type": "shortcut", "shortcut": "FireFrame Presentation Mode"},
    "break_mode":     {"type": "shortcut", "shortcut": "FireFrame Break Mode"},
    "sleep_focus":    {"type": "shortcut", "shortcut": "FireFrame Sleep Mode"},
    # Mac Controls (direct, no Shortcut needed)
    "sleep_mac":      {"type": "sleep_mac"},
    "mute":           {"type": "mute"},
    "display_settings": {"type": "open_url",
                         "url": "x-apple.systempreferences:com.apple.Displays-Settings.extension",
                         "label": "Display Settings"},
    # Apps & Tools (generic app names; change them in backend/config.py)
    "open_spotify":   {"type": "open_app", "app": "Spotify"},
    "quick_note":     {"type": "shortcut", "shortcut": "FireFrame Quick Note"},
    "gpt":            {"type": "open_app_or_url", "app": "ChatGPT",
                       "url": "https://chatgpt.com/", "label": "ChatGPT"},
    "wallpapers":     {"type": "open_app", "app": "iWallpaper"},
    # App launcher (Home "Open App" row). Edit the app names to match yours.
    "launch_chrome":    {"type": "open_app", "app": "Google Chrome"},
    "launch_vscode":    {"type": "open_app", "app": "Visual Studio Code"},
    "launch_terminal":  {"type": "open_app", "app": "Terminal"},
    "launch_notes":     {"type": "open_app", "app": "Notes"},
    "launch_finder":    {"type": "open_app", "app": "Finder"},
    "bluetooth_settings": {"type": "open_url",
                           "url": "x-apple.systempreferences:com.apple.BluetoothSettings",
                           "label": "Bluetooth Settings"},
    # FireFrame
    "prepare":        {"type": "prepare"},
}


# Built-in, environment-driven defaults for every setting the app reads. A local
# backend/config.py overrides any of these, so a config file written before a
# given option existed keeps working when new options are added later.
_DEFAULTS = {
    # Server
    "HOST": os.getenv("HOST", "0.0.0.0"),
    "PORT": int(os.getenv("PORT", "8765")),
    # Security
    "DASHBOARD_PASSWORD": os.getenv("DASHBOARD_PASSWORD", "change-me"),
    "SESSION_SECRET": os.getenv("SESSION_SECRET", "change-this-random-string"),
    # Calendar
    "CALENDAR_SOURCE": os.getenv("CALENDAR_SOURCE", "none"),
    "CALENDAR_ICS_PATH": os.getenv("CALENDAR_ICS_PATH", ""),
    "CALENDAR_ICS_PATHS": os.getenv("CALENDAR_ICS_PATHS", ""),
    "CALENDAR_UPCOMING_DAYS": int(os.getenv("CALENDAR_UPCOMING_DAYS", "7")),
    "CALENDAR_REFRESH_SECONDS": int(os.getenv("CALENDAR_REFRESH_SECONDS", "300")),
    # Photos
    "PHOTOS_DIR_OVERRIDE": os.getenv("PHOTOS_DIR", ""),
    "PHOTO_INTERVAL_SECONDS": int(os.getenv("PHOTO_INTERVAL_SECONDS", "30")),
    # Timers: the soft macOS sound played with the completion notification.
    # A name from /System/Library/Sounds (e.g. Glass, Tink, Pop, Ping). Set
    # to "" for a silent (banner-only) notification.
    "TIMER_SOUND": os.getenv("TIMER_SOUND", "Glass"),
    # Weather (optional, off by default). When on, the Home weather card runs a
    # macOS Shortcut that returns a short weather string: no API key, and the
    # location/units stay inside your Shortcut, not the repo. See the README.
    "WEATHER_ENABLED": _flag("WEATHER_ENABLED", "0"),
    "WEATHER_SHORTCUT": os.getenv("WEATHER_SHORTCUT", "FireFrame Weather"),
    # Bluetooth
    "BLUETOOTH_ALLOW_CONNECT": _flag("BLUETOOTH_ALLOW_CONNECT"),
    "BLUEUTIL_PATH": os.getenv("BLUEUTIL_PATH", ""),
    # Tasks: scheduled calendar blocks created from FireFrame. A task lands in a
    # calendar named like "Tasks" when one exists, else TASK_DEFAULT_CALENDAR (by
    # name), else a calendar the user picks. Durations are per importance level.
    "TASK_DEFAULT_CALENDAR": os.getenv("TASK_DEFAULT_CALENDAR", ""),
    "TASK_REGULAR_DURATION_MINUTES": int(os.getenv("TASK_REGULAR_DURATION_MINUTES", "60")),
    "TASK_IMPORTANT_DURATION_MINUTES": int(os.getenv("TASK_IMPORTANT_DURATION_MINUTES", "240")),
    # Buttons tab
    "SHORTCUT_ACTIONS": _SHORTCUT_ACTIONS_DEFAULT,
    # "Prepare" opens these apps and links. Keep them generic in a public repo.
    "PREPARE_APPS": ["Spotify", "Discord"],
    "PREPARE_URLS": ["https://www.google.com"],
}

for _key, _val in _DEFAULTS.items():
    globals()[_key] = _val

# Load the local config if present, otherwise the example, and let whatever it
# defines override the defaults above.
config_path = LOCAL_CONFIG_PATH if os.path.exists(LOCAL_CONFIG_PATH) else EXAMPLE_CONFIG_PATH

spec = importlib.util.spec_from_file_location("dynamic_config", config_path)
dynamic_config = importlib.util.module_from_spec(spec)
sys.modules["dynamic_config"] = dynamic_config
spec.loader.exec_module(dynamic_config)

# Export all upper-case variables from the loaded config (overriding defaults).
for key in dir(dynamic_config):
    if key.isupper():
        globals()[key] = getattr(dynamic_config, key)

# True when a local backend/config.py is in use (vs the bundled example).
CONFIG_IS_LOCAL = os.path.exists(LOCAL_CONFIG_PATH)

# The default secret is public, so cookies signed with it can be forged.
if SESSION_SECRET == "change-this-random-string":
    sys.stderr.write(
        "FATAL: SESSION_SECRET is still the default value.\n"
        "       Set a long random value in .env before starting FireFrame:\n"
        "         python3 -c \"import secrets; print(secrets.token_hex(32))\"\n")
    raise SystemExit(1)

if DASHBOARD_PASSWORD == "change-me":
    sys.stderr.write(
        "WARNING: DASHBOARD_PASSWORD is still the default 'change-me'. "
        "Set your own PIN/password in .env.\n")
