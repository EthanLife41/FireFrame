import psutil
import time

BOOT_TIME = psutil.boot_time()

# Prime the CPU counter so later interval=None reads are non-blocking
# (usage since the previous poll) instead of stalling the event loop.
psutil.cpu_percent(interval=None)

def get_mac_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)  # non-blocking (primed above)
    
    # RAM
    mem = psutil.virtual_memory()
    ram_percent = mem.percent
    ram_used_gb = round(mem.used / (1024 ** 3), 1)
    ram_total_gb = round(mem.total / (1024 ** 3), 1)
    
    # Battery (may not be available on all Macs)
    battery = psutil.sensors_battery()
    battery_available = False
    battery_percent = 0
    if battery:
        battery_available = True
        battery_percent = int(battery.percent)
        
    # Uptime
    uptime_seconds = int(time.time() - BOOT_TIME)
    
    # GPU skipped on purpose: system_profiler is slow and leaks identifiers.
    gpu_available = False
    gpu_note = "GPU stats unavailable on this macOS setup without heavy polling."
    
    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "gpu_available": gpu_available,
        "gpu_note": gpu_note,
        "battery_available": battery_available,
        "battery_percent": battery_percent,
        "uptime_seconds": uptime_seconds
    }
