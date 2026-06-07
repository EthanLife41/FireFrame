"""Lightweight local system stats for the Mac Stats dashboard.

Everything here is read-only and cheap. psutil covers CPU, memory, battery,
disk, processes, and network counters. A few macOS extras (computer name, Wi-Fi
name, volume, now playing) shell out to small, well-known commands and are
cached so they never run on every poll. Heavier reads are serialised behind a
lock so two requests can't spawn the same subprocess at once. Nothing is logged
and nothing is written to disk.
"""

import platform
import socket
import subprocess
import threading
import time

import psutil

_IS_MAC = platform.system() == "Darwin"

# Prime the system-wide CPU counter so interval=None reads are non-blocking
# (usage since the previous call) rather than stalling for a sample.
psutil.cpu_percent(interval=None)
# Prime per-process CPU too: process_iter caches its Process objects, so the
# first real scan already has a baseline to measure against.
try:
    list(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]))
except Exception:
    pass

_BOOT = psutil.boot_time()
_lock = threading.Lock()        # serialises subprocess-backed reads
_net_lock = threading.Lock()    # guards the network-rate baseline
_net_prev = {"ts": 0.0, "sent": 0, "recv": 0}

# Simple TTL cache: key -> {"value": ..., "ts": float}
_cache = {}


def _cached(key, ttl, producer, lock=False):
    """Return a cached value, refreshing it past its TTL. When lock=True the
    refresh happens under _lock with a re-check, so a slow producer (a
    subprocess) only ever runs once even under concurrent requests."""
    hit = _cache.get(key)
    if hit and (time.time() - hit["ts"]) < ttl:
        return hit["value"]
    if lock:
        with _lock:
            hit = _cache.get(key)
            if hit and (time.time() - hit["ts"]) < ttl:
                return hit["value"]
            value = producer()
            _cache[key] = {"value": value, "ts": time.time()}
            return value
    value = producer()
    _cache[key] = {"value": value, "ts": time.time()}
    return value


