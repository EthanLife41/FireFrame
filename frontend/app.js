// FireFrame frontend. Built for the Fire HD 8 in landscape (Fully Kiosk Browser).

// Log uncaught errors to the console for troubleshooting on the tablet.
window.addEventListener('error', (event) => {
    console.error(`JS error: ${event.message} at ${event.filename || 'app.js'}:${event.lineno}`);
});

// --- State ---
let isLoggedIn    = false;
let statsInterval = null;
let btStatusInterval = null;
let calendarCountdownInterval = null;
let macStatsInterval = null;
let macStatsClock = null;
let currentTab    = 'home';
let pinBuffer     = '';
const MAX_PIN_LEN = 4;

// Polling cadence. Kept modest so the app is cheap to leave running: psutil
// stats are light; Bluetooth status triggers a (server-cached) system_profiler,
// so it runs less often. Both pause while the browser tab is hidden.
const STATS_POLL_MS = 15000;
const BT_STATUS_POLL_MS = 30000;

// Calendar view state
let calView = 'week';
let calAnchor = new Date();
let calHidden = new Set();   // calendar names hidden via the source filter
let calLoaded = false;
let calLastData = null;

// --- DOM refs ---
const loginScreen    = document.getElementById('login-screen');
const mainScreen     = document.getElementById('main-screen');
const loginError     = document.getElementById('login-error');
const kbLoginError   = document.getElementById('kb-login-error');
const logoutBtn      = document.getElementById('logout-btn');
const toast          = document.getElementById('toast');
let toastTimer       = null;

// ============================================================
// INITIALISE
// ============================================================
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

function init() {
    checkLogin();
    setupNavigation();
    setupActions();
    setupClock();
    setupModals();
    setupPinPad();
    setupKeyboardFallback();
    setupFullscreen();
    setupReloadButtons();
    setupBluetooth();
    setupCalendar();
    setupEventModal();
    setupPhotos();
    setupMacStats();
    setupSettings();
    setupHome();
    setupTasks();
    setupVisibility();
}

// Pause background polling when the tab/screen isn't visible.
function setupVisibility() {
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopStatsPolling();
            stopMacStats();
        } else if (isLoggedIn) {
            startStatsPolling();
            if (currentTab === 'mac-stats') startMacStats();
        }
    });
}

// ============================================================
// AUTH
// ============================================================
async function checkLogin() {
    try {
        const res = await fetch('/api/me');
        if (res.ok && (await res.json()).logged_in) {
            showMainApp();
        } else {
            showLogin();
        }
    } catch {
        showLogin();
    }
}

async function attemptLogin(password) {
    if (!password) return;

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });

        if (res.ok) {
            showMainApp();
            return;
        }

        const body = await res.json().catch(() => ({}));
        const msg  = body.detail || 'Login failed.';

        if (res.status === 429) {
            // Lockout
            showLoginError(msg, true);
        } else {
            showLoginError(msg, false);
        }
    } catch {
        showLoginError('Connection error. Is the server running?', false);
    }
}

function showLoginError(msg, isLockout) {
    // Show in both places so it's visible regardless of mode
    loginError.textContent    = msg;
    kbLoginError.textContent  = msg;
    loginError.classList.remove('hidden');
    kbLoginError.classList.remove('hidden');
    if (isLockout) {
        loginError.style.color   = 'var(--danger)';
        kbLoginError.style.color = 'var(--danger)';
    }
    // Clear PIN buffer on error
    pinBuffer = '';
    updateDots();
}

function clearLoginErrors() {
    loginError.classList.add('hidden');
    kbLoginError.classList.add('hidden');
}

logoutBtn.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    showLogin();
});

function showLogin() {
    isLoggedIn = false;
    stopStatsPolling();
    stopMacStats();
    cancelTimer();
    loginScreen.classList.add('active');
    loginScreen.classList.remove('hidden');
    mainScreen.classList.add('hidden');
    mainScreen.classList.remove('active');
    pinBuffer = '';
    updateDots();
    clearLoginErrors();
}

function showMainApp() {
    isLoggedIn = true;
    loginScreen.classList.remove('active');
    loginScreen.classList.add('hidden');
    mainScreen.classList.add('active');
    mainScreen.classList.remove('hidden');
    loadHomeNextEvent();
    fillHomeStatus();
    fetchWeather();
    loadHomeTasks();
    refreshTaskConfig();
    startStatsPolling();
}

// ============================================================
// PIN PAD
// ============================================================
function setupPinPad() {
    // Digit buttons
    document.querySelectorAll('.pin-btn[data-digit]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (pinBuffer.length >= MAX_PIN_LEN) return;
            pinBuffer += btn.getAttribute('data-digit');
            updateDots();
            clearLoginErrors();

            if (pinBuffer.length === MAX_PIN_LEN) {
                // Short delay so dot fill is visible before sending
                setTimeout(() => {
                    attemptLogin(pinBuffer);
                    pinBuffer = '';
                    updateDots();
                }, 150);
            }
        });
    });

    document.getElementById('pin-del-btn').addEventListener('click', () => {
        pinBuffer = pinBuffer.slice(0, -1);
        updateDots();
    });

    document.getElementById('pin-clear-btn').addEventListener('click', () => {
        pinBuffer = '';
        updateDots();
    });

    document.getElementById('pin-submit-btn').addEventListener('click', () => {
        if (pinBuffer.length > 0) {
            attemptLogin(pinBuffer);
            pinBuffer = '';
            updateDots();
        }
    });

    // Add keyboard support for PIN pad
    document.addEventListener('keydown', e => {
        const pinMode = document.getElementById('pin-mode');
        // Ignore keydown if PIN mode is hidden (e.g. keyboard fallback mode or authed)
        if (!pinMode || pinMode.classList.contains('hidden') || isLoggedIn) return;

        if (e.key >= '0' && e.key <= '9') {
            if (pinBuffer.length >= MAX_PIN_LEN) return;
            pinBuffer += e.key;
            updateDots();
            clearLoginErrors();

            if (pinBuffer.length === MAX_PIN_LEN) {
                setTimeout(() => {
                    attemptLogin(pinBuffer);
                    pinBuffer = '';
                    updateDots();
                }, 150);
            }
        } else if (e.key === 'Backspace') {
            pinBuffer = pinBuffer.slice(0, -1);
            updateDots();
        } else if (e.key === 'Escape' || e.key === 'c' || e.key === 'C') {
            pinBuffer = '';
            updateDots();
        } else if (e.key === 'Enter') {
            if (pinBuffer.length > 0) {
                attemptLogin(pinBuffer);
                pinBuffer = '';
                updateDots();
            }
        }
    });
}

function updateDots() {
    for (let i = 0; i < MAX_PIN_LEN; i++) {
        const dot = document.getElementById(`d${i}`);
        if (dot) dot.classList.toggle('filled', i < pinBuffer.length);
    }
}

// ============================================================
// KEYBOARD FALLBACK
// ============================================================
function setupKeyboardFallback() {
    document.getElementById('show-password-btn').addEventListener('click', () => {
        document.getElementById('pin-mode').classList.add('hidden');
        document.getElementById('keyboard-mode').classList.remove('hidden');
    });

    document.getElementById('show-pin-btn').addEventListener('click', () => {
        document.getElementById('keyboard-mode').classList.add('hidden');
        document.getElementById('pin-mode').classList.remove('hidden');
    });

    document.getElementById('login-btn').addEventListener('click', () => {
        const val = document.getElementById('password-input').value;
        attemptLogin(val);
    });

    document.getElementById('password-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            const val = document.getElementById('password-input').value;
            attemptLogin(val);
        }
    });

    document.getElementById('toggle-pw-btn').addEventListener('click', () => {
        const inp = document.getElementById('password-input');
        const btn = document.getElementById('toggle-pw-btn');
        if (inp.type === 'password') {
            inp.type = 'text';
            btn.textContent = '🙈';
        } else {
            inp.type = 'password';
            btn.textContent = '👁';
        }
    });
}

// ============================================================
// FULLSCREEN
// ============================================================
function setupFullscreen() {
    const loginFsBtn   = document.getElementById('login-fullscreen-btn');
    const settingFsBtn = document.getElementById('settings-fullscreen-btn');

    const requestFs = () => {
        const el = document.documentElement;
        const req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
        if (req) {
            req.call(el).catch(() => {
                showToast('Fullscreen blocked. Use Fully Kiosk Browser settings instead.', true);
            });
        } else {
            showToast('Fullscreen API not supported by this browser.', true);
        }
    };

    loginFsBtn.addEventListener('click', requestFs);
    settingFsBtn.addEventListener('click', requestFs);

    document.addEventListener('fullscreenchange', () => {
        const inFs = !!document.fullscreenElement;
        const label = inFs ? '✕ Exit Fullscreen' : '⛶ Request Fullscreen';
        settingFsBtn.textContent = label;
    });
}

// ============================================================
// RELOAD CONTROL
// ============================================================
function setupReloadButtons() {
    const reload = () => {
        // Appends refresh query parameter to bypass cache
        window.location.href = window.location.pathname + "?refresh=" + Date.now();
    };
    const loginReloadBtn = document.getElementById('login-reload-btn');
    if (loginReloadBtn) loginReloadBtn.addEventListener('click', reload);

    const settingsReloadBtn = document.getElementById('settings-reload-btn');
    if (settingsReloadBtn) settingsReloadBtn.addEventListener('click', reload);
}

// ============================================================
// NAVIGATION
// ============================================================
function setupNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
    });
}

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const activeNavBtn = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
    if (activeNavBtn) activeNavBtn.classList.add('active');

    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const activeTabEl = document.getElementById(`tab-${tabId}`);
    if (activeTabEl) activeTabEl.classList.add('active');

    if (tabId === 'photos') { startPhotoShow(); } else { stopPhotoShow(); }
    if (tabId === 'bluetooth') { loadBluetooth(); }
    if (tabId === 'calendar') { if (calSection === 'tasks') loadCalTasks(); else if (!calLoaded) loadCalendarView(); }
    if (tabId === 'home') { loadHomeNextEvent(); loadHomeTasks(); }
    if (tabId === 'settings') { loadSettings(); }
    // Mac Stats polls only while its tab is open, to stay cheap in the background.
    if (tabId === 'mac-stats') { startMacStats(); } else { stopMacStats(); }
}
window.switchTab = switchTab; // used by inline onclick

