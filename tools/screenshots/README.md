# FireFrame screenshot generator

Renders the **real** FireFrame UI (no mockups) at Fire-tablet dimensions with
believable sample data, and saves polished PNGs to `docs/screenshots/`.

It works by opening the app with `?demo=true&screenshot=true`, which activates
[`frontend/demo.js`](../../frontend/demo.js): that stubs every `/api/*` call with
sample data, auto-logs in, and hides the version badge / scrollbars for clean
captures.

## Regenerate the screenshots

```bash
cd tools/screenshots
npm run setup     # one-time: installs Playwright + Chromium
npm run shots     # boots the server, captures 4 PNGs at 1280×800 @2x
```

The script starts a throwaway FireFrame server itself, so you don't need one
running. Output:

```
docs/screenshots/home-dashboard.png
docs/screenshots/mac-stats.png
docs/screenshots/calendar-tasks.png
docs/screenshots/remote-controls.png
```

### Higher-resolution exports

```bash
npm run shots:hires   # 1920×1200 @1x
```

### Options (env vars)

| Var          | Default      | Meaning                                                  |
|--------------|--------------|----------------------------------------------------------|
| `FF_VIEWPORT`| `1280x800`   | Logical viewport (Fire HD 8 landscape, 16:10).           |
| `FF_SCALE`   | `2`          | `deviceScaleFactor` — `2` gives crisp retina PNGs.       |
| `FF_URL`     | _(unset)_    | Capture an already-running server instead of booting one.|
| `FF_PORT`    | `8799`       | Port for the temporary server.                           |

## No-Playwright fallback (manual capture)

Open this URL in desktop Chrome at a 1280×800 window and screenshot the viewport:

```
http://<your-mac>:8765/?demo=true&screenshot=true&tab=home
```

Swap `tab=` for `mac-stats`, `calendar`, or `buttons`.