def _run(cmd, timeout=4):
    """Run a command without a shell. Return stripped stdout, or None on any
    failure (missing command, non-zero exit, timeout)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


# --- system overview (cached long; this rarely changes) ---

def _wifi_interface():
    out = _run(["networksetup", "-listallhardwareports"])
    if not out:
        return None
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "Wi-Fi" in line or "AirPort" in line:
            for j in range(i, min(i + 3, len(lines))):
                if lines[j].startswith("Device:"):
                    return lines[j].split(":", 1)[1].strip()
    return None


def _system_info():
    def produce():
        name = None
        if _IS_MAC:
            name = _run(["scutil", "--get", "ComputerName"], timeout=3)
        if not name:
            try:
                name = socket.gethostname().split(".")[0]
            except Exception:
                name = None
        if _IS_MAC:
            os_name, os_version = "macOS", platform.mac_ver()[0] or ""
        else:
            os_name, os_version = platform.system() or "System", platform.release() or ""
        return {
            "name": name or "Mac",
            "os_name": os_name,
            "os_version": os_version,
            "cpu_cores_logical": psutil.cpu_count(logical=True) or 0,
            "cpu_cores_physical": psutil.cpu_count(logical=False) or 0,
            "wifi_iface": _wifi_interface() if _IS_MAC else None,
        }
    return _cached("system", 3600, produce, lock=True)


# --- CPU ---

def _cpu():
    info = _system_info()
    return {
        "percent": psutil.cpu_percent(interval=None),
        "cores_logical": info["cpu_cores_logical"],
        "cores_physical": info["cpu_cores_physical"],
    }


# --- memory ---

def _memory():
    m = psutil.virtual_memory()
    return {
        "percent": m.percent,
        "used_gb": round(m.used / 1024 ** 3, 1),
        "total_gb": round(m.total / 1024 ** 3, 1),
        "available_gb": round(m.available / 1024 ** 3, 1),
    }


# --- battery ---

def _battery():
    try:
        b = psutil.sensors_battery()
    except Exception:
        b = None
    if not b:
        return {"available": False}
    # secsleft is negative when unknown or on AC power, so a >= 0 check is enough.
    time_left = None
    secs = b.secsleft
    if secs is not None and secs >= 0:
        time_left = f"{secs // 3600}h {(secs % 3600) // 60}m"
    return {
        "available": True,
        "percent": int(round(b.percent)),
        "charging": bool(b.power_plugged),
        "power_source": "AC Power" if b.power_plugged else "Battery",
        "time_left": time_left,
    }


# --- disk (cached; capacity changes slowly) ---

def _disk():
    def produce():
        try:
            u = psutil.disk_usage("/")
        except Exception:
            return {"available": False}
        return {
            "available": True,
            "percent": u.percent,
            "used_gb": round(u.used / 1024 ** 3, 1),
            "total_gb": round(u.total / 1024 ** 3, 1),
            "free_gb": round(u.free / 1024 ** 3, 1),
        }
    return _cached("disk", 60, produce)


# --- network ---

def _local_ip():
    # Open a UDP socket to a reserved (TEST-NET) address to learn the outbound
    # interface IP. No packets are sent and no DNS lookup happens.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 53))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


def _wifi_ssid(iface):
    if not (_IS_MAC and iface):
        return None
    out = _run(["networksetup", "-getairportnetwork", iface])
    if not out or "not associated" in out.lower() or ":" not in out:
        return None
    ssid = out.split(":", 1)[1].strip()
    # Recent macOS may redact the SSID when Location access isn't granted.
    if not ssid or ssid.lower() in ("", "<redacted>"):
        return None
    return ssid


def _network_addr():
    def produce():
        return {
            "local_ip": _local_ip(),
            "wifi_ssid": _wifi_ssid(_system_info().get("wifi_iface")),
        }
    return _cached("net_addr", 45, produce, lock=True)


def _network_speed():
    try:
        c = psutil.net_io_counters()
    except Exception:
        return {"up_bps": 0.0, "down_bps": 0.0}
    now = time.time()
    up = down = 0.0
    with _net_lock:
        if _net_prev["ts"]:
            dt = now - _net_prev["ts"]
            if dt > 0:
                up = max(0.0, (c.bytes_sent - _net_prev["sent"]) / dt)
                down = max(0.0, (c.bytes_recv - _net_prev["recv"]) / dt)
        _net_prev.update(ts=now, sent=c.bytes_sent, recv=c.bytes_recv)
    return {"up_bps": up, "down_bps": down}


# --- top processes (cached briefly; a scan isn't free) ---

def _processes():
    def produce():
        cores = psutil.cpu_count(logical=True) or 1
        rows = []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            info = p.info
            rows.append({
                "name": info.get("name") or "?",
                "cpu": info.get("cpu_percent") or 0.0,
                "mem": info.get("memory_percent") or 0.0,
            })
        # cpu_percent is per-core (can exceed 100); show share of the whole CPU.
        fmt = lambda r: {"name": r["name"], "cpu": round(r["cpu"] / cores, 1), "mem": round(r["mem"], 1)}
        by_cpu = [fmt(r) for r in sorted(rows, key=lambda r: r["cpu"], reverse=True)[:5]]
        by_mem = [fmt(r) for r in sorted(rows, key=lambda r: r["mem"], reverse=True)[:5]]
        return {"by_cpu": by_cpu, "by_mem": by_mem}
    return _cached("processes", 10, produce, lock=True)


# --- volume (macOS, cached) ---

def _volume():
    if not _IS_MAC:
        return {"available": False}

    def produce():
        out = _run([
            "osascript", "-e",
            "set v to output volume of (get volume settings)\n"
            "set m to output muted of (get volume settings)\n"
            'return (v as text) & "," & (m as text)',
        ])
        if not out or "," not in out:
            return {"available": False}
        vol_s, mute_s = out.split(",", 1)
        try:
            return {"available": True, "percent": int(vol_s.strip()),
                    "muted": mute_s.strip().lower() == "true"}
        except ValueError:
            return {"available": False}
    return _cached("volume", 10, produce, lock=True)


# --- public API ---

def get_mac_stats() -> dict:
    info = _system_info()
    addr = _network_addr()
    return {
        "platform": platform.system(),
        "is_mac": _IS_MAC,
        "system": {
            "name": info["name"],
            "os_name": info["os_name"],
            "os_version": info["os_version"],
            "uptime_seconds": int(time.time() - _BOOT),
        },
        "cpu": _cpu(),
        "memory": _memory(),
        "battery": _battery(),
        "disk": _disk(),
        "network": {
            "local_ip": addr["local_ip"],
            "wifi_ssid": addr["wifi_ssid"],
            **_network_speed(),
        },
        "processes": _processes(),
        "volume": _volume(),
    }