// ============================================================
// ACTION BUTTONS
// ============================================================
function setupActions() {
    // Server-backed actions (run through the config registry). Covers the
    // Buttons-page tiles and the compact Home quick-action / launcher tiles.
    document.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => onActionButton(btn));
    });
    // Timer preset buttons are wired in setupTimer().
    // Restart instructions.
    const restartBtn = document.getElementById('open-restart-btn');
    if (restartBtn) restartBtn.addEventListener('click', () =>
        document.getElementById('restart-modal').classList.remove('hidden'));
}

function onActionButton(btn) {
    const action = btn.getAttribute('data-action');
    const confirmMsg = btn.getAttribute('data-confirm');
    if (confirmMsg) { showConfirm(confirmMsg, () => triggerAction(action, {}, btn)); return; }
    triggerAction(action, {}, btn);
}

async function triggerAction(action, params = {}, btn = null) {
    if (btn) { btn.classList.add('btn-busy'); btn.disabled = true; }
    try {
        const res = await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, params })
        });
        if (!res.ok) {
            showToast(`Server error (${res.status}).`, true);
            return;
        }
        const data = await res.json();
        showToast(data.success ? (data.message || 'Done.') : `Error: ${data.message}`, !data.success);
    } catch {
        showToast('Connection error.', true);
    } finally {
        if (btn) { btn.classList.remove('btn-busy'); btn.disabled = false; }
    }
}

// Generic confirm dialog (used by destructive actions like Sleep Mac).
let _confirmCb = null;
function showConfirm(message, onConfirm) {
    _confirmCb = onConfirm;
    setText('confirm-message', message);
    document.getElementById('confirm-modal').classList.remove('hidden');
}
function hideConfirm() {
    document.getElementById('confirm-modal').classList.add('hidden');
    _confirmCb = null;
}

// ============================================================
// TOAST
// ============================================================
function showToast(msg, isError = false) {
    toast.textContent = msg;
    toast.style.background = isError ? 'var(--danger)' : 'var(--primary)';
    toast.classList.remove('hidden');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add('hidden'), 3000);
}

// ============================================================
// CLOCK
// ============================================================
function setupClock() {
    const tick = () => {
        const now  = new Date();
        const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
        document.getElementById('clock').textContent      = time;
        document.getElementById('photo-clock').textContent = time;
        document.getElementById('date').textContent        = date;
    };
    tick();
    setInterval(tick, 1000);
}

// ============================================================
// STATS POLLING
// ============================================================
function startStatsPolling() {
    if (!statsInterval) {
        fetchStats();
        statsInterval = setInterval(fetchStats, STATS_POLL_MS);
    }
    if (!btStatusInterval) {
        fetchHomeBluetooth();
        btStatusInterval = setInterval(fetchHomeBluetooth, BT_STATUS_POLL_MS);
    }
}

function stopStatsPolling() {
    clearInterval(statsInterval);
    statsInterval = null;
    clearInterval(btStatusInterval);
    btStatusInterval = null;
}

async function fetchStats() {
    if (!isLoggedIn) return;
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) return;
        const d = await res.json();
        const pct = (v) => (v === undefined || v === null) ? '—' : Math.round(v) + '%';

        setText('home-cpu', pct(d.cpu_percent));
        setBar('home-cpu-bar', d.cpu_percent);
        setText('home-ram', pct(d.ram_percent));
        setBar('home-ram-bar', d.ram_percent);

        if (d.disk_percent != null) {
            setText('home-disk', pct(d.disk_percent));
            setBar('home-disk-bar', d.disk_percent);
        } else {
            setText('home-disk', 'N/A');
        }

        if (d.battery_available) {
            setText('home-battery', d.battery_percent + '%' + (d.battery_charging ? ' ⚡' : ''));
            setBatteryBar('home-battery-bar', d.battery_percent, d.battery_charging);
        } else {
            setText('home-battery', 'N/A');
            setBatteryBar('home-battery-bar', 0, false);
        }

        const secs = d.uptime_seconds || 0;
        const days = Math.floor(secs / 86400), hrs = Math.floor((secs % 86400) / 3600);
        setText('home-uptime', days > 0 ? `${days}d ${hrs}h` : `${hrs}h`);

        setText('home-ff-updated', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch { /* ignore */ }
}

// Battery bar is coloured by how low it is (full is fine, low is the warning).
function setBatteryBar(id, pct, charging) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = Math.max(0, Math.min(100, pct || 0));
    el.style.width = v + '%';
    el.classList.remove('warn', 'crit');
    if (!charging && v <= 10) el.classList.add('crit');
    else if (!charging && v <= 20) el.classList.add('warn');
}

async function fetchHomeBluetooth() {
    if (!isLoggedIn) return;
    try {
        const res = await fetch('/api/bluetooth/devices');
        if (!res.ok) return;
        renderHomeBluetooth(await res.json());
    } catch { /* ignore */ }
}

function renderHomeBluetooth(d) {
    const pill = document.getElementById('home-bt-pill');
    const devices = document.getElementById('home-bt-devices');
    const status = document.getElementById('home-bt-status');
    const openBtn = document.querySelector('.home-bt-open');
    if (devices) devices.innerHTML = '';

    let pillText = 'Unknown', pillClass = '';
    if (!d.available) pillText = 'Unavailable';
    else if (d.powered === false) pillText = 'Off';
    else if (d.powered === true) { pillText = 'On'; pillClass = 'on'; }
    if (pill) { pill.textContent = pillText; pill.className = 'pill-badge ' + pillClass; }

    if (!d.available) {
        if (status) status.textContent = d.message || 'Bluetooth is macOS only.';
        if (openBtn) openBtn.classList.add('hidden');
        return;
    }
    if (openBtn) openBtn.classList.remove('hidden');

    const connected = (d.devices || []).filter(x => x.connected);
    if (status) status.textContent = connected.length
        ? `${connected.length} connected`
        : (d.powered === false ? 'Turned off' : 'Nothing connected');
    connected.slice(0, 3).forEach(dev => {
        devices.appendChild(el('div', 'home-bt-dev', `${btIconFor(dev.type)} ${dev.name || 'Device'}`));
    });
}

// ============================================================
// SETTINGS  (app status, config health, maintenance)
// Loaded on demand when the tab opens, plus a manual Refresh. No polling.
// ============================================================
function setupSettings() {
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    on('set-refresh', loadSettings);
    on('set-copy-url', copyTabletUrl);
    on('set-open-photos', openPhotosFolder);
}

function setStatus(id, text, kind) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.classList.remove('st-ok', 'st-warn', 'st-off');
    if (kind) el.classList.add('st-' + kind);
}

