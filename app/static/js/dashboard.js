/**
 * MikroTik NOC — Dashboard Frontend Logic
 *
 * Handles:
 * - Auto-refresh of KPI cards and tables via fetch()
 * - Chart.js chart initialization and updates
 * - Countdown timer for next refresh
 * - Smooth value transitions and flash animations
 */

// ═══════════════════════════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════════════════════════

const REFRESH_INTERVAL = 10_000; // ms — fetch new data
const API = {
    status: '/api/status',
    traffic24h: '/api/traffic/24h',
    traffic7d: '/api/traffic/7d',
    trafficDaily: '/api/traffic/daily',
    cpuHistory: '/api/cpu/history',
    ramHistory: '/api/ram/history',
    usersHistory: '/api/users/history',
    usersUnified: '/api/users/unified',
    vpnSummary: '/api/vpn/summary',
    topConsumers: '/api/top-consumers',
    interfaces: '/api/interfaces',
    alerts: '/api/alerts',
    outages: '/api/outages',
};

// ═══════════════════════════════════════════════════════════════
// Chart.js Global Config
// ═══════════════════════════════════════════════════════════════

Chart.defaults.color = '#71717a';
Chart.defaults.borderColor = 'rgba(255,255,255,0.04)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#1e1e24';
Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.1)';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.titleColor = '#f4f4f5';
Chart.defaults.plugins.tooltip.bodyColor = '#a1a1aa';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.displayColors = true;
Chart.defaults.plugins.tooltip.boxPadding = 4;

// ═══════════════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════════════

function formatBps(bps) {
    if (bps == null || bps < 0) return '0 bps';
    const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
    let idx = 0;
    let val = bps;
    while (val >= 1000 && idx < units.length - 1) { val /= 1000; idx++; }
    return idx === 0 ? `${Math.round(val)} ${units[idx]}` : `${val.toFixed(2)} ${units[idx]}`;
}

