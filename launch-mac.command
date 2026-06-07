#!/bin/bash
# Double-click on macOS to start FireFrame (opens Terminal and runs the server).
# Tip: drag this onto the Dock for one-tap launch, and set a custom icon via
# Finder > Get Info > paste an image onto the icon. Close the Terminal window
# (or Ctrl+C) to stop the server.
cd "$(dirname "$0")"
exec ./scripts/start.sh