function setHint(id, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

async function loadSettings() {
    setText('set-url', window.location.origin);
    setText('set-version', window.FF_VERSION || '—');

    try {
        const s = await (await fetch('/api/status')).json();
        setStatus('set-server', s.message || 'Running', 'ok');
    } catch {
        setStatus('set-server', 'Offline', 'off');
    }

    try {
        renderSettings(await (await fetch('/api/settings')).json());
    } catch {
        ['set-cal', 'set-photos', 'set-bt', 'set-shortcuts', 'set-cfg', 'set-pw', 'set-secret']
            .forEach(id => setStatus(id, 'Unavailable', 'off'));
    }
}

function renderSettings(h) {
    const sv = h.server || {};
    setText('set-hostport', `${sv.host || '—'} · ${sv.port || ''}`);

    // Calendar
    const c = h.calendar || {};
    if (!c.configured) {
        setStatus('set-cal', 'Not configured', 'warn');
        setHint('set-cal-hint', 'Set CALENDAR_SOURCE (demo, ics, or apple) in .env.');
    } else if (c.connected) {
        setStatus('set-cal', `Connected · ${c.source}`, 'ok');
        setHint('set-cal-hint', '');
    } else {
        setStatus('set-cal', `Configured · ${c.source}`, 'warn');
        setHint('set-cal-hint', c.message || 'Open the Calendar tab to verify it loads.');
    }

    // Photos
    const p = h.photos || {};
    if (!p.exists) setStatus('set-photos', 'Folder missing', 'warn');
    else if (p.count > 0) setStatus('set-photos', `${p.count} photo${p.count === 1 ? '' : 's'} · ${p.folder}/`, 'ok');
    else setStatus('set-photos', `Empty · ${p.folder}/`, 'warn');

    // Bluetooth
    const b = h.bluetooth || {};
    if (!b.available) setStatus('set-bt', 'Unavailable (macOS only)', 'off');
    else if (b.connect_supported) setStatus('set-bt', 'Ready · blueutil installed', 'ok');
    else if (b.blueutil_installed) setStatus('set-bt', 'Listing only · connect disabled', 'warn');
    else setStatus('set-bt', 'Listing only · no blueutil', 'warn');

    // Shortcuts
    const sc = h.shortcuts || {};
    if (!sc.cli_available) setStatus('set-shortcuts', 'Shortcuts app not found', 'warn');
    else if (sc.configured) setStatus('set-shortcuts', `${sc.count} configured`, 'ok');
    else setStatus('set-shortcuts', 'None configured', 'warn');

    // Config health
    const cfg = h.config || {};
    setStatus('set-cfg', cfg.local_config ? 'Local config in use' : 'Using example config', cfg.local_config ? 'ok' : 'warn');
    setStatus('set-pw', cfg.password_is_default ? 'Default — change it' : 'Set', cfg.password_is_default ? 'warn' : 'ok');
    const todo = [];
    if (cfg.password_is_default) todo.push('DASHBOARD_PASSWORD');
    setHint('set-cfg-hint', todo.length ? `Set in .env: ${todo.join(', ')}.` : '');

    refreshTaskConfig().then(renderTaskSettings);
}

async function copyTabletUrl() {
    const url = window.location.origin;
    try {
        await navigator.clipboard.writeText(url);
        showToast('Tablet URL copied.');
    } catch {
        showToast(url, false);   // clipboard blocked: show it so it can be typed
    }
}

async function openPhotosFolder() {
    try {
        const res = await fetch('/api/photos/open', { method: 'POST' });
        const d = await res.json();
        showToast(d.success ? (d.message || 'Opened.') : `Error: ${d.message}`, !d.success);
    } catch {
        showToast('Connection error.', true);
    }
}

// ============================================================
// CALENDAR  (day / week schedule grid; Apple Calendar or ICS)
// ============================================================
const CAL_HOUR_PX = 48;        // pixel height of one hour
const CAL_SCROLL_HOUR = 7;     // initial scroll position in the timed grid

function setupCalendar() {
    calView = localStorage.getItem('ff_cal_view') === 'day' ? 'day' : 'week';
    syncViewButtons();
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    on('cal-today',       () => { calAnchor = new Date(); loadCalendarView(); });
    on('cal-prev',        () => { shiftAnchor(-1); loadCalendarView(); });
    on('cal-next',        () => { shiftAnchor(1);  loadCalendarView(); });
    on('cal-refresh-btn', () => loadCalendarView(true));
    on('cal-view-day',    () => setCalView('day'));
    on('cal-view-week',   () => setCalView('week'));
}

function setCalView(v) {
    if (calView === v) return;
    calView = v;
    localStorage.setItem('ff_cal_view', v);
    syncViewButtons();
    loadCalendarView();
}

function syncViewButtons() {
    document.querySelectorAll('.seg-btn[data-view]').forEach(b =>
        b.classList.toggle('active', b.getAttribute('data-view') === calView));
}

function shiftAnchor(dir) {
    const step = calView === 'week' ? 7 : 1;
    calAnchor = new Date(calAnchor.getTime() + dir * step * 86400000);
}

function ymd(d) {
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
}

function mondayOf(d) {
    const r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    r.setDate(r.getDate() - ((r.getDay() + 6) % 7));   // 0 = Monday
    return r;
}

function calStatus(msg) {
    const s = document.getElementById('cal-status');
    const grid = document.getElementById('cal-grid');
    if (msg) { s.textContent = msg; s.classList.remove('hidden'); grid.classList.add('hidden'); }
    else { s.classList.add('hidden'); grid.classList.remove('hidden'); }
}

async function loadCalendarView(force = false) {
    calStatus('Loading calendar...');
    const url = calView === 'week'
        ? `/api/calendar/week?start=${ymd(mondayOf(calAnchor))}`
        : `/api/calendar/day?date=${ymd(calAnchor)}`;
    try {
        if (force) await fetch('/api/calendar/refresh', { method: 'POST' });
        const d = await (await fetch(url)).json();
        calLoaded = true;
        calLastData = d;
        renderCalendar(d);
    } catch {
        calStatus('Unable to load the calendar.');
    }
}

function renderCalendar(d) {
    calLastData = d;
    const grid = document.getElementById('cal-grid');
    grid.innerHTML = '';
    updateCalRange();

    if (!d.connected) { renderSourceChips([]); calStatus(d.message || 'Calendar not connected.'); return; }

    const days = [];
    if (d.view === 'week') {
        const start = mondayOf(calAnchor);
        for (let i = 0; i < 7; i++) days.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
    } else {
        days.push(new Date(calAnchor.getFullYear(), calAnchor.getMonth(), calAnchor.getDate()));
    }

    renderSourceChips(d.events || []);
    const events = (d.events || []).filter(e => !calHidden.has(e.calendar));

    if (!events.length) {
        calStatus(d.view === 'week' ? 'No events this week.' : 'No events today.');
        return;
    }
    calStatus(null);

    grid.appendChild(buildGrid(days, events));
    const scroll = grid.querySelector('.cal-scroll');
    if (scroll) scroll.scrollTop = CAL_SCROLL_HOUR * CAL_HOUR_PX;
}

function updateCalRange() {
    const label = document.getElementById('cal-range');
    if (!label) return;
    if (calView === 'week') {
        const s = mondayOf(calAnchor);
        const e = new Date(s.getFullYear(), s.getMonth(), s.getDate() + 6);
        const opt = { month: 'short', day: 'numeric' };
        const right = s.getMonth() === e.getMonth() ? e.getDate() : e.toLocaleDateString([], opt);
        label.textContent = `${s.toLocaleDateString([], opt)} – ${right}, ${e.getFullYear()}`;
    } else {
        label.textContent = calAnchor.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    }
}

function calHue(name) {
    let h = 0;
    const s = name || '';
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
    return h;
}

// Hue (0-359) of a #RRGGBB colour, or null if it isn't a valid hex string.
function hexToHue(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return null;
    const n = parseInt(m[1], 16);
    const r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    if (d === 0) return 0;
    let h;
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    return (Math.round(h * 60) + 360) % 360;
}

// Prefer the calendar's real Apple colour (hex), fall back to the name hash.
// Using the hue (not the raw colour) keeps FireFrame's dark-mode-tuned tones,
// so event blocks stay readable instead of glaring.
function hueForCalendar(name, colorHex) {
    if (colorHex) {
        const h = hexToHue(colorHex);
        if (h !== null) return h;
    }
    return calHue(name);
}

function renderSourceChips(events) {
    const wrap = document.getElementById('cal-sources');
    if (!wrap) return;
    const cals = [];
    const seen = new Set();
    events.forEach(e => {
        if (e.calendar && !seen.has(e.calendar)) {
            seen.add(e.calendar);
            cals.push({ name: e.calendar, color: e.calendar_color });
        }
    });
    if (cals.length <= 1) { wrap.classList.add('hidden'); wrap.innerHTML = ''; return; }
    wrap.classList.remove('hidden');
    wrap.innerHTML = '';
    cals.forEach(c => {
        const n = c.name;
        const chip = el('button', 'cal-chip' + (calHidden.has(n) ? ' off' : ''));
        chip.style.setProperty('--chip-hue', hueForCalendar(n, c.color));
        chip.appendChild(el('span', 'cal-chip-dot'));
        chip.appendChild(el('span', '', n));
        chip.addEventListener('click', () => {
            if (calHidden.has(n)) calHidden.delete(n); else calHidden.add(n);
            renderCalendar(calLastData);
        });
        wrap.appendChild(chip);
    });
}

function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
}

function hourLabel(h) {
    if (h === 0 || h === 24) return '';
    const ampm = h < 12 ? 'AM' : 'PM';
    return `${h % 12 === 0 ? 12 : h % 12} ${ampm}`;
}

function buildGrid(days, events) {
    const inner = el('div', 'cal-grid-inner');
    inner.style.setProperty('--cal-cols', days.length);
    const today = ymd(new Date());

    // Header: corner + day labels
    const head = el('div', 'cal-head');
    head.appendChild(el('div', 'cal-corner'));
    days.forEach(day => {
        const h = el('div', 'cal-dayhead' + (ymd(day) === today ? ' today' : ''));
        h.appendChild(el('div', 'cal-dayhead-wd', day.toLocaleDateString([], { weekday: 'short' })));
        h.appendChild(el('div', 'cal-dayhead-dn', String(day.getDate())));
        head.appendChild(h);
    });
    inner.appendChild(head);

    // All-day events get their own row, as blocks that span the days they cover.
    const allDayItems = allDayLayout(days, events.filter(ev => ev.all_day));
    if (allDayItems.length) {
        const lanes = Math.max(...allDayItems.map(it => it.lane)) + 1;
        const row = el('div', 'cal-allday');
        row.style.setProperty('--ad-lanes', lanes);
        row.appendChild(el('div', 'cal-allday-label', 'all-day'));
        allDayItems.forEach(it => row.appendChild(allDayBlock(it)));
        inner.appendChild(row);
    }

    // Scrollable timed grid (timed events only; all-day handled above)
    const timed = events.filter(ev => !ev.all_day);
    const scroll = el('div', 'cal-scroll');
    const body = el('div', 'cal-body');
    body.style.height = (24 * CAL_HOUR_PX) + 'px';

    const axis = el('div', 'cal-axis');
    for (let h = 0; h <= 24; h++) {
        const lab = el('div', 'cal-axis-h', hourLabel(h));
        lab.style.top = (h * CAL_HOUR_PX) + 'px';
        axis.appendChild(lab);
    }
    body.appendChild(axis);

    days.forEach(day => {
        const col = el('div', 'cal-col' + (ymd(day) === today ? ' today' : ''));
        layoutTimed(day, timed).forEach(b => col.appendChild(b));
        body.appendChild(col);
    });

    scroll.appendChild(body);
    inner.appendChild(scroll);
    return inner;
}

// Work out which day columns each all-day event spans, then stack overlapping
// ones into separate lanes so they never sit on top of each other.
function allDayLayout(days, events) {
    const bounds = days.map(d => {
        const ds = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        return [ds, new Date(ds.getTime() + 86400000)];
    });
    const items = [];
    events.forEach(ev => {
        const es = new Date(ev.start), ee = new Date(ev.end);
        let startIdx = -1, endIdx = -1;
        bounds.forEach(([ds, de], i) => {
            if (es < de && ee > ds) { if (startIdx < 0) startIdx = i; endIdx = i; }
        });
        if (startIdx >= 0) items.push({ ev, startIdx, span: endIdx - startIdx + 1 });
    });
    items.sort((a, b) => a.startIdx - b.startIdx || b.span - a.span);
    const laneEnd = [];   // last covered column index per lane
    items.forEach(it => {
        let placed = false;
        for (let L = 0; L < laneEnd.length; L++) {
            if (it.startIdx > laneEnd[L]) { it.lane = L; laneEnd[L] = it.startIdx + it.span - 1; placed = true; break; }
        }
        if (!placed) { it.lane = laneEnd.length; laneEnd.push(it.startIdx + it.span - 1); }
    });
    return items;
}

function allDayBlock(it) {
    const ev = it.ev;
    const b = el('div', 'cal-allday-ev', ev.title);
    b.style.setProperty('--ev-hue', hueForCalendar(ev.calendar, ev.calendar_color));
    b.style.gridColumn = `${2 + it.startIdx} / span ${it.span}`;   // +1 axis, +1 to 1-base
    b.style.gridRow = String(it.lane + 1);
    if (ev.location) b.title = ev.location;
    b.addEventListener('click', () => showEventDetails(ev));
    return b;
}

