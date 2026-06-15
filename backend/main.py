from fastapi import FastAPI, Depends, Request, Response, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import os
import time
import secrets
import subprocess
from collections import defaultdict

from backend.auth import create_session_token, get_current_user, SESSION_MAX_AGE_SECONDS
from backend.config_loader import DASHBOARD_PASSWORD
from backend.actions import handle_action, notify_timer_done, get_weather
from backend.bluetooth import (
    get_bluetooth_status,
    get_bluetooth_devices,
    connect_device,
    disconnect_device,
)
from backend.stats import get_home_stats
from backend.mac_stats import get_mac_stats as get_dashboard_stats
from backend.health import get_settings_status
from backend.photos import get_photos_payload, get_random_photo, open_photos_dir, PHOTOS_DIR
from backend.calendar_service import (
    get_today,
    get_day,
    get_week,
    get_upcoming,
    get_sources,
    refresh_calendar,
)

def _app_version() -> str:
    """Build label shown in the corner: commit count + short hash (e.g. v26 ·
    3d80e9b). Computed once at startup; falls back to "dev" without a git repo
    (e.g. a zip download)."""
    repo = os.path.join(os.path.dirname(__file__), "..")
    try:
        count = subprocess.run(["git", "-C", repo, "rev-list", "--count", "HEAD"],
                               capture_output=True, text=True, timeout=3)
        sha = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=3)
        if count.returncode == 0 and sha.returncode == 0:
            c, s = count.stdout.strip(), sha.stdout.strip()
            if c and s:
                return f"v{c} · {s}"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return "dev"


APP_VERSION = _app_version()

app = FastAPI(title="FireFrame API")

# Mount frontend and photos static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
# Ensure the photos folder exists so a custom PHOTOS_DIR never crashes startup.
os.makedirs(PHOTOS_DIR, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# --- Rate Limiting for Login ---
# In-memory tracker: {ip: {"attempts": int, "lockout_until": float}}
_login_attempts: dict = defaultdict(lambda: {"attempts": 0, "lockout_until": 0.0})
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 30

def get_client_ip(request: Request) -> str:
    # Use the real socket peer, not X-Forwarded-For: there's no proxy here, so a
    # spoofed XFF header would let a client bypass the per-IP login lockout.
    return request.client.host if request.client else "unknown"

def check_rate_limit(ip: str):
    record = _login_attempts[ip]
    now = time.time()
    # Clear lockout if enough time has passed
    if record["lockout_until"] > 0 and now >= record["lockout_until"]:
        record["attempts"] = 0
        record["lockout_until"] = 0.0
    # Check if currently locked out
    if record["lockout_until"] > now:
        wait = int(record["lockout_until"] - now)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Please wait {wait} seconds."
        )

def record_failed_attempt(ip: str):
    record = _login_attempts[ip]
    record["attempts"] += 1
    if record["attempts"] >= MAX_ATTEMPTS:
        record["lockout_until"] = time.time() + LOCKOUT_SECONDS

def clear_attempts(ip: str):
    _login_attempts[ip] = {"attempts": 0, "lockout_until": 0.0}

# --- Pydantic Models ---
class LoginRequest(BaseModel):
    password: str

class ActionRequest(BaseModel):
    action: str
    params: dict = {}

class DeviceRequest(BaseModel):
    id: str

class TimerNotifyRequest(BaseModel):
    minutes: int = 0
    label: str = ""

# --- Routes ---

