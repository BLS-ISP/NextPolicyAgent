/**
 * Data Browser — Tree view with JSON editor for data documents.
 */
import { API, toast, showModal, closeModal, escapeHtml, formatJson, createEditor } from '../app.js';

let jsonEditor = null;
let selectedPath = '';

export function render() {
    return `
        <div class="page-header">
            <h2>Data Browser</h2>
            <div class="btn-group">
                <button class="btn btn-primary btn-sm" id="add-data-btn">+ Add Document</button>
                <button class="btn btn-secondary btn-sm" id="refresh-data-btn">↻ Refresh</button>
            </div>
        </div>
        <div class="split-layout">
            <div class="split-left">
                <div class="panel">
                    <div class="panel-header"><h3>Document Tree</h3></div>
                    <div class="panel-body tree-container" id="data-tree">
                        <div class="loading-inline">Loading…</div>
                    </div>
                </div>
            </div>
            <div class="split-right">
                <div class="panel">
                    <div class="panel-header">
                        <h3 id="data-path-display">Select a node</h3>
                        <div class="btn-group">
                            <button class="btn btn-success btn-sm" id="save-data-btn" disabled>💾 Save</button>
                            <button class="btn btn-danger btn-sm" id="delete-data-btn" disabled>🗑️ Delete</button>
                        </div>
                    </div>
                    <div class="panel-body editor-container" id="data-editor-container">
                        <div class="empty-state"><p>Select a node from the tree to view or edit</p></div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

async function loadTree() {
    try {
        const data = await API.get('/v1/ui/data-tree');
        renderTree(data.tree);
    } catch (err) {
        document.getElementById('data-tree').innerHTML =
            `<div class="error-box">${escapeHtml(err.message)}</div>`;
    }
}

function renderTree(node, parentEl = null, path = '') {
    const container = parentEl || document.getElementById('data-tree');
    if (!parentEl) container.innerHTML = '';

    if (!node.children || node.children.length === 0) {
        if (!parentEl) container.innerHTML = '<div class="empty-state"><p>No data documents</p></div>';
        return;
    }

    const ul = document.createElement('ul');
    ul.className = 'tree-list';

    for (const child of node.children) {
        const li = document.createElement('li');
        li.className = 'tree-node';
        const childPath = path ? `${path}/${child.key}` : child.key;

        if (child.children && child.children.length > 0) {
            li.innerHTML = `
                <div class="tree-folder" data-path="${escapeHtml(childPath)}">
                    <span class="tree-toggle">▶</span>
                    <span class="tree-icon">📂</span>
                    <span class="tree-label">${escapeHtml(child.key)}</span>
                    <span class="tree-meta">${child.count} items</span>
                </div>`;
            const sub = document.createElement('div');
            sub.className = 'tree-children collapsed';
            li.appendChild(sub);

            const folder = li.querySelector('.tree-folder');
            folder.addEventListener('click', () => {
                const collapsed = sub.classList.contains('collapsed');
                sub.classList.toggle('collapsed');
                li.querySelector('.tree-toggle').textContent = collapsed ? '▼' : '▶';
                if (collapsed && sub.children.length === 0) renderTree(child, sub, childPath);
                selectNode(childPath);
            });
        } else {
            const icon = child.type === 'str' ? '📝' :
                         child.type === 'int' || child.type === 'float' ? '🔢' :
                         child.type === 'bool' ? '✅' : '📄';
            const preview = formatJson(child.value);
            li.innerHTML = `
                <div class="tree-leaf" data-path="${escapeHtml(childPath)}">
                    <span class="tree-icon">${icon}</span>
                    <span class="tree-label">${escapeHtml(child.key)}</span>
                    <span class="tree-value">${escapeHtml(preview.substring(0, 50))}</span>
                </div>`;
            li.querySelector('.tree-leaf').addEventListener('click', () => selectNode(childPath));
        }
        ul.appendChild(li);
    }
    container.appendChild(ul);
}

async function selectNode(path) {
    selectedPath = path;
    document.getElementById('data-path-display').textContent = `data.${path.replace(/\//g, '.')}`;
    document.getElementById('save-data-btn').disabled = false;
    document.getElementById('delete-data-btn').disabled = false;

    try {
        const result = await API.get(`/v1/data/${path}`);
        const container = document.getElementById('data-editor-container');
        container.innerHTML = '';
        jsonEditor = createEditor(container, {
            value: formatJson(result.result),
            mode: { name: 'javascript', json: true },
            lineNumbers: true,
        });
    } catch (err) {
        document.getElementById('data-editor-container').innerHTML =
            `<div class="error-box">${escapeHtml(err.message)}</div>`;
    }
}

async function saveData() {
    if (!jsonEditor || !selectedPath) return;
    let value;
    try { value = JSON.parse(jsonEditor.getValue()); }
    catch (e) { toast('Invalid JSON: ' + e.message, 'error'); return; }

    try {
        await API.put(`/v1/data/${selectedPath}`, value);
        toast('Data saved', 'success');
        loadTree();
    } catch (err) { toast('Save failed: ' + err.message, 'error'); }
}

async function deleteData() {
    if (!selectedPath) return;
    showModal(`
        <div class="modal-header"><h3>Delete Document</h3></div>
        <div class="modal-body">
            <p>Delete <strong>data.${escapeHtml(selectedPath.replace(/\//g, '.'))}</strong>?</p>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
            <button class="btn btn-danger" id="modal-confirm">Delete</button>
        </div>`);

    document.getElementById('modal-cancel').onclick = closeModal;
    document.getElementById('modal-confirm').onclick = async () => {
        closeModal();
        try {
            await API.del(`/v1/data/${selectedPath}`);
            toast('Document deleted', 'success');
            selectedPath = '';
            document.getElementById('data-editor-container').innerHTML =
                '<div class="empty-state"><p>Select a node</p></div>';
            document.getElementById('data-path-display').textContent = 'Select a node';
            document.getElementById('save-data-btn').disabled = true;
            document.getElementById('delete-data-btn').disabled = true;
            loadTree();
        } catch (err) { toast('Delete failed: ' + err.message, 'error'); }
    };
}

function showAddDialog() {
    showModal(`
        <div class="modal-header"><h3>Add Document</h3></div>
        <div class="modal-body">
            <div class="form-group">
                <label class="form-label">Path</label>
                <input type="text" class="form-input" id="add-data-path"
                       placeholder="e.g. myapp/config" autocomplete="off">
            </div>
            <div class="form-group">
                <label class="form-label">Value (JSON)</label>
                <textarea class="form-textarea" id="add-data-value" rows="5"
                          placeholder='{"key": "value"}'></textarea>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
            <button class="btn btn-primary" id="modal-confirm">Add</button>
        </div>`);

    document.getElementById('add-data-path').focus();
    document.getElementById('modal-cancel').onclick = closeModal;
    document.getElementById('modal-confirm').onclick = async () => {
        const path = document.getElementById('add-data-path').value.trim();
        const raw = document.getElementById('add-data-value').value.trim();
        if (!path) { toast('Enter a path', 'warning'); return; }
        let value;
        try { value = JSON.parse(raw || '{}'); }
        catch (e) { toast('Invalid JSON: ' + e.message, 'error'); return; }
        closeModal();
        try {
            await API.put(`/v1/data/${path}`, value);
            toast('Document created', 'success');
            loadTree();
        } catch (err) { toast('Create failed: ' + err.message, 'error'); }
    };
}

export function mount() {
    document.getElementById('add-data-btn').addEventListener('click', showAddDialog);
    document.getElementById('refresh-data-btn').addEventListener('click', loadTree);
    document.getElementById('save-data-btn').addEventListener('click', saveData);
    document.getElementById('delete-data-btn').addEventListener('click', deleteData);
    loadTree();
    return () => { jsonEditor = null; selectedPath = ''; };
}
