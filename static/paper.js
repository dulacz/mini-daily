'use strict';

/**
 * paper.js — paper trading account page.
 */

const SYMBOL_RE = /^((sh|sz|bj)\d{6}|\d{6})$/;

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

function codeLink(symbol, code) {
    const url = `https://xueqiu.com/S/${escapeHtml(String(symbol).toUpperCase())}`;
    return `<a class="code-link" href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(code)}</a>`;
}

// A-share lots are 100 shares, so split the last two digits instead of thousands.
function shares(count) {
    const lots = Math.floor(count / 100);
    if (!lots) return String(count);
    return `${lots},${String(count % 100).padStart(2, '0')}`;
}

function money(value, digits = 2) {
    if (!Number.isFinite(value)) return '—';
    return value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
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

function weightCell(pct) {
    const capped = Math.max(0, Math.min(100, pct || 0));
    return `<span class="dim">${(pct || 0).toFixed(1)}%</span>` +
        `<span class="weight-bar"><span style="width:${capped}%"></span></span>`;
}

function driftCell(row) {
    if (!Number.isFinite(row.drift_pct)) return '<span class="muted">—</span>';
    const sign = row.drift_pct > 0 ? '+' : '';
    const cls = row.drift_pct > 0 ? 'up' : row.drift_pct < 0 ? 'down' : 'muted';
    const weight = row.drifted ? ' drifted' : '';
    return `<span class="${cls}${weight}">${sign}${row.drift_pct.toFixed(0)}%</span>`;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderSummary(data) {
    const dash = '<span class="muted">—</span>';
    const ok = data.prices_complete;

    document.getElementById('meta-total').textContent = ok ? `总资产 ${money(data.total_assets)}` : '总资产 —';
    document.getElementById('sum-total').innerHTML = ok ? money(data.total_assets) : dash;
    document.getElementById('sum-market').innerHTML = ok ? money(data.market_value_total) : dash;
    document.getElementById('sum-unrealized').innerHTML = ok ? pnl(data.total_unrealized_pnl) : dash;
    document.getElementById('sum-realized').innerHTML = pnl(data.total_realized_pnl);

    const holdingsWeight = data.total_assets ? data.market_value_total / data.total_assets * 100 : 0;
    document.getElementById('sum-cash-weight').textContent = ok ? `占比 ${data.cash_weight_pct.toFixed(1)}%` : '';
    document.getElementById('sum-market-weight').textContent = ok ? `占比 ${holdingsWeight.toFixed(1)}%` : '';

    const status = document.getElementById('meta-status');
    const drifted = data.positions.filter((p) => p.drifted).length;
    if (!ok) {
        status.textContent = '行情获取失败，市值与权重暂不可用';
        status.className = 'meta-status status-empty';
    } else if (drifted) {
        status.textContent = `${drifted} 项偏离目标`;
        status.className = 'meta-status status-running';
    } else {
        status.textContent = '权重正常';
        status.className = 'meta-status status-ready';
    }
}

function renderPositions(data) {
    const tbody = document.getElementById('positions-tbody');
    if (!data.positions.length) {
        tbody.innerHTML = '<tr><td colspan="13" class="muted">暂无持仓，先在上方下单买入</td></tr>';
        return;
    }

    tbody.innerHTML = '';
    const dash = '<span class="muted">—</span>';
    data.positions.forEach((row) => {
        const tr = document.createElement('tr');
        tr.className = row.drifted ? 'row-drifted' : '';
        tr.innerHTML = `
            <td>${codeLink(row.symbol, row.code)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td class="num">
                <input class="cell-input" type="text" inputmode="numeric" step="100" min="0"
                       value="${money(row.shares, 0)}" data-role="shares" title="上下箭头每次买卖 1 手">
            </td>
            <td class="num">${row.priced ? money(row.price, 3) : dash}</td>
            <td class="num">
                <input class="cell-input" type="number" step="0.001" min="0"
                       value="${row.shares > 0 ? row.avg_cost.toFixed(3) : ''}"
                       data-role="cost" ${row.shares > 0 ? '' : 'disabled'}>
            </td>
            <td class="num">${row.priced ? money(row.market_value) : dash}</td>
            <td class="num">${row.priced ? pnl(row.total_pnl) : dash}</td>
            <td class="num">${row.priced ? pnlPct(row.return_pct) : dash}</td>
            <td class="num">${row.priced ? weightCell(row.weight_pct) : dash}</td>
            <td class="num">
                <input class="cell-input" type="number" step="1" min="0" max="100"
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

const ORDER_LABELS = {
    buy: { text: '买', cls: 'buy' },
    sell: { text: '卖', cls: 'sell' },
};

function renderTotals(data) {
    const tfoot = document.getElementById('positions-tfoot');
    const rows = data.positions;
    const priced = rows.every((r) => r.priced);
    const dash = '<span class="muted">—</span>';

    const costTotal = rows.reduce((sum, r) => sum + r.cost_total, 0);
    const pnlTotal = rows.reduce((sum, r) => sum + (r.priced ? r.total_pnl : 0), 0);
    const weightTotal = rows.reduce((sum, r) => sum + (r.priced ? r.weight_pct : 0), 0);
    const targetTotal = rows.reduce((sum, r) => sum + (r.target_weight || 0), 0);
    // Rebalance normalises targets to 100%, so flag any other sum as unintended.
    const targetOff = rows.some((r) => r.target_weight != null) && Math.abs(targetTotal - 100) > 0.05;

    tfoot.innerHTML = `<tr class="totals-row">
        <td colspan="2">合计 ${rows.length} 只</td>
        <td></td>
        <td></td>
        <td class="num dim">${money(costTotal)}</td>
        <td class="num">${priced ? money(data.market_value_total) : dash}</td>
        <td class="num">${priced ? pnl(pnlTotal) : dash}</td>
        <td class="num">${priced && costTotal ? pnlPct(pnlTotal / costTotal * 100) : dash}</td>
        <td class="num dim">${priced ? `${weightTotal.toFixed(1)}%` : dash}</td>
        <td class="num ${targetOff ? 'breach' : 'dim'}" ${targetOff ? 'title="目标合计不等于 100%，再平衡时会按比例归一化"' : ''}>${targetTotal.toFixed(0)}%</td>
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

function renderRebalanceSummary(plan) {
    const summary = document.getElementById('rebalance-summary');
    const button = document.getElementById('btn-rebalance');

    if (!plan.ready) {
        summary.textContent = plan.reason;
        button.disabled = true;
        return;
    }
    button.disabled = plan.order_count === 0;
    const skipped = plan.skipped.length
        ? ` · 未设目标权重不参与：${plan.skipped.map((s) => s.name).join('、')}`
        : '';
    summary.textContent = plan.order_count
        ? `卖出 ${money(plan.sell_amount)} · 买入 ${money(plan.buy_amount)} · 执行后剩余现金 ${money(plan.cash_after)}${skipped}`
        : `无需调整（低于最小调仓金额 ${money(plan.min_trade_amount, 0)} 的差距不操作）${skipped}`;
}

function renderAlerts(alerts) {
    const tbody = document.getElementById('alerts-tbody');
    if (!alerts.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted">暂无漂移警告</td></tr>';
        return;
    }
    tbody.innerHTML = alerts.map((a) => {
        const isOver = a.direction === 'over';
        return `<tr>
            <td>${escapeHtml(a.trade_date)}</td>
            <td>${escapeHtml(a.name)}</td>
            <td class="${isOver ? 'up' : 'down'}">${isOver ? '超配' : '低配'}</td>
            <td class="num">${a.weight_pct.toFixed(1)}%</td>
            <td class="num">${a.target_pct.toFixed(1)}%</td>
            <td class="num ${isOver ? 'up' : 'down'} drifted">${a.drift_pct > 0 ? '+' : ''}${a.drift_pct.toFixed(0)}%</td>
            <td>${escapeHtml(a.triggered_at)}</td>
        </tr>`;
    }).join('');
}

function fillSettings(data) {
    // Don't clobber whatever the user is typing.
    const active = document.activeElement;
    if (active !== document.getElementById('field-cash')) {
        document.getElementById('field-cash').value = data.cash.toFixed(2);
    }
    if (active !== document.getElementById('field-tolerance')) {
        document.getElementById('field-tolerance').value = data.drift_tolerance_pct;
    }
    if (active !== document.getElementById('field-min-trade')) {
        document.getElementById('field-min-trade').value = data.min_trade_amount;
    }
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

async function loadAll() {
    const [portfolioResp, alertsResp, rebalanceResp] = await Promise.all([
        fetch('/api/paper/portfolio'),
        fetch('/api/paper/alerts?limit=50'),
        fetch('/api/paper/rebalance'),
    ]);
    portfolio = await portfolioResp.json();
    const plan = await rebalanceResp.json();
    rebalanceOrders = Object.fromEntries((plan.orders || []).map((o) => [o.symbol, o]));

    renderSummary(portfolio);
    renderPositions(portfolio);
    renderTotals(portfolio);
    fillSettings(portfolio);
    renderRebalanceSummary(plan);
    renderAlerts((await alertsResp.json()).alerts || []);
}

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

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function submitTrade() {
    const errorEl = document.getElementById('trade-error');
    const btn = document.getElementById('btn-trade');
    const symbol = document.getElementById('trade-symbol').value.trim().toLowerCase();
    const side = document.getElementById('trade-side').value;
    const shares = parseInt(document.getElementById('trade-shares').value, 10);

    if (!SYMBOL_RE.test(symbol)) {
        errorEl.textContent = '请输入 6 位数字代码，例如 600519';
        return;
    }
    if (!Number.isInteger(shares) || shares <= 0) {
        errorEl.textContent = '数量必须是正整数';
        return;
    }

    btn.disabled = true;
    errorEl.textContent = '下单中…';
    try {
        if (await postJson('/api/paper/trade', { symbol, side, shares }, errorEl)) {
            document.getElementById('trade-shares').value = '';
            await loadAll();
        }
    } finally {
        btn.disabled = false;
    }
}

async function saveCash() {
    const errorEl = document.getElementById('settings-error');
    const cash = Number(document.getElementById('field-cash').value);
    if (!Number.isFinite(cash) || cash < 0) {
        errorEl.textContent = '现金必须是非负数';
        return;
    }
    if (await postJson('/api/paper/cash', { cash }, errorEl)) await loadAll();
}

async function saveSettings() {
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
    if (await postJson('/api/paper/settings', { drift_tolerance_pct: tolerance, min_trade_amount: minTrade }, errorEl)) {
        await loadAll();
    }
}

async function saveTarget(symbol, rawValue) {
    const value = rawValue.trim() === '' ? null : Number(rawValue);
    await postJson('/api/paper/target', { symbol, target_weight: value }, null);
    await loadAll();
}

// A zero-weight target is how a symbol enters the table without buying anything yet.
async function addSymbol() {
    const errorEl = document.getElementById('trade-error');
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
    const errorEl = document.getElementById('trade-error');
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
    const errorEl = document.getElementById('trade-error');
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
        document.getElementById('trade-error'),
    );
    await loadAll();
}

async function runRebalance() {
    const button = document.getElementById('btn-rebalance');
    const plan = await (await fetch('/api/paper/rebalance')).json();
    if (!plan.ready || !plan.order_count) return;

    const lines = plan.orders
        .filter((o) => o.side !== 'hold')
        .map((o) => `${o.side === 'buy' ? '买入' : '卖出'} ${o.name} ${shares(o.order_shares)} 股  ${money(o.order_amount)}`)
        .join('\n');
    if (!window.confirm(`确定执行以下 ${plan.order_count} 笔交易？\n\n${lines}`)) return;

    button.disabled = true;
    try {
        const resp = await fetch('/api/paper/rebalance/execute', { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            window.alert(typeof err.detail === 'string' ? err.detail : '执行失败');
        }
        await loadAll();
    } finally {
        button.disabled = false;
    }
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
    document.getElementById('btn-trade').addEventListener('click', submitTrade);
    document.getElementById('btn-refresh').addEventListener('click', loadAll);
    document.getElementById('btn-rebalance').addEventListener('click', runRebalance);
    document.getElementById('field-cash').addEventListener('change', saveCash);
    document.getElementById('field-tolerance').addEventListener('change', saveSettings);
    document.getElementById('field-min-trade').addEventListener('change', saveSettings);

    await loadAll();
});
