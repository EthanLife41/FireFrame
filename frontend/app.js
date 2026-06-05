// ============================================================
// Desk Companion — app.js
// Target: Fire HD 8, landscape, Fully Kiosk Browser
// ============================================================

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
let pinBuffer     = '';
const MAX_PIN_LEN = 4;

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
        showLoginError('Connection error — is the server running?', false);
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
    fetchCalendar();
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
                showToast('Fullscreen blocked — use Fully Kiosk Browser settings instead.', true);
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

    tabId === 'photos' ? startPhotoRotation() : stopPhotoRotation();
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
    if (statsInterval) return;
    fetchStats();
    fetchBluetoothStatus();
    statsInterval = setInterval(() => {
        fetchStats();
        fetchBluetoothStatus();
    }, 4000);
}

function stopStatsPolling() {
    clearInterval(statsInterval);
    statsInterval = null;
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
        if (res.ok) {
            const d = await res.json();
            setText('home-bt-status', d.bluetooth_state || 'Unknown');
        }
    } catch { /* ignore */ }
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

async function fetchCalendar() {
    try {
        const res = await fetch('/api/calendar');
        if (!res.ok) return;
        const d   = await res.json();
        const list = document.getElementById('calendar-list');
        list.innerHTML = '';

        if (!d.events || !d.events.length) {
            list.innerHTML = '<p style="color:var(--muted);font-size:0.8rem;">No events today.</p>';
            setText('next-event', '—');
            return;
        }

        d.events.forEach(ev => {
            const s = fmtTime(ev.start), e = fmtTime(ev.end);
            const item = document.createElement('div');
            item.className = 'agenda-item';
            item.innerHTML = `<div class="ev-title">${ev.title}</div>
                              <div class="ev-time">${s} – ${e}</div>
                              ${ev.location ? `<div class="ev-loc">📍 ${ev.location}</div>` : ''}`;
            list.appendChild(item);
        });

        setText('next-event', d.events[0].title);
        const nextStart = new Date(d.events[0].start);
        const tickCountdown = () => {
            const diff = nextStart - new Date();
            if (diff > 0) {
                const h = Math.floor(diff / 3600000);
                const m = Math.floor((diff % 3600000) / 60000);
                setText('event-countdown', 'In ' + (h > 0 ? h + 'h ' : '') + m + 'm');
            } else {
                setText('event-countdown', 'Now');
            }
        };
        tickCountdown();
        setInterval(tickCountdown, 60000);
    } catch {
        setText('next-event', 'Failed to load');
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
// PHOTO ROTATION
// ============================================================
let photoList = [], photoIdx = 0, photoTimer = null;

async function startPhotoRotation() {
    if (photoTimer) return;
    try {
        const res = await fetch('/api/photos');
        if (res.ok) photoList = (await res.json()).photos || [];
    } catch { photoList = []; }

    const img = document.getElementById('current-photo');
    const msg = document.getElementById('no-photos-msg');

    if (!photoList.length) {
        img.classList.add('hidden');
        msg.classList.remove('hidden');
        return;
    }

    msg.classList.add('hidden');

    const show = () => {
        img.style.opacity = '0';
        img.src = `/photos/${photoList[photoIdx]}`;
        img.onload = () => { img.classList.remove('hidden'); img.style.opacity = '1'; };
        photoIdx = (photoIdx + 1) % photoList.length;
    };

    img.style.transition = 'opacity 0.8s ease';
    show();
    photoTimer = setInterval(show, 30000);
}

function stopPhotoRotation() {
    clearInterval(photoTimer);
    photoTimer = null;
}
