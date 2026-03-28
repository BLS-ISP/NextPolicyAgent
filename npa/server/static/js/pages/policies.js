/**
 * Policy Editor Page — CRUD with syntax-highlighted editor, format, check, AST, test.
 */
import { API, createEditor, toast, showModal, closeModal, escapeHtml, formatJson } from '../app.js';

let editor = null;
let currentPolicyId = null;

export function render() {
    return `
        <div class="page-header">
            <h2>Policies</h2>
            <div class="btn-group">
                <button class="btn btn-primary" id="new-policy-btn">+ New Policy</button>
                <button class="btn btn-secondary btn-sm" id="run-tests-btn">🧪 Run Tests</button>
            </div>
        </div>
        <div class="split-layout">
            <div class="split-left">
                <div class="panel">
                    <div class="panel-header">
                        <h3>Policy List</h3>
                        <button class="btn btn-ghost btn-sm" id="refresh-policies-btn">↻</button>
                    </div>
                    <div class="panel-body" id="policy-list">
                        <div class="loading-inline">Loading…</div>
                    </div>
                </div>
            </div>
            <div class="split-right">
                <div class="panel">
                    <div class="panel-header">
                        <h3 id="editor-title">Select a policy</h3>
                        <div class="btn-group">
                            <button class="btn btn-ghost btn-sm" id="fmt-btn" disabled title="Format code">🎨 Fmt</button>
                            <button class="btn btn-ghost btn-sm" id="check-btn" disabled title="Check syntax">✓ Check</button>
                            <button class="btn btn-ghost btn-sm" id="ast-btn" disabled title="View AST">🌳 AST</button>
                            <button class="btn btn-success btn-sm" id="save-policy-btn" disabled>💾 Save</button>
                            <button class="btn btn-danger btn-sm" id="delete-policy-btn" disabled>🗑️ Delete</button>
                        </div>
                    </div>
                    <div class="panel-body editor-container" id="editor-container">
                        <div class="empty-state">
                            <p>Select a policy from the list or create a new one</p>
                        </div>
                    </div>
                    <div class="panel-footer" id="editor-footer" style="display:none">
                        <div id="parse-status" class="parse-status"></div>
                    </div>
                </div>
                <div class="panel" id="ast-panel" style="display:none">
                    <div class="panel-header">
                        <h3>AST View</h3>
                        <button class="btn btn-ghost btn-sm" id="close-ast-btn">✕</button>
                    </div>
                    <div class="panel-body result-container" id="ast-container"></div>
                </div>
            </div>
        </div>
    `;
}

async function loadPolicies() {
    try {
        const data = await API.get('/v1/policies');
        const list = document.getElementById('policy-list');
        if (data.result.length === 0) {
            list.innerHTML = '<div class="empty-state"><p>No policies yet</p></div>';
            return;
        }
        list.innerHTML = data.result.map(p => `
            <div class="list-item ${currentPolicyId === p.id ? 'active' : ''}" data-id="${escapeHtml(p.id)}">
                <span class="list-item-icon">📄</span>
                <span class="list-item-text">${escapeHtml(p.id)}</span>
                <span class="list-item-meta">${p.raw.split('\\n').length} lines</span>
            </div>
        `).join('');

        list.querySelectorAll('.list-item').forEach(el =>
            el.addEventListener('click', () => openPolicy(el.dataset.id)));
    } catch (err) {
        toast('Failed to load policies: ' + err.message, 'error');
    }
}

async function openPolicy(policyId) {
    try {
        const data = await API.get(`/v1/policies/${encodeURIComponent(policyId)}`);
        currentPolicyId = policyId;

        document.getElementById('editor-title').textContent = policyId;
        document.getElementById('save-policy-btn').disabled = false;
        document.getElementById('delete-policy-btn').disabled = false;
        document.getElementById('fmt-btn').disabled = false;
        document.getElementById('check-btn').disabled = false;
        document.getElementById('ast-btn').disabled = false;
        document.getElementById('editor-footer').style.display = '';
        document.getElementById('parse-status').innerHTML =
            '<span class="text-success">✓ Valid</span>';

        initEditor(data.raw);

        document.querySelectorAll('#policy-list .list-item').forEach(el =>
            el.classList.toggle('active', el.dataset.id === policyId));
    } catch (err) {
        toast('Failed to load policy: ' + err.message, 'error');
    }
}