// Place timed events for one day, splitting width across overlapping events.
function layoutTimed(day, events) {
    const ds = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const de = new Date(ds.getTime() + 86400000);
    const items = [];
    events.forEach(ev => {
        const es = new Date(ev.start), ee = new Date(ev.end);
        if (ee <= ds || es >= de) return;   // not on this day
        const startH = Math.max(0, (es - ds) / 3600000);
        const endH = Math.min(24, (ee - ds) / 3600000);
        items.push({ ev, startH, endH: Math.max(endH, startH + 0.25) });
    });
    items.sort((a, b) => a.startH - b.startH || a.endH - b.endH);

    const blocks = [];
    let i = 0;
    while (i < items.length) {
        const cluster = [items[i]];
        let clusterEnd = items[i].endH, j = i + 1;
        while (j < items.length && items[j].startH < clusterEnd) {
            cluster.push(items[j]);
            clusterEnd = Math.max(clusterEnd, items[j].endH);
            j++;
        }
        const cols = [];
        cluster.forEach(it => {
            let placed = false;
            for (let c = 0; c < cols.length; c++) {
                if (it.startH >= cols[c] - 1e-6) { it.col = c; cols[c] = it.endH; placed = true; break; }
            }
            if (!placed) { it.col = cols.length; cols.push(it.endH); }
        });
        cluster.forEach(it => blocks.push(timedBlock(it, cols.length)));
        i = j;
    }
    return blocks;
}

function timedBlock(it, nCols) {
    const ev = it.ev;
    const b = el('div', 'cal-event');
    b.style.setProperty('--ev-hue', hueForCalendar(ev.calendar, ev.calendar_color));
    b.style.top = (it.startH * CAL_HOUR_PX) + 'px';
    b.style.height = Math.max(16, (it.endH - it.startH) * CAL_HOUR_PX - 2) + 'px';
    const w = 100 / nCols;
    b.style.left = (it.col * w) + '%';
    b.style.width = `calc(${w}% - 3px)`;
    b.appendChild(el('div', 'cal-event-title', ev.title));
    b.appendChild(el('div', 'cal-event-time', `${fmtTime(ev.start)} – ${fmtTime(ev.end)}`));
    if (ev.location) b.title = ev.location;
    b.addEventListener('click', () => showEventDetails(ev));
    return b;
}

// --- event details popup ---
function setupEventModal() {
    const modal = document.getElementById('event-modal');
    if (!modal) return;
    const close = () => modal.classList.add('hidden');
    const btn = document.getElementById('ev-detail-close');
    if (btn) btn.addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });   // tap backdrop
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
}

function showEventDetails(ev) {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const row = (id, show) => { const el = document.getElementById(id); if (el) el.classList.toggle('hidden', !show); };

    set('ev-detail-title', ev.title || 'Untitled');
    const dot = document.getElementById('ev-detail-dot');
    if (dot) dot.style.background = `hsl(${hueForCalendar(ev.calendar, ev.calendar_color)}, 70%, 60%)`;

    const s = new Date(ev.start), e = new Date(ev.end);
    set('ev-detail-when', ev.all_day ? 'All day' : `${fmtTime(ev.start)} – ${fmtTime(ev.end)}`);

    const dOpt = { weekday: 'long', month: 'long', day: 'numeric' };
    const dispEnd = ev.all_day ? new Date(e.getTime() - 1) : e;   // all-day end is exclusive midnight
    const sameDay = s.toDateString() === dispEnd.toDateString();
    set('ev-detail-date', sameDay
        ? s.toLocaleDateString([], dOpt)
        : `${s.toLocaleDateString([], dOpt)} – ${dispEnd.toLocaleDateString([], dOpt)}`);

    set('ev-detail-loc', ev.location || '');
    row('ev-detail-loc-row', !!ev.location);
    set('ev-detail-cal', ev.calendar || '');
    row('ev-detail-cal-row', !!ev.calendar);

    const notes = document.getElementById('ev-detail-notes');
    if (notes) {
        notes.textContent = ev.description || '';
        notes.classList.toggle('hidden', !ev.description);
    }
    document.getElementById('event-modal').classList.remove('hidden');
}

// Home tab: the next few events, with a live countdown on the first one.
async function loadHomeNextEvent() {
    const wrap = document.getElementById('home-events');
    try {
        renderHomeEvents(await (await fetch('/api/calendar/upcoming')).json());
    } catch {
        if (wrap) wrap.innerHTML = '<div class="home-empty">Could not load the calendar.</div>';
    }
}

function renderHomeEvents(d) {
    const wrap = document.getElementById('home-events');
    if (!wrap) return;
    wrap.innerHTML = '';
    clearInterval(calendarCountdownInterval);

    if (!d.connected) {
        const msg = el('div', 'home-empty');
        msg.append((d.message || 'Calendar not connected.') + ' ');
        const link = el('span', 'home-setup-link', 'Open Settings');
        link.addEventListener('click', () => switchTab('settings'));
        msg.appendChild(link);
        wrap.appendChild(msg);
        return;
    }

    const events = (d.events || []).slice(0, 3);
    if (!events.length) { wrap.appendChild(el('div', 'home-empty', 'No upcoming events.')); return; }

    let firstSub = null;
    events.forEach((ev, i) => {
        const row = el('div', 'home-ev');
        row.appendChild(el('div', 'home-ev-time', ev.all_day ? 'All day' : fmtTime(ev.start)));
        const main = el('div', 'home-ev-main');
        main.appendChild(el('div', 'home-ev-title', ev.title));
        if (i === 0 && !ev.all_day) { firstSub = el('div', 'home-ev-sub'); main.appendChild(firstSub); }
        row.appendChild(main);
        wrap.appendChild(row);
    });

    if (firstSub) {
        const start = new Date(events[0].start);
        const tick = () => {
            const diff = start - new Date();
            if (diff > 0) {
                const h = Math.floor(diff / 3600000), m = Math.floor((diff % 3600000) / 60000);
                firstSub.textContent = 'in ' + (h > 0 ? h + 'h ' : '') + m + 'm';
            } else {
                firstSub.textContent = 'now';
            }
        };
        tick();
        calendarCountdownInterval = setInterval(tick, 60000);
    }
}

// Optional Home weather card (macOS Shortcut source). Hidden unless enabled.
async function fetchWeather() {
    const card = document.getElementById('home-weather-card');
    if (!card) return;
    try {
        const d = await (await fetch('/api/weather')).json();
        if (!d.enabled) { card.classList.add('hidden'); return; }
        card.classList.remove('hidden');
        setText('home-weather', d.available ? d.text : (d.message || 'Weather Shortcut not set up.'));
    } catch {
        card.classList.add('hidden');
    }
}

// Subtle Home footer: server status, tablet URL, version, last refresh.
async function fillHomeStatus() {
    setText('home-ff-url', window.location.origin);
    setText('home-ff-version', window.FF_VERSION || '—');
    try {
        const s = await (await fetch('/api/status')).json();
        setStatus('home-ff-server', s.message || 'Running', 'ok');
    } catch {
        setStatus('home-ff-server', 'Offline', 'off');
    }
}

function setupHome() {
    const copy = document.getElementById('home-copy-url');
    if (copy) copy.addEventListener('click', copyTabletUrl);
    const toggle = document.getElementById('home-timer-toggle');
    if (toggle) toggle.addEventListener('click', toggleTimer);
    const cancel = document.getElementById('home-timer-cancel');
    if (cancel) cancel.addEventListener('click', cancelTimer);
    const custom = document.getElementById('home-timer-custom');
    if (custom) custom.addEventListener('click', () => openTimerModal(true));
}

// ============================================================
// BLUETOOTH SELECTOR (macOS)
// ============================================================
function setupBluetooth() {
    const btn = document.getElementById('bt-refresh-btn');
    if (btn) btn.addEventListener('click', () => loadBluetooth(true));

    // Event delegation for connect/disconnect buttons in the device list.
    const list = document.getElementById('bt-device-list');
    if (list) {
        list.addEventListener('click', e => {
            const action = e.target.closest('button[data-bt-action]');
            if (!action) return;
            const id = action.getAttribute('data-bt-id');
            const want = action.getAttribute('data-bt-action'); // connect | disconnect
            btAction(want, id, action);
        });
    }
}

function btShowOnly(visibleId) {
    ['bt-loading', 'bt-empty'].forEach(s => {
        const el = document.getElementById(s);
        if (el) el.classList.toggle('hidden', s !== visibleId);
    });
}

async function loadBluetooth(force = false) {
    btShowOnly('bt-loading');
    setText('bt-state-text', 'Scanning...');
    try {
        const url = force ? '/api/bluetooth/refresh' : '/api/bluetooth/devices';
        const res = await fetch(url, { method: force ? 'POST' : 'GET' });
        const d = await res.json();
        renderBluetooth(d);
    } catch {
        btShowOnly(null);
        setText('bt-state-text', 'Error scanning');
        setBtNote('Could not reach the server.');
    }
}

function setBtNote(msg) {
    const note = document.getElementById('bt-note');
    if (!note) return;
    if (msg) { note.textContent = msg; note.classList.remove('hidden'); }
    else { note.classList.add('hidden'); }
}

function renderBluetooth(d) {
    const list = document.getElementById('bt-device-list');
    const pill = document.getElementById('bt-power-pill');
    list.innerHTML = '';

    // Power/availability pill
    let pillText = '—', pillClass = '';
    if (!d.available) { pillText = 'Unavailable'; }
    else if (d.powered === false) { pillText = 'Off'; }
    else if (d.powered === true) { pillText = 'On'; pillClass = 'on'; }
    else { pillText = 'Unknown'; }
    pill.textContent = pillText;
    pill.className = 'pill-badge ' + pillClass;

    if (!d.available) {
        btShowOnly(null);
        setText('bt-state-text', d.message || 'Bluetooth unavailable on this platform.');
        setBtNote(null);
        return;
    }

    setText('bt-state-text', d.connect_supported
        ? 'Tap a device to connect or disconnect.'
        : 'Listing devices (read-only).');
    setBtNote(d.connect_supported ? null : d.note);

    const devices = d.devices || [];
    if (!devices.length) { btShowOnly('bt-empty'); return; }
    btShowOnly(null);

    devices.forEach(dev => {
        const row = document.createElement('div');
        row.className = 'bt-row';

        const icon = document.createElement('div');
        icon.className = 'bt-row-icon';
        icon.textContent = btIconFor(dev.type);

        const main = document.createElement('div');
        main.className = 'bt-row-main';
        const name = document.createElement('div');
        name.className = 'bt-row-name';
        name.textContent = dev.name || 'Unknown device';
        const sub = document.createElement('div');
        sub.className = 'bt-row-sub' + (dev.connected ? ' connected' : '');
        sub.textContent = dev.connected ? 'Connected' : 'Not connected';
        main.appendChild(name);
        main.appendChild(sub);

        row.appendChild(icon);
        row.appendChild(main);

        if (d.connect_supported && dev.actionable) {
            const act = document.createElement('button');
            act.className = 'btn small-btn' + (dev.connected ? ' danger-btn' : ' primary-btn');
            act.textContent = dev.connected ? 'Disconnect' : 'Connect';
            act.setAttribute('data-bt-action', dev.connected ? 'disconnect' : 'connect');
            act.setAttribute('data-bt-id', dev.id);
            row.appendChild(act);
        }
        list.appendChild(row);
    });
}

