/**
 * Bundle Management Page — Full CRUD: list, upload, delete, inspect.
 */
import { API, toast, escapeHtml, formatJson, showModal, closeModal } from '../app.js';

export function render() {
    return `
        <div class="page-header">
            <h2>Bundle Management</h2>
            <button class="btn btn-secondary btn-sm" id="refresh-bundles-btn">↻ Refresh</button>
        </div>
        <div class="card">
            <div class="card-header"><h3>Active Bundles</h3></div>
            <div class="card-body" id="bundle-list">
                <div class="loading-inline">Loading…</div>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><h3>Upload Bundle</h3></div>
            <div class="card-body">
                <div class="form-group" style="margin-bottom:12px">
                    <label class="form-label">Bundle Name</label>
                    <input type="text" class="form-input" id="bundle-name-input"
                           placeholder="e.g. authz-bundle" autocomplete="off" style="max-width:300px">
                </div>
                <div class="upload-area" id="upload-area">
                    <p>📦 Drag & drop a bundle (.tar.gz) here or click to browse</p>
                    <input type="file" id="bundle-file-input" accept=".tar.gz,.gz,.bundle" style="display:none">
                    <button class="btn btn-primary" id="browse-bundle-btn">Browse Files</button>
                </div>
                <div id="upload-status" style="margin-top:8px"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><h3>Bundle Configuration</h3></div>
            <div class="card-body">
                <p class="text-muted">
                    Remote bundle sources are configured in the server configuration file.
                    The bundle plugin periodically fetches and loads bundles from configured sources.
                </p>
                <table class="info-table" style="margin-top:12px">
                    <tr><td class="info-label">Polling</td><td>Configurable interval (default: 60s)</td></tr>
                    <tr><td class="info-label">Verification</td><td>JWT-based bundle signatures</td></tr>
                    <tr><td class="info-label">Format</td><td>.tar.gz with data.json / .rego files</td></tr>
                </table>
            </div>
        </div>
    `;
}

async function loadBundles() {
    try {
        const bundleData = await API.get('/v1/bundles');
        const container = document.getElementById('bundle-list');
        const bundles = bundleData.result || {};
        const names = Object.keys(bundles);

        if (names.length === 0) {
            // Fall back to showing API-loaded policies
            const status = await API.get('/v1/ui/status');
            if (status.policies.count > 0) {
                container.innerHTML = `
                    <table class="data-table">
                        <thead><tr><th>Source</th><th>Policies</th><th>Data Roots</th><th>Status</th><th>Actions</th></tr></thead>
                        <tbody>
                            <tr>
                                <td>Local / API</td>
                                <td>${status.policies.count} policies</td>
                                <td>${status.data.root_keys.length ? escapeHtml(status.data.root_keys.join(', ')) : '–'}</td>
                                <td><span class="badge badge-success">Active</span></td>
                                <td>–</td>
                            </tr>
                        </tbody>
                    </table>`;
            } else {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>No bundles loaded</p>
                        <p class="text-muted">Upload a bundle above or add policies via the <a href="#/policies" class="link">Policy Editor</a></p>
                    </div>`;
            }
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead><tr><th>Name</th><th>Revision</th><th>Roots</th><th>Policies</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>${names.map(name => {
                    const b = bundles[name];
                    return `<tr>
                        <td><strong>${escapeHtml(name)}</strong></td>
                        <td><code>${escapeHtml(b.revision || '–')}</code></td>
                        <td>${b.roots?.length ? escapeHtml(b.roots.join(', ')) : '–'}</td>
                        <td>${b.policies?.length || 0} files</td>
                        <td>${b.active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-muted">Inactive</span>'}</td>
                        <td>
                            <button class="btn btn-ghost btn-sm inspect-bundle-btn" data-name="${escapeHtml(name)}">🔍</button>
                            <button class="btn btn-danger btn-sm delete-bundle-btn" data-name="${escapeHtml(name)}">🗑️</button>
                        </td>
                    </tr>`;
                }).join('')}</tbody>
            </table>`;

        container.querySelectorAll('.inspect-bundle-btn').forEach(btn =>
            btn.addEventListener('click', () => inspectBundle(btn.dataset.name)));
        container.querySelectorAll('.delete-bundle-btn').forEach(btn =>
            btn.addEventListener('click', () => deleteBundle(btn.dataset.name)));
    } catch (err) {
        toast('Failed to load bundles: ' + err.message, 'error');
    }
}

function inspectBundle(name) {
    API.get(`/v1/bundles/${encodeURIComponent(name)}`).then(res => {
        showModal(`
            <div class="modal-header"><h3>Bundle: ${escapeHtml(name)}</h3></div>
            <div class="modal-body">
                <pre class="result-json">${escapeHtml(formatJson(res.result))}</pre>
            </div>
            <div class="modal-footer"><button class="btn btn-secondary" id="modal-cancel">Close</button></div>`);
        document.getElementById('modal-cancel').onclick = closeModal;
    }).catch(err => toast('Failed to inspect bundle: ' + err.message, 'error'));
}

function deleteBundle(name) {
    showModal(`
        <div class="modal-header"><h3>Delete Bundle</h3></div>
        <div class="modal-body">
            <p>Remove bundle <strong>${escapeHtml(name)}</strong>?</p>
            <p class="text-muted">All policies and data from this bundle will be unloaded.</p>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
            <button class="btn btn-danger" id="modal-confirm">Delete</button>
        </div>`);
    document.getElementById('modal-cancel').onclick = closeModal;
    document.getElementById('modal-confirm').onclick = async () => {
        closeModal();
        try {
            await API.del(`/v1/bundles/${encodeURIComponent(name)}`);
            toast(`Bundle "${name}" removed`, 'success');
            loadBundles();
        } catch (err) { toast('Delete failed: ' + err.message, 'error'); }
    };
}

async function uploadBundle(file) {
    const nameInput = document.getElementById('bundle-name-input');
    const name = nameInput?.value.trim();
    if (!name) {
        toast('Enter a bundle name first', 'warning');
        nameInput?.focus();
        return;
    }
    const statusEl = document.getElementById('upload-status');
    statusEl.innerHTML = `<span class="loading-inline">Uploading ${escapeHtml(file.name)}…</span>`;
    try {
        const buffer = await file.arrayBuffer();
        await API.putBinary(`/v1/bundles/${encodeURIComponent(name)}`, buffer);
        statusEl.innerHTML = `<span class="text-success">✓ Bundle "${escapeHtml(name)}" uploaded successfully</span>`;
        toast(`Bundle "${name}" activated`, 'success');
        nameInput.value = '';
        loadBundles();
    } catch (err) {
        statusEl.innerHTML = `<span class="text-danger">✗ Upload failed: ${escapeHtml(err.message)}</span>`;
        toast('Upload failed: ' + err.message, 'error');
    }
}

export function mount() {
    document.getElementById('refresh-bundles-btn').addEventListener('click', loadBundles);
    document.getElementById('browse-bundle-btn').addEventListener('click', () =>
        document.getElementById('bundle-file-input').click());

    document.getElementById('bundle-file-input').addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (file) uploadBundle(file);
    });

    // Drag & drop
    const area = document.getElementById('upload-area');
    area.addEventListener('dragover', e => { e.preventDefault(); area.style.borderColor = 'var(--accent-primary)'; });
    area.addEventListener('dragleave', () => { area.style.borderColor = ''; });
    area.addEventListener('drop', e => {
        e.preventDefault();
        area.style.borderColor = '';
        const file = e.dataTransfer?.files?.[0];
        if (file) uploadBundle(file);
    });

    loadBundles();
}
