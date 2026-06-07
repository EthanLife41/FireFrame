import subprocess
from backend.config_loader import ACTION_CONFIG, PREPARE_LAPTOP_URLS

def run_shortcut(shortcut_name: str) -> dict:
    try:
        # Never use shell=True
        subprocess.run(
            ["shortcuts", "run", shortcut_name],
            check=True,
            capture_output=True,
            timeout=10
        )
        return {"success": True, "message": f"Shortcut '{shortcut_name}' ran successfully."}
    except subprocess.CalledProcessError as e:
        return {"success": False, "message": f"Shortcut failed to run. Make sure '{shortcut_name}' exists."}
    except FileNotFoundError:
        return {"success": False, "message": "The 'shortcuts' command is not available."}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Shortcut execution timed out."}

def run_open_command(app_name: str) -> dict:
    try:
        subprocess.run(
            ["open", "-a", app_name],
            check=True,
            capture_output=True,
            timeout=5
        )
        return {"success": True, "message": f"Opened '{app_name}'."}
    except Exception as e:
        return {"success": False, "message": f"Failed to open '{app_name}'."}

def open_urls(urls: list) -> dict:
    successes = 0
    for url in urls:
        try:
            subprocess.run(["open", url], check=True, capture_output=True, timeout=5)
            successes += 1
        except Exception:
            pass
    return {"success": True, "message": f"Opened {successes} URLs."}

def handle_action(action_id: str, params: dict) -> dict:
    config = ACTION_CONFIG.get(action_id, {})
    if not config.get("enabled", False):
        return {"success": False, "message": f"Action '{action_id}' is disabled or unknown."}

    if action_id == "toggle_dnd":
        return run_shortcut("Desk Toggle DND")

    elif action_id == "toggle_locked_in":
        return run_shortcut("Desk Toggle Locked In Mode")

    elif action_id == "sleep_mode_alarm":
        wake_time = params.get("wake_time")
        if not wake_time:
            return {"success": False, "message": "Wake time is required."}
        # Runs the shortcut without args; wake_time is just echoed back for now.
        res = run_shortcut("Desk Sleep Mode")
        if res["success"]:
            res["message"] = f"Sleep Mode activated. Alarm set for {wake_time}."
        return res

    elif action_id == "open_calendar":
        return run_open_command("Calendar")

    elif action_id == "prepare_laptop":
        run_open_command("Google Chrome")
        run_open_command("Spotify")
        run_open_command("Discord")
        run_open_command("Slack")
        open_urls(PREPARE_LAPTOP_URLS)
        return {"success": True, "message": "Laptop prepared."}

    elif action_id == "open_assistant":
        return open_urls(["https://chatgpt.com/"])

    else:
        # Check if it's a bluetooth action, handled in bluetooth.py
        return {"success": False, "message": f"Handler for '{action_id}' not found."}
