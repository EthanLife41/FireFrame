# FireFrame

A local-first, personal dashboard meant to turn an Amazon Fire HD 8 tablet into a "Stream Deck" controller and desk companion for macOS.

## Security Model

**The Fire tablet is treated as entirely untrusted.**

It should not have any Google, Apple, or sensitive accounts signed in.
This dashboard runs locally on your Mac. The tablet merely displays the UI and sends predefined "Action IDs" (e.g. `toggle_dnd`) to the Mac. The Mac backend validates these IDs and runs fixed, allowlisted commands. The tablet cannot run arbitrary shell commands. 

This project is intended for **local-network use only** and should **not** be exposed to the public internet. Please see `SECURITY.md` for more details.

## Features

- **Large Touch Buttons:** Trigger Mac Shortcuts or open specific workflows.
- **Bluetooth Selector:** A macOS Control-Center-style panel that lists paired/known devices via the built-in `system_profiler`, with optional connect/disconnect when `blueutil` is installed.
- **Live Mac Stats:** See real-time CPU, RAM, Battery, and Uptime.
- **Calendar:** Today + upcoming agenda from a pluggable local source (demo data, a local `.ics` file, or Apple Calendar).
- **Photos:** Local photo slideshow with shuffle, pause/resume, lock-on-photo, and prev/next/random controls.
- **Pomodoro Timer:** Built into the frontend for quick access.

> **Runtime target:** FireFrame is designed to run from a **macOS** laptop. The Bluetooth and Calendar features use macOS tools; on other platforms they degrade gracefully (clear "unsupported / not connected" states) so you can still develop the UI.

## Setup Instructions

1. **Clone the repository:** (Or navigate to the downloaded directory)
2. **Create a virtual environment & install requirements:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure Environment:**
   Copy the example environment file and set your custom password and secret.
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor and set DASHBOARD_PASSWORD and SESSION_SECRET
   ```
4. **Configure Local Settings (Optional):**
   Copy the example config file to enable/disable buttons and set custom URLs or Bluetooth identifiers.
   ```bash
   cp backend/config.example.py backend/config.py
   # Edit backend/config.py to match your local setup
   ```
5. **Run the server:**
   ```bash
   ./scripts/start.sh
   ```
6. **Open on Tablet:**
   Find your Mac's local IP address (e.g., `192.16.1.X`) and open `http://<MAC_LOCAL_IP>:8765` on the Fire tablet.

## Development vs. hosting

