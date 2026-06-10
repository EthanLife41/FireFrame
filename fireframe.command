#!/bin/bash
# Double-click on macOS to start FireFrame (opens Terminal and runs the server).
# Tip: drag this onto the Dock for one-tap launch, and set a custom icon via
# Finder > Get Info > paste an image onto the icon. Close the Terminal window
# (or Ctrl+C) to stop the server.
cd "$(dirname "$0")"

IP=$(ipconfig getifaddr en0)

echo "======================================"
echo "FireFrame starting..."
echo ""
echo "Mac Wi-Fi IP: $IP"
echo "Open on tablet:"
echo "http://$IP:8765"
echo "======================================"
echo ""

./scripts/start.sh