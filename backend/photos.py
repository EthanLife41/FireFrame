"""Lists local image files for the photo slideshow.

Reads from ./photos by default, or PHOTOS_DIR if set, so pictures can live
outside the repo. Images are never committed (see .gitignore).
"""

import os
import platform
import random
import subprocess
import time

from backend.config_loader import PHOTOS_DIR_OVERRIDE, PHOTO_INTERVAL_SECONDS

_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), "..", "photos")
PHOTOS_DIR = os.path.abspath(PHOTOS_DIR_OVERRIDE) if PHOTOS_DIR_OVERRIDE else os.path.abspath(_DEFAULT_DIR)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Cache the directory listing briefly so repeated /api/photos and random calls
# don't hit the filesystem every time.
_LISTING_TTL_SECONDS = 30
_listing_cache = {"ts": 0.0, "photos": None}


def _scan_dir() -> list:
    if not os.path.isdir(PHOTOS_DIR):
        return []
    photos = []
    for filename in os.listdir(PHOTOS_DIR):
        if filename.startswith("."):
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            photos.append(filename)
    return sorted(photos)


def get_local_photos() -> list:
    now = time.time()
    if _listing_cache["photos"] is None or (now - _listing_cache["ts"]) > _LISTING_TTL_SECONDS:
        _listing_cache["photos"] = _scan_dir()
        _listing_cache["ts"] = now
    return _listing_cache["photos"]


def get_random_photo():
    photos = get_local_photos()
    return random.choice(photos) if photos else None


def get_photos_payload() -> dict:
    photos = get_local_photos()
    return {
        "photos": photos,
        "count": len(photos),
        "interval_seconds": max(3, int(PHOTO_INTERVAL_SECONDS)),
    }


def open_photos_dir() -> dict:
    """Open the photos folder in Finder (macOS only). Fixed path, no user input."""
    if platform.system() != "Darwin":
        return {"success": False, "message": "Opening the folder is supported on macOS only."}
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        subprocess.run(["open", PHOTOS_DIR], check=True, capture_output=True, timeout=5)
        return {"success": True, "message": "Opened the photos folder on the Mac."}
    except Exception:
        return {"success": False, "message": "Could not open the photos folder."}
