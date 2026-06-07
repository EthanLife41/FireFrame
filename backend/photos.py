"""Local photo listing.

Photos are read from a local folder. The folder defaults to ``../photos`` in
the repo, but can be pointed anywhere with the ``PHOTOS_DIR`` env var so each
person can keep their own pictures outside the repository. No personal images
are ever committed (see .gitignore).
"""

import os
import random

from backend.config_loader import PHOTOS_DIR_OVERRIDE, PHOTO_INTERVAL_SECONDS

_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), "..", "photos")
PHOTOS_DIR = os.path.abspath(PHOTOS_DIR_OVERRIDE) if PHOTOS_DIR_OVERRIDE else os.path.abspath(_DEFAULT_DIR)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_local_photos() -> list:
    photos = []
    if not os.path.isdir(PHOTOS_DIR):
        return photos

    for filename in os.listdir(PHOTOS_DIR):
        if filename.startswith("."):
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            photos.append(filename)

    return sorted(photos)


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
