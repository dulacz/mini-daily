'use strict';

/**
 * stocks.js — A-share monitor and paper portfolio on one page.
 */

const POLL_ACTIVE_MS = 10_000;
const POLL_IDLE_MS = 300_000;
// While the page is open, refetch quotes on the same cadence as the idle poll.
const AUTO_RUN_MS = 300_000;
const SYMBOL_RE = /^((sh|sz|bj)\d{6}|\d{6})$/;

const ALERT_LABELS = {
    up: { text: '涨破上限', cls: 'up' },
    down: { text: '跌破下限', cls: 'down' },
    rsi_high: { text: 'RSI 超买', cls: 'up' },
    rsi_low: { text: 'RSI 超卖', cls: 'down' },
    pct_high: { text: '分位偏高', cls: 'up' },
    pct_low: { text: '分位偏低', cls: 'down' },
};

const ORDER_LABELS = {
    buy: { text: '买', cls: 'buy' },
    sell: { text: '卖', cls: 'sell' },
};

let pollTimer = null;
let lastStatus = null;
let settings = {};
let editingId = null;
let portfolio = null;
let rebalanceOrders = {};

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

function money(value, digits = 2) {
    if (!Number.isFinite(value)) return '—';
    return value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// A-share lots are 100 shares, so split the last two digits instead of thousands.
function shares(count) {
    const lots = Math.floor(count / 100);
    if (!lots) return String(count);
    return `${lots},${String(count % 100).padStart(2, '0')}`;
}

// Number inputs refuse to display thousands separators, so show grouped text until the field is focused.
function bindGroupedNumber(input, rawValue) {
    input.addEventListener('focus', () => {
        input.value = '';  // a grouped value would be rejected by the number type
        input.type = 'number';
        input.value = rawValue;
    });
    input.addEventListener('blur', () => {
        const current = Number(input.value);
        input.type = 'text';
        input.value = Number.isFinite(current) ? money(current, 0) : money(rawValue, 0);
    });
}

function signedPct(value) {
    if (!Number.isFinite(value)) return '<span class="muted">—</span>';
    const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
    const sign = value > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${value.toFixed(2)}%</span>`;
}

function pnl(value) {
    if (!Number.isFinite(value)) return '<span class="muted">—</span>';
    const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
    const sign = value > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${money(value)}</span>`;
}

function pnlPct(value) {
    if (!Number.isFinite(value)) return '<span class="muted">—</span>';
    const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
    const sign = value > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${value.toFixed(2)}%</span>`;
}

function codeLink(symbol, code) {
    const url = `https://xueqiu.com/S/${escapeHtml(String(symbol).toUpperCase())}`;
    return `<a class="code-link" href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(code)}</a>`;
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

// Payout inferred from adjusted-vs-raw drift, so it only means anything for distributing funds.
const MIN_SHOWN_YIELD_PCT = 0.5;

function dividendCell(row) {
    if (!Number.isFinite(row.div_yield) || row.div_yield < MIN_SHOWN_YIELD_PCT) {
        return '<span class="muted" title="近一年无可观分红">—</span>';
    }
    const rank = Number.isFinite(row.div_yield_pct)
        ? ` <span class="dim" title="该分红率在自身历史中的分位，越高越便宜">${row.div_yield_pct.toFixed(0)}%</span>`
        : '';
    return `<span>${row.div_yield.toFixed(2)}%</span>${rank}`;
}

// Intraday this compares a partial session against a full one, so it reads light until the close.
const VOLUME_FLAT_BAND_PCT = 10;

function volumeCell(row) {
    const lots = row.volume ? Math.round(row.volume / 100).toLocaleString() : '—';
    if (!Number.isFinite(row.volume_ratio)) return lots;

    const delta = (row.volume_ratio - 1) * 100;
    const title = `较上一交易日 ${delta > 0 ? '+' : ''}${delta.toFixed(0)}%（盘中为累计量）`;
    if (Math.abs(delta) < VOLUME_FLAT_BAND_PCT) return `<span title="${title}">${lots}</span>`;
    return `<span title="${title}">${lots} <span class="dim">${delta > 0 ? '▲' : '▼'}</span></span>`;
}

function weightCell(pct) {
    return `<span class="dim">${(pct || 0).toFixed(1)}%</span>`;
}

// Today's P&L on the shares currently held.
function dayPnlCell(row) {
    if (!Number.isFinite(row.day_pnl)) return '<span class="muted">—</span>';
    return pnl(row.day_pnl);
}

function returnTitle(pct) {
    return Number.isFinite(pct) ? ` title="收益率 ${pct > 0 ? '+' : ''}${pct.toFixed(2)}%"` : '';
}

function driftCell(row) {
    if (!Number.isFinite(row.drift_pct)) return '<span class="muted">—</span>';
    const sign = row.drift_pct > 0 ? '+' : '';
    if (!row.drifted) return `<span class="dim">${sign}${row.drift_pct.toFixed(0)}%</span>`;
    const cls = row.drift_pct > 0 ? 'up' : 'down';
    return `<span class="${cls} drifted">${sign}${row.drift_pct.toFixed(0)}%</span>`;
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
// Watchlist rendering
// ---------------------------------------------------------------------------

function renderStocks(rows) {
    const tbody = document.getElementById('stocks-tbody');
    tbody.innerHTML = '';

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="10" class="muted">自选列表为空，点击右上方「＋ 添加股票」添加</td></tr>';
        return;
    }

    rows.forEach((row) => {
        const tr = document.createElement('tr');
        const classes = [];
        if (row.breached.some((d) => d.endsWith('_high'))) classes.push('row-up');
        else if (row.breached.some((d) => d.endsWith('_low'))) classes.push('row-down');
        if (!row.enabled) classes.push('row-disabled');
        tr.className = classes.join(' ');

        tr.innerHTML = `
            <td>${codeLink(row.symbol, row.code)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td class="num">${row.valid ? fmt(row.price) : '<span class="muted">停牌/无数据</span>'}</td>
            <td class="num">${signedPct(row.change_pct)}</td>
            <td class="num">${rsiCell(row)}</td>
            <td class="num">${percentileCell(row)}</td>
            <td class="num">${dividendCell(row)}</td>
            <td class="num">${volumeCell(row)}</td>
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

// ---------------------------------------------------------------------------
// Portfolio rendering
// ---------------------------------------------------------------------------

function renderSummary(data) {
    const dash = '<span class="muted">—</span>';
    const ok = data.prices_complete;

    document.getElementById('sum-market').innerHTML = ok ? money(data.market_value_total) : dash;
    document.getElementById('sum-day').innerHTML = ok ? pnl(data.total_day_pnl) : dash;
    document.getElementById('sum-unrealized').innerHTML = ok ? pnl(data.total_unrealized_pnl) : dash;
    document.getElementById('sum-cash').innerHTML = money(data.cash);
    document.getElementById('sum-total').innerHTML = ok ? money(data.total_assets) : dash;

    const holdingsWeight = data.total_assets ? data.market_value_total / data.total_assets * 100 : 0;
    document.getElementById('sum-cash-weight').textContent = ok ? `占比 ${data.cash_weight_pct.toFixed(1)}%` : '';
    document.getElementById('sum-market-weight').textContent = ok ? `占比 ${holdingsWeight.toFixed(1)}%` : '';

    const pct = Number.isFinite(data.total_return_pct)
        ? ` ${data.total_return_pct > 0 ? '+' : ''}${data.total_return_pct.toFixed(2)}%`
        : '';
    document.getElementById('sum-return').innerHTML = ok ? `${pnl(data.total_return)}${pct}` : '';
}

function renderPositions(data) {
    const tbody = document.getElementById('positions-tbody');
    if (!data.positions.length) {
        tbody.innerHTML = '<tr><td colspan="14" class="muted">暂无持仓，点击下方「＋」新增代码</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    const dash = '<span class="muted">—</span>';
    data.positions.forEach((row) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${codeLink(row.symbol, row.code)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td class="num">
                <input class="cell-input" type="text" inputmode="numeric" step="100" min="0"
                       value="${money(row.shares, 0)}" data-role="shares" title="上下箭头每次买卖 1 手">
            </td>
            <td class="num">
                <input class="cell-input w-cost" type="number" step="0.001" min="0"
                       value="${row.shares > 0 ? row.avg_cost.toFixed(3) : ''}"
                       data-role="cost" ${row.shares > 0 ? '' : 'disabled'}>
            </td>
            <td class="num">${row.priced ? money(row.price, 3) : dash}</td>
            <td class="num">${row.priced ? money(row.market_value) : dash}</td>
            <td class="num">${dayPnlCell(row)}</td>
            <td class="num">${pnlPct(row.day_change_pct)}</td>
            <td class="num"${returnTitle(row.return_pct)}>${row.priced ? pnl(row.unrealized_pnl) : dash}</td>
            <td class="num">${row.priced ? weightCell(row.weight_pct) : dash}</td>
            <td class="num">
                <input class="cell-input w-target" type="number" step="1" min="0" max="100"
                       value="${row.target_weight == null ? '' : row.target_weight}" data-role="target">
            </td>
            <td class="num">${row.priced ? driftCell(row) : dash}</td>
            <td>${rebalanceCell(row.symbol)}</td>
            <td>
                <div class="row-actions">
                    <button class="btn-mini btn-icon" data-action="delete" title="移除" aria-label="移除"
                            ${row.shares > 0 ? 'disabled' : ''}>−</button>
                </div>
            </td>`;

        const target = tr.querySelector('[data-role="target"]');
        target.addEventListener('change', () => saveTarget(row.symbol, target.value));
        const sharesInput = tr.querySelector('[data-role="shares"]');
        bindGroupedNumber(sharesInput, row.shares);
        sharesInput.addEventListener('change', () => saveShares(row.symbol, sharesInput.value));
        const cost = tr.querySelector('[data-role="cost"]');
        cost.addEventListener('change', () => saveCost(row.symbol, cost.value));
        const rebalance = tr.querySelector('[data-action="rebalance"]');
        if (rebalance) rebalance.addEventListener('click', () => runSingleOrder(row.symbol));
        tr.querySelector('[data-action="delete"]').addEventListener('click', () => removePosition(row.symbol, row.code));
        tbody.appendChild(tr);
    });
}

function renderTotals(data) {
    const tfoot = document.getElementById('positions-tfoot');
    const rows = data.positions;
    const priced = rows.every((r) => r.priced);
    const dash = '<span class="muted">—</span>';

    const costTotal = rows.reduce((sum, r) => sum + r.cost_total, 0);
    const pnlTotal = rows.reduce((sum, r) => sum + (r.priced ? r.unrealized_pnl : 0), 0);
    const dayPriced = rows.some((r) => Number.isFinite(r.day_pnl));
    // Yesterday's value of today's holdings, which is what the day's move is measured against.
    const prevValue = data.market_value_total - data.total_day_pnl;
    const weightTotal = rows.reduce((sum, r) => sum + (r.priced ? r.weight_pct : 0), 0);
    const targetTotal = rows.reduce((sum, r) => sum + (r.target_weight || 0), 0);
    // Rebalance normalises targets to 100%, so flag any other sum as unintended.
    const targetOff = rows.some((r) => r.target_weight != null) && Math.abs(targetTotal - 100) > 0.05;
    const targetCls = targetOff ? 'breach' : 'dim';

    tfoot.innerHTML = `<tr class="totals-row">
        <td colspan="2">合计 ${rows.length} 只</td>
        <td></td>
        <td class="num dim">${money(costTotal)}</td>
        <td></td>
        <td class="num">${priced ? money(data.market_value_total) : dash}</td>
        <td class="num">${dayPriced ? pnl(data.total_day_pnl) : dash}</td>
        <td class="num">${dayPriced && prevValue ? pnlPct(data.total_day_pnl / prevValue * 100) : dash}</td>
        <td class="num"${returnTitle(costTotal ? pnlTotal / costTotal * 100 : null)}>${priced ? pnl(pnlTotal) : dash}</td>
        <td class="num dim">${priced ? `${weightTotal.toFixed(1)}%` : dash}</td>
        <td class="num ${targetCls}" ${targetOff ? 'title="目标合计不等于 100%，再平衡时会按比例归一化"' : ''}>${targetTotal.toFixed(0)}%</td>
        <td></td>
        <td></td>
        <td>
            <button class="btn-mini btn-icon" id="btn-add-symbol" title="新增代码" aria-label="新增代码">+</button>
        </td>
    </tr>`;

    document.getElementById('btn-add-symbol').addEventListener('click', addSymbol);
}

function rebalanceCell(symbol) {
    const order = rebalanceOrders[symbol];
    if (!order || order.side === 'hold') return '<span class="muted">—</span>';
    const meta = ORDER_LABELS[order.side];
    return `<button class="btn-mini btn-order ${meta.cls}" data-action="rebalance"` +
        ` title="${money(order.order_amount)} 元，执行后占比 ${order.projected_weight_pct.toFixed(1)}%">` +
        `${meta.text} ${shares(order.order_shares)}</button>`;
}

// Only surfaces why a plan could not be built; the per-row buttons already show the orders.
function renderRebalanceSummary(plan) {
    document.getElementById('rebalance-summary').textContent = plan.ready ? '' : plan.reason;
}

// ---------------------------------------------------------------------------
// Combined alert history
// ---------------------------------------------------------------------------

// Trading days the condition has stayed breached, with the covered date range as a tooltip.
function durationCell(a) {
    const days = a.days || 1;
    const range = a.last_date && a.last_date !== a.trade_date
        ? `${a.trade_date} → ${a.last_date}`
        : a.trade_date;
    return `<td class="num" title="${escapeHtml(range)}">${days} 天</td>`;
}

function alertRow(a) {
    if (a.kind === 'drift') {
        const isOver = a.direction === 'over';
        const cls = isOver ? 'up' : 'down';
        const sign = a.drift_pct > 0 ? '+' : '';
        return `<tr>
            <td>${escapeHtml(a.trade_date)}</td>
            <td>${escapeHtml(a.name)}</td>
            <td class="${cls}">${isOver ? '超配' : '低配'} <span class="drifted">${sign}${a.drift_pct.toFixed(0)}%</span></td>
            <td class="num">${a.weight_pct.toFixed(1)}%</td>
            <td class="num">${a.target_pct.toFixed(1)}%</td>
            ${durationCell(a)}
            <td>${escapeHtml(a.triggered_at)}</td>
        </tr>`;
    }
    const meta = ALERT_LABELS[a.direction] || { text: a.direction, cls: 'dim' };
    return `<tr>
        <td>${escapeHtml(a.trade_date)}</td>
        <td>${escapeHtml(a.name)} <span class="muted">${escapeHtml(a.code)}</span></td>
        <td class="${meta.cls}">${meta.text}</td>
        <td class="num">${fmt(a.price, 1)}</td>
        <td class="num">${fmt(a.threshold, 1)}</td>
        ${durationCell(a)}
        <td>${escapeHtml(a.triggered_at)}</td>
    </tr>`;
}

function renderAlerts(priceAlerts, driftAlerts) {
    const tbody = document.getElementById('alerts-tbody');
    const merged = [
        ...priceAlerts.map((a) => ({ ...a, kind: 'price' })),
        ...driftAlerts.map((a) => ({ ...a, kind: 'drift' })),
    ].sort((a, b) => `${b.trade_date}${b.triggered_at}`.localeCompare(`${a.trade_date}${a.triggered_at}`));

    tbody.innerHTML = merged.length
        ? merged.map(alertRow).join('')
        : '<tr><td colspan="7" class="muted">暂无警告记录</td></tr>';
}

// ---------------------------------------------------------------------------
// Header meta
// ---------------------------------------------------------------------------

function updateMeta(status) {
    if (status) lastStatus = status;
    status = lastStatus;
    if (!status) return;
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
    if (portfolio) {
        const drifted = portfolio.positions.filter((p) => p.drifted).length;
        if (!portfolio.drift_enabled) parts.push('漂移监测已关闭');
        else parts.push(drifted ? `${drifted} 项偏离目标` : '权重正常');
    }
    hint.textContent = parts.join(' · ');
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

const SETTINGS_FIELDS = {
    rsi_high: 'set-rsi-high',
    rsi_low: 'set-rsi-low',
    pct_high: 'set-pct-high',
    pct_low: 'set-pct-low',
};

function readNumberField(id) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) return null;
    const num = Number(raw);
    return Number.isFinite(num) ? num : null;
}

function fillSettings(alertValues, account) {
    const active = document.activeElement;
    // Don't clobber whatever the user is typing.
    const setValue = (id, value) => {
        const input = document.getElementById(id);
        if (input && active !== input) input.value = value;
    };
    Object.entries(SETTINGS_FIELDS).forEach(([key, id]) => {
        setValue(id, alertValues[key] == null ? '' : alertValues[key]);
    });
    if (account) {
        setValue('field-tolerance', account.drift_tolerance_pct);
        setValue('field-min-trade', account.min_trade_amount);
        const toggle = document.getElementById('field-drift-enabled');
        if (toggle !== active) toggle.checked = account.drift_enabled;
        document.getElementById('field-tolerance').disabled = !account.drift_enabled;
    }
}

async function saveAlertSettings() {
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
    if (await postJson('/api/stocks/settings', payload, errorEl)) await loadAll();
}

async function savePaperSettings() {
    const errorEl = document.getElementById('settings-error');
    const tolerance = Number(document.getElementById('field-tolerance').value);
    const minTrade = Number(document.getElementById('field-min-trade').value);
    if (!Number.isFinite(tolerance) || tolerance <= 0) {
        errorEl.textContent = '漂移容差必须大于 0';
        return;
    }
    if (!Number.isFinite(minTrade) || minTrade < 0) {
        errorEl.textContent = '最小调仓金额不能为负数';
        return;
    }
    const payload = {
        drift_tolerance_pct: tolerance,
        min_trade_amount: minTrade,
        drift_enabled: document.getElementById('field-drift-enabled').checked,
    };
    if (await postJson('/api/paper/settings', payload, errorEl)) await loadAll();
}

function openAccountModal() {
    document.getElementById('field-cash').value = portfolio ? portfolio.cash.toFixed(2) : '';
    document.getElementById('field-return').value = portfolio ? portfolio.total_return.toFixed(2) : '';
    document.getElementById('account-modal-error').textContent = '';
    document.getElementById('account-modal').style.display = '';
}

function closeAccountModal() {
    document.getElementById('account-modal').style.display = 'none';
}

async function saveAccount() {
    const errorEl = document.getElementById('account-modal-error');
    const cash = Number(document.getElementById('field-cash').value);
    const wantedReturn = Number(document.getElementById('field-return').value);
    if (!Number.isFinite(cash) || cash < 0) {
        errorEl.textContent = '现金必须是非负数';
        return;
    }
    if (!Number.isFinite(wantedReturn)) {
        errorEl.textContent = '累计收益必须是数字';
        return;
    }

    if (!await postJson('/api/paper/cash', { cash }, errorEl)) return;
    // Cash moved the asset total, so the deposit baseline is derived from the new one.
    const account = await (await fetch('/api/paper/portfolio')).json();
    const payload = { net_deposit: Number((account.total_assets - wantedReturn).toFixed(2)) };
    if (!await postJson('/api/paper/net-deposit', payload, errorEl)) return;

    closeAccountModal();
    await loadAll();
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function postJson(url, payload, errorEl) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        if (errorEl) errorEl.textContent = typeof err.detail === 'string' ? err.detail : '操作失败';
        return false;
    }
    if (errorEl) errorEl.textContent = '';
    return true;
}

