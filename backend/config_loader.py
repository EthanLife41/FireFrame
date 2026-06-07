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
    "CALENDAR_UPCOMING_DAYS": int(os.getenv("CALENDAR_UPCOMING_DAYS", "7")),
    # Photos
    "PHOTOS_DIR_OVERRIDE": os.getenv("PHOTOS_DIR", ""),
    "PHOTO_INTERVAL_SECONDS": int(os.getenv("PHOTO_INTERVAL_SECONDS", "30")),
    # Bluetooth
    "BLUETOOTH_ALLOW_CONNECT": _flag("BLUETOOTH_ALLOW_CONNECT"),
    # Feature config (safe empties; a config file normally supplies these)
    "PREPARE_LAPTOP_URLS": [],
    "ACTION_CONFIG": {},
    "BLUETOOTH_DEVICES": {},
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