function btIconFor(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('headphone') || t.includes('headset') || t.includes('audio')) return '🎧';
    if (t.includes('speaker')) return '🔊';
    if (t.includes('keyboard')) return '⌨️';
    if (t.includes('mouse') || t.includes('trackpad')) return '🖱️';
    if (t.includes('phone')) return '📱';
    return '🔵';
}

async function btAction(want, id, btnEl) {
    if (!id) return;
    btnEl.disabled = true;
    const original = btnEl.textContent;
    btnEl.textContent = want === 'connect' ? 'Connecting...' : 'Disconnecting...';
    try {
        const res = await fetch('/api/bluetooth/' + want, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        showToast(data.success ? (data.message || 'Done.') : `Error: ${data.message}`, !data.success);
    } catch {
        showToast('Connection error.', true);
    } finally {
        btnEl.textContent = original;
        btnEl.disabled = false;
        // Give the radio a moment, then refresh the list to reflect new state.
        setTimeout(() => loadBluetooth(true), 1200);
    }
}

// ============================================================
// MAC STATS DASHBOARD
// ============================================================
// Polled every 5s, but only while the Stats tab is open and the page is
// visible (see switchTab / setupVisibility). Heavier reads are cached on the
// server, so this stays cheap to leave running.
const MAC_STATS_POLL_MS = 5000;

function setupMacStats() {
    const btn = document.getElementById('ms-refresh-btn');
    if (btn) btn.addEventListener('click', () => fetchMacStats());
}

function startMacStats() {
    if (!macStatsInterval) {
        fetchMacStats();
        macStatsInterval = setInterval(fetchMacStats, MAC_STATS_POLL_MS);
    }
    if (!macStatsClock) {
        tickMacStatsClock();
        macStatsClock = setInterval(tickMacStatsClock, 1000);
    }
}

function stopMacStats() {
    clearInterval(macStatsInterval);
    macStatsInterval = null;
    clearInterval(macStatsClock);
    macStatsClock = null;
}

function tickMacStatsClock() {
    setText('ms-time', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
}

async function fetchMacStats() {
    if (!isLoggedIn) return;
    const errEl = document.getElementById('ms-error');
    try {
        const res = await fetch('/api/mac-stats');
        if (!res.ok) throw new Error('bad status');
        const d = await res.json();
        if (errEl) errEl.classList.add('hidden');
        renderMacStats(d);
    } catch {
        if (errEl) errEl.classList.remove('hidden');
    }
}

function renderMacStats(d) {
    const sys = d.system || {};
    setText('ms-subtitle', d.is_mac ? (sys.name || '') : 'Some stats are macOS-only on this platform.');
    setText('ms-name', sys.name || '—');
    setText('ms-os', sys.os_version ? `${sys.os_name} ${sys.os_version}` : (sys.os_name || '—'));
    setText('ms-uptime', fmtUptime(sys.uptime_seconds));
    setText('ms-updated', 'Updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));

    // CPU
    const cpu = d.cpu || {};
    setText('ms-cpu-pct', fmtPct(cpu.percent));
    setBar('ms-cpu-bar', cpu.percent);
    setText('ms-cpu-cores', cpu.cores_logical ? `${cpu.cores_logical} cores` : '—');

    // Memory
    const mem = d.memory || {};
    setText('ms-mem-pct', fmtPct(mem.percent));
    setBar('ms-mem-bar', mem.percent);
    setText('ms-mem-detail', mem.used_gb != null
        ? `${mem.used_gb} GB used · ${mem.available_gb} GB avail · ${mem.total_gb} GB total`
        : '—');

    // Battery
    const b = d.battery || {};
    if (b.available) {
        setText('ms-batt-pct', b.percent + '%');
        setBar('ms-batt-bar', b.percent);
        let detail = b.charging ? 'Charging' : (b.power_source || 'On battery');
        if (b.time_left) detail += ` · ${b.time_left} left`;
        setText('ms-batt-detail', detail);
    } else {
        setText('ms-batt-pct', 'N/A');
        setBar('ms-batt-bar', 0);
        setText('ms-batt-detail', 'No battery detected');
    }

    // Storage
    const dk = d.disk || {};
    if (dk.available) {
        setText('ms-disk-pct', fmtPct(dk.percent));
        setBar('ms-disk-bar', dk.percent);
        setText('ms-disk-detail', `${dk.used_gb} GB used · ${dk.free_gb} GB free · ${dk.total_gb} GB total`);
    } else {
        setText('ms-disk-pct', '—');
        setBar('ms-disk-bar', 0);
        setText('ms-disk-detail', 'Unavailable');
    }

    // Network
    const n = d.network || {};
    setText('ms-conn', n.connected ? 'Connected' : 'Not connected');
    setText('ms-ip', n.local_ip || 'Unavailable');
    setText('ms-down', fmtRate(n.down_bps));
    setText('ms-up', fmtRate(n.up_bps));

    // Processes
    renderProcList('ms-proc-cpu', (d.processes && d.processes.by_cpu) || [], 'cpu');
    renderProcList('ms-proc-mem', (d.processes && d.processes.by_mem) || [], 'mem');

    // Volume
    const v = d.volume || {};
    setText('ms-volume', v.available ? (v.muted ? 'Muted' : v.percent + '%') : 'Unavailable');
}

function fmtPct(x) { return (x == null) ? '—' : Math.round(x) + '%'; }

function fmtUptime(s) {
    s = s || 0;
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function fmtRate(bps) {
    // bytes/s -> MB/s using decimal MB (1 MB = 1,000,000 bytes).
    return `${(Math.max(0, bps || 0) / 1e6).toFixed(2)} MB/s`;
}

function setBar(id, pct) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = Math.max(0, Math.min(100, pct || 0));
    el.style.width = v + '%';
    el.classList.toggle('warn', v >= 75 && v < 90);
    el.classList.toggle('crit', v >= 90);
}

function renderProcList(id, rows, key) {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.innerHTML = '';
    if (!rows.length) { wrap.appendChild(el('div', 'ms-proc-empty', '—')); return; }
    const valOf = (r) => key === 'cpu' ? r.cpu : r.mem;
    // Scale bars to the busiest process in the list so the column reads clearly
    // even when every value is a small share of the whole CPU/RAM.
    const max = Math.max(1, ...rows.map(valOf));
    rows.forEach(r => {
        const v = valOf(r);
        const row = el('div', 'ms-proc-row');
        row.appendChild(el('span', 'nm', r.name));
        const bar = el('div', 'ms-proc-bar');
        const fill = el('div', 'ms-proc-bar-fill' + (key === 'mem' ? ' mem' : ''));
        fill.style.width = Math.max(4, Math.round(v / max * 100)) + '%';
        bar.appendChild(fill);
        row.appendChild(bar);
        row.appendChild(el('span', 'vl', v + '%'));
        wrap.appendChild(row);
    });
}

function fmtTime(iso) {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

// ============================================================
// MODALS
// ============================================================
function setupModals() {
    // Restart-instructions modal
    const restartClose = document.getElementById('restart-close-btn');
    if (restartClose) restartClose.addEventListener('click', () =>
        document.getElementById('restart-modal').classList.add('hidden'));

    // Generic confirm modal
    const confirmModal = document.getElementById('confirm-modal');
    document.getElementById('confirm-cancel-btn').addEventListener('click', hideConfirm);
    document.getElementById('confirm-ok-btn').addEventListener('click', () => {
        const cb = _confirmCb;
        hideConfirm();
        if (cb) cb();
    });
    if (confirmModal) confirmModal.addEventListener('click', e => { if (e.target === confirmModal) hideConfirm(); });

    setupTimer();
}

// ============================================================
// TIMER  (FireFrame's own countdown; gentle Mac notification on finish)
// One active timer. The countdown runs client-side; completion pings the
// server to post a passive macOS notification (see /api/timer/notify). A single
// interval is used and always cleared before a new one starts (no stacking).
// ============================================================
const TIMER_PRESETS = { 5: '5 min timer', 15: '15 min timer', 25: 'Focus timer', 45: 'Work timer' };

let tmrInterval = null;
let tmrRemaining = 0;          // seconds left
let tmrTotal = 0;             // seconds total
let tmrName = 'Timer';
let tmrMode = 'idle';        // idle | running | paused | finished (timer state)
let tmrCustomOpen = false;   // is the custom-entry view showing? (view only)

function setupTimer() {
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };

    on('timer-custom-btn', () => openTimerModal(true)); // Timers section "Custom"

    // Buttons-page presets open the timer panel; Home presets start quietly
    // (the Home timer card already shows the running state).
    document.querySelectorAll('.action-btn[data-timer]').forEach(btn => {
        btn.addEventListener('click', () => startTimerFor(parseInt(btn.getAttribute('data-timer'), 10)));
    });
    document.querySelectorAll('#home-timer-quick [data-timer]').forEach(btn => {
        btn.addEventListener('click', () => startTimerFor(parseInt(btn.getAttribute('data-timer'), 10), null, false));
    });
    document.querySelectorAll('.timer-quick [data-quick]').forEach(btn => {
        btn.addEventListener('click', () => startTimerFor(parseInt(btn.getAttribute('data-quick'), 10)));
    });

    on('timer-toggle-btn', toggleTimer);
    on('timer-reset-btn', resetTimer);
    on('timer-cancel-btn', cancelTimer);
    on('timer-close-btn', closeTimerModal);
    on('timer-start-btn', startCustomTimer);
    on('timer-chip', () => openTimerModal());

    renderTimer();
}

function timerModalEl() { return document.getElementById('timer-modal'); }

function openTimerModal(forceCustom) {
    const m = timerModalEl();
    if (m) m.classList.remove('hidden');
    if (forceCustom || tmrMode === 'idle') showCustomEntry();
    else { tmrCustomOpen = false; renderTimer(); }
}

function closeTimerModal() {
    const m = timerModalEl();
    if (m) m.classList.add('hidden');
}

// Show the custom-entry view. This does NOT change the timer state, so a timer
// already running keeps counting down (and its chip keeps updating) underneath.
function showCustomEntry() {
    tmrCustomOpen = true;
    const err = document.getElementById('timer-error');
    if (err) err.classList.add('hidden');
    renderTimer();
}

function presetName(mins) {
    if (TIMER_PRESETS[mins]) return TIMER_PRESETS[mins];
    if (mins >= 60) {
        const h = Math.floor(mins / 60), mm = mins % 60;
        return mm ? `${h}h ${mm}m timer` : `${h}h timer`;
    }
    return `${mins} min timer`;
}

function startTimerFor(mins, name, openModal = true) {
    if (!mins || mins < 1) return;
    tmrCustomOpen = false;
    tmrName = name || presetName(mins);
    tmrTotal = mins * 60;
    tmrRemaining = tmrTotal;
    tmrMode = 'running';
    runTimerInterval();
    if (openModal) { const m = timerModalEl(); if (m) m.classList.remove('hidden'); }
    renderTimer();
    updateChip();
}

function startCustomTimer() {
    const h = parseInt(document.getElementById('timer-hours').value, 10) || 0;
    const mins = parseInt(document.getElementById('timer-mins').value, 10) || 0;
    const total = h * 60 + mins;
    const err = document.getElementById('timer-error');
    const fail = (msg) => { if (err) { err.textContent = msg; err.classList.remove('hidden'); } };
    if (h < 0 || mins < 0 || total < 1) return fail('Enter at least 1 minute.');
    if (total > 1440) return fail('Maximum is 24 hours.');
    if (err) err.classList.add('hidden');
    document.getElementById('timer-hours').value = '';
    document.getElementById('timer-mins').value = '';
    startTimerFor(total);
}

function runTimerInterval() {
    clearInterval(tmrInterval);   // never stack intervals
    tmrInterval = setInterval(timerTick, 1000);
}

function timerTick() {
    if (tmrMode !== 'running') return;
    tmrRemaining--;
    if (tmrRemaining <= 0) { finishTimer(); return; }
    renderTimer();
    updateChip();
}

function toggleTimer() {
    if (tmrMode === 'running') {
        tmrMode = 'paused';
        clearInterval(tmrInterval);
        tmrInterval = null;
    } else if (tmrMode === 'paused') {
        tmrMode = 'running';
        runTimerInterval();
    } else {
        return;
    }
    renderTimer();
    updateChip();
}

function resetTimer() {
    if (tmrMode === 'idle') return;
    clearInterval(tmrInterval);
    tmrInterval = null;
    tmrRemaining = tmrTotal;
    tmrMode = 'paused';
    renderTimer();
    updateChip();
}

function cancelTimer() {
    clearInterval(tmrInterval);
    tmrInterval = null;
    tmrMode = 'idle';
    tmrRemaining = 0;
    tmrTotal = 0;
    tmrCustomOpen = false;
    updateChip();
    closeTimerModal();
}

function finishTimer() {
    clearInterval(tmrInterval);
    tmrInterval = null;
    tmrRemaining = 0;
    tmrMode = 'finished';
    tmrCustomOpen = false;   // surface the finished state even if custom was open
    renderTimer();
    updateChip();
    showToast(`⏱️ ${tmrName} finished`);
    notifyTimerDone(tmrName, Math.round(tmrTotal / 60));
}

// Ping the server to post a passive macOS notification. The on-screen finished
// state is the primary signal, so a failure here is silently ignored.
async function notifyTimerDone(label, minutes) {
    try {
        await fetch('/api/timer/notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ minutes, label })
        });
    } catch { /* ignore */ }
}

function fmtClock(totalSec) {
    totalSec = Math.max(0, totalSec);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function renderTimer() {
    const show = (id, vis) => { const el = document.getElementById(id); if (el) el.classList.toggle('hidden', !vis); };
    const custom = tmrCustomOpen;

    show('timer-custom', custom);
    show('timer-display', !custom);
    show('timer-state', !custom);
    const controls = document.querySelector('.timer-controls');
    if (controls) controls.classList.toggle('hidden', custom);

    setText('timer-name', custom ? 'Custom Timer' : tmrName);
    setText('timer-display', fmtClock(tmrRemaining));
    setText('timer-state', { running: 'Running', paused: 'Paused', finished: 'Done', idle: 'Ready' }[tmrMode] || '');

    const box = document.querySelector('#timer-modal .timer-box');
    if (box) box.classList.toggle('timer-done', tmrMode === 'finished');

    const toggle = document.getElementById('timer-toggle-btn');
    if (toggle) {
        toggle.textContent = tmrMode === 'paused' ? 'Resume' : 'Pause';
        toggle.classList.toggle('hidden', tmrMode === 'finished');
    }

    renderHomeTimer();
}

// Mirror the timer state into the Home card: active controls vs quick-start.
function renderHomeTimer() {
    const active = document.getElementById('home-timer-active');
    const quick = document.getElementById('home-timer-quick');
    if (!active || !quick) return;
    const running = ['running', 'paused', 'finished'].includes(tmrMode);
    active.classList.toggle('hidden', !running);
    quick.classList.toggle('hidden', running);
    if (!running) return;
    setText('home-timer-name', tmrMode === 'finished' ? `${tmrName} · Done` : tmrName);
    setText('home-timer-time', fmtClock(tmrRemaining));
    active.classList.toggle('timer-done', tmrMode === 'finished');
    const toggle = document.getElementById('home-timer-toggle');
    if (toggle) {
        toggle.textContent = tmrMode === 'paused' ? 'Resume' : 'Pause';
        toggle.classList.toggle('hidden', tmrMode === 'finished');
    }
}

function updateChip() {
    const chip = document.getElementById('timer-chip');
    if (!chip) return;
    const active = ['running', 'paused', 'finished'].includes(tmrMode);
    chip.classList.toggle('hidden', !active);
    chip.classList.toggle('done', tmrMode === 'finished');
    chip.classList.toggle('paused', tmrMode === 'paused');
    setText('timer-chip-time', tmrMode === 'finished' ? 'Done' : fmtClock(tmrRemaining));
}

// ============================================================
// TASKS  (create / reschedule / delete calendar blocks from the tablet)
// The UI says "task"; each is a real Apple Calendar event sized by importance
// (Regular vs Important). All reads/writes go through /api/tasks. Input is
// collected on the tablet, or via native Mac dialogs in "mac_prompt" mode.
// ============================================================
let taskImportance = 'regular';
let taskConfig = null;          // { available, regular_minutes, important_minutes, input_location, ... }
let taskMode = 'create';        // 'create' | 'edit' (reschedule reuses the modal)
let taskEditId = null;          // event id being rescheduled
let detailTask = null;          // task shown in the details modal
let calSection = 'calendar';    // Calendar tab sub-view: 'calendar' | 'tasks'
// Durations used only before /api/tasks/config has loaded (mirrors the backend defaults).
const TASK_FALLBACK = { regular_minutes: 60, important_minutes: 240 };
// Default start time for a new task (7 PM).
const DEFAULT_TASK_TIME = '19:00';

function setupTasks() {
    const on = (id, fn) => { const node = document.getElementById(id); if (node) node.addEventListener('click', fn); };
    on('home-add-task', addTask);
    on('home-view-all-tasks', viewAllTasks);
    on('caltask-add', addTask);
    on('task-cancel-btn', closeTaskModal);
    on('task-save-btn', submitTask);
    document.querySelectorAll('#task-modal [data-importance]').forEach(btn => {
        btn.addEventListener('click', () => setTaskImportance(btn.getAttribute('data-importance')));
    });
    const modal = document.getElementById('task-modal');
    if (modal) modal.addEventListener('click', e => { if (e.target === modal) closeTaskModal(); });

    // Task details modal
    on('td-close', closeTaskDetail);
    on('td-reschedule', () => { const t = detailTask; if (!t) return; closeTaskDetail(); openTaskModal(t); });
    on('td-delete', () => {
        const t = detailTask;
        if (!t || !t.event_id) return;
        closeTaskDetail();
        showConfirm('Delete this task?', () => deleteTask(t.event_id));
    });
    const dm = document.getElementById('task-detail-modal');
    if (dm) dm.addEventListener('click', e => { if (e.target === dm) closeTaskDetail(); });

    // Calendar tab: Calendar | Tasks sub-view
    document.querySelectorAll('[data-calsec]').forEach(btn => {
        btn.addEventListener('click', () => setCalSection(btn.getAttribute('data-calsec')));
    });

    // Settings: task input-location toggle
    document.querySelectorAll('[data-task-input]').forEach(btn => {
        btn.addEventListener('click', () => setTaskInputLocation(btn.getAttribute('data-task-input')));
    });
}

// Decide where Add Task collects input, then open the tablet form or hand off
// to the Mac. Falls back to the tablet form when Mac prompt isn't usable.
async function addTask() {
    let loc = 'dashboard';
    try {
        const res = await fetch('/api/tasks/config');
        if (res.ok) {
            taskConfig = await res.json();
            loc = taskConfig.input_location || 'dashboard';
            if (loc === 'mac_prompt' && !taskConfig.mac_prompt_supported) loc = 'dashboard';
        }
    } catch { /* default to the tablet form */ }

    if (loc === 'mac_prompt') {
        try {
            const res = await fetch('/api/tasks/prompt', { method: 'POST' });
            const d = await res.json();
            if (res.ok && d.success) {
                showToast(d.message || 'Continue on your Mac.');
                // The dialogs stay open for an unknown time, so refresh a few
                // times to surface the task once it's saved.
                [10000, 30000, 60000].forEach(ms => setTimeout(refreshTaskViews, ms));
                return;
            }
            showToast((d && d.message) || 'Mac prompt unavailable; using the tablet form.', true);
        } catch {
            showToast('Mac prompt failed; using the tablet form.', true);
        }
    }
    openTaskModal();
}

// Open the modal for a new task, or to reschedule an existing one (editTask).
function openTaskModal(editTask) {
    const modal = document.getElementById('task-modal');
    if (!modal) return;
    const title = document.getElementById('task-title');
    const date = document.getElementById('task-date');
    const time = document.getElementById('task-time');
    const notes = document.getElementById('task-notes');
    const notesField = document.getElementById('task-notes-field');
    const calField = document.getElementById('task-cal-field');
    const header = document.getElementById('task-modal-title');
    const save = document.getElementById('task-save-btn');
    setTaskError('');

    if (editTask && editTask.event_id) {
        taskMode = 'edit';
        taskEditId = editTask.event_id;
        const s = new Date(editTask.start);
        if (title) { title.value = editTask.title || ''; title.disabled = true; }
        if (date) date.value = ymd(s);
        if (time) time.value = hhmm(s);
        setTaskImportance(inferImportance(editTask));
        if (notesField) notesField.classList.add('hidden');
        if (calField) calField.classList.add('hidden');
        if (header) header.textContent = 'Reschedule';
        if (save) save.textContent = 'Save';
    } else {
        taskMode = 'create';
        taskEditId = null;
        if (title) { title.value = ''; title.disabled = false; }
        if (notes) notes.value = '';
        if (date) date.value = ymd(new Date());
        if (time) time.value = DEFAULT_TASK_TIME;
        setTaskImportance('regular');
        if (notesField) notesField.classList.remove('hidden');
        if (header) header.textContent = 'New Task';
        if (save) save.textContent = 'Add Task';
    }
    modal.classList.remove('hidden');
    if (taskMode === 'create' && title) setTimeout(() => title.focus(), 50);
    loadTaskMeta();
}

function closeTaskModal() {
    const modal = document.getElementById('task-modal');
    if (modal) modal.classList.add('hidden');
}

function hhmm(d) {
    const pad = n => String(n).padStart(2, '0');
    return pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function setTaskImportance(level) {
    taskImportance = level === 'important' ? 'important' : 'regular';
    document.querySelectorAll('#task-modal [data-importance]').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-importance') === taskImportance);
    });
    updateDurationHint();
}

function updateDurationHint() {
    const hint = document.getElementById('task-duration-hint');
    if (!hint) return;
    const cfg = taskConfig || TASK_FALLBACK;
    const mins = taskImportance === 'important' ? cfg.important_minutes : cfg.regular_minutes;
    hint.textContent = (taskMode === 'edit' ? 'Resizes to a ' : 'Books a ') + describeDuration(mins) + ' block';
}

function describeDuration(mins) {
    mins = mins || 0;
    if (mins % 60 === 0) return (mins / 60) + 'h';
    if (mins > 60) return Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm';
    return mins + ' min';
}

// Tasks don't store an importance flag, so infer it from the block length.
function inferImportance(ev) {
    const mins = (new Date(ev.end) - new Date(ev.start)) / 60000;
    const threshold = (taskConfig || TASK_FALLBACK).important_minutes;
    return mins >= threshold ? 'important' : 'regular';
}

function setTaskError(msg) {
    const e = document.getElementById('task-error');
    if (!e) return;
    if (msg) { e.textContent = msg; e.classList.remove('hidden'); }
    else { e.textContent = ''; e.classList.add('hidden'); }
}

// Load durations + the calendar picker once the modal is open.
async function loadTaskMeta() {
    try {
        const res = await fetch('/api/tasks/config');
        if (res.ok) taskConfig = await res.json();
        updateDurationHint();
    } catch { /* keep the built-in defaults */ }
    if (taskMode === 'edit') return;   // reschedule keeps the task's own calendar
    await loadTaskCalendars();
}

async function loadTaskCalendars() {
    const field = document.getElementById('task-cal-field');
    const select = document.getElementById('task-calendar');
    if (!field || !select) return;
    try {
        const res = await fetch('/api/tasks/calendars');
        if (!res.ok) { field.classList.add('hidden'); return; }
        const d = await res.json();
        const cals = d.calendars || [];
        if (!d.available || !cals.length) {
            field.classList.add('hidden');
            if (d.message && taskConfig && !taskConfig.available) setTaskError(d.message);
            return;
        }
        select.innerHTML = '';
        cals.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            if (c.id === d.suggested_id) opt.selected = true;
            select.appendChild(opt);
        });
        // Only show the picker when there's an actual choice to make.
        field.classList.toggle('hidden', cals.length < 2);
    } catch {
        field.classList.add('hidden');
    }
}