async function loadMarketNote() {
    try {
        const note = await (await fetch('/api/stocks/market-note')).json();
        // Remote copy, so it goes in as text and never as markup.
        document.getElementById('satori-note').textContent = note.title || '';
    } catch (error) {
        console.error('loadMarketNote error:', error);
    }
}

async function loadAll() {
    try {
        const responses = await Promise.all([
            fetch('/api/stocks/list'),
            fetch('/api/stocks/alerts?limit=50'),
            fetch('/api/paper/portfolio'),
            fetch('/api/paper/rebalance'),
            fetch('/api/paper/alerts?limit=50'),
        ]);
        const [list, priceAlerts, account, plan, driftAlerts] =
            await Promise.all(responses.map((r) => r.json()));

        settings = list.settings || {};
        portfolio = account;
        rebalanceOrders = Object.fromEntries((plan.orders || []).map((o) => [o.symbol, o]));

        renderStocks(list.stocks || []);
        renderSummary(account);
        renderPositions(account);
        renderTotals(account);
        renderRebalanceSummary(plan);
        // Past drift records stay in the database, they just stop being shown once the
        // switch is off — otherwise the history contradicts the greyed-out drift column.
        renderAlerts(priceAlerts.alerts || [], account.drift_enabled ? (driftAlerts.alerts || []) : []);
        fillSettings(settings, account);
        updateMeta();  // the hint line mixes job status with portfolio state
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

// Keeping the page open acts as a subscription: fetch quotes on a timer instead of
// waiting for the 14:30 / 15:05 slots. Hidden tabs stay quiet.
function startAutoRun() {
    setInterval(async () => {
        if (document.visibilityState !== 'visible') return;
        await fetch('/api/stocks/run', { method: 'POST' });
        await pollStatus();
    }, AUTO_RUN_MS);
}

// ---------------------------------------------------------------------------
// Watchlist mutations
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

    if (await postJson(url, payload, errorEl)) {
        closeModal();
        await loadAll();
    }
}

async function toggleStock(row) {
    await postJson('/api/stocks/update', { id: row.id, name: row.name, enabled: !row.enabled }, null);
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

async function testToast() {
    const btn = document.getElementById('btn-test-toast');
    const errorEl = document.getElementById('settings-error');
    btn.disabled = true;
    try {
        const result = await (await fetch('/api/stocks/test-toast', { method: 'POST' })).json();
        if (!result.sent) {
            errorEl.textContent = '发送失败，请查看服务端日志';
        } else {
            errorEl.textContent = result.count
                ? `已发送 ${result.count} 条提醒并记入历史`
                : '当前没有任何越界、漂移或调仓建议';
        }
        await loadAll();
    } finally {
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Portfolio mutations
// ---------------------------------------------------------------------------

async function saveTarget(symbol, rawValue) {
    const value = rawValue.trim() === '' ? null : Number(rawValue);
    await postJson('/api/paper/target', { symbol, target_weight: value }, document.getElementById('positions-error'));
    await loadAll();
}

// A zero-weight target is how a symbol enters the table without buying anything yet.
async function addSymbol() {
    const errorEl = document.getElementById('positions-error');
    const raw = window.prompt('新增代码（如 510300 或 sh510300）');
    if (raw === null) return;
    const symbol = raw.trim().toLowerCase();
    if (!SYMBOL_RE.test(symbol)) {
        errorEl.textContent = '代码格式不对，应为 6 位数字或 sh/sz/bj + 6 位数字';
        return;
    }
    if (portfolio.positions.some((p) => p.symbol === symbol || p.code === symbol)) {
        errorEl.textContent = '该代码已在持仓列表中';
        return;
    }
    errorEl.textContent = '';
    await postJson('/api/paper/target', { symbol, target_weight: 0 }, errorEl);
    await loadAll();
}

async function saveShares(symbol, rawValue) {
    const errorEl = document.getElementById('positions-error');
    const value = parseInt(String(rawValue).replace(/,/g, ''), 10);
    if (!Number.isInteger(value) || value < 0) {
        errorEl.textContent = '数量必须是非负整数';
        await loadAll();
        return;
    }
    await postJson('/api/paper/shares', { symbol, shares: value }, errorEl);
    await loadAll();
}

async function saveCost(symbol, rawValue) {
    const errorEl = document.getElementById('positions-error');
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value < 0) {
        errorEl.textContent = '成本价必须是非负数';
        await loadAll();
        return;
    }
    await postJson('/api/paper/cost', { symbol, avg_cost: value }, errorEl);
    await loadAll();
}

async function runSingleOrder(symbol) {
    const order = rebalanceOrders[symbol];
    if (!order || order.side === 'hold') return;
    await postJson(
        '/api/paper/trade',
        { symbol, side: order.side, shares: order.order_shares },
        document.getElementById('positions-error'),
    );
    await loadAll();
}

async function removePosition(symbol, code) {
    if (!window.confirm(`确定移除 ${code} 的记录？`)) return;
    await fetch(`/api/paper/position/${symbol}`, { method: 'DELETE' });
    await loadAll();
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
        document.getElementById(id).addEventListener('change', saveAlertSettings);
    });
    document.getElementById('field-tolerance').addEventListener('change', savePaperSettings);
    document.getElementById('field-drift-enabled').addEventListener('change', savePaperSettings);
    document.getElementById('field-min-trade').addEventListener('change', savePaperSettings);
    document.getElementById('btn-edit-account').addEventListener('click', openAccountModal);
    document.getElementById('account-modal-cancel').addEventListener('click', closeAccountModal);
    document.getElementById('account-modal-save').addEventListener('click', saveAccount);
    document.getElementById('account-modal').addEventListener('click', (e) => {
        if (e.target.id === 'account-modal') closeAccountModal();
    });
    document.getElementById('btn-test-toast').addEventListener('click', testToast);

    await loadAll();
    await pollStatus();
    startAutoRun();
    loadMarketNote();
});
