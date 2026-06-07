# FireFrame

A local dashboard that turns an Amazon Fire HD 8 tablet into a desk control panel for your Mac: large touch buttons, live Mac stats, a Bluetooth device picker, your calendar, and a photo slideshow. FireFrame runs on your Mac; the tablet just displays it over your local Wi-Fi.

## How it works and security

The Fire tablet is treated as **untrusted**. It should not be signed into any personal accounts. The tablet only shows the UI and sends fixed action IDs (like `toggle_dnd`); the Mac validates each ID and runs a small allowlist of commands. The tablet can never run arbitrary commands.

Run it on your **local network only**. Do not port-forward it or expose it to the internet. See `SECURITY.md` for the full model.

## Features

- **Buttons:** large touch tiles that trigger macOS Shortcuts or open apps and URLs.
- **Bluetooth:** a Control-Center-style device list (built-in `system_profiler`), with connect/disconnect when `blueutil` is present.
- **Calendar:** today and upcoming events from Apple Calendar, a local or remote `.ics`, or demo data.
- **Photos:** a slideshow with shuffle, pause, lock-on-photo, and prev/next/random.
- **Mac stats:** CPU, RAM, battery, and uptime.
- **Pomodoro timer:** built in.

> FireFrame targets **macOS**. Bluetooth and Calendar use macOS tools; on other systems they show a clear "unavailable / not connected" state so you can still work on the UI.

## Quick start (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set DASHBOARD_PASSWORD and SESSION_SECRET
./scripts/start.sh            # serves on 0.0.0.0:8765
```

Find your Mac's LAN IP (System Settings > Wi-Fi > Details, e.g. `192.168.x.x`) and open `http://<MAC_IP>:8765` on the tablet.

- The login PIN is your `DASHBOARD_PASSWORD`. Use a 4-digit value for the keypad; a keyboard fallback handles longer passwords.
- `.env` is read only at startup, so restart the server after editing it.
- Optional: `cp backend/config.example.py backend/config.py` to customize buttons, "prepare laptop" URLs, and Bluetooth device labels.

## Configuration

Set these in `.env` (copied from `.env.example`). Nothing personal is committed.

| Variable | Default | Purpose |
|---|---|---|
| `DASHBOARD_PASSWORD` | `change-me` | Login PIN / password |
| `SESSION_SECRET` | `change-this-random-string` | Signs the session cookie (use a long random value) |
| `PORT` | `8765` | Server port |
| `CALENDAR_SOURCE` | `none` | `none`, `demo`, `ics`, or `apple` |
| `CALENDAR_ICS_PATH` | _(empty)_ | `.ics` file path or https URL (used by `ics`) |
| `CALENDAR_ICS_PATHS` | _(empty)_ | Several `.ics` paths at once, `:`-separated |
| `CALENDAR_UPCOMING_DAYS` | `7` | Days ahead the Home card looks |
| `CALENDAR_REFRESH_SECONDS` | `300` | How long calendar reads are cached |
| `PHOTOS_DIR` | _(empty, uses `./photos`)_ | Folder to read photos from |
| `PHOTO_INTERVAL_SECONDS` | `30` | Slideshow interval |
| `BLUETOOTH_ALLOW_CONNECT` | `1` | Set `0` to disable connect/disconnect |
| `BLUEUTIL_PATH` | _(empty)_ | Path to blueutil (auto-detected if empty) |

## Calendar setup

Set `CALENDAR_SOURCE`, restart, and open the Calendar tab. The Calendar tab is a schedule grid with **Day** and **Week** views (Week is the default): a Today button, previous/next navigation, a time axis, rounded event blocks placed by time, and an all-day row. When more than one calendar has events, source-filter chips appear so you can hide or show each one.

**Apple Calendar (`apple`) is the recommended option.** It reads every accessible calendar in macOS Calendar.app (including Google accounts you have added there) and handles recurring events.

1. Set `CALENDAR_SOURCE=apple`.
2. **Install the fast reader (recommended, macOS only):** `./.venv/bin/python -m pip install pyobjc-framework-EventKit` (into the same environment that runs the server). FireFrame uses EventKit when present and otherwise falls back to a much slower AppleScript path that can time out on large calendars.
3. Restart. The first load asks for **Calendar** access; approve it. If it does not appear or it errors, enable it under **System Settings > Privacy & Security > Calendars** (and **Automation** if you are on the AppleScript fallback). The grant attaches to whatever launches the server, so re-approve if you change launcher.

To include Google here, add the account in Calendar.app (**Settings > Accounts > + > Google**).

**ICS file or URL (`ics`)** is good for a single Google calendar without Calendar.app.

