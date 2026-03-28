/**
 * Configuration Page — Server config, metrics, capabilities & API reference.
 */
import { API, toast, escapeHtml, formatJson } from '../app.js';

let metricsInterval = null;

export function render() {
    return `
        <div class="page-header">
            <h2>Configuration</h2>
            <button class="btn btn-secondary btn-sm" id="refresh-config-btn">↻ Refresh</button>
        </div>

        <div class="grid-2col">
            <div class="card">
                <div class="card-header"><h3>Server Status</h3></div>
                <div class="card-body" id="config-container">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
            <div class="card">
                <div class="card-header"><h3>Live Metrics</h3></div>
                <div class="card-body" id="metrics-live-container">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><h3>Capabilities</h3></div>
            <div class="card-body" id="capabilities-container">
                <div class="loading-inline">Loading…</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><h3>Server Configuration</h3></div>
            <div class="card-body" id="full-config-container">
                <div class="loading-inline">Loading…</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><h3>API Reference</h3></div>
            <div class="card-body">
                <table class="data-table">
                    <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/data/{path}</code></td><td>Query data or evaluate policy at path</td></tr>
                        <tr><td><span class="badge badge-primary">POST</span></td><td><code>/v1/data/{path}</code></td><td>Evaluate policy with input document</td></tr>
                        <tr><td><span class="badge badge-warning">PUT</span></td><td><code>/v1/data/{path}</code></td><td>Create or overwrite a data document</td></tr>
                        <tr><td><span class="badge badge-warning">PATCH</span></td><td><code>/v1/data/{path}</code></td><td>Apply JSON Patch to data document</td></tr>
                        <tr><td><span class="badge badge-danger">DELETE</span></td><td><code>/v1/data/{path}</code></td><td>Delete a data document</td></tr>
                        <tr><td colspan="3" style="height:8px;border:none"></td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/policies</code></td><td>List all loaded policies</td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/policies/{id}</code></td><td>Get a specific policy</td></tr>
                        <tr><td><span class="badge badge-warning">PUT</span></td><td><code>/v1/policies/{id}</code></td><td>Create or update a policy (text/plain body)</td></tr>
                        <tr><td><span class="badge badge-danger">DELETE</span></td><td><code>/v1/policies/{id}</code></td><td>Delete a policy</td></tr>
                        <tr><td colspan="3" style="height:8px;border:none"></td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/query</code></td><td>Ad-hoc query (GET with ?q=)</td></tr>
                        <tr><td><span class="badge badge-primary">POST</span></td><td><code>/v1/query</code></td><td>Execute an ad-hoc Rego query</td></tr>
                        <tr><td><span class="badge badge-primary">POST</span></td><td><code>/v1/compile</code></td><td>Partially evaluate / compile a query</td></tr>
                        <tr><td colspan="3" style="height:8px;border:none"></td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/bundles</code></td><td>List all bundles</td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/bundles/{name}</code></td><td>Get bundle info</td></tr>
                        <tr><td><span class="badge badge-warning">PUT</span></td><td><code>/v1/bundles/{name}</code></td><td>Upload bundle (.tar.gz)</td></tr>
                        <tr><td><span class="badge badge-danger">DELETE</span></td><td><code>/v1/bundles/{name}</code></td><td>Delete / deactivate bundle</td></tr>
                        <tr><td colspan="3" style="height:8px;border:none"></td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/config</code></td><td>Server configuration</td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/v1/metrics</code></td><td>Prometheus metrics</td></tr>
                        <tr><td colspan="3" style="height:8px;border:none"></td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/health</code></td><td>Health check</td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/health/live</code></td><td>Liveness probe</td></tr>
                        <tr><td><span class="badge badge-success">GET</span></td><td><code>/health/ready</code></td><td>Readiness probe</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><h3>Documentation Links</h3></div>
            <div class="card-body">
                <table class="info-table">
                    <tr><td class="info-label">OpenAPI Docs</td><td><a href="/v1/docs" target="_blank" class="link">/v1/docs (Swagger UI)</a></td></tr>
                    <tr><td class="info-label">ReDoc</td><td><a href="/v1/redoc" target="_blank" class="link">/v1/redoc</a></td></tr>
                </table>
            </div>
        </div>
    `;
}