async function submitTask() {
    const date = document.getElementById('task-date').value;
    const time = document.getElementById('task-time').value;
    if (!date) return setTaskError('Pick a date.');
    if (!time) return setTaskError('Pick a start time.');
    setTaskError('');

    const save = document.getElementById('task-save-btn');
    const label = save ? save.textContent : '';
    if (save) { save.disabled = true; save.textContent = taskMode === 'edit' ? 'Saving...' : 'Adding...'; }
    try {
        let res;
        if (taskMode === 'edit') {
            res = await fetch('/api/tasks/reschedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ event_id: taskEditId, date, time, importance: taskImportance })
            });
        } else {
            const title = (document.getElementById('task-title').value || '').trim();
            if (!title) { setTaskError('Give the task a title.'); return; }
            const notes = (document.getElementById('task-notes').value || '').trim();
            const field = document.getElementById('task-cal-field');
            const select = document.getElementById('task-calendar');
            const calendarId = (field && !field.classList.contains('hidden') && select) ? select.value : '';
            res = await fetch('/api/tasks/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, date, time, importance: taskImportance, notes, calendar_id: calendarId })
            });
        }
        const data = await res.json();
        if (!res.ok || !data.success) {
            setTaskError((data && data.message) || 'Could not save the task.');
            return;
        }
        closeTaskModal();
        showToast(data.message || (taskMode === 'edit' ? 'Task rescheduled.' : 'Task added.'));
        refreshTaskViews();
    } catch {
        setTaskError('Connection error. Try again.');
    } finally {
        if (save) { save.disabled = false; save.textContent = label; }
    }
}

