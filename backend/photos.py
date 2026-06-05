import os

PHOTOS_DIR = os.path.join(os.path.dirname(__file__), "..", "photos")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

def get_local_photos() -> list:
    photos = []
    if not os.path.exists(PHOTOS_DIR):
        return photos
        
    for filename in os.listdir(PHOTOS_DIR):
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            photos.append(filename)
            
    return sorted(photos)