function formatBytes(bytes) {
    if (bytes == null || bytes < 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let idx = 0;
    let val = bytes;
    while (val >= 1024 && idx < units.length - 1) { val /= 1024; idx++; }
    return idx === 0 ? `${Math.round(val)} ${units[idx]}` : `${val.toFixed(2)} ${units[idx]}`;
}

function formatTime(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr + 'Z');
    return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr + 'Z');
    return d.toLocaleString('es-AR', {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

function timeAgo(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr + 'Z');
    const seconds = Math.floor((Date.now() - d.getTime()) / 1000);
    if (seconds < 5) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return `${Math.floor(seconds / 3600)}h ago`;
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '—';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const parts = [];
    if (d) parts.push(`${d}d`);
    if (h) parts.push(`${h}h`);
    if (m) parts.push(`${m}m`);
    if (!parts.length) parts.push(`${seconds}s`);
    return parts.join(' ');
}

function flashElement(el) {
    el.classList.remove('value-updated');
    void el.offsetWidth; // trigger reflow
    el.classList.add('value-updated');
}

async function fetchJSON(url) {
    try {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (err) {
        console.warn(`Fetch failed: ${url}`, err);
        return null;
    }
}

// ═══════════════════════════════════════════════════════════════
// KPI Card Updates
// ═══════════════════════════════════════════════════════════════

let prevStatus = null;

async function updateStatus() {
    const data = await fetchJSON(API.status);
    if (!data || data.error) {
        document.getElementById('status-dot').className = 'status-dot offline';
        document.getElementById('status-label').textContent = 'Offline';
        return;
    }

    // Status dot
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    dot.className = `status-dot ${data.is_online ? 'online' : 'offline'}`;
    label.textContent = data.is_online ? 'Online' : 'Offline';

    // Router meta
    if (data.router) {
        const r = data.router;
        document.getElementById('router-identity').textContent = r.identity || r.name || '—';
        const metaParts = [r.board, r.version, r.architecture].filter(Boolean);
        document.getElementById('router-meta').textContent = metaParts.join(' • ') || '—';
    }

    // KPI values
    const updates = {
        'val-clients': data.clients_total ?? '—',
        'val-download': data.rx_fmt || '—',
        'val-upload': data.tx_fmt || '—',
        'val-uptime': data.uptime || '—',
    };

    for (const [id, value] of Object.entries(updates)) {
        const el = document.getElementById(id);
        if (el && el.textContent !== String(value)) {
            el.textContent = value;
            flashElement(el);
        }
    }

    // CPU
    const cpuEl = document.getElementById('val-cpu');
    const cpuVal = data.cpu_load ?? 0;
    cpuEl.innerHTML = `${cpuVal}<span class="kpi-unit">%</span>`;

    // RAM
    const ramEl = document.getElementById('val-ram');
    const ramVal = data.ram_percent ?? 0;
    ramEl.innerHTML = `${ramVal}<span class="kpi-unit">%</span>`;

    // Router status badge
    const routerBadge = document.getElementById('val-router-status');
    if (data.is_online) {
        routerBadge.className = 'badge-status online';
        routerBadge.innerHTML = '<span class="status-dot online" style="width:7px;height:7px"></span> Online';
    } else {
        routerBadge.className = 'badge-status offline';
        routerBadge.innerHTML = '<span class="status-dot offline" style="width:7px;height:7px"></span> Offline';
    }

    // ISP status badge
    const ispBadge = document.getElementById('val-isp-status');
    if (data.wan_status === 'up') {
        ispBadge.className = 'badge-status online';
        ispBadge.innerHTML = '<span class="status-dot online" style="width:7px;height:7px"></span> Connected';
    } else if (data.wan_status === 'down') {
        ispBadge.className = 'badge-status offline';
        ispBadge.innerHTML = '<span class="status-dot offline" style="width:7px;height:7px"></span> Down';
    } else {
        ispBadge.className = 'badge-status warning';
        ispBadge.innerHTML = `<i class="bi bi-question-circle"></i> ${data.wan_status || 'Unknown'}`;
    }

    // Last update
    document.getElementById('last-update').textContent = timeAgo(data.last_update);

    prevStatus = data;
}

// ═══════════════════════════════════════════════════════════════
// Chart Instances
// ═══════════════════════════════════════════════════════════════

const charts = {};

function createTrafficChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Download',
                    data: [],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.08)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHitRadius: 10,
                },
                {
                    label: 'Upload',
                    data: [],
                    borderColor: '#22d3ee',
                    backgroundColor: 'rgba(34, 211, 238, 0.08)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHitRadius: 10,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 8, maxRotation: 0 },
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (v) => formatBps(v),
                        maxTicksLimit: 5,
                    },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${formatBps(ctx.raw)}`,
                    },
                },
            },
        },
    });
}

function createSingleLineChart(canvasId, color, unit = '%', dangerZone = null) {
    const ctx = document.getElementById(canvasId).getContext('2d');

    const plugins = [];
    if (dangerZone !== null) {
        plugins.push({
            id: 'dangerZone',
            beforeDraw(chart) {
                const { ctx, chartArea, scales } = chart;
                const yPos = scales.y.getPixelForValue(dangerZone);
                if (yPos < chartArea.top) return;
                ctx.save();
                ctx.fillStyle = 'rgba(244, 63, 94, 0.06)';
                ctx.fillRect(chartArea.left, chartArea.top, chartArea.width, yPos - chartArea.top);
                ctx.strokeStyle = 'rgba(244, 63, 94, 0.3)';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.moveTo(chartArea.left, yPos);
                ctx.lineTo(chartArea.right, yPos);
                ctx.stroke();
                ctx.restore();
            },
        });
    }

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                data: [],
                borderColor: color,
                backgroundColor: color.replace(')', ', 0.08)').replace('rgb', 'rgba'),
                fill: true,
                tension: 0.35,
                borderWidth: 2,
                pointRadius: 0,
                pointHitRadius: 10,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 8, maxRotation: 0 },
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    max: unit === '%' ? 100 : undefined,
                    ticks: {
                        callback: (v) => `${v}${unit}`,
                        maxTicksLimit: 5,
                    },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.raw}${unit}`,
                    },
                },
            },
        },
        plugins,
    });
}

function createDailyChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Download',
                    data: [],
                    backgroundColor: 'rgba(99, 102, 241, 0.7)',
                    borderRadius: 4,
                    borderSkipped: false,
                },
                {
                    label: 'Upload',
                    data: [],
                    backgroundColor: 'rgba(34, 211, 238, 0.7)',
                    borderRadius: 4,
                    borderSkipped: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    ticks: { maxRotation: 0, maxTicksLimit: 10 },
                    grid: { display: false },
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (v) => formatBytes(v),
                        maxTicksLimit: 5,
                    },
                },
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${formatBytes(ctx.raw)}`,
                    },
                },
            },
        },
    });
}

function initCharts() {
    charts.traffic24h = createTrafficChart('chart-traffic-24h');
    charts.traffic7d = createTrafficChart('chart-traffic-7d');
    charts.users = createSingleLineChart('chart-users', 'rgb(99, 102, 241)', '');
    charts.daily = createDailyChart('chart-daily');
    charts.cpu = createSingleLineChart('chart-cpu', 'rgb(251, 191, 36)', '%', 80);
    charts.ram = createSingleLineChart('chart-ram', 'rgb(244, 63, 94)', '%', 85);
}

// ═══════════════════════════════════════════════════════════════
// Chart Data Updates
// ═══════════════════════════════════════════════════════════════

function updateTrafficChart(chart, data) {
    if (!data || !data.length) return;
    chart.data.labels = data.map(d => formatTime(d.time));
    chart.data.datasets[0].data = data.map(d => d.rx);
    chart.data.datasets[1].data = data.map(d => d.tx);
    chart.update('none');
}

function updateSingleChart(chart, data) {
    if (!data || !data.length) return;
    chart.data.labels = data.map(d => formatTime(d.time));
    chart.data.datasets[0].data = data.map(d => d.value);
    chart.update('none');
}

function updateDailyChart(chart, data) {
    if (!data || !data.length) return;
    chart.data.labels = data.map(d => d.day);
    chart.data.datasets[0].data = data.map(d => d.rx_bytes);
    chart.data.datasets[1].data = data.map(d => d.tx_bytes);
    chart.update('none');
}

async function refreshCharts() {
    const [t24, t7d, users, daily, cpu, ram] = await Promise.all([
        fetchJSON(API.traffic24h),
        fetchJSON(API.traffic7d),
        fetchJSON(API.usersHistory),
        fetchJSON(API.trafficDaily),
        fetchJSON(API.cpuHistory),
        fetchJSON(API.ramHistory),
    ]);

    updateTrafficChart(charts.traffic24h, t24);
    updateTrafficChart(charts.traffic7d, t7d);
    updateSingleChart(charts.users, users);
    updateDailyChart(charts.daily, daily);
    updateSingleChart(charts.cpu, cpu);
    updateSingleChart(charts.ram, ram);
}

// ═══════════════════════════════════════════════════════════════
// VPN Summary Card Updates
// ═══════════════════════════════════════════════════════════════

async function updateVpnSummary() {
    const vpn = await fetchJSON(API.vpnSummary);
    if (!vpn) return;

    document.getElementById('vpn-val-connected').textContent = vpn.connected_users ?? 0;
    document.getElementById('vpn-val-avg-time').textContent = vpn.avg_session_time || '—';

    if (vpn.max_session_time) {
        document.getElementById('vpn-val-max-time').textContent = vpn.max_session_time.time || '—';
        document.getElementById('vpn-sub-max-user').textContent = vpn.max_session_time.user ? `👤 ${vpn.max_session_time.user}` : '—';
    }

    if (vpn.last_connection) {
        document.getElementById('vpn-val-last-user').textContent = vpn.last_connection.user || '—';
        document.getElementById('vpn-sub-last-time').textContent = timeAgo(vpn.last_connection.time);
    }

    // Render detected protocol badges
    const protocolsContainer = document.getElementById('vpn-protocols-badge');
    if (protocolsContainer) {
        if (vpn.protocols_detected && vpn.protocols_detected.length) {
            protocolsContainer.innerHTML = vpn.protocols_detected.map(p =>
                `<span class="badge-protocol ${p.toLowerCase()}"><i class="bi bi-shield-check me-1"></i>${p}</span>`
            ).join(' ');
        } else {
            protocolsContainer.innerHTML = '<span class="badge-protocol text-muted">Sin VPNs activas</span>';
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// Unified Users Logic
// ═══════════════════════════════════════════════════════════════

let activeCategory = 'all';
let userSearchQuery = '';
let cachedUsersData = null;

function renderUnifiedUsersTable() {
    const tbody = document.getElementById('table-unified-users');
    if (!tbody || !cachedUsersData) return;

    const counts = cachedUsersData.counts || {};
    document.getElementById('count-user-all').textContent = counts.total_all || 0;
    document.getElementById('count-user-oficina').textContent = counts.oficina || 0;
    document.getElementById('count-user-vpn').textContent = counts.vpn || 0;
    document.getElementById('count-user-vm').textContent = counts.vm || 0;
    document.getElementById('count-user-offline').textContent = counts.offline || 0;

    let usersList = activeCategory === 'all'
        ? (cachedUsersData.all || [])
        : (cachedUsersData[activeCategory] || []);

    if (userSearchQuery.trim()) {
        const q = userSearchQuery.toLowerCase();
        usersList = usersList.filter(u =>
            (u.hostname && u.hostname.toLowerCase().includes(q)) ||
            (u.vpn_user && u.vpn_user.toLowerCase().includes(q)) ||
            (u.ip && u.ip.includes(q)) ||
            (u.mac && u.mac.toLowerCase().includes(q))
        );
    }

    if (!usersList.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state"><p>No se encontraron usuarios en esta categoría.</p></td></tr>';
        return;
    }

    tbody.innerHTML = usersList.map(u => {
        let typeBadge = '';
        if (u.device_type === 'vpn') {
            typeBadge = `<span class="badge-user-type vpn"><i class="bi bi-shield-lock-fill me-1"></i>VPN (${u.vpn_type || 'Remoto'})</span>`;
        } else if (u.device_type === 'vm') {
            typeBadge = `<span class="badge-user-type vm"><i class="bi bi-cpu-fill me-1"></i>Servers / VMs</span>`;
        } else if (u.is_active) {
            typeBadge = `<span class="badge-user-type oficina"><i class="bi bi-building-fill me-1"></i>Oficina</span>`;
        } else {
            typeBadge = `<span class="badge-user-type offline"><i class="bi bi-dash-circle me-1"></i>Offline</span>`;
        }

        let userTitle = u.hostname;
        if (u.device_type === 'vpn' && u.vpn_user && u.vpn_user !== u.hostname) {
            userTitle = `<strong>${u.hostname}</strong> <span class="text-muted" style="font-size:0.78rem;">(${u.vpn_user})</span>`;
        }

        let queueDetails = '—';
        if (u.has_queue) {
            queueDetails = `
                <div class="queue-info">
                    <span class="queue-limit-badge" title="Límite configurado"><i class="bi bi-speedometer2 me-1"></i>${u.queue_limit}</span>
                    <div class="queue-speed"><i class="bi bi-arrow-down-short text-cyan"></i>${u.queue_rx_fmt} &bull; <i class="bi bi-arrow-up-short text-violet"></i>${u.queue_tx_fmt}</div>
                    <div class="queue-total">${u.queue_rx_bytes_fmt} / ${u.queue_tx_bytes_fmt}</div>
                </div>
            `;
        } else {
            queueDetails = `<div class="traffic-simple"><span>&darr; ${u.rx_fmt}</span> &bull; <span>&uarr; ${u.tx_fmt}</span></div>`;
        }

        let statusDot = u.is_active
            ? '<span class="status-dot online" style="width:7px;height:7px;display:inline-block;margin-right:4px;"></span> Online'
            : '<span class="status-dot offline" style="width:7px;height:7px;display:inline-block;margin-right:4px;"></span> Offline';

        return `
            <tr>
                <td>${userTitle}</td>
                <td>${typeBadge}</td>
                <td><code style="color:var(--accent-indigo)">${u.ip}</code></td>
                <td>${u.session_time || '—'}</td>
                <td>${queueDetails}</td>
                <td>
                    <div>${statusDot}</div>
                    <div style="font-size:0.7rem;color:var(--text-muted);">${timeAgo(u.last_seen)}</div>
                </td>
            </tr>
        `;
    }).join('');
}

async function updateUnifiedUsers() {
    const data = await fetchJSON(API.usersUnified);
    if (!data) return;
    cachedUsersData = data;
    renderUnifiedUsersTable();
}

// ═══════════════════════════════════════════════════════════════
// Table Updates
// ═══════════════════════════════════════════════════════════════

async function updateTables() {
    const [interfaces, alerts, outages] = await Promise.all([
        fetchJSON(API.interfaces),
        fetchJSON(API.alerts),
        fetchJSON(API.outages),
    ]);

    // Interfaces
    const tbody2 = document.getElementById('table-interfaces');
    if (tbody2 && interfaces && interfaces.length) {
        document.getElementById('count-interfaces').textContent = interfaces.length;
        tbody2.innerHTML = interfaces.map(i => {
            let statusClass = i.disabled ? 'disabled' : (i.running ? 'up' : 'down');
            let statusText = i.disabled ? 'disabled' : (i.running ? 'running' : 'down');
            return `
                <tr>
                    <td><strong>${i.name}</strong></td>
                    <td>${i.type}</td>
                    <td><span class="iface-status ${statusClass}"></span>${statusText}</td>
                    <td>${i.rx_fmt}</td>
                    <td>${i.tx_fmt}</td>
                </tr>
            `;
        }).join('');
    }

    // Alerts
    const tbody3 = document.getElementById('table-alerts');
    if (tbody3 && alerts && alerts.length) {
        document.getElementById('count-alerts').textContent = alerts.filter(a => a.is_active).length;
        tbody3.innerHTML = alerts.slice(0, 20).map(a => `
            <tr>
                <td><span class="severity-tag ${a.severity}">${a.severity}</span></td>
                <td>${a.type}</td>
                <td>${a.message}</td>
                <td>${formatDateTime(a.started_at)}</td>
                <td>${a.is_active
                    ? '<span class="badge-status offline" style="font-size:0.68rem">Active</span>'
                    : '<span class="badge-status online" style="font-size:0.68rem">Resolved</span>'
                }</td>
            </tr>
        `).join('');
    } else if (tbody3) {
        document.getElementById('count-alerts').textContent = '0';
        tbody3.innerHTML = '<tr><td colspan="5" class="empty-state"><p>No alerts &mdash; all systems normal</p></td></tr>';
    }

    // Outages
    const tbody4 = document.getElementById('table-outages');
    if (tbody4 && outages && outages.length) {
        document.getElementById('count-outages').textContent = outages.length;
        tbody4.innerHTML = outages.map(o => `
            <tr>
                <td>${o.type}</td>
                <td>${formatDateTime(o.started_at)}</td>
                <td>${o.ended_at ? formatDateTime(o.ended_at) : '—'}</td>
                <td>${o.duration_fmt || '—'}</td>
                <td>${o.is_active
                    ? '<span class="badge-status offline" style="font-size:0.68rem">Ongoing</span>'
                    : '<span class="badge-status online" style="font-size:0.68rem">Resolved</span>'
                }</td>
            </tr>
        `).join('');
    }
}

// ═══════════════════════════════════════════════════════════════
// Countdown Timer
// ═══════════════════════════════════════════════════════════════

let countdown = REFRESH_INTERVAL / 1000;

function startCountdown() {
    setInterval(() => {
        countdown--;
        if (countdown <= 0) countdown = REFRESH_INTERVAL / 1000;
        const el = document.getElementById('refresh-countdown');
        if (el) el.textContent = `${countdown}s`;
    }, 1000);
}

// ═══════════════════════════════════════════════════════════════
// Main Refresh Loop
// ═══════════════════════════════════════════════════════════════

async function refreshAll() {
    await Promise.all([
        updateStatus(),
        updateVpnSummary(),
        updateUnifiedUsers(),
        refreshCharts(),
        updateTables(),
    ]);
    countdown = REFRESH_INTERVAL / 1000;
}

// ═══════════════════════════════════════════════════════════════
// Initialization & Event Binding
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initCharts();

    // Category Tabs Binding
    const tabsContainer = document.getElementById('user-tabs');
    if (tabsContainer) {
        tabsContainer.addEventListener('click', (e) => {
            const btn = e.target.closest('.tab-btn');
            if (!btn) return;
            tabsContainer.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeCategory = btn.dataset.cat || 'all';
            renderUnifiedUsersTable();
        });
    }

    // Search Input Binding
    const searchInput = document.getElementById('user-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            userSearchQuery = e.target.value;
            renderUnifiedUsersTable();
        });
    }

    refreshAll();
    startCountdown();
    setInterval(refreshAll, REFRESH_INTERVAL);
});