function initEditor(value = '') {
    const container = document.getElementById('editor-container');
    container.innerHTML = '';
    const mode = (typeof CodeMirror !== 'undefined' && CodeMirror.modes.rego)
        ? 'rego' : 'javascript';
    editor = createEditor(container, { value, mode, placeholder: 'Enter Rego policy…' });
}

async function savePolicy() {
    if (!currentPolicyId || !editor) return;
    const source = editor.getValue();
    try {
        await API.putText(`/v1/policies/${encodeURIComponent(currentPolicyId)}`, source);
        toast('Policy saved', 'success');
        document.getElementById('parse-status').innerHTML =
            '<span class="text-success">✓ Valid</span>';
        loadPolicies();
    } catch (err) {
        toast('Save failed: ' + err.message, 'error');
        document.getElementById('parse-status').innerHTML =
            `<span class="text-danger">✗ ${escapeHtml(err.message)}</span>`;
    }
}

async function deletePolicy() {
    if (!currentPolicyId) return;
    showModal(`
        <div class="modal-header"><h3>Delete Policy</h3></div>
        <div class="modal-body">
            <p>Delete <strong>${escapeHtml(currentPolicyId)}</strong>?</p>
            <p class="text-muted">This cannot be undone.</p>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
            <button class="btn btn-danger" id="modal-confirm">Delete</button>
        </div>`);

    document.getElementById('modal-cancel').onclick = closeModal;
    document.getElementById('modal-confirm').onclick = async () => {
        closeModal();
        try {
            await API.del(`/v1/policies/${encodeURIComponent(currentPolicyId)}`);
            toast('Policy deleted', 'success');
            currentPolicyId = null;
            document.getElementById('editor-container').innerHTML =
                '<div class="empty-state"><p>Select a policy</p></div>';
            document.getElementById('editor-title').textContent = 'Select a policy';
            document.getElementById('save-policy-btn').disabled = true;
            document.getElementById('delete-policy-btn').disabled = true;
            document.getElementById('editor-footer').style.display = 'none';
            loadPolicies();
        } catch (err) { toast('Delete failed: ' + err.message, 'error'); }
    };
}

async function formatCode() {
    if (!editor) return;
    const source = editor.getValue();
    try {
        const res = await API.post('/v1/ui/fmt', { source, filename: currentPolicyId || 'input.rego' });
        if (res.changed) {
            editor.setValue(res.result);
            toast('Code formatted', 'success');
        } else {
            toast('Already formatted', 'info');
        }
    } catch (err) {
        toast('Format error: ' + err.message, 'error');
    }
}

async function checkSyntax() {
    if (!editor) return;
    const source = editor.getValue();
    try {
        const res = await API.post('/v1/ui/check', { source, filename: currentPolicyId || 'input.rego' });
        const status = document.getElementById('parse-status');
        if (res.valid) {
            status.innerHTML = `<span class="text-success">✓ Valid — package: ${escapeHtml(res.package)}, ${res.rules} rule(s), ${res.imports} import(s)</span>`;
            toast('Syntax OK', 'success');
        } else {
            const msgs = res.errors.map(e => escapeHtml(e.message)).join('<br>');
            status.innerHTML = `<span class="text-danger">✗ ${msgs}</span>`;
            toast('Syntax errors found', 'error');
        }
    } catch (err) {
        toast('Check error: ' + err.message, 'error');
    }
}