async function deleteTask(eventId) {
    try {
        const res = await fetch('/api/tasks/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_id: eventId })
        });
        const d = await res.json();
        const ok = res.ok && d.success;
        showToast(ok ? (d.message || 'Task deleted.') : ((d && d.message) || 'Could not delete.'), !ok);
        if (ok) refreshTaskViews();
    } catch {
        showToast('Connection error.', true);
    }
}

// Refresh everywhere tasks are shown after a change.
function refreshTaskViews() {
    loadHomeTasks();
    if (calSection === 'tasks') loadCalTasks();
    if (calLoaded) loadCalendarView(true);
}

// --- task rows + details ---

function taskRow(ev) {
    const row = el('div', 'task-item');
    row.appendChild(el('div', 'home-task-when', taskWhen(ev.start)));
    const main = el('div', 'task-item-main');
    main.appendChild(el('div', 'home-task-title', ev.title));
    main.appendChild(el('div', 'task-item-time', fmtTime(ev.start) + ' – ' + fmtTime(ev.end)));
    row.appendChild(main);
    const imp = inferImportance(ev);
    row.appendChild(el('span', 'imp-badge imp-' + imp, imp === 'important' ? 'Important' : 'Regular'));
    if (ev.event_id) row.addEventListener('click', () => openTaskDetail(ev));
    else row.classList.add('task-item-static');   // ics/demo: no edit id
    return row;
}

function openTaskDetail(task) {
    detailTask = task;
    setText('td-title', task.title || 'Task');
    setText('td-when', taskWhen(task.start) + ' · ' + fmtTime(task.start) + ' – ' + fmtTime(task.end));
    const imp = inferImportance(task);
    const badge = document.getElementById('td-importance');
    if (badge) { badge.textContent = imp === 'important' ? 'Important' : 'Regular'; badge.className = 'imp-badge imp-' + imp; }
    const editable = !!task.event_id;
    ['td-reschedule', 'td-delete'].forEach(id => { const b = document.getElementById(id); if (b) b.disabled = !editable; });
    const m = document.getElementById('task-detail-modal');
    if (m) m.classList.remove('hidden');
}

function closeTaskDetail() {
    detailTask = null;
    const m = document.getElementById('task-detail-modal');
    if (m) m.classList.add('hidden');
}

// --- Home tasks card ---

async function loadHomeTasks() {
    const wrap = document.getElementById('home-tasks-list');
    if (!wrap) return;
    if (!taskConfig) await refreshTaskConfig();   // so importance badges are right
    try {
        renderHomeTasks(await (await fetch('/api/tasks/upcoming?limit=3')).json());
    } catch {
        wrap.innerHTML = '';
        wrap.appendChild(el('div', 'home-empty', 'Could not load tasks.'));
        toggleViewAllTasks(false);
    }
}

function renderHomeTasks(d) {
    const wrap = document.getElementById('home-tasks-list');
    if (!wrap) return;
    wrap.innerHTML = '';
    const items = (d && d.tasks) || [];
    if (!d || !d.available || !items.length) {
        wrap.appendChild(el('div', 'home-empty', 'No upcoming tasks. Tap Add Task to block time.'));
        toggleViewAllTasks(false);
        return;
    }
    items.forEach(ev => wrap.appendChild(taskRow(ev)));
    toggleViewAllTasks(true);
}

function toggleViewAllTasks(show) {
    const btn = document.getElementById('home-view-all-tasks');
    if (btn) btn.classList.toggle('hidden', !show);
}

// Open the Calendar tab's Tasks sub-view to manage all tasks.
function viewAllTasks() {
    switchTab('calendar');
    setCalSection('tasks');
}

