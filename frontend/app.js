// FireFrame frontend. Built for the Fire HD 8 in landscape (Fully Kiosk Browser).

// Global error logger for easier troubleshooting on tablets
window.addEventListener('error', (event) => {
    const msg = `JS Error: ${event.message} at ${event.filename || 'app.js'}:${event.lineno}`;
    console.error(msg);
    const toastEl = document.getElementById('toast');
    if (toastEl) {
        showToast(msg, true);
    } else {
        alert(msg);
    }
});

// --- State ---
let isLoggedIn    = false;
let statsInterval = null;
let btStatusInterval = null;
let calendarCountdownInterval = null;
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
    setupPhotos();
    setupVisibility();
}

// Pause background polling when the tab/screen isn't visible.
function setupVisibility() {
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) stopStatsPolling();
        else if (isLoggedIn) startStatsPolling();
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
    fetchServerStatus();
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
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const activeNavBtn = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
    if (activeNavBtn) activeNavBtn.classList.add('active');

    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const activeTabEl = document.getElementById(`tab-${tabId}`);
    if (activeTabEl) activeTabEl.classList.add('active');

    if (tabId === 'photos') { startPhotoShow(); } else { stopPhotoShow(); }
    if (tabId === 'bluetooth') { loadBluetooth(); }
    if (tabId === 'calendar' && !calLoaded) { loadCalendarView(); }
}
window.switchTab = switchTab; // used by inline onclick

// ============================================================
// ACTION BUTTONS
// ============================================================
function setupActions() {
    document.querySelectorAll('.action-btn[data-action]').forEach(btn => {
        btn.addEventListener('click', () => triggerAction(btn.getAttribute('data-action')));
    });

    // Second pomodoro trigger in buttons tab
    const pomodoroBtn2 = document.getElementById('open-pomodoro-btn2');
    if (pomodoroBtn2) {
        pomodoroBtn2.addEventListener('click', () => {
            document.getElementById('pomodoro-modal').classList.remove('hidden');
        });
    }
}

async function triggerAction(action, params = {}) {
    try {
        const res  = await fetch('/api/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, params })
        });
        const data = await res.json();
        showToast(data.success ? (data.message || 'Done.') : `Error: ${data.message}`, !data.success);
    } catch {
        showToast('Connection error.', true);
    }
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
        fetchBluetoothStatus();
        btStatusInterval = setInterval(fetchBluetoothStatus, BT_STATUS_POLL_MS);
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

        const cpu  = (d.cpu_percent !== undefined && d.cpu_percent !== null) ? d.cpu_percent.toFixed(1) + '%' : '—';
        const ram  = (d.ram_percent !== undefined && d.ram_percent !== null) ? d.ram_percent.toFixed(1) + '%' : '—';
        const batt = d.battery_available ? d.battery_percent + '%' : 'N/A';
        const h    = Math.floor((d.uptime_seconds || 0) / 3600);
        const m    = Math.floor(((d.uptime_seconds || 0) % 3600) / 60);
        const up   = `${h}h ${m}m`;

        setText('home-cpu',      cpu);
        setText('home-ram',      ram);
        setText('home-battery',  batt);
        setText('home-uptime',   up);
        setText('setting-cpu',   cpu);
        setText('setting-ram-pct', ram);
        setText('setting-ram-gb',  `${d.ram_used_gb} / ${d.ram_total_gb} GB`);
        setText('setting-battery', batt);
        setText('setting-uptime',  up);
        setText('setting-gpu',  d.gpu_available ? 'Available' : (d.gpu_note || 'N/A'));
    } catch { /* ignore */ }
}

async function fetchBluetoothStatus() {
    if (!isLoggedIn) return;
    try {
        const res = await fetch('/api/bluetooth/status');
        if (!res.ok) return;
        const d = await res.json();
        setText('home-bt-status', formatBtStatus(d));
    } catch { /* ignore */ }
}

function formatBtStatus(d) {
    if (!d.available) return 'Unavailable';
    if (d.powered === false) return 'Off';
    const n = d.connected_count || 0;
    if (d.powered === true) return n ? `On · ${n} connected` : 'On';
    return n ? `${n} connected` : 'Unknown';
}