**Develop** (editing/testing on any machine, e.g. a remote Linux box):

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
# localhost only, auto-reload:
./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```

To reach it from another machine, tunnel instead of exposing the port:
`ssh -L 8765:127.0.0.1:8765 <dev-box>`. Off macOS the UI/stats/photos work; the
Shortcuts/`open` actions just return a failure message (run them on the Mac).

If `venv` reports `ensurepip` is missing (minimal Debian/Ubuntu):

```bash
python3 -m venv .venv --without-pip
curl -sSL https://bootstrap.pypa.io/get-pip.py | ./.venv/bin/python -
./.venv/bin/python -m pip install -r requirements.txt
```

**Host** (the live workflow, from your Mac): `git pull`, then `./scripts/start.sh`.

## Adding Buttons Safely

To add a new safe action:
1. Define a new action ID in your `config.py` (or `actions.py` for core logic).
2. Add metadata (label, category, enabled status).
3. Add a handler in the backend that maps the action ID to a safe, list-based `subprocess.run()` command. Never use `shell=True` or accept arbitrary commands from the frontend.

## Adding Photos

Manually copy `.jpg`, `.jpeg`, `.png`, `.gif`, or `.webp` files into the `photos/` directory. They will be automatically served by the local backend. See `photos/README.md` for details. Do not commit personal photos to Git.

To keep your pictures outside the repository entirely, set `PHOTOS_DIR` in `.env` to any local folder. The Photos tab supports shuffle, pause/resume, lock-on-photo, and prev/next/random; your shuffle/pause/locked preferences persist in the browser via `localStorage`. The default slideshow interval is `PHOTO_INTERVAL_SECONDS` (30s).

## macOS Shortcuts Setup

To make the default buttons work, create the following Shortcuts in the macOS Shortcuts app:

- `Desk Toggle DND`: Toggles Focus mode on/off.
- `Desk Toggle Locked In Mode`: Toggles a specific "Locked In" Focus mode on/off.
- `Desk Sleep Mode`: Toggles a sleep mode or runs a specific bedtime script.
- `Desk Bluetooth Toggle`: Toggles Bluetooth on/off.
- `Desk Connect Headphones`: Connects to your specific Bluetooth headphones.
- `Desk Disconnect Headphones`: Disconnects your headphones.
- `Desk Connect Speaker`: Connects to your Bluetooth speaker.
- `Desk Disconnect Speaker`: Disconnects your Bluetooth speaker.

The backend calls these exactly by name using `shortcuts run "Shortcut Name"`.

## macOS Feature Configuration

All feature config is supplied through environment variables (see `.env.example`). Nothing personal is stored in the repo.

| Variable | Default | Purpose |
|---|---|---|
| `CALENDAR_SOURCE` | `none` | `none` \| `demo` \| `ics` \| `apple` |
| `CALENDAR_ICS_PATH` | _(empty)_ | Local `.ics` path (used when source is `ics`) |
| `CALENDAR_UPCOMING_DAYS` | `7` | How many days ahead to include |
| `PHOTOS_DIR` | _(empty → `./photos`)_ | Folder to read photos from |
| `PHOTO_INTERVAL_SECONDS` | `30` | Slideshow auto-advance interval |
| `BLUETOOTH_ALLOW_CONNECT` | `1` | Set `0` to disable connect/disconnect |

### Bluetooth (macOS)

- **Listing/status** uses the built-in `system_profiler SPBluetoothDataType` — no Homebrew, no third-party tools, read-only.
- **Connect/disconnect** is optional and uses [`blueutil`](https://github.com/toy/blueutil) **only if it is installed**: `brew install blueutil`. Without it, the panel still lists devices and shows a clear "connect/disconnect unsupported" note.
- Real Bluetooth addresses never reach the tablet — the UI only receives opaque per-device tokens, and every address is validated before use. No `shell=True`.
- On non-macOS machines the panel shows an "unavailable on this platform" state (Linux Bluetooth is intentionally **not** implemented).

### Calendar (macOS)

Pick a source with `CALENDAR_SOURCE`:

- `none` — default; the tab shows "Calendar not connected".
- `demo` — built-in placeholder events (handy for UI testing).
- `ics` — point `CALENDAR_ICS_PATH` at a local `.ics` file (e.g. an exported/sync'd calendar). No extra dependencies. `*.ics` files are gitignored.
- `apple` — reads **Apple Calendar** via `osascript`/JXA. The first run prompts for **Automation** permission: approve it under **System Settings → Privacy & Security → Automation**. If denied or unavailable, the tab shows a clear error and you can fall back to `ics`.

Event details are never written to logs.

### Mac Stats

Uses `psutil` to fetch CPU, RAM, Battery, and Uptime securely. GPU stats on macOS are limited; we provide a best-effort fallback without installing heavy dependencies. Stats polling does not expose usernames, serial numbers, or process lists.

## Using on Fire Tablet with Fully Kiosk Browser

The dashboard is designed to run inside **Fully Kiosk Browser** on the Amazon Fire HD 8.

### Recommended browser

[Fully Kiosk Browser](https://www.fully-kiosk.com/) (available on Amazon Appstore or sideloaded via APK).

> ⚠️ Normal browsers (Silk, Chrome) cannot reliably be forced into true fullscreen. Fully Kiosk's kiosk mode is the cleanest option.

### Recommended Fully Kiosk settings

| Setting | Value |
|---|---|
| Start URL | `http://MAC_LOCAL_IP:8765` |
| Enable fullscreen mode | ✅ |
| Hide address bar | ✅ |
| Keep screen on | ✅ |
| Lock orientation | Landscape |
| Reload on network reconnect | ✅ |
| Use dark theme | ✅ if available |

