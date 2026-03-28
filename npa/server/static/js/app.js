/**
 * NPA Web UI — Main Application
 * SPA router, API client, session management, and shared utilities.
 */

// --- API Client ---
export const API = {
    async request(method, path, body = null, contentType = 'application/json') {
        const opts = { method, headers: {} };
        if (body !== null) {
            opts.headers['Content-Type'] = contentType;
            opts.body = contentType === 'application/json' ? JSON.stringify(body) : body;
        }
        const res = await fetch(path, opts);
        if (res.status === 401 && !path.includes('/ui/login') && !path.includes('/ui/session')) {
            showLoginScreen();
            throw new Error('Session expired');
        }
        if (!res.ok) {
            const text = await res.text();
            throw new Error(text || `HTTP ${res.status}`);
        }
        return res.status === 204 ? null : res.json();
    },
    async requestBinary(method, path, binaryBody) {
        const opts = { method, headers: { 'Content-Type': 'application/gzip' }, body: binaryBody };
        const res = await fetch(path, opts);
        if (res.status === 401) { showLoginScreen(); throw new Error('Session expired'); }
        if (!res.ok) { const text = await res.text(); throw new Error(text || `HTTP ${res.status}`); }
        return res.status === 204 ? null : res.text();
    },
    get:       (path)           => API.request('GET', path),
    post:      (path, body)     => API.request('POST', path, body),
    put:       (path, body)     => API.request('PUT', path, body),
    putText:   (path, body)     => API.request('PUT', path, body, 'text/plain'),
    putBinary: (path, body)     => API.requestBinary('PUT', path, body),
    patch:     (path, body)     => API.request('PATCH', path, body),
    del:       (path)           => API.request('DELETE', path),
};

// --- Toast Notifications ---
export function toast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('toast-visible'));
    setTimeout(() => {
        el.classList.remove('toast-visible');
        setTimeout(() => el.remove(), 300);
    }, duration);
}

// --- Modal ---
export function showModal(html) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.getElementById('modal-content');
    content.innerHTML = html;
    overlay.classList.remove('hidden');
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
}

export function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

// --- CodeMirror Helper ---
export function createEditor(container, options = {}) {
    if (typeof CodeMirror !== 'undefined') {
        return CodeMirror(container, {
            theme: 'material-darker',
            lineNumbers: true,
            matchBrackets: true,
            autoCloseBrackets: true,
            tabSize: 2,
            indentWithTabs: false,
            ...options,
        });
    }
    // Fallback: plain textarea
    const ta = document.createElement('textarea');
    ta.className = 'fallback-editor';
    ta.value = options.value || '';
    container.appendChild(ta);
    return {
        getValue: () => ta.value,
        setValue: (v) => { ta.value = v; },
        on: () => {},
        refresh: () => {},
        setOption: () => {},
        focus: () => ta.focus(),
    };
}

// --- Utility ---
export function formatDuration(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}

export function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
}

export function formatJson(obj) {
    try { return JSON.stringify(obj, null, 2); }
    catch { return String(obj); }
}

// --- Router ---
const pages = {};
let currentCleanup = null;

export function registerPage(name, mod) { pages[name] = mod; }

async function navigate(pageName) {
    if (currentCleanup) { currentCleanup(); currentCleanup = null; }

    const page = pages[pageName];
    if (!page) {
        document.getElementById('page-container').innerHTML =
            `<div class="page-header"><h2>404</h2></div><p>Page not found: ${escapeHtml(pageName)}</p>`;
        return;
    }

    document.querySelectorAll('.nav-item').forEach(el =>
        el.classList.toggle('active', el.dataset.page === pageName));

    const container = document.getElementById('page-container');
    container.innerHTML = page.render();

    if (page.mount) {
        currentCleanup = await page.mount(container) || null;
    }
}

// --- Login / Logout ---
function showLoginScreen() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
    document.getElementById('login-error').textContent = '';
}

function showApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
}

function setupLoginForm() {
    const form = document.getElementById('login-form');
    const errorEl = document.getElementById('login-error');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorEl.textContent = '';
        const username = document.getElementById('login-user').value.trim();
        const password = document.getElementById('login-pass').value;
        try {
            await API.post('/v1/ui/login', { username, password });
            showApp();
            initApp();
        } catch (err) {
            errorEl.textContent = 'Invalid credentials';
        }
    });

    document.getElementById('logout-btn').addEventListener('click', async () => {
        try { await API.post('/v1/ui/logout'); } catch { /* ignore */ }
        showLoginScreen();
    });
}

// --- Server Status ---
async function checkServerStatus() {
    const el = document.getElementById('server-status');
    try {
        await API.get('/health');
        el.innerHTML = '<span class="status-dot status-ok"></span><span class="status-text">Connected</span>';
    } catch {
        el.innerHTML = '<span class="status-dot status-error"></span><span class="status-text">Disconnected</span>';
    }
}

// --- App Init (after login) ---
let appInitialized = false;
async function initApp() {
    if (appInitialized) return;
    appInitialized = true;

    const [dashboard, policies, playground, databrowser, bundles, logs, config] =
        await Promise.all([
            import('./pages/dashboard.js'),
            import('./pages/policies.js'),
            import('./pages/playground.js'),
            import('./pages/databrowser.js'),
            import('./pages/bundles.js'),
            import('./pages/logs.js'),
            import('./pages/config.js'),
        ]);

    registerPage('dashboard',  dashboard);
    registerPage('policies',   policies);
    registerPage('playground', playground);
    registerPage('data',       databrowser);
    registerPage('bundles',    bundles);
    registerPage('logs',       logs);
    registerPage('config',     config);

    function handleRoute() {
        const hash = window.location.hash.slice(2) || 'dashboard';
        navigate(hash.split('?')[0]);
    }
    window.addEventListener('hashchange', handleRoute);
    handleRoute();

    checkServerStatus();
    setInterval(checkServerStatus, 15000);
}

// --- Bootstrap ---
async function init() {
    setupLoginForm();

    try {
        const session = await fetch('/v1/ui/session');
        const data = await session.json();
        if (data.authenticated) {
            showApp();
            await initApp();
            return;
        }
    } catch { /* no session */ }

    showLoginScreen();
}

init().catch(err => {
    console.error('NPA init failed:', err);
    showLoginScreen();
});