async function fetchServerStatus() {
    try {
        const res = await fetch('/api/status');
        if (res.ok) {
            const d = await res.json();
            setText('server-status', d.message || 'Running');
        }
    } catch {
        setText('server-status', 'Offline');
    }
    setText('server-url', window.location.href);
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

function renderSourceChips(events) {
    const wrap = document.getElementById('cal-sources');
    if (!wrap) return;
    const names = [];
    const seen = new Set();
    events.forEach(e => { if (e.calendar && !seen.has(e.calendar)) { seen.add(e.calendar); names.push(e.calendar); } });
    if (names.length <= 1) { wrap.classList.add('hidden'); wrap.innerHTML = ''; return; }
    wrap.classList.remove('hidden');
    wrap.innerHTML = '';
    names.forEach(n => {
        const chip = el('button', 'cal-chip' + (calHidden.has(n) ? ' off' : ''));
        chip.style.setProperty('--chip-hue', calHue(n));
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

    // All-day row (only when there are all-day / multi-day events)
    const allDay = days.map(day => allDayEventsFor(day, events));
    if (allDay.some(list => list.length)) {
        const row = el('div', 'cal-allday');
        row.appendChild(el('div', 'cal-allday-label', 'all-day'));
        days.forEach((day, i) => {
            const cell = el('div', 'cal-allday-cell');
            allDay[i].forEach(ev => cell.appendChild(eventChip(ev)));
            row.appendChild(cell);
        });
        inner.appendChild(row);
    }

    // Scrollable timed grid
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
        layoutTimed(day, events).forEach(b => col.appendChild(b));
        body.appendChild(col);
    });

    scroll.appendChild(body);
    inner.appendChild(scroll);
    return inner;
}

function allDayEventsFor(day, events) {
    const ds = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const de = new Date(ds.getTime() + 86400000);
    return events.filter(ev => {
        const es = new Date(ev.start), ee = new Date(ev.end);
        if (ee <= ds || es >= de) return false;
        return ev.all_day || (es <= ds && ee >= de);
    });
}

function eventChip(ev) {
    const c = el('div', 'cal-chip-ev', ev.title);
    c.style.setProperty('--ev-hue', calHue(ev.calendar));
    if (ev.location) c.title = ev.location;
    return c;
}

// Place timed events for one day, splitting width across overlapping events.
function layoutTimed(day, events) {
    const ds = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const de = new Date(ds.getTime() + 86400000);
    const items = [];
    events.forEach(ev => {
        const es = new Date(ev.start), ee = new Date(ev.end);
        if (ee <= ds || es >= de) return;
        if (ev.all_day || (es <= ds && ee >= de)) return;   // in the all-day row
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
    b.style.setProperty('--ev-hue', calHue(ev.calendar));
    b.style.top = (it.startH * CAL_HOUR_PX) + 'px';
    b.style.height = Math.max(16, (it.endH - it.startH) * CAL_HOUR_PX - 2) + 'px';
    const w = 100 / nCols;
    b.style.left = (it.col * w) + '%';
    b.style.width = `calc(${w}% - 3px)`;
    b.appendChild(el('div', 'cal-event-title', ev.title));
    b.appendChild(el('div', 'cal-event-time', `${fmtTime(ev.start)} – ${fmtTime(ev.end)}`));
    if (ev.location) b.title = ev.location;
    return b;
}

// Home tab: show the next upcoming event with a live countdown.
async function loadHomeNextEvent() {
    try {
        const d = await (await fetch('/api/calendar/upcoming')).json();
        if (!d.connected) { setText('next-event', 'Not connected'); setText('event-countdown', ''); return; }
        if (!d.events || !d.events.length) { setText('next-event', 'No upcoming events'); setText('event-countdown', ''); return; }
        const ev = d.events[0];
        setText('next-event', ev.title);
        const nextStart = new Date(ev.start);
        const tick = () => {
            const diff = nextStart - new Date();
            if (diff > 0) {
                const h = Math.floor(diff / 3600000), m = Math.floor((diff % 3600000) / 60000);
                setText('event-countdown', 'In ' + (h > 0 ? h + 'h ' : '') + m + 'm');
            } else {
                setText('event-countdown', 'Now');
            }
        };
        tick();
        clearInterval(calendarCountdownInterval);
        calendarCountdownInterval = setInterval(tick, 60000);
    } catch {
        setText('next-event', 'Failed to load');
        setText('event-countdown', '');
    }
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
    // Sleep modal
    const sleepModal = document.getElementById('sleep-modal');
    document.getElementById('sleep-mode-btn').addEventListener('click', () =>
        sleepModal.classList.remove('hidden'));
    document.getElementById('cancel-sleep-btn').addEventListener('click', () =>
        sleepModal.classList.add('hidden'));
    document.getElementById('confirm-sleep-btn').addEventListener('click', () => {
        const t = document.getElementById('wake-time').value;
        if (!t) { showToast('Please set a wake time.', true); return; }
        triggerAction('sleep_mode_alarm', { wake_time: t });
        sleepModal.classList.add('hidden');
    });

    // Pomodoro modal
    const pomodoroModal = document.getElementById('pomodoro-modal');
    document.getElementById('open-pomodoro-btn').addEventListener('click', () =>
        pomodoroModal.classList.remove('hidden'));
    document.getElementById('close-pomodoro-btn').addEventListener('click', () =>
        pomodoroModal.classList.add('hidden'));

    setupTimer();
}

// ============================================================
// POMODORO TIMER
// ============================================================
let timerSec = 25 * 60, timerRunning = false, timerInterval2 = null;

function setupTimer() {
    const display   = document.getElementById('timer-display');
    const toggleBtn = document.getElementById('timer-toggle-btn');

    const render = () => {
        const m = String(Math.floor(timerSec / 60)).padStart(2, '0');
        const s = String(timerSec % 60).padStart(2, '0');
        display.textContent = `${m}:${s}`;
    };

    document.querySelectorAll('.timer-presets .btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const v = btn.getAttribute('data-time');
            let mins = 25;
            if (v === 'custom') {
                const inp = prompt('Minutes:');
                if (inp && !isNaN(inp)) mins = parseInt(inp);
            } else {
                mins = parseInt(v);
            }
            clearInterval(timerInterval2);
            timerRunning = false;
            timerSec = mins * 60;
            toggleBtn.textContent = 'Start';
            render();
        });
    });

    toggleBtn.addEventListener('click', () => {
        if (timerRunning) {
            clearInterval(timerInterval2);
            timerRunning = false;
            toggleBtn.textContent = 'Resume';
        } else {
            timerRunning = true;
            toggleBtn.textContent = 'Pause';
            timerInterval2 = setInterval(() => {
                if (timerSec > 0) {
                    timerSec--;
                    render();
                } else {
                    clearInterval(timerInterval2);
                    timerRunning = false;
                    toggleBtn.textContent = 'Start';
                    showToast('⏱️ Timer done!');
                }
            }, 1000);
        }
    });

    document.getElementById('timer-reset-btn').addEventListener('click', () => {
        clearInterval(timerInterval2);
        timerRunning = false;
        timerSec = 25 * 60;
        toggleBtn.textContent = 'Start';
        render();
    });

    render();
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
