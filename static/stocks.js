'use strict';

/**
 * stocks.js — A-share price monitor page.
 */

const POLL_ACTIVE_MS = 10_000;
const POLL_IDLE_MS = 300_000;
const SYMBOL_RE = /^((sh|sz|bj)\d{6}|\d{6})$/;
const ALERT_LABELS = {
    up: { text: '涨破上限', cls: 'up' },
    down: { text: '跌破下限', cls: 'down' },
    rsi_high: { text: 'RSI 超买', cls: 'up' },
    rsi_low: { text: 'RSI 超卖', cls: 'down' },
    pct_high: { text: '分位偏高', cls: 'up' },
    pct_low: { text: '分位偏低', cls: 'down' },
};

let pollTimer = null;
let settings = {};
let editingId = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function showState(state) {
    const sections = {
        loading: document.getElementById('loading-state'),
        empty: document.getElementById('empty-state'),
        main: document.getElementById('stocks-main'),
    };
    Object.entries(sections).forEach(([key, el]) => {
        if (el) el.style.display = key === state ? '' : 'none';
    });
}

function fmt(value, digits = 2) {
    return Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function signedPct(value) {
    if (!Number.isFinite(value)) return '<span class="muted">—</span>';
    const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
    const sign = value > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${value.toFixed(2)}%</span>`;
}

function codeLink(row) {
    const url = `https://xueqiu.com/S/${escapeHtml(row.symbol.toUpperCase())}`;
    return `<a class="code-link" href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.code)}</a>`;
}

function rsiCell(row) {
    if (!Number.isFinite(row.rsi)) return '<span class="muted">—</span>';
    const breached = (settings.rsi_high != null && row.rsi >= settings.rsi_high)
        || (settings.rsi_low != null && row.rsi <= settings.rsi_low);
    return `<span class="${breached ? 'breach' : 'dim'}">${row.rsi.toFixed(1)}</span>`;
}

function percentileCell(row) {
    if (!Number.isFinite(row.pct_1y)) return '<span class="muted">—</span>';
    const breached = (settings.pct_high != null && row.pct_1y >= settings.pct_high)
        || (settings.pct_low != null && row.pct_1y <= settings.pct_low);
    // Beijing-exchange names fall back to unadjusted bars, so say so rather than mislead.
    const note = row.adjusted === false
        ? '<span class="muted" title="无前复权数据，已用不复权价格代替">*</span>'
        : '';
    return `<span class="${breached ? 'breach' : 'dim'}">${row.pct_1y.toFixed(1)}%</span>${note}`;
}

function formatBeijing(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(date);
}

// ---------------------------------------------------------------------------
// Sparkline (inline SVG, no chart library)
// ---------------------------------------------------------------------------

function sparklineSvg(bars, width = 150, height = 32) {
    const closes = bars.map((b) => b.close).filter((c) => Number.isFinite(c) && c > 0);
    if (closes.length < 2) return '<span class="muted">—</span>';

    // Both series share one scale so the MA sits correctly against the price line.
    const mas = bars.map((b) => b.ma).filter((m) => Number.isFinite(m) && m > 0);
    const min = Math.min(...closes, ...mas);
    const max = Math.max(...closes, ...mas);
    const span = max - min || 1;
    const stepX = width / (bars.length - 1);
    const y = (value) => (height - ((value - min) / span) * height).toFixed(1);

    const pathFor = (accessor) => {
        let d = '';
        let penDown = false;
        bars.forEach((bar, i) => {
            const value = accessor(bar);
            if (!Number.isFinite(value) || value <= 0) {
                penDown = false;
                return;
            }
            d += `${penDown ? 'L' : 'M'}${(i * stepX).toFixed(1)},${y(value)} `;
            penDown = true;
        });
        return d.trim();
    };

    const pricePath = pathFor((b) => b.close);
    const maPath = pathFor((b) => b.ma);

    return `<svg class="sparkline" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">` +
        (maPath ? `<path class="ma-line" d="${maPath}"></path>` : '') +
        `<path class="price-line" d="${pricePath}"></path></svg>`;
}

async function loadSparkline(symbol, cell) {
    try {
        const resp = await fetch(`/api/stocks/kline?symbol=${encodeURIComponent(symbol)}`);
        const data = await resp.json();
        cell.innerHTML = sparklineSvg(data.bars || []);
    } catch (error) {
        cell.innerHTML = '<span class="muted">—</span>';
    }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderStocks(rows) {
    const tbody = document.getElementById('stocks-tbody');
    tbody.innerHTML = '';

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="muted">自选列表为空，点击右上方「＋ 添加股票」添加</td></tr>';
        return;
    }

    rows.forEach((row) => {
        const tr = document.createElement('tr');
        const classes = [];
        if (row.breached.length) classes.push('row-breach');
        if (!row.enabled) classes.push('row-disabled');
        tr.className = classes.join(' ');

        tr.innerHTML = `
            <td>${codeLink(row)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td class="num">${row.valid ? fmt(row.price) : '<span class="muted">停牌/无数据</span>'}</td>
            <td class="num">${signedPct(row.change_pct)}</td>
            <td class="num">${rsiCell(row)}</td>
            <td class="num">${percentileCell(row)}</td>
            <td class="num">${row.volume ? Math.round(row.volume / 100).toLocaleString() : '—'}</td>
            <td class="spark-cell"><span class="muted">…</span></td>
            <td>
                <div class="row-actions">
                    <button class="btn-mini" data-action="edit">重命名</button>
                    <button class="btn-mini" data-action="toggle">${row.enabled ? '停用' : '启用'}</button>
                    <button class="btn-mini" data-action="delete">删除</button>
                </div>
            </td>`;

        tr.querySelector('[data-action="edit"]').addEventListener('click', () => openModal(row));
        tr.querySelector('[data-action="toggle"]').addEventListener('click', () => toggleStock(row));
        tr.querySelector('[data-action="delete"]').addEventListener('click', () => deleteStock(row));
        tbody.appendChild(tr);

        loadSparkline(row.symbol, tr.querySelector('.spark-cell'));
    });
}

function renderAlerts(alerts) {
    const tbody = document.getElementById('alerts-tbody');
    if (!alerts.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="muted">暂无警告记录</td></tr>';
        return;
    }
    tbody.innerHTML = alerts.map((a) => {
        const meta = ALERT_LABELS[a.direction] || { text: a.direction, cls: 'dim' };
        return `<tr>
            <td>${escapeHtml(a.trade_date)}</td>
            <td>${escapeHtml(a.name)} <span class="muted">${escapeHtml(a.code)}</span></td>
            <td class="${meta.cls}">${meta.text}</td>
            <td class="num">${fmt(a.price)}</td>
            <td class="num">${fmt(a.threshold)}</td>
            <td>${escapeHtml(a.triggered_at)}</td>
        </tr>`;
    }).join('');
}

function updateMeta(status) {
    const metaDate = document.getElementById('meta-date');
    const metaStatus = document.getElementById('meta-status');
    const hint = document.getElementById('action-hint');

    const fetched = formatBeijing(status.last_run);
    metaDate.textContent = fetched ? `最近抓取 (北京时间): ${fetched}` : '尚未抓取';

    if (status.is_running) {
        metaStatus.textContent = '抓取中…';
        metaStatus.className = 'meta-status status-running';
    } else if (status.ready) {
        metaStatus.textContent = '就绪';
        metaStatus.className = 'meta-status status-ready';
    } else {
        metaStatus.textContent = '无数据';
        metaStatus.className = 'meta-status status-empty';
    }

    const parts = [];
    if (status.trade_date) parts.push(`行情交易日 ${status.trade_date}`);
    if (!status.is_trading_day && status.trade_date) parts.push('今日非交易日，不触发警告');
    if (status.runs_done && status.runs_done.length) parts.push(`今日已完成时段: ${status.runs_done.join(' / ')}`);
    hint.textContent = parts.join(' · ');
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadAll() {
    try {
        const [listResp, alertsResp] = await Promise.all([
            fetch('/api/stocks/list'),
            fetch('/api/stocks/alerts?limit=50'),
        ]);
        const list = await listResp.json();
        const alerts = await alertsResp.json();

        settings = list.settings || {};
        renderStocks(list.stocks || []);
        renderAlerts(alerts.alerts || []);
        fillSettings(list.settings || {});
        showState('main');
    } catch (error) {
        console.error('loadAll error:', error);
        showState('empty');
    }
}

async function pollStatus() {
    try {
        const status = await (await fetch('/api/stocks/status')).json();
        updateMeta(status);

        const wasRunning = pollTimer && pollTimer.interval === POLL_ACTIVE_MS;
        if (wasRunning && !status.is_running) await loadAll();
        schedulePoll(status.is_running ? POLL_ACTIVE_MS : POLL_IDLE_MS);
    } catch (error) {
        console.error('pollStatus error:', error);
        schedulePoll(POLL_IDLE_MS);
    }
}

function schedulePoll(interval) {
    if (pollTimer) clearTimeout(pollTimer.id);
    pollTimer = { id: setTimeout(pollStatus, interval), interval };
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

function openModal(row) {
    editingId = row ? row.id : null;
    document.getElementById('modal-title').textContent = row ? '重命名' : '添加股票';
    document.getElementById('field-symbol').value = row ? row.code : '';
    document.getElementById('field-symbol').disabled = Boolean(row);
    document.getElementById('field-name').value = row ? row.name : '';
    document.getElementById('modal-error').textContent = '';
    document.getElementById('stock-modal').style.display = '';
}

function closeModal() {
    document.getElementById('stock-modal').style.display = 'none';
    editingId = null;
}

function readNumberField(id) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) return null;
    const num = Number(raw);
    return Number.isFinite(num) ? num : null;
}

async function saveStock() {
    const errorEl = document.getElementById('modal-error');
    const name = document.getElementById('field-name').value.trim();

    let url, payload;
    if (editingId) {
        url = '/api/stocks/update';
        payload = { id: editingId, name };
    } else {
        const symbol = document.getElementById('field-symbol').value.trim().toLowerCase();
        if (!SYMBOL_RE.test(symbol)) {
            errorEl.textContent = '请输入 6 位数字代码，例如 600519（指数需加交易所前缀，如 sh000001）';
            return;
        }
        url = '/api/stocks/add';
        payload = { symbol, name };
    }

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            errorEl.textContent = typeof err.detail === 'string' ? err.detail : '保存失败';
            return;
        }
        closeModal();
        await loadAll();
    } catch (error) {
        errorEl.textContent = '保存失败';
    }
}

