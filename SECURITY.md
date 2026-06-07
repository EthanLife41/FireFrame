# Security Advisory

**This application is local-first software and is NOT hardened for public internet exposure.**

FireFrame is designed to be run on a trusted local network (like your home Wi-Fi) to serve a dashboard to a single tablet.

## Core Security Tenets

1. **Untrusted Tablet:** The Fire tablet is treated as completely untrusted. Do not log into sensitive accounts on the tablet.
2. **No Arbitrary Commands:** The backend explicitly forbids executing arbitrary commands passed from the frontend. It only executes fixed, pre-defined actions.
3. **No Network Exposure:** You should NEVER port-forward this application on your router or expose it via services like ngrok or Cloudflare Tunnels. 
4. **Data Privacy:** The stats endpoint (`/api/stats`) exposes general resource usage (CPU/RAM/Battery) but does not expose usernames, serial numbers, hardware UUIDs, process lists, or file paths.

Please ensure you follow the "Open-Source Publishing Checklist" in the `README.md` to avoid committing personal secrets, URLs, or Bluetooth device identifiers to version control.
