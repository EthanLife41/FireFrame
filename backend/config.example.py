import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Server Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8765))

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
