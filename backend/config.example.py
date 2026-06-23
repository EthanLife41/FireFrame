"""Optional local overrides for FireFrame.

Every setting has a default in backend/config_loader.py, driven by environment
variables (.env). For most setups, editing .env is all you need.

To override values in code (for example to rename a button's Shortcut or the app
it opens), copy this file to backend/config.py (gitignored) and uncomment what
you want to change. Any UPPERCASE name defined here replaces the default of the
same name; backend/config_loader.py stays the source of truth for the rest.
"""

# --- Buttons tab -----------------------------------------------------------
# The full default registry lives in backend/config_loader.py. Defining
# SHORTCUT_ACTIONS here replaces it wholesale (it is not merged), so copy across
# every entry you want to keep, then edit the Shortcut/app names. Types:
#   shortcut | open_app | open_url | open_app_or_url | mute | sleep_mac | prepare
#
# SHORTCUT_ACTIONS = {
#     "dnd":          {"type": "shortcut", "shortcut": "FireFrame DND"},
#     "open_spotify": {"type": "open_app", "app": "Spotify"},
#     "gpt":          {"type": "open_app_or_url", "app": "ChatGPT",
#                      "url": "https://chatgpt.com/", "label": "ChatGPT"},
# }

# --- "Prepare" button ------------------------------------------------------
# Apps and links the Prepare action opens.
#
# PREPARE_APPS = ["Spotify", "Discord"]
# PREPARE_URLS = ["https://www.google.com"]

# --- Tasks -----------------------------------------------------------------
# Scheduled calendar blocks. Leave TASK_DEFAULT_CALENDAR blank to auto-pick a
# calendar named like "Tasks" (else the system default), or set a name to force
# the target. Durations are per importance level, in minutes.
#
# TASK_DEFAULT_CALENDAR = ""
# TASK_REGULAR_DURATION_MINUTES = 60
# TASK_IMPORTANT_DURATION_MINUTES = 240
# Where "Add Task" collects input: "dashboard" or "mac_prompt".
# TASK_INPUT_LOCATION = "dashboard"