function taskWhen(iso) {
    const d = new Date(iso);
    const sameDay = d.toDateString() === new Date().toDateString();
    return sameDay ? 'Today' : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

// --- Calendar tab Tasks sub-view ---

function setCalSection(section) {
    calSection = section === 'tasks' ? 'tasks' : 'calendar';
    document.querySelectorAll('[data-calsec]').forEach(b =>
        b.classList.toggle('active', b.getAttribute('data-calsec') === calSection));
    const main = document.getElementById('cal-view-main');
    const tasksView = document.getElementById('cal-view-tasks');
    if (main) main.classList.toggle('hidden', calSection !== 'calendar');
    if (tasksView) tasksView.classList.toggle('hidden', calSection !== 'tasks');
    if (calSection === 'tasks') loadCalTasks();
    else if (!calLoaded) loadCalendarView();
}

async function loadCalTasks() {
    const wrap = document.getElementById('cal-tasks-list');
    if (!wrap) return;
    wrap.innerHTML = '';
    wrap.appendChild(el('div', 'home-empty', 'Loading...'));
    if (!taskConfig) await refreshTaskConfig();   // so importance badges are right
    try {
        renderCalTasks(await (await fetch('/api/tasks/upcoming?limit=12')).json());
    } catch {
        wrap.innerHTML = '';
        wrap.appendChild(el('div', 'home-empty', 'Could not load tasks.'));
    }
}

function renderCalTasks(d) {
    const wrap = document.getElementById('cal-tasks-list');
    if (!wrap) return;
    wrap.innerHTML = '';
    const items = (d && d.tasks) || [];
    if (!d || !d.available) {
        wrap.appendChild(el('div', 'home-empty', (d && d.message) || 'Tasks are available on macOS only.'));
        return;
    }
    if (!items.length) {
        wrap.appendChild(el('div', 'home-empty', 'No upcoming tasks.'));
        return;
    }
    items.forEach(ev => wrap.appendChild(taskRow(ev)));
}

// --- input-location indicator + Settings ---

async function refreshTaskConfig() {
    try {
        const res = await fetch('/api/tasks/config');
        if (!res.ok) return;
        taskConfig = await res.json();
    } catch { return; }
    updateTaskInputIndicator();
}

function updateTaskInputIndicator() {
    const tag = document.getElementById('home-task-mode');
    if (!tag || !taskConfig) return;
    tag.textContent = taskConfig.input_location === 'mac_prompt' ? 'Mac prompt' : 'Tablet';
}

// Fill the Settings Tasks card (called from loadSettings).
function renderTaskSettings() {
    if (!taskConfig) { refreshTaskConfig(); return; }
    const cfg = taskConfig;
    document.querySelectorAll('[data-task-input]').forEach(b =>
        b.classList.toggle('active', b.getAttribute('data-task-input') === (cfg.input_location || 'dashboard')));
    setText('set-task-cal', cfg.default_calendar ? cfg.default_calendar : 'Auto (Tasks calendar)');
    if (cfg.regular_minutes) setText('set-task-dur', cfg.regular_minutes + ' / ' + cfg.important_minutes + ' min');
    const hint = document.getElementById('set-task-hint');
    if (hint) {
        const macOnly = cfg.available === false;
        hint.textContent = macOnly ? 'Tasks need macOS with the EventKit reader.' : '';
        hint.classList.toggle('hidden', !macOnly);
    }
}

async function setTaskInputLocation(value) {
    try {
        const res = await fetch('/api/tasks/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input_location: value })
        });
        const d = await res.json();
        if (!res.ok || !d.success) { showToast((d && d.message) || 'Could not change input mode.', true); return; }
        await refreshTaskConfig();
        renderTaskSettings();
        showToast('Add Task input set to ' + (value === 'mac_prompt' ? 'Mac prompt' : 'tablet') + '.');
    } catch {
        showToast('Connection error.', true);
    }
}

// ============================================================
// PHOTOS  (shuffle / pause / lock; state persists in localStorage)
// ============================================================
const PH_KEYS = { shuffle: 'ff_photo_shuffle', paused: 'ff_photo_paused', locked: 'ff_photo_locked' };

let photoFiles = [];        // all filenames from the server
let photoOrder = [];        // working order (sequential or shuffled)
let photoPos = 0;           // index into photoOrder
let photoTimer = null;
let photoIntervalMs = 30000;
let photosLoaded = false;
let photoShuffle = false;
let photoPaused = false;
let photoLockedName = null;
let photoErrorStreak = 0;

function setupPhotos() {
    photoShuffle    = localStorage.getItem(PH_KEYS.shuffle) === '1';
    photoPaused     = localStorage.getItem(PH_KEYS.paused) === '1';
    photoLockedName = localStorage.getItem(PH_KEYS.locked) || null;

    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    on('ph-prev',      () => stepPhoto(-1));
    on('ph-next',      () => stepPhoto(1));
    on('ph-random',    randomPhoto);
    on('ph-playpause', togglePause);
    on('ph-shuffle',   toggleShuffle);
    on('ph-lock',      toggleLock);
}

async function loadPhotos() {
    try {
        const res = await fetch('/api/photos');
        if (res.ok) {
            const d = await res.json();
            photoFiles = d.photos || [];
            if (d.interval_seconds) photoIntervalMs = Math.max(3, d.interval_seconds) * 1000;
        }
    } catch { photoFiles = []; }
    photosLoaded = true;

    buildOrder(photoLockedName);
    if (photoLockedName) {
        const i = photoOrder.indexOf(photoLockedName);
        if (i >= 0) photoPos = i; else clearLock();   // locked photo no longer present
    }
    renderCurrent();
    updatePhotoUi();
}

function buildOrder(keepName) {
    photoOrder = photoShuffle ? shuffleArray(photoFiles.slice()) : photoFiles.slice();
    if (keepName) {
        const i = photoOrder.indexOf(keepName);
        photoPos = i >= 0 ? i : 0;
    } else if (photoPos >= photoOrder.length) {
        photoPos = 0;
    }
}

function shuffleArray(a) {
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
}

function startPhotoShow() {
    // Re-fetch if never loaded, or if it was empty last time (so "add photos
    // then come back" works without a full reload).
    if (!photosLoaded || !photoFiles.length) { loadPhotos().then(restartPhotoTimer); }
    else { restartPhotoTimer(); }
}

function stopPhotoShow() {
    clearInterval(photoTimer);
    photoTimer = null;
}

// Auto-advance only when not paused and not locked on a photo.
function restartPhotoTimer() {
    clearInterval(photoTimer);
    photoTimer = null;
    if (!photoPaused && !photoLockedName && photoOrder.length > 1) {
        photoTimer = setInterval(() => stepPhoto(1, true), photoIntervalMs);
    }
}

function stepPhoto(dir, isAuto = false) {
    if (!photoOrder.length) return;
    // Manual prev/next leaves the locked photo, so drop the lock.
    if (photoLockedName && !isAuto) clearLock();
    photoPos = (photoPos + dir + photoOrder.length) % photoOrder.length;
    renderCurrent();
    updatePhotoUi();
    if (!isAuto) restartPhotoTimer();
}

async function randomPhoto() {
    if (!photoOrder.length) return;
    if (photoLockedName) clearLock();
    let name = null;
    try {
        const res = await fetch('/api/photos/random');
        if (res.ok) name = (await res.json()).photo;
    } catch { /* fall back to client-side random below */ }
    const i = name ? photoOrder.indexOf(name) : -1;
    photoPos = i >= 0 ? i : Math.floor(Math.random() * photoOrder.length);
    renderCurrent();
    updatePhotoUi();
    restartPhotoTimer();
}

function togglePause() {
    photoPaused = !photoPaused;
    localStorage.setItem(PH_KEYS.paused, photoPaused ? '1' : '0');
    restartPhotoTimer();
    updatePhotoUi();
}

function toggleShuffle() {
    photoShuffle = !photoShuffle;
    localStorage.setItem(PH_KEYS.shuffle, photoShuffle ? '1' : '0');
    buildOrder(photoOrder[photoPos]);   // keep the current photo on screen
    restartPhotoTimer();
    updatePhotoUi();
}

function toggleLock() {
    if (photoLockedName) {
        clearLock();
    } else {
        photoLockedName = photoOrder[photoPos] || null;
        if (photoLockedName) localStorage.setItem(PH_KEYS.locked, photoLockedName);
    }
    restartPhotoTimer();
    updatePhotoUi();
}

function clearLock() {
    photoLockedName = null;
    localStorage.removeItem(PH_KEYS.locked);
}

function renderCurrent() {
    const img    = document.getElementById('current-photo');
    const noMsg  = document.getElementById('no-photos-msg');
    const errMsg = document.getElementById('photo-error-msg');
    if (!img) return;

    if (!photoOrder.length) {
        img.classList.add('hidden');
        errMsg.classList.add('hidden');
        noMsg.classList.remove('hidden');
        return;
    }
    noMsg.classList.add('hidden');
    errMsg.classList.add('hidden');

    const name = photoOrder[photoPos];
    img.style.transition = 'opacity 0.6s ease';
    img.style.opacity = '0';
    img.onload = () => { img.classList.remove('hidden'); img.style.opacity = '1'; photoErrorStreak = 0; };
    img.onerror = () => {
        img.classList.add('hidden');
        errMsg.classList.remove('hidden');
        photoErrorStreak++;
        // Skip a broken image, but stop if everything is failing or we're locked.
        if (photoErrorStreak < photoOrder.length && !photoLockedName) {
            setTimeout(() => stepPhoto(1, true), 1500);
        }
    };
    // encodeURIComponent so names with spaces or "?" resolve correctly.
    img.src = `/photos/${encodeURIComponent(name)}`;
}

function updatePhotoUi() {
    const badge = (id, on) => { const el = document.getElementById(id); if (el) el.classList.toggle('hidden', !on); };
    badge('badge-shuffle', photoShuffle);
    badge('badge-paused',  photoPaused);
    badge('badge-locked',  !!photoLockedName);

    const pp = document.getElementById('ph-playpause');
    if (pp) pp.textContent = photoPaused ? '▶' : '⏸';
    const sh = document.getElementById('ph-shuffle');
    if (sh) sh.classList.toggle('active', photoShuffle);
    const lk = document.getElementById('ph-lock');
    if (lk) { lk.textContent = photoLockedName ? '🔓' : '🔒'; lk.classList.toggle('active', !!photoLockedName); }

    const counter = document.getElementById('photo-counter');
    if (counter) counter.textContent = photoOrder.length ? `${photoPos + 1} / ${photoOrder.length}` : '0 / 0';
}