async function loadConfig() {
    try {
        const status = await API.get('/v1/ui/status');
        document.getElementById('config-container').innerHTML =
            `<pre class="result-json">${escapeHtml(formatJson(status))}</pre>`;
    } catch (err) {
        toast('Failed to load status: ' + err.message, 'error');
    }
}

async function loadMetrics() {
    try {
        const m = await API.get('/v1/ui/metrics');
        const c = document.getElementById('metrics-live-container');
        c.innerHTML = `
            <table class="info-table">
                <tr><td class="info-label">Uptime</td><td>${formatUptime(m.uptime_seconds)}</td></tr>
                <tr><td class="info-label">Total Decisions</td><td>${m.decisions.total}</td></tr>
                <tr><td class="info-label">Avg Duration</td><td>${m.decisions.avg_duration_ms.toFixed(2)} ms</td></tr>
                <tr><td class="info-label">Errors</td><td>${m.decisions.error_count}</td></tr>
                <tr><td class="info-label">Memory (RSS)</td><td>${m.memory.rss_mb} MB</td></tr>
                <tr><td class="info-label">Memory (VMS)</td><td>${m.memory.vms_mb} MB</td></tr>
                <tr><td class="info-label">CPU</td><td>${m.cpu_percent.toFixed(1)}%</td></tr>
            </table>`;
    } catch {
        document.getElementById('metrics-live-container').innerHTML =
            '<span class="text-muted">Metrics unavailable</span>';
    }
}

async function loadCapabilities() {
    try {
        const caps = await API.get('/v1/ui/capabilities');
        const c = document.getElementById('capabilities-container');
        c.innerHTML = `
            <table class="info-table">
                <tr><td class="info-label">NPA Version</td><td>${escapeHtml(caps.npa_version)}</td></tr>
                <tr><td class="info-label">Builtins</td><td>${caps.builtin_count} functions</td></tr>
                <tr><td class="info-label">Features</td><td>${caps.features.map(f => `<span class="badge badge-primary" style="margin:2px">${escapeHtml(f)}</span>`).join(' ')}</td></tr>
            </table>
            <details style="margin-top:12px">
                <summary class="text-muted" style="cursor:pointer">All builtins (${caps.builtin_count})</summary>
                <div style="max-height:300px;overflow-y:auto;margin-top:8px;columns:3;column-gap:16px">
                    ${caps.builtins.map(b => `<code style="display:block;line-height:1.8">${escapeHtml(b)}</code>`).join('')}
                </div>
            </details>`;
    } catch {
        document.getElementById('capabilities-container').innerHTML =
            '<span class="text-muted">Capabilities unavailable</span>';
    }
}

async function loadFullConfig() {
    try {
        const cfg = await API.get('/v1/config');
        document.getElementById('full-config-container').innerHTML =
            `<pre class="result-json">${escapeHtml(formatJson(cfg.result))}</pre>`;
    } catch {
        document.getElementById('full-config-container').innerHTML =
            '<span class="text-muted">Configuration endpoint unavailable</span>';
    }
}

function formatUptime(sec) {
    if (sec < 60) return `${Math.round(sec)}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return `${h}h ${m}m`;
}

function loadAll() {
    loadConfig();
    loadMetrics();
    loadCapabilities();
    loadFullConfig();
}

export function mount() {
    document.getElementById('refresh-config-btn').addEventListener('click', loadAll);
    loadAll();
    metricsInterval = setInterval(loadMetrics, 10000);
    return () => { clearInterval(metricsInterval); metricsInterval = null; };
}
