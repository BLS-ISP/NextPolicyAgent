/**
 * Query Playground — Interactive Rego query execution with explain, metrics, and compile.
 */
import { API, createEditor, toast, formatJson, escapeHtml } from '../app.js';

let queryEditor = null;
let inputEditor = null;
let historyList = [];
const HISTORY_KEY = 'npa_query_history';

export function render() {
    return `
        <div class="page-header">
            <h2>Query Playground</h2>
            <div class="btn-group">
                <span class="text-muted text-sm" style="margin-right:8px">Ctrl+Enter to run</span>
                <button class="btn btn-primary" id="run-query-btn">▶ Execute</button>
                <button class="btn btn-secondary btn-sm" id="compile-btn">⚙ Compile</button>
                <button class="btn btn-secondary btn-sm" id="clear-result-btn">Clear</button>
            </div>
        </div>

        <div class="toolbar" style="margin-bottom:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <label class="toolbar-label">
                Explain:
                <select id="explain-mode" class="form-select-sm">
                    <option value="off">Off</option>
                    <option value="notes">Notes</option>
                    <option value="fails">Fails</option>
                    <option value="full">Full</option>
                    <option value="debug">Debug</option>
                </select>
            </label>
            <label class="toolbar-check">
                <input type="checkbox" id="metrics-toggle"> Metrics
            </label>
            <label class="toolbar-check">
                <input type="checkbox" id="instrument-toggle"> Instrument
            </label>
            <label class="toolbar-check">
                <input type="checkbox" id="strict-builtin-toggle"> Strict Builtins
            </label>
        </div>

        <div class="playground-layout">
            <div class="playground-editors">
                <div class="panel">
                    <div class="panel-header">
                        <h3>Query</h3>
                        <span class="text-muted text-sm">Rego expression</span>
                    </div>
                    <div class="panel-body editor-sm" id="query-editor-container"></div>
                </div>
                <div class="panel">
                    <div class="panel-header">
                        <h3>Input (JSON)</h3>
                        <span class="text-muted text-sm">Optional input document</span>
                    </div>
                    <div class="panel-body editor-sm" id="input-editor-container"></div>
                </div>
            </div>
            <div class="playground-result">
                <div class="panel">
                    <div class="panel-header">
                        <h3>Result</h3>
                        <span class="text-muted text-sm" id="result-meta"></span>
                    </div>
                    <div class="panel-body result-container" id="result-container">
                        <div class="empty-state">
                            <p>Run a query to see results</p>
                            <p class="text-muted">Try: <code>data</code>, <code>1 + 1</code>, or <code>data.myapp.allow</code></p>
                        </div>
                    </div>
                </div>
                <div class="panel" id="explain-panel" style="display:none">
                    <div class="panel-header"><h3>Explanation Trace</h3></div>
                    <div class="panel-body result-container" id="explain-container"></div>
                </div>
                <div class="panel" id="metrics-panel" style="display:none">
                    <div class="panel-header"><h3>Metrics</h3></div>
                    <div class="panel-body" id="metrics-container"></div>
                </div>
            </div>
            <div class="playground-sidebar">
                <div class="panel">
                    <div class="panel-header">
                        <h3>History</h3>
                        <button class="btn btn-ghost btn-sm" id="clear-history-btn">Clear</button>
                    </div>
                    <div class="panel-body" id="history-container">
                        <div class="empty-state"><p class="text-muted">No queries yet</p></div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function getOptions() {
    return {
        explain: document.getElementById('explain-mode')?.value || 'off',
        metrics: document.getElementById('metrics-toggle')?.checked || false,
        instrument: document.getElementById('instrument-toggle')?.checked || false,
        strictBuiltin: document.getElementById('strict-builtin-toggle')?.checked || false,
    };
}

async function executeQuery() {
    if (!queryEditor) return;
    const query = queryEditor.getValue().trim();
    if (!query) { toast('Enter a query', 'warning'); return; }

    let inputData = null;
    const inputText = inputEditor?.getValue().trim();
    if (inputText && inputText !== '{}') {
        try { inputData = JSON.parse(inputText); }
        catch (e) { toast('Invalid input JSON: ' + e.message, 'error'); return; }
    }

    const container = document.getElementById('result-container');
    const meta = document.getElementById('result-meta');
    container.innerHTML = '<div class="loading-inline">Evaluating…</div>';

    const opts = getOptions();
    const params = [];
    if (opts.explain !== 'off') params.push('explain=' + opts.explain);
    if (opts.metrics) params.push('metrics=true');
    if (opts.instrument) params.push('instrument=true');
    if (opts.strictBuiltin) params.push('strict-builtin-errors=true');
    const url = '/v1/query' + (params.length ? '?' + params.join('&') : '');

    const t0 = performance.now();
    try {
        const res = await API.post(url, { query, input: inputData });
        const ms = performance.now() - t0;
        meta.textContent = `${ms.toFixed(1)}ms`;
        container.innerHTML = `<pre class="result-json">${escapeHtml(formatJson(res.result))}</pre>`;

        // Show explanation trace if available
        const explainPanel = document.getElementById('explain-panel');
        if (res.explanation && res.explanation.length > 0) {
            explainPanel.style.display = '';
            document.getElementById('explain-container').innerHTML =
                `<pre class="result-json trace-output">${escapeHtml(res.explanation.join('\n'))}</pre>`;
        } else {
            explainPanel.style.display = 'none';
        }

        // Show metrics if available
        const metricsPanel = document.getElementById('metrics-panel');
        if (res.metrics) {
            metricsPanel.style.display = '';
            const mc = document.getElementById('metrics-container');
            mc.innerHTML = `<table class="info-table">${Object.entries(res.metrics).map(([k, v]) =>
                `<tr><td class="info-label">${escapeHtml(k)}</td><td>${typeof v === 'number' ? v.toLocaleString() : escapeHtml(String(v))}</td></tr>`
            ).join('')}</table>`;
        } else {
            metricsPanel.style.display = 'none';
        }

        addHistory(query, inputData, res.result, ms, null);
    } catch (err) {
        const ms = performance.now() - t0;
        meta.textContent = `${ms.toFixed(1)}ms — Error`;
        container.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
        document.getElementById('explain-panel').style.display = 'none';
        document.getElementById('metrics-panel').style.display = 'none';
        addHistory(query, inputData, null, ms, err.message);
    }
}

async function compileQuery() {
    if (!queryEditor) return;
    const query = queryEditor.getValue().trim();
    if (!query) { toast('Enter a query', 'warning'); return; }

    let inputData = null;
    const inputText = inputEditor?.getValue().trim();
    if (inputText && inputText !== '{}') {
        try { inputData = JSON.parse(inputText); }
        catch (e) { toast('Invalid input JSON: ' + e.message, 'error'); return; }
    }

    const container = document.getElementById('result-container');
    const meta = document.getElementById('result-meta');
    container.innerHTML = '<div class="loading-inline">Compiling…</div>';

    const opts = getOptions();
    let url = '/v1/compile';
    if (opts.metrics) url += '?metrics=true';

    const t0 = performance.now();
    try {
        const body = { query, input: inputData, unknowns: ['input'] };
        const res = await API.post(url, body);
        const ms = performance.now() - t0;
        meta.textContent = `Compile ${ms.toFixed(1)}ms`;
        container.innerHTML = `<pre class="result-json">${escapeHtml(formatJson(res.result))}</pre>`;

        const metricsPanel = document.getElementById('metrics-panel');
        if (res.metrics) {
            metricsPanel.style.display = '';
            const mc = document.getElementById('metrics-container');
            mc.innerHTML = `<table class="info-table">${Object.entries(res.metrics).map(([k, v]) =>
                `<tr><td class="info-label">${escapeHtml(k)}</td><td>${typeof v === 'number' ? v.toLocaleString() : escapeHtml(String(v))}</td></tr>`
            ).join('')}</table>`;
        } else {
            metricsPanel.style.display = 'none';
        }
        document.getElementById('explain-panel').style.display = 'none';
    } catch (err) {
        const ms = performance.now() - t0;
        meta.textContent = `Compile ${ms.toFixed(1)}ms — Error`;
        container.innerHTML = `<div class="error-box">${escapeHtml(err.message)}</div>`;
    }
}

function addHistory(query, input, result, duration, error) {
    historyList.unshift({ query, input, result, duration, error, time: new Date().toLocaleTimeString() });
    if (historyList.length > 50) historyList.pop();
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(historyList.slice(0, 20))); } catch {}
    renderHistory();
}

function renderHistory() {
    const c = document.getElementById('history-container');
    if (!historyList.length) {
        c.innerHTML = '<div class="empty-state"><p class="text-muted">No queries yet</p></div>';
        return;
    }
    c.innerHTML = historyList.map((h, i) => `
        <div class="history-item" data-index="${i}">
            <div class="history-query"><code>${escapeHtml(h.query)}</code></div>
            <div class="history-meta">
                <span class="text-muted">${h.time}</span>
                <span class="${h.error ? 'text-danger' : 'text-success'}">${h.duration.toFixed(0)}ms</span>
            </div>
        </div>`).join('');

    c.querySelectorAll('.history-item').forEach(el =>
        el.addEventListener('click', () => {
            const h = historyList[parseInt(el.dataset.index)];
            if (h && queryEditor) {
                queryEditor.setValue(h.query);
                if (h.input && inputEditor) inputEditor.setValue(formatJson(h.input));
            }
        }));
}

function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); executeQuery(); }
}

export function mount() {
    try {
        const saved = localStorage.getItem(HISTORY_KEY);
        if (saved) historyList = JSON.parse(saved);
    } catch { historyList = []; }

    const qMode = (typeof CodeMirror !== 'undefined' && CodeMirror.modes.rego) ? 'rego' : 'javascript';
    queryEditor = createEditor(document.getElementById('query-editor-container'), {
        value: 'data', mode: qMode, lineNumbers: true,
    });
    inputEditor = createEditor(document.getElementById('input-editor-container'), {
        value: '{}', mode: { name: 'javascript', json: true }, lineNumbers: true,
    });

    document.getElementById('run-query-btn').addEventListener('click', executeQuery);
    document.getElementById('compile-btn').addEventListener('click', compileQuery);
    document.getElementById('clear-result-btn').addEventListener('click', () => {
        document.getElementById('result-container').innerHTML =
            '<div class="empty-state"><p>Run a query to see results</p></div>';
        document.getElementById('result-meta').textContent = '';
        document.getElementById('explain-panel').style.display = 'none';
        document.getElementById('metrics-panel').style.display = 'none';
    });
    document.getElementById('clear-history-btn').addEventListener('click', () => {
        historyList = [];
        localStorage.removeItem(HISTORY_KEY);
        renderHistory();
    });

    document.addEventListener('keydown', handleKeydown);
    renderHistory();

    return () => { document.removeEventListener('keydown', handleKeydown); queryEditor = null; inputEditor = null; };
}
