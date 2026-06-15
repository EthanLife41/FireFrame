# Security Advisory

**This application is local-first software and is NOT hardened for public internet exposure.**

FireFrame is designed to be run on a trusted local network (like your home Wi-Fi) to serve a dashboard to a single tablet.

## Core security model

1. **Untrusted tablet.** The Fire tablet is treated as untrusted. Do not log into sensitive accounts on it.
2. **No arbitrary commands.** The backend never runs commands sent by the frontend. The browser only sends an action key, and the server runs the matching entry from a fixed allowlist (`SHORTCUT_ACTIONS`). No `shell=True` is used anywhere.
3. **No network exposure.** Do not port-forward this app or expose it through tunnels (ngrok, Cloudflare, etc.). Run it on a trusted LAN only.
4. **Authentication.** Every data and action endpoint requires a signed session cookie. Login is rate-limited (5 attempts, then a 30-second lockout per device).
5. **What the stats endpoints expose.** They report resource usage (CPU, RAM, storage, battery, uptime) and the names of the top processes by CPU and memory. They do not expose full command lines, arguments, file paths, usernames, serial numbers, or hardware UUIDs. Bluetooth MAC addresses stay on the Mac; the tablet only receives an opaque per-device token. The Wi-Fi SSID is deliberately not reported.

Before publishing, follow the "Before publishing" checklist in `README.md` so no personal secrets, URLs, or device identifiers reach version control.
