/**
 * Decision Logs — Searchable, filterable log with export.
 */
import { API, toast, escapeHtml, formatJson, showModal, closeModal } from '../app.js';

let refreshInterval = null;
let allEntries = [];

export function render() {
    return `
        <div class="page-header">
            <h2>Decision Logs</h2>
            <div class="btn-group">
                <button class="btn btn-secondary btn-sm" id="export-json-btn">📥 JSON</button>
                <button class="btn btn-secondary btn-sm" id="export-csv-btn">📥 CSV</button>
                <button class="btn btn-secondary btn-sm" id="refresh-logs-btn">↻ Refresh</button>
                <button class="btn btn-danger btn-sm" id="clear-logs-btn">Clear All</button>
            </div>
        </div>
        <div class="toolbar" style="margin-bottom:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <input type="text" class="form-input" id="log-search" placeholder="Search query or path…"
                   style="max-width:300px;flex:1">
            <select class="form-select-sm" id="log-status-filter">
                <option value="all">All Status</option>
                <option value="ok">OK Only</option>
                <option value="error">Errors Only</option>
            </select>
            <label class="toolbar-label">
                Limit:
                <select class="form-select-sm" id="log-limit">
                    <option value="50">50</option>
                    <option value="100" selected>100</option>
                    <option value="200">200</option>
                    <option value="500">500</option>
                </select>
            </label>
        </div>
        <div class="card">
            <div class="card-header">
                <h3>Recent Decisions</h3>
                <span class="text-muted" id="log-count"></span>
            </div>
            <div class="card-body" id="log-container">
                <div class="loading-inline">Loading…</div>
            </div>
        </div>
    `;
}

function getFilteredEntries() {
    const search = (document.getElementById('log-search')?.value || '').toLowerCase();
    const status = document.getElementById('log-status-filter')?.value || 'all';
    return allEntries.filter(e => {
        if (status === 'ok' && e.error) return false;
        if (status === 'error' && !e.error) return false;
        if (search && !e.query.toLowerCase().includes(search)) return false;
        return true;
    });
}

function renderEntries() {
    const entries = getFilteredEntries();
    const container = document.getElementById('log-container');
    document.getElementById('log-count').textContent = `${entries.length} of ${allEntries.length} total`;

    if (entries.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No decisions match your filter</p>
            </div>`;
        return;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Timestamp</th>
                    <th>Query</th>
                    <th>Duration</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>${entries.map(e => `
                <tr>
                    <td class="text-muted">${e.id}</td>
                    <td>${new Date(e.timestamp * 1000).toLocaleString()}</td>
                    <td><code>${escapeHtml(e.query)}</code></td>
                    <td>${e.duration_ms.toFixed(1)}ms</td>
                    <td>${e.error
                        ? '<span class="badge badge-danger">Error</span>'
                        : '<span class="badge badge-success">OK</span>'}</td>
                    <td><button class="btn btn-ghost btn-sm detail-btn" data-id="${e.id}">Details</button></td>
                </tr>`).join('')}
            </tbody>
        </table>`;

    container.querySelectorAll('.detail-btn').forEach(btn =>
        btn.addEventListener('click', () => {
            const entry = allEntries.find(e => e.id === parseInt(btn.dataset.id));
            if (entry) showDetail(entry);
        }));
}

async function loadLogs() {
    const limit = parseInt(document.getElementById('log-limit')?.value || '100');
    try {
        const data = await API.get(`/v1/ui/decisions?limit=${limit}`);
        allEntries = data.entries;
        renderEntries();
    } catch (err) {
        toast('Failed to load logs: ' + err.message, 'error');
    }
}

function showDetail(entry) {
    showModal(`
        <div class="modal-header"><h3>Decision #${entry.id}</h3></div>
        <div class="modal-body">
            <table class="info-table">
                <tr><td class="info-label">Time</td><td>${new Date(entry.timestamp * 1000).toLocaleString()}</td></tr>
                <tr><td class="info-label">Query</td><td><code>${escapeHtml(entry.query)}</code></td></tr>
                <tr><td class="info-label">Duration</td><td>${entry.duration_ms.toFixed(2)}ms</td></tr>
                <tr><td class="info-label">Status</td><td>${entry.error ? 'Error' : 'OK'}</td></tr>
            </table>
            ${entry.input != null ? `<h4 style="margin-top:16px">Input</h4><pre class="result-json">${escapeHtml(formatJson(entry.input))}</pre>` : ''}
            ${entry.result != null ? `<h4 style="margin-top:16px">Result</h4><pre class="result-json">${escapeHtml(formatJson(entry.result))}</pre>` : ''}
            ${entry.error ? `<h4 style="margin-top:16px">Error</h4><div class="error-box">${escapeHtml(entry.error)}</div>` : ''}
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Close</button>
        </div>`);
    document.getElementById('modal-cancel').onclick = closeModal;
}

function exportJSON() {
    const entries = getFilteredEntries();
    const blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `npa-decisions-${new Date().toISOString().slice(0,10)}.json`;
    a.click(); URL.revokeObjectURL(url);
    toast(`Exported ${entries.length} entries as JSON`, 'success');
}

function exportCSV() {
    const entries = getFilteredEntries();
    const header = 'id,timestamp,query,duration_ms,status,error\n';
    const rows = entries.map(e =>
        `${e.id},"${new Date(e.timestamp * 1000).toISOString()}","${e.query.replace(/"/g, '""')}",${e.duration_ms.toFixed(2)},${e.error ? 'error' : 'ok'},"${(e.error || '').replace(/"/g, '""')}"`
    ).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `npa-decisions-${new Date().toISOString().slice(0,10)}.csv`;
    a.click(); URL.revokeObjectURL(url);
    toast(`Exported ${entries.length} entries as CSV`, 'success');
}

export function mount() {
    document.getElementById('refresh-logs-btn').addEventListener('click', loadLogs);
    document.getElementById('clear-logs-btn').addEventListener('click', async () => {
        try {
            await API.del('/v1/ui/decisions');
            toast('Logs cleared', 'success');
            loadLogs();
        } catch (err) { toast('Clear failed: ' + err.message, 'error'); }
    });
    document.getElementById('export-json-btn').addEventListener('click', exportJSON);
    document.getElementById('export-csv-btn').addEventListener('click', exportCSV);
    document.getElementById('log-search').addEventListener('input', renderEntries);
    document.getElementById('log-status-filter').addEventListener('change', renderEntries);
    document.getElementById('log-limit').addEventListener('change', loadLogs);

    loadLogs();
    refreshInterval = setInterval(loadLogs, 10000);
    return () => { clearInterval(refreshInterval); refreshInterval = null; allEntries = []; };
}
