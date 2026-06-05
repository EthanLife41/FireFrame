import subprocess
from backend.actions import run_shortcut
from backend.config_loader import ACTION_CONFIG, BLUETOOTH_DEVICES

def handle_bluetooth_action(action_id: str, params: dict) -> dict:
    config = ACTION_CONFIG.get(action_id, {})
    if not config.get("enabled", False):
        return {"success": False, "message": f"Action '{action_id}' is disabled or unknown."}

    if action_id == "bluetooth_toggle":
        return run_shortcut("Desk Bluetooth Toggle")
        
    elif action_id == "bluetooth_connect_headphones":
        # Check if headphones are enabled in config
        if not BLUETOOTH_DEVICES.get("headphones", {}).get("enabled", False):
            return {"success": False, "message": "Headphones are not enabled in config."}
        return run_shortcut("Desk Connect Headphones")
        
    elif action_id == "bluetooth_disconnect_headphones":
        if not BLUETOOTH_DEVICES.get("headphones", {}).get("enabled", False):
            return {"success": False, "message": "Headphones are not enabled in config."}
        return run_shortcut("Desk Disconnect Headphones")
        
    elif action_id == "bluetooth_connect_speaker":
        if not BLUETOOTH_DEVICES.get("speaker", {}).get("enabled", False):
            return {"success": False, "message": "Speaker is not enabled in config."}
        return run_shortcut("Desk Connect Speaker")
        
    elif action_id == "bluetooth_disconnect_speaker":
        if not BLUETOOTH_DEVICES.get("speaker", {}).get("enabled", False):
            return {"success": False, "message": "Speaker is not enabled in config."}
        return run_shortcut("Desk Disconnect Speaker")
        
    elif action_id == "open_bluetooth_settings":
        try:
            # Try specific settings pane
            subprocess.run(
                ["open", "x-apple.systempreferences:com.apple.BluetoothSettings"],
                check=True,
                capture_output=True,
                timeout=5
            )
            return {"success": True, "message": "Opened Bluetooth Settings."}
        except Exception:
            try:
                # Fallback to general system settings
                subprocess.run(
                    ["open", "-b", "com.apple.systempreferences"],
                    check=True,
                    capture_output=True,
                    timeout=5
                )
                return {"success": True, "message": "Opened System Settings."}
            except Exception:
                return {"success": False, "message": "Could not open Settings."}
                
    return {"success": False, "message": f"Handler for '{action_id}' not found."}

def get_bluetooth_status() -> dict:
    # Best-effort for v1: just return placeholder status.
    # We do not want to expose real MAC addresses to the frontend.
    return {
        "bluetooth_state": "unknown",
        "connected_devices": [],
        "note": "Bluetooth status detection is not implemented yet."
    }
