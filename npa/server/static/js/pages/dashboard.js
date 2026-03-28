/**
 * Dashboard Page — Server overview with live stats, metrics & bundles.
 */
import { API, formatDuration, toast, escapeHtml } from '../app.js';

let refreshInterval = null;

export function render() {
    return `
        <div class="page-header">
            <h2>Dashboard</h2>
            <button class="btn btn-secondary btn-sm" id="refresh-btn">↻ Refresh</button>
        </div>
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">🏥</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-health">–</div>
                    <div class="stat-label">Server Health</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📜</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-policies">–</div>
                    <div class="stat-label">Policies Loaded</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">🗄️</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-documents">–</div>
                    <div class="stat-label">Data Documents</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">⏱️</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-uptime">–</div>
                    <div class="stat-label">Uptime</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-decisions">–</div>
                    <div class="stat-label">Total Decisions</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">💾</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-memory">–</div>
                    <div class="stat-label">Memory (RSS)</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">⚡</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-avgduration">–</div>
                    <div class="stat-label">Avg Query Time</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon">📦</div>
                <div class="stat-info">
                    <div class="stat-value" id="stat-bundles">–</div>
                    <div class="stat-label">Bundles</div>
                </div>
            </div>
        </div>

        <div class="grid-2col">
            <div class="card">
                <div class="card-header"><h3>Server Info</h3></div>
                <div class="card-body" id="server-info">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
            <div class="card">
                <div class="card-header"><h3>Loaded Policies</h3></div>
                <div class="card-body" id="policy-list-mini">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
        </div>

        <div class="grid-2col">
            <div class="card">
                <div class="card-header"><h3>Bundle Status</h3></div>
                <div class="card-body" id="bundle-status">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
            <div class="card">
                <div class="card-header"><h3>Recent Decisions</h3></div>
                <div class="card-body" id="recent-decisions">
                    <div class="loading-inline">Loading…</div>
                </div>
            </div>
        </div>
    `;
}

async function loadDashboard() {
    try {
        const [status, metrics, bundles] = await Promise.all([
            API.get('/v1/ui/status'),
            API.get('/v1/ui/metrics').catch(() => null),
            API.get('/v1/bundles').catch(() => null)
        ]);

        // Stats cards
        const healthEl = document.getElementById('stat-health');
        healthEl.textContent = status.server.healthy ? '✓ Healthy' : '✗ Unhealthy';
        healthEl.className = `stat-value ${status.server.healthy ? 'text-success' : 'text-danger'}`;

        document.getElementById('stat-policies').textContent = status.policies.count;
        document.getElementById('stat-documents').textContent = status.data.document_count;
        document.getElementById('stat-uptime').textContent = formatDuration(status.server.uptime_seconds);

        // Metrics cards
        if (metrics) {
            document.getElementById('stat-decisions').textContent = metrics.decisions.total;
            document.getElementById('stat-memory').textContent = metrics.memory.rss_mb + ' MB';
            document.getElementById('stat-avgduration').textContent = metrics.decisions.avg_duration_ms.toFixed(1) + ' ms';
        }

        // Bundle count
        const bundleList = bundles && bundles.bundles ? Object.keys(bundles.bundles) : [];
        document.getElementById('stat-bundles').textContent = bundleList.length;

        // Server info table
        document.getElementById('server-info').innerHTML = `
            <table class="info-table">
                <tr><td class="info-label">Version</td><td>${esc(status.server.version)}</td></tr>
                <tr><td class="info-label">Address</td><td>${esc(status.server.addr)}:${status.server.port}</td></tr>
                <tr><td class="info-label">TLS</td>
                    <td>${status.server.tls_enabled
                        ? '<span class="badge badge-success">Enabled</span>'
                        : '<span class="badge badge-warning">Disabled</span>'}</td></tr>
                <tr><td class="info-label">Evaluator</td>
                    <td>${status.evaluator.ready
                        ? '<span class="badge badge-success">Ready</span>'
                        : '<span class="badge badge-muted">No policies</span>'}</td></tr>
                <tr><td class="info-label">Data Roots</td>
                    <td>${status.data.root_keys.length
                        ? esc(status.data.root_keys.join(', '))
                        : '<span class="text-muted">empty</span>'}</td></tr>
                ${metrics ? `<tr><td class="info-label">CPU</td><td>${metrics.cpu_percent.toFixed(1)}%</td></tr>` : ''}
            </table>
        `;

        // Policy list mini
        const plEl = document.getElementById('policy-list-mini');
        if (status.policies.ids.length > 0) {
            plEl.innerHTML = `<ul class="simple-list">${status.policies.ids.map(id =>
                `<li><a href="#/policies?edit=${encodeURIComponent(id)}" class="link">${esc(id)}</a></li>`
            ).join('')}</ul>`;
        } else {
            plEl.innerHTML = `<div class="empty-state"><p>No policies loaded</p>
                <a href="#/policies" class="btn btn-primary btn-sm">Add Policy</a></div>`;
        }

        // Bundle status
        const bsEl = document.getElementById('bundle-status');
        if (bundleList.length > 0) {
            bsEl.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Revision</th><th>Status</th></tr></thead>
                    <tbody>${bundleList.map(name => {
                        const b = bundles.bundles[name];
                        return `<tr>
                            <td><a href="#/bundles" class="link">${esc(name)}</a></td>
                            <td class="text-muted">${esc(b.revision || '–')}</td>
                            <td><span class="badge badge-success">Active</span></td>
                        </tr>`;
                    }).join('')}</tbody>
                </table>`;
        } else {
            bsEl.innerHTML = `<div class="empty-state"><p>No bundles loaded</p>
                <a href="#/bundles" class="btn btn-primary btn-sm">Upload Bundle</a></div>`;
        }

        // Recent decisions
        const decisions = await API.get('/v1/ui/decisions?limit=5');
        const rdEl = document.getElementById('recent-decisions');
        if (decisions.entries.length > 0) {
            rdEl.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Time</th><th>Query</th><th>Duration</th><th>Status</th></tr></thead>
                    <tbody>${decisions.entries.map(d => `
                        <tr>
                            <td class="text-muted">${new Date(d.timestamp * 1000).toLocaleTimeString()}</td>
                            <td><code>${esc(d.query)}</code></td>
                            <td>${d.duration_ms.toFixed(1)}ms</td>
                            <td>${d.error
                                ? '<span class="badge badge-danger">Error</span>'
                                : '<span class="badge badge-success">OK</span>'}</td>
                        </tr>`).join('')}
                    </tbody>
                </table>
                <a href="#/logs" class="link" style="display:block;margin-top:8px;">View all decisions →</a>`;
        } else {
            rdEl.innerHTML = `<div class="empty-state"><p>No decisions recorded yet</p>
                <p class="text-muted">Use the <a href="#/playground" class="link">Playground</a> to run queries</p></div>`;
        }
    } catch (err) {
        toast('Failed to load dashboard: ' + err.message, 'error');
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
}

export function mount() {
    document.getElementById('refresh-btn')?.addEventListener('click', loadDashboard);
    loadDashboard();
    refreshInterval = setInterval(loadDashboard, 30000);
    return () => { clearInterval(refreshInterval); refreshInterval = null; };
}
