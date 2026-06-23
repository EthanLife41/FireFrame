// FireFrame demo / screenshot mode. Loaded before app.js, inert unless the page
// is opened with ?demo=true — then it stubs the /api/* calls with sample data so
// the dashboard looks populated for screenshots (no Mac, no login needed).
//
//   ?demo=true                  fill the UI with sample data (auto-logs in)
//   ?demo=true&screenshot=true  also hide the version badge + scrollbars
//   &tab=home|mac-stats|calendar|buttons   open straight to that screen
//
// Driven by tools/screenshots/capture.mjs; also fine for a manual capture.

(function () {
    const params = new URLSearchParams(location.search);
    if (params.get('demo') !== 'true') return;   // off by default — real app untouched

    const SCREENSHOT = params.get('screenshot') === 'true';
    const TAB = params.get('tab');

    // A believable LAN address so screenshots never show "localhost:8799".
    const TABLET_URL = 'http://192.168.1.50:8765';

    // ---- time helpers (events/tasks are anchored to "now" so they look live) ----
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const ymdLocal = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    // dayOffset days from today, at h:m local -> ISO string
    const at = (dayOffset, h, m) => {
        const d = new Date(now);
        d.setDate(d.getDate() + dayOffset);
        d.setHours(h, m || 0, 0, 0);
        return d.toISOString();
    };
    const rel = (mins) => new Date(now.getTime() + mins * 60000).toISOString();
    // Days from today back to Monday of the current week (0 = Mon).
    const MON = -((now.getDay() + 6) % 7);

    const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    const ev = (title, d, sh, sm, eh, em, cal, color, loc) => ({
        id: slug(title) + '-' + d,
        title, start: at(d, sh, sm), end: at(d, eh, em),
        all_day: false, calendar: cal, calendar_color: color,
        location: loc || '', description: '',
    });
    const allDay = (title, dStart, dEnd, cal, color) => ({
        id: slug(title), title, start: at(dStart, 0, 0), end: at(dEnd, 0, 0),
        all_day: true, calendar: cal, calendar_color: color, location: '', description: '',
    });

    // Calendar palette: Work (blue), Personal (green), Travel (orange).
    const WORK = '#0a84ff', PERSONAL = '#30d158', TRAVEL = '#ff9f0a';

    // ---- sample data ----------------------------------------------------------

    // Full week schedule for the Calendar tab (week view).
    const weekEvents = [
        ev('Team Standup',    MON + 0,  9, 30,  9, 45, 'Work', WORK),
        ev('Design Review',   MON + 0, 14,  0, 15,  0, 'Work', WORK, 'Zoom'),
        ev('Meeting with Wirtz',   MON + 1, 11,  0, 11, 30, 'Work', WORK),
        ev('Evening Run',     MON + 1, 18,  0, 19,  0, 'Personal', PERSONAL),
        ev('Deep Work: API',  MON + 2, 10,  0, 12, 30, 'Work', WORK),
        ev('Lunch w/ Sam',    MON + 2, 12, 30, 13, 30, 'Personal', PERSONAL, 'Cafe Luna'),
        ev('Sprint Planning', MON + 3, 10,  0, 11,  0, 'Work', WORK),
        ev('Dentist',         MON + 3, 16,  0, 16, 45, 'Personal', PERSONAL),
        ev('Demo Day',        MON + 4, 15,  0, 16,  0, 'Work', WORK),
        ev('Flight to NYC',   MON + 4, 19,  0, 22,  0, 'Travel', TRAVEL, 'SFO → JFK'),
        ev('Brunch',          MON + 5, 11,  0, 12, 30, 'Personal', PERSONAL),
        ev('Meal Prep',       MON + 6, 17,  0, 18,  0, 'Personal', PERSONAL),
        // All-day banner spanning Thu–Fri (end midnight is exclusive).
        allDay('Design Sprint', MON + 3, MON + 5, 'Work', WORK),
    ];

    // Home "Up Next": the first one is minutes away so the countdown reads "in 25m".
    const upcoming = {
        connected: true,
        events: [
            { title: 'Design Review', start: rel(25),  end: rel(85),  all_day: false, calendar: 'Work', calendar_color: WORK },
            { title: '1:1 with Alex', start: rel(150), end: rel(180), all_day: false, calendar: 'Work', calendar_color: WORK },
            { title: 'Evening Run',   start: rel(300), end: rel(360), all_day: false, calendar: 'Personal', calendar_color: PERSONAL },
        ],
    };

    // Tasks (calendar blocks). Durations drive the Regular/Important badge:
    // >= important_minutes (240) renders as Important.
    const tasks = [
        { event_id: 't1', title: 'Write project proposal', start: at(0, 19, 0), end: at(0, 20, 0) },
        { event_id: 't2', title: 'Prep investor deck',     start: at(1,  9, 0), end: at(1, 13, 0) },
        { event_id: 't3', title: 'Review pull requests',   start: at(1, 15, 0), end: at(1, 16, 0) },
        { event_id: 't4', title: 'Plan Q3 roadmap',        start: at(2, 10, 0), end: at(2, 14, 0) },
        { event_id: 't5', title: 'Email follow-ups',       start: at(2, 16, 0), end: at(2, 17, 0) },
    ];

    // Home quick-stats card.
    const homeStats = {
        cpu_percent: 41, ram_percent: 47, disk_percent: 63,
        battery_available: true, battery_percent: 82, battery_charging: false,
        uptime_seconds: 3 * 86400 + 5 * 3600,   // 3d 5h
    };

    // Full Mac Stats dashboard (consistent with homeStats).
    const macStats = {
        is_mac: true,
        system: { name: "Ethan's MacBook Pro", os_name: 'macOS', os_version: 'Sequoia 15.5', uptime_seconds: 3 * 86400 + 5 * 3600 },
        cpu: { percent: 41, cores_logical: 12 },
        memory: { percent: 47, used_gb: 15.2, available_gb: 16.8, total_gb: 32 },
        battery: { available: true, percent: 82, charging: false, power_source: 'On battery', time_left: '4:35' },
        disk: { available: true, percent: 63, used_gb: 627, free_gb: 367, total_gb: 994 },
        network: { connected: true, local_ip: '192.168.1.50', down_bps: 4_200_000, up_bps: 700_000 },
        volume: { available: true, muted: false, percent: 35 },
        processes: {
            // Per-process CPU is a share of the whole CPU, so the top-5 sum stays
            // under the 41% total (the rest is spread across smaller processes).
            by_cpu: [
                { name: 'Visual Studio Code', cpu: 22.6 },
                { name: 'Google Chrome',      cpu: 9.8 },
                { name: 'Discord',            cpu: 4.7 },
                { name: 'Spotify',            cpu: 2.3 },
                { name: 'Terminal',           cpu: 1.1 },
            ],
            by_mem: [
                { name: 'Google Chrome',      mem: 11.4 },
                { name: 'Visual Studio Code', mem: 7.8 },
                { name: 'Discord',            mem: 6.2 },
                { name: 'Slack',              mem: 4.9 },
                { name: 'Music',              mem: 3.1 },
            ],
        },
    };

    const bluetooth = {
        available: true, powered: true, connect_supported: true,
        blueutil_installed: true, note: '',
        devices: [
            { id: 'bt-airpods',  name: 'AirPods Pro',    type: 'headphones', connected: true,  actionable: true },
            { id: 'bt-keyboard', name: 'Magic Keyboard', type: 'keyboard',   connected: true,  actionable: true },
            { id: 'bt-trackpad', name: 'Magic Trackpad', type: 'trackpad',   connected: false, actionable: true },
            { id: 'bt-xm5',      name: 'WH-1000XM5',     type: 'headphones', connected: false, actionable: true },
            { id: 'bt-homepod',  name: 'HomePod mini',   type: 'speaker',    connected: false, actionable: true },
        ],
    };

    const taskConfig = {
        available: true, regular_minutes: 60, important_minutes: 240,
        input_location: 'dashboard', mac_prompt_supported: true, default_calendar: 'Tasks',
    };
    const taskCalendars = {
        available: true,
        calendars: [{ id: 'cal-tasks', name: 'Tasks' }, { id: 'cal-work', name: 'Work' }],
        suggested_id: 'cal-tasks',
    };

    const settingsHealth = {
        server: { host: '192.168.1.50', port: 8765 },
        calendar: { configured: true, connected: true, source: 'demo' },
        photos: { exists: true, count: 42, folder: 'photos' },
        bluetooth: { available: true, connect_supported: true, blueutil_installed: true },
        shortcuts: { cli_available: true, configured: true, count: 6 },
        config: { local_config: true, password_is_default: false },
    };

    function dayResponse(date) {
        const target = date || ymdLocal(now);
        const onDay = (e) => e.all_day
            ? ymdLocal(new Date(e.start)) <= target && target < ymdLocal(new Date(e.end))
            : ymdLocal(new Date(e.start)) === target;
        return { connected: true, source: 'demo', view: 'day', events: weekEvents.filter(onDay) };
    }

    // ---- route table ----------------------------------------------------------
    // Responses don't depend on the HTTP method: GET reads and POST writes
    // (actions, refresh) both just return believable sample data.
    function route(p, q) {
        switch (p) {
            case '/api/me':                return { logged_in: true };
            case '/api/status':            return { status: 'ok', message: 'Running locally' };
            case '/api/stats':             return homeStats;
            case '/api/mac-stats':         return macStats;
            case '/api/bluetooth/devices':
            case '/api/bluetooth/refresh': return bluetooth;
            case '/api/bluetooth/status':  return { available: true, powered: true };
            case '/api/calendar/upcoming': return upcoming;
            case '/api/calendar/week':     return { connected: true, source: 'demo', view: 'week', events: weekEvents };
            case '/api/calendar/day':      return dayResponse(q.get('date'));
            case '/api/calendar/today':    return dayResponse(null);
            case '/api/calendar/sources':  return { connected: true, sources: ['Work', 'Personal', 'Travel'] };
            case '/api/calendar/refresh':  return { connected: true, source: 'demo' };
            case '/api/weather':           return { enabled: false };
            case '/api/tasks/config':      return taskConfig;
            case '/api/tasks/calendars':   return taskCalendars;
            case '/api/tasks/upcoming':    return { available: true, tasks: tasks.slice(0, Number(q.get('limit')) || 3) };
            case '/api/settings':          return settingsHealth;
            case '/api/photos':            return { photos: [], interval_seconds: 30 };
            case '/api/photos/random':     return { photo: null };
            default:                       return { success: true, message: 'Demo mode' };
        }
    }

    // ---- fetch interception ---------------------------------------------------
    const realFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        let pathname = url, search = new URLSearchParams();
        try {
            const u = new URL(url, location.origin);
            pathname = u.pathname;
            search = u.searchParams;
        } catch { /* keep raw url */ }

        if (!pathname.startsWith('/api/')) return realFetch(input, init);

        const data = route(pathname, search);
        return Promise.resolve(new Response(JSON.stringify(data), {
            status: 200, headers: { 'Content-Type': 'application/json' },
        }));
    };

    // ---- presentation tweaks (run once the DOM is ready) ----------------------
    function onReady(fn) {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
        else fn();
    }

    function injectScreenshotStyle() {
        const style = document.createElement('style');
        style.textContent = `
            .app-version { display: none !important; }
            .tab-content.active { animation: none !important; }
            * { scrollbar-width: none !important; }
            *::-webkit-scrollbar { width: 0 !important; height: 0 !important; display: none !important; }
        `;
        document.head.appendChild(style);
    }

    // Keep the localhost URL out of screenshots: pin the status fields to a
    // believable LAN address even after app.js writes window.location.origin.
    function pinUrl(id, val) {
        const node = document.getElementById(id);
        if (!node) return;
        const apply = () => { if (node.textContent !== val) node.textContent = val; };
        apply();
        new MutationObserver(apply).observe(node, { childList: true, characterData: true, subtree: true });
    }

    // Open straight to the requested tab once the app has logged in.
    function switchWhenReady(tab) {
        let tries = 0;
        const iv = setInterval(() => {
            const main = document.getElementById('main-screen');
            if (main && main.classList.contains('active') && typeof window.switchTab === 'function') {
                window.switchTab(tab);
                clearInterval(iv);
            } else if (++tries > 100) {
                clearInterval(iv);
            }
        }, 50);
    }

    onReady(() => {
        if (SCREENSHOT) injectScreenshotStyle();
        pinUrl('home-ff-url', TABLET_URL);
        pinUrl('set-url', TABLET_URL);
        if (TAB) switchWhenReady(TAB);
    });
})();
