// Generate FireFrame screenshots for the README.
//
// It boots the real FireFrame backend (only to serve the static UI — every
// /api/* call is stubbed client-side by frontend/demo.js), opens each screen in
// a Fire-tablet-sized viewport with `?demo=true&screenshot=true`, waits for the
// sample data to settle, and writes PNGs to docs/screenshots/.
//
//   npm run setup     # one-time: install Playwright + its Chromium
//   npm run shots     # 1280×800 @2x  -> docs/screenshots/*.png
//   npm run shots:hires  # 1920×1200 @1x
//
// Env overrides:
//   FF_VIEWPORT=1280x800   logical viewport (Fire HD 8 landscape, 16:10)
//   FF_SCALE=2             deviceScaleFactor (2 = crisp/retina exports)
//   FF_URL=http://host:port  capture an already-running server instead of booting one
//   FF_PORT=8799           port to boot the temporary server on

import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');     // tools/screenshots -> repo root
const OUT_DIR = path.join(REPO_ROOT, 'docs', 'screenshots');

const [VW, VH] = (process.env.FF_VIEWPORT || '1280x800').split('x').map(Number);
const SCALE = Number(process.env.FF_SCALE || 2);
const PORT = Number(process.env.FF_PORT || 8799);

// Wait until a field has real content (non-empty and not the "—" placeholder).
const waitText = (page, sel, placeholder) => page.waitForFunction(
    ([s, ph]) => { const el = document.querySelector(s); const t = el && el.textContent.trim(); return !!t && t !== ph; },
    [sel, placeholder], { timeout: 15000 });
const waitSel = (page, sel) => page.waitForSelector(sel, { timeout: 15000 });

// Each capture: output name, the tab to open, and how to tell it has rendered.
const SHOTS = [
    { name: 'home-dashboard',  tab: 'home',      ready: (page) => waitText(page, '#home-cpu', '—') },
    { name: 'mac-stats',       tab: 'mac-stats', ready: (page) => waitText(page, '#ms-name', '—') },
    { name: 'calendar-tasks',  tab: 'calendar',  ready: (page) => waitSel(page, '.cal-event') },
    { name: 'remote-controls', tab: 'buttons',   ready: (page) => waitSel(page, '.deck-section') },
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function waitForServer(url, timeoutMs = 30000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        try {
            const res = await fetch(url, { method: 'GET' });
            if (res.ok) return;
        } catch { /* not up yet */ }
        await sleep(300);
    }
    throw new Error(`Server at ${url} did not start within ${timeoutMs}ms`);
}

async function main() {
    let serverProc = null;
    let baseUrl = process.env.FF_URL;

    if (!baseUrl) {
        baseUrl = `http://127.0.0.1:${PORT}`;
        console.log(`Starting FireFrame server on ${baseUrl} …`);
        serverProc = spawn('python3',
            ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(PORT)],
            {
                cwd: REPO_ROOT,
                stdio: ['ignore', 'inherit', 'inherit'],
                env: {
                    ...process.env,
                    // Backend refuses to boot with the default secret; supply a throwaway.
                    SESSION_SECRET: process.env.SESSION_SECRET || randomBytes(32).toString('hex'),
                    DASHBOARD_PASSWORD: process.env.DASHBOARD_PASSWORD || '0000',
                    CALENDAR_SOURCE: 'none',   // irrelevant: demo.js stubs all /api calls
                },
            });
        await waitForServer(baseUrl + '/');
    } else {
        console.log(`Using existing server at ${baseUrl}`);
    }

    const browser = await chromium.launch();
    const context = await browser.newContext({
        viewport: { width: VW, height: VH },
        deviceScaleFactor: SCALE,
    });
    const page = await context.newPage();
    await mkdir(OUT_DIR, { recursive: true });

    try {
        for (const shot of SHOTS) {
            const url = `${baseUrl}/?demo=true&screenshot=true&tab=${shot.tab}`;
            await page.goto(url, { waitUntil: 'load' });
            await page.waitForSelector('#main-screen.active', { timeout: 15000 });
            // demo.js opens the tab from the query param; click as a fallback.
            await page.click(`.nav-btn[data-tab="${shot.tab}"]`).catch(() => {});
            await page.waitForSelector(`#tab-${shot.tab}.active`, { timeout: 15000 });
            await shot.ready(page);
            await sleep(1200);   // let bars/fade-ins settle
            const file = path.join(OUT_DIR, `${shot.name}.png`);
            await page.screenshot({ path: file });
            console.log(`✓ ${path.relative(REPO_ROOT, file)}  (${VW}×${VH} @${SCALE}x)`);
        }
    } finally {
        await browser.close();
        if (serverProc) serverProc.kill('SIGTERM');
    }

    console.log(`\nDone — ${SHOTS.length} screenshots in ${path.relative(REPO_ROOT, OUT_DIR)}/`);
}

main().catch((err) => { console.error(err); process.exit(1); });