- Google: in Google Calendar (web), open the calendar's **Settings and sharing > Integrate calendar > Secret address in iCal format**, then set:
  ```
  CALENDAR_SOURCE=ics
  CALENDAR_ICS_PATH=https://calendar.google.com/calendar/ical/.../basic.ics
  ```
- Or point `CALENDAR_ICS_PATH` at a local `.ics` file you export.
- For several calendars at once, list them in `CALENDAR_ICS_PATHS`, separated by `:` (each file's name becomes its source label).

That URL is a credential: keep it in `.env` (gitignored) and never commit it. The built-in parser does not expand recurring events, so for recurring-heavy calendars prefer `apple`.

**demo / none.** `demo` shows placeholder events; `none` (the default) shows "not connected".

## Bluetooth setup

Listing and status work out of the box on macOS via `system_profiler` (read-only, no extra tools). Real device addresses stay on the Mac; the tablet only ever sees a token per device.

Connect/disconnect needs the small [`blueutil`](https://github.com/toy/blueutil) CLI:

```bash
# Homebrew (simplest):
brew install blueutil

# Or keep it inside the project, no global install:
git clone https://github.com/toy/blueutil /tmp/blueutil
make -C /tmp/blueutil
mkdir -p bin && cp /tmp/blueutil/blueutil bin/   # FireFrame auto-detects ./bin/blueutil
```

`bin/` is gitignored. You can also set `BLUEUTIL_PATH` to an explicit location. blueutil acts on already-paired devices, so pair new ones in macOS Bluetooth settings first. Bluetooth control is macOS-only.

## Photos

Copy `.jpg`, `.jpeg`, `.png`, `.gif`, or `.webp` files into `photos/`, or set `PHOTOS_DIR` to a folder outside the repo. The Photos tab has shuffle, pause/resume, lock (stops on the current photo), and prev/next/random. Your shuffle/pause/locked choices persist in the browser via `localStorage`. Personal photos are gitignored and never committed.

## Buttons tab (macOS control centre)

The Buttons tab is grouped into **Focus & Modes**, **Mac Controls**, **Apps & Tools**, **Timers**, and **FireFrame**. Each button maps to an entry in the `SHORTCUT_ACTIONS` registry in `backend/config.py` (or the defaults in `backend/config_loader.py`). The browser only ever sends the registry **key** — never a command — and the backend runs the matching `shortcuts run`, `open`, or small fixed command (never `shell=True`). To customise, copy `backend/config.example.py` to `backend/config.py` (gitignored) and edit the Shortcut/app names.

Focus modes have no command-line equivalent on macOS, so they go through Shortcuts you create in the **Shortcuts app**. The others work out of the box.

| Button | What it does | Type | Setup | Permissions | Test in Terminal |
|---|---|---|---|---|---|
| DND | Enables Do Not Disturb / Focus | macOS Shortcut | Create **FireFrame DND** | Shortcuts/Focus | `shortcuts run "FireFrame DND"` |
| Locked In | Starts deep-work Focus | macOS Shortcut | Create **FireFrame Locked In** | Focus | `shortcuts run "FireFrame Locked In"` |
| Presentation | Presentation Focus + muted notifications | macOS Shortcut | Create **FireFrame Presentation Mode** | Focus | `shortcuts run "FireFrame Presentation Mode"` |
| Break | Switches to a break Focus | macOS Shortcut | Create **FireFrame Break Mode** | Optional | `shortcuts run "FireFrame Break Mode"` |
| Sleep Mode | Enables **Sleep Focus** (not sleeping the Mac) | macOS Shortcut | Create **FireFrame Sleep Mode** | Focus | `shortcuts run "FireFrame Sleep Mode"` |
| Sleep Mac | Sleeps this Mac (asks to confirm first) | Direct (`pmset sleepnow`) | None | May need Energy access | `pmset sleepnow` |
| Mute | Toggles system mute | Direct (`osascript`) | None | Usually none | `osascript -e 'set volume output muted true'` |
| Display | Opens Display settings | Direct (`open` URL) | None | None | `open "x-apple.systempreferences:com.apple.Displays-Settings.extension"` |
| Spotify | Opens Spotify | Direct (`open -a`) | Install Spotify | None | `open -a Spotify` |
| Quick Note | New quick note | macOS Shortcut | Create **FireFrame Quick Note** | Shortcuts | `shortcuts run "FireFrame Quick Note"` |
| GPT | Opens the ChatGPT app, else the website | App or URL | Install ChatGPT (optional) | None | `open -a ChatGPT` |
| Wallpapers | Opens the **iWallpaper** app | Direct (`open -a`) | Install/rename in config | macOS may prompt | `open -a iWallpaper` |
| 5 / 15 / 25 / 45 min | Starts FireFrame's built-in timer | In-app (no setup) | None | None | n/a |
| Prepare | Opens your work apps + links | Direct (`open`) | Edit `PREPARE_APPS` / `PREPARE_URLS` | None | `open -a Spotify` |
| Restart | Shows safe restart instructions | Info modal | None | None | n/a |

Notes:
- **Shortcut names you must create:** `FireFrame DND`, `FireFrame Locked In`, `FireFrame Presentation Mode`, `FireFrame Break Mode`, `FireFrame Sleep Mode`, `FireFrame Quick Note`. (You can also point `prepare`/timers at Shortcuts named `FireFrame Prepare`, `FireFrame 5 Minute Timer`, etc. by editing the registry.)
- **Timers** use FireFrame's own timer UI by default (most reliable). To use Shortcuts instead, set e.g. `"timer_25": {"type": "shortcut", "shortcut": "FireFrame 25 Minute Focus Timer"}` and add a button.
- **iWallpaper / Spotify / ChatGPT** are app names. If your app is named differently, change `app` in `SHORTCUT_ACTIONS`. If an app isn't installed, the button shows a clean "Is it installed?" error.
- **Sleep Mac** is the only confirmed action and won't fire from a stray tap or background refresh.
- **Restart** never restarts the server remotely; it shows manual steps (Ctrl-C in the terminal, re-run your launch command, then Reload App).

To keep your setup out of Git, put your edited `SHORTCUT_ACTIONS`, `PREPARE_APPS`, and `PREPARE_URLS` in `backend/config.py`, which is gitignored. The committed `backend/config.example.py` carries only generic placeholders.

## Fire tablet (Fully Kiosk Browser)

Use [Fully Kiosk Browser](https://www.fully-kiosk.com/) from the Amazon Appstore or an APK. Silk and Chrome cannot reliably stay fullscreen.

| Setting | Value |
|---|---|
| Start URL | `http://<MAC_IP>:8765` |
| Fullscreen | on |
| Hide address bar | on |
| Keep screen on | on |
| Orientation | Landscape |
| Reload on network reconnect | on |

- **Stable IP:** set a DHCP reservation on your router so the Mac's IP (and the Start URL) stay put after a reboot.
- **Login:** tap-based PIN pad, no soft keyboard needed; keyboard fallback for longer passwords.
- **Rate limit:** 5 failed attempts locks that device out for 30 seconds.
- **Caching:** the page is served with no-cache headers and the CSS/JS are versioned, so a reload always picks up new code. The Settings tab has a "Force Reload" button.
- **Exit kiosk:** use the Fully Kiosk admin overlay, swipe up for recent apps, or force-stop from Fire OS settings.

## Developing on another machine

You can edit and run on any machine (for example a Linux box):

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```

Reach it without exposing a port: `ssh -L 8765:127.0.0.1:8765 <dev-box>`. Off macOS the UI, stats, and photos work; Bluetooth, Calendar, and Shortcuts show their unsupported states.

If `python3 -m venv` reports that `ensurepip` is missing (minimal Debian/Ubuntu):

```bash
python3 -m venv .venv --without-pip
curl -sSL https://bootstrap.pypa.io/get-pip.py | ./.venv/bin/python -
./.venv/bin/python -m pip install -r requirements.txt
```

## Launching without a terminal (macOS)

- **`launch-mac.command`:** double-click it in Finder to start the server (first run: right-click > Open). Drag it to the Dock for one tap.
- **Automator app:** New > Application > Run Shell Script, paste `cd "$HOME/path/to/FireFrame" && ./scripts/start.sh`, and save as `FireFrame.app`.
- **At login:** an example launchd agent is in `scripts/launchd/`. Copy it to `~/Library/LaunchAgents/`, fix the paths, and load it.

## Troubleshooting

- **New PIN does not work:** restart the server; `.env` is read only at startup.
- **Buttons fail:** check the Shortcut names match exactly, and that the terminal running the server has Automation/Accessibility permission.
- **Calendar error:** for `apple`, grant Automation permission; otherwise use an `.ics` file or URL.
- **Bluetooth connect greyed out:** install `blueutil` (or drop the binary in `./bin/`) and restart. Listing and status work without it.
- **Disable an action:** set `"enabled": False` for it in `backend/config.py`.

## Before publishing

- [ ] `.env` and `backend/config.py` are gitignored and not committed.
- [ ] No personal photos in `photos/` (only `README.md`).
- [ ] No personal URLs, IPs, or Bluetooth identifiers in committed files.
- [ ] No `*.ics`, logs, or `__pycache__` committed.
- [ ] Choose a license (below).

## License

_TODO: choose a license before publishing (MIT, Apache-2.0, GPL, etc.)._