async function toggleStock(row) {
    await fetch('/api/stocks/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: row.id, name: row.name, enabled: !row.enabled }),
    });
    await loadAll();
}

const SETTINGS_FIELDS = {
    rsi_high: 'set-rsi-high',
    rsi_low: 'set-rsi-low',
    pct_high: 'set-pct-high',
    pct_low: 'set-pct-low',
};

function fillSettings(values) {
    Object.entries(SETTINGS_FIELDS).forEach(([key, id]) => {
        const input = document.getElementById(id);
        // Don't clobber whatever the user is typing.
        if (input && document.activeElement !== input) input.value = values[key] == null ? '' : values[key];
    });
}

async function saveSettings() {
    const errorEl = document.getElementById('settings-error');
    const payload = {};
    for (const [key, id] of Object.entries(SETTINGS_FIELDS)) {
        const value = readNumberField(id);
        if (value != null && (value < 0 || value > 100)) {
            errorEl.textContent = '阈值需在 0-100 之间';
            return;
        }
        payload[key] = value;
    }

    const resp = await fetch('/api/stocks/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        errorEl.textContent = typeof err.detail === 'string' ? err.detail : '保存失败';
        return;
    }
    errorEl.textContent = '';
    await loadAll();
}

async function deleteStock(row) {
    if (!window.confirm(`确定从自选中删除 ${row.name} (${row.code}) ？`)) return;
    await fetch(`/api/stocks/${row.id}`, { method: 'DELETE' });
    await loadAll();
}

async function onRefreshClicked() {
    const btn = document.getElementById('btn-refresh');
    btn.disabled = true;
    try {
        await fetch('/api/stocks/run', { method: 'POST' });
        await pollStatus();
    } finally {
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
    document.getElementById('btn-refresh').addEventListener('click', onRefreshClicked);
    document.getElementById('btn-add').addEventListener('click', () => openModal(null));
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('modal-save').addEventListener('click', saveStock);
    document.getElementById('stock-modal').addEventListener('click', (e) => {
        if (e.target.id === 'stock-modal') closeModal();
    });
    Object.values(SETTINGS_FIELDS).forEach((id) => {
        document.getElementById(id).addEventListener('change', saveSettings);
    });

    await loadAll();
    await pollStatus();
});