@app.get("/")
async def serve_dashboard():
    css_path = os.path.join(frontend_dir, "style.css")
    js_path = os.path.join(frontend_dir, "app.js")

    css_mtime = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else int(time.time())
    js_mtime = int(os.path.getmtime(js_path)) if os.path.exists(js_path) else int(time.time())

    html_path = os.path.join(frontend_dir, "index.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="index.html not found")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Replace template version placeholders
    html_content = html_content.replace("{{CSS_VERSION}}", str(css_mtime))
    html_content = html_content.replace("{{JS_VERSION}}", str(js_mtime))
    html_content = html_content.replace("{{VERSION}}", APP_VERSION)

    response = HTMLResponse(content=html_content)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.post("/api/login")
async def login(req: LoginRequest, request: Request, response: Response):
    ip = get_client_ip(request)
    check_rate_limit(ip)  # raises 429 if locked out

    # Constant-time compare to avoid leaking the password via response timing.
    if secrets.compare_digest(req.password.encode("utf-8"), DASHBOARD_PASSWORD.encode("utf-8")):
        clear_attempts(ip)
        token = create_session_token(True)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_MAX_AGE_SECONDS,
        )
        return {"success": True}

    # Wrong password: record the failed attempt
    record_failed_attempt(ip)
    record = _login_attempts[ip]
    remaining = MAX_ATTEMPTS - record["attempts"]
    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Please wait {LOCKOUT_SECONDS} seconds."
        )
    raise HTTPException(
        status_code=401,
        detail=f"Invalid password. {remaining} attempt(s) remaining."
    )

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(key="session")
    return {"success": True}

@app.get("/api/me")
async def check_login(user: bool = Depends(get_current_user)):
    return {"logged_in": True}

@app.get("/api/status")
async def get_status(user: bool = Depends(get_current_user)):
    return {"status": "ok", "message": "Server is running locally."}

@app.post("/api/action")
async def perform_action(req: ActionRequest, user: bool = Depends(get_current_user)):
    return handle_action(req.action, req.params)

@app.get("/api/bluetooth/status")
async def bluetooth_status(user: bool = Depends(get_current_user)):
    return get_bluetooth_status()

@app.get("/api/bluetooth/devices")
async def bluetooth_devices(user: bool = Depends(get_current_user)):
    return get_bluetooth_devices()

@app.post("/api/bluetooth/refresh")
async def bluetooth_refresh(user: bool = Depends(get_current_user)):
    return get_bluetooth_devices(force=True)

@app.post("/api/bluetooth/connect")
async def bluetooth_connect(req: DeviceRequest, user: bool = Depends(get_current_user)):
    return connect_device(req.id)

@app.post("/api/bluetooth/disconnect")
async def bluetooth_disconnect(req: DeviceRequest, user: bool = Depends(get_current_user)):
    return disconnect_device(req.id)

@app.get("/api/stats")
async def mac_stats(user: bool = Depends(get_current_user)):
    return get_home_stats()

@app.get("/api/mac-stats")
async def mac_stats_dashboard(user: bool = Depends(get_current_user)):
    return get_dashboard_stats()

@app.get("/api/settings")
async def settings_status(user: bool = Depends(get_current_user)):
    return get_settings_status()

@app.post("/api/timer/notify")
async def timer_notify(req: TimerNotifyRequest, user: bool = Depends(get_current_user)):
    return notify_timer_done(req.minutes, req.label)

@app.get("/api/weather")
async def weather(user: bool = Depends(get_current_user)):
    return get_weather()

@app.post("/api/photos/open")
async def photos_open(user: bool = Depends(get_current_user)):
    return open_photos_dir()

@app.get("/api/calendar/today")
async def calendar_today(user: bool = Depends(get_current_user)):
    return get_today()

@app.get("/api/calendar/day")
async def calendar_day(date: str = "", user: bool = Depends(get_current_user)):
    return get_day(date or None)

@app.get("/api/calendar/week")
async def calendar_week(start: str = "", user: bool = Depends(get_current_user)):
    return get_week(start or None)

@app.get("/api/calendar/sources")
async def calendar_sources(user: bool = Depends(get_current_user)):
    return get_sources()

@app.get("/api/calendar/upcoming")
async def calendar_upcoming(user: bool = Depends(get_current_user)):
    return get_upcoming()

@app.post("/api/calendar/refresh")
async def calendar_refresh(user: bool = Depends(get_current_user)):
    return refresh_calendar()

# Backwards-compatible alias for the original single calendar route.
@app.get("/api/calendar")
async def calendar_events(user: bool = Depends(get_current_user)):
    return get_upcoming()

@app.get("/api/photos")
async def list_photos(user: bool = Depends(get_current_user)):
    return get_photos_payload()

@app.get("/api/photos/random")
async def random_photo(user: bool = Depends(get_current_user)):
    return {"photo": get_random_photo()}
