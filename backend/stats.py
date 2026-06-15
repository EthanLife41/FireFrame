import os
import platform
import time

import psutil

BOOT_TIME = psutil.boot_time()
_IS_MAC = platform.system() == "Darwin"

# Prime the CPU counter so later interval=None reads are non-blocking
# (usage since the previous poll) instead of stalling the event loop.
psutil.cpu_percent(interval=None)

# Disk capacity barely moves, so cache it for a minute.
_disk_cache = {"ts": 0.0, "data": None}


def _disk():
    now = time.time()
    if _disk_cache["data"] is not None and (now - _disk_cache["ts"]) < 60:
        return _disk_cache["data"]
    # On macOS the user-visible storage is the Data volume, not the read-only "/".
    path = "/System/Volumes/Data" if _IS_MAC and os.path.isdir("/System/Volumes/Data") else "/"
    try:
        u = psutil.disk_usage(path)
        data = {
            "disk_percent": u.percent,
            "disk_used_gb": round(u.used / (1024 ** 3), 1),
            "disk_total_gb": round(u.total / (1024 ** 3), 1),
        }
    except OSError:
        data = {"disk_percent": None, "disk_used_gb": None, "disk_total_gb": None}
    _disk_cache.update(ts=now, data=data)
    return data


def get_home_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)  # non-blocking (primed above)

    mem = psutil.virtual_memory()
    ram_percent = mem.percent
    # used = total - available keeps used/total in step with the percentage;
    # psutil's mem.used omits cached/compressed memory on macOS.
    ram_used_gb = round((mem.total - mem.available) / (1024 ** 3), 1)
    ram_total_gb = round(mem.total / (1024 ** 3), 1)

    battery = psutil.sensors_battery()
    battery_available = False
    battery_percent = 0
    battery_charging = False
    if battery:
        battery_available = True
        battery_percent = int(battery.percent)
        battery_charging = bool(battery.power_plugged)

    uptime_seconds = int(time.time() - BOOT_TIME)

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        **_disk(),
        "battery_available": battery_available,
        "battery_percent": battery_percent,
        "battery_charging": battery_charging,
        "uptime_seconds": uptime_seconds,
    }