async function viewAST() {
    if (!editor) return;
    const source = editor.getValue();
    const astPanel = document.getElementById('ast-panel');
    const astContainer = document.getElementById('ast-container');
    astContainer.innerHTML = '<div class="loading-inline">Parsing…</div>';
    astPanel.style.display = '';
    try {
        const res = await API.post('/v1/ui/parse', { source, filename: currentPolicyId || 'input.rego' });
        astContainer.innerHTML = `<pre class="result-json">${escapeHtml(formatJson(res.result))}</pre>`;
    } catch (err) {
        astContainer.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    }
}

async function runTests() {
    try {
        const res = await API.post('/v1/ui/test');
        if (res.total === 0) {
            toast('No test_ rules found in loaded policies', 'info');
            return;
        }
        let html = `<div class="modal-header"><h3>Test Results</h3></div><div class="modal-body">`;
        html += `<p><strong>${res.passed}</strong> passed, <strong>${res.failed}</strong> failed of <strong>${res.total}</strong> tests</p>`;
        html += `<table class="data-table"><thead><tr><th>Test</th><th>Status</th><th>Message</th></tr></thead><tbody>`;
        for (const t of res.results) {
            const cls = t.status === 'PASS' ? 'badge-success' : 'badge-danger';
            html += `<tr><td><code>${escapeHtml(t.name)}</code></td><td><span class="badge ${cls}">${t.status}</span></td><td>${escapeHtml(t.message || '')}</td></tr>`;
        }
        html += `</tbody></table></div><div class="modal-footer"><button class="btn btn-secondary" id="modal-cancel">Close</button></div>`;
        showModal(html);
        document.getElementById('modal-cancel').onclick = closeModal;
        toast(`${res.passed}/${res.total} tests passed`, res.failed > 0 ? 'warning' : 'success');
    } catch (err) {
        toast('Test error: ' + err.message, 'error');
    }
}

function showNewPolicyDialog() {
    showModal(`
        <div class="modal-header"><h3>New Policy</h3></div>
        <div class="modal-body">
            <div class="form-group">
                <label class="form-label">Policy ID</label>
                <input type="text" class="form-input" id="new-policy-id"
                       placeholder="e.g. example/authz" autocomplete="off">
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
            <button class="btn btn-primary" id="modal-confirm">Create</button>
        </div>`);

    const input = document.getElementById('new-policy-id');
    input.focus();
    document.getElementById('modal-cancel').onclick = closeModal;
    document.getElementById('modal-confirm').onclick = () => {
        const id = input.value.trim();
        if (!id) { toast('Enter a policy ID', 'warning'); return; }
        closeModal();
        currentPolicyId = id;
        document.getElementById('editor-title').textContent = id;
        document.getElementById('save-policy-btn').disabled = false;
        document.getElementById('delete-policy-btn').disabled = false;
        document.getElementById('editor-footer').style.display = '';
        document.getElementById('parse-status').innerHTML =
            '<span class="text-muted">New — not saved yet</span>';
        initEditor(
            `package ${id.replace(/\//g, '.')}\n\ndefault allow := false\n\nallow if {\n    # Your rules here\n}\n`
        );
    };
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') document.getElementById('modal-confirm').click();
    });
}

export function mount() {
    document.getElementById('new-policy-btn').addEventListener('click', showNewPolicyDialog);
    document.getElementById('save-policy-btn').addEventListener('click', savePolicy);
    document.getElementById('delete-policy-btn').addEventListener('click', deletePolicy);
    document.getElementById('refresh-policies-btn').addEventListener('click', loadPolicies);
    document.getElementById('fmt-btn').addEventListener('click', formatCode);
    document.getElementById('check-btn').addEventListener('click', checkSyntax);
    document.getElementById('ast-btn').addEventListener('click', viewAST);
    document.getElementById('run-tests-btn').addEventListener('click', runTests);
    document.getElementById('close-ast-btn').addEventListener('click', () => {
        document.getElementById('ast-panel').style.display = 'none';
    });
    loadPolicies();

    const hash = window.location.hash;
    const m = hash.match(/edit=([^&]+)/);
    if (m) openPolicy(decodeURIComponent(m[1]));

    return () => { editor = null; currentPolicyId = null; };
}