### IP stability

Set a **DHCP reservation** on your router so that your Mac always gets the same local IP address. This prevents the Start URL from breaking after a router reboot.

### PIN login

The dashboard uses a **tap-based numeric PIN pad** so you do not need the Fire tablet's soft keyboard. The PIN is the value you set as `DASHBOARD_PASSWORD` in your `.env` file (e.g. `0000`). A standard keyboard password fallback is also available via the small link below the keypad.

> **Important:** After editing `.env`, you **must restart the server** (`./scripts/stop.sh && ./scripts/start.sh`) for the new password to take effect.

### Login rate limiting

After **5 failed login attempts**, the IP is locked out for **30 seconds**. This prevents brute-force attacks from other devices on the same Wi-Fi.

### Exiting Fully Kiosk

- Use the Fully Kiosk admin overlay (if configured).
- Swipe up from the bottom to open Android's recent-apps view.
- Force-stop the app from Fire OS → Settings → Apps.
- Reboot the tablet as a last resort.

### In-app Fullscreen button

The Settings tab and login screen both have a **"Request Fullscreen"** button that calls the browser Fullscreen API. Some browsers block this unless triggered by a user gesture. If it is blocked, a toast message will explain this and recommend using Fully Kiosk's own fullscreen setting instead.

---

## One-Click Launch on macOS

After the one-time setup above (venv + requirements installed on the Mac), you can start the server without opening a terminal:

1. **`launch-mac.command`** (included) — double-click it in Finder to open Terminal and run the server; close the window or press `Ctrl+C` to stop. First run, macOS may block it: right-click → **Open** once. Drag it onto the Dock for one-tap launch, and set a custom icon via **Finder → Get Info → paste an image onto the icon**.
2. **App with a real icon** — Open **Automator → New → Application → "Run Shell Script"**, paste `cd "$HOME/path/to/FireFrame" && ./scripts/start.sh`, and save as `FireFrame.app` in `/Applications` or the Dock.

To start automatically at login instead of on a click, see *Running at Login* below.

## Running at Login

An example launchd plist is provided in `scripts/launchd/com.example.deskcompanion.plist.example`.
You can copy this file to `~/Library/LaunchAgents/` and edit the paths to match your local setup to run the server automatically on boot. Do not modify system files without understanding the consequences.

## Troubleshooting

- **Password not working after change**: Stop and restart the server — `.env` is only read on startup.
- **Actions failing**: Check the server logs. Ensure the macOS Shortcuts are named correctly and that the terminal running the server has Automation/Accessibility permissions.
- **Disabling Risky Actions**: Edit `backend/config.py` and set `"enabled": False` for any action you want to disable.
- **Calendar**: Configure `CALENDAR_SOURCE` (see *macOS Feature Configuration*). If `apple` shows an error, grant Automation permission or switch to a local `.ics` file.
- **Bluetooth connect/disconnect greyed out**: install the optional `blueutil` (`brew install blueutil`) and restart the server. Listing/status work without it.

## Open-Source Publishing Checklist

Before publishing this repository or your fork publicly:
- [ ] Ensure `.env` is removed and gitignored.
- [ ] Ensure personal photos are removed from `photos/`.
- [ ] Ensure personal URLs and local IPs are removed from any committed config files.
- [ ] Check that `backend/config.py` is ignored and use `backend/config.example.py` for the repo.
- [ ] Clear logs and `__pycache__` directories.
- [ ] Confirm `.gitignore` is working.
- [ ] Ensure no real Bluetooth identifiers are committed.

## License

[PLACEHOLDER - Choose a license before publishing (e.g., MIT, GPL, etc.)]
