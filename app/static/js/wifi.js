/**
 * Orbit — WiFi Monitoring Page Logic
 *
 * Handles:
 * - SSID card rendering with client counts
 * - WiFi history chart (Chart.js)
 * - AP status table
 * - Auto-refresh
 */

const WIFI_REFRESH = 10_000;
const WIFI_API = {
    summary: '/api/wifi/summary',
    history: '/api/wifi/history',
    aps: '/api/wifi/aps',
};

// Chart.js config
Chart.defaults.color = '#71717a';
Chart.defaults.borderColor = 'rgba(255,255,255,0.04)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;

// ═══════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════

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

function formatUptime(seconds) {
    if (!seconds || seconds <= 0) return '—';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const parts = [];
    if (d) parts.push(`${d}d`);
    if (h) parts.push(`${h}h`);
    if (m) parts.push(`${m}m`);
    return parts.length ? parts.join(' ') : `${seconds}s`;
}

// SSID color palette
const SSID_COLORS = [
    '#6366f1', // indigo
    '#06b6d4', // cyan
    '#f59e0b', // amber
    '#ec4899', // pink
    '#10b981', // emerald
    '#8b5cf6', // violet
    '#ef4444', // red
    '#14b8a6', // teal
];

function getSsidColor(index) {
    return SSID_COLORS[index % SSID_COLORS.length];
}

// ═══════════════════════════════════════════════════════════════
// SSID Cards
// ═══════════════════════════════════════════════════════════════

async function updateSsidCards() {
    const data = await fetchJSON(WIFI_API.summary);
    if (!data) return;

    // Update KPIs
    const totalEl = document.getElementById('wifi-total-clients');
    const ssidEl = document.getElementById('wifi-total-ssids');
    const apEl = document.getElementById('wifi-total-aps');
    if (totalEl) totalEl.textContent = data.total_clients ?? '—';
    if (ssidEl) ssidEl.textContent = data.total_ssids ?? '—';
    if (apEl) apEl.textContent = data.total_aps ?? '—';

    // Render SSID cards
    const container = document.getElementById('ssid-cards-section');
    if (!container) return;

    if (!data.ssids || data.ssids.length === 0) {
        container.innerHTML = '<div class="empty-state"><p><i class="bi bi-wifi-off me-2"></i>No hay datos de WiFi disponibles. Configurá los APs en .env</p></div>';
        return;
    }

    const maxClients = Math.max(...data.ssids.map(s => s.client_count), 1);
    let html = '';

    data.ssids.forEach((ssid, i) => {
        const color = getSsidColor(i);
        const pct = Math.round((ssid.client_count / maxClients) * 100);
        const radios = ssid.radios ? ssid.radios.join(' / ') : '';

        html += `
        <div class="wifi-ssid-card" style="--ssid-color: ${color}">
            <div class="ssid-header">
                <div class="ssid-name"><i class="bi bi-wifi me-2"></i>${ssid.name}</div>
                <div class="ssid-client-count">${ssid.client_count}</div>
            </div>
            <div class="ssid-bar-track">
                <div class="ssid-bar-fill" style="width: ${pct}%; background: ${color}"></div>
            </div>
            <div class="ssid-meta">
                <span>${ssid.ap_count} AP${ssid.ap_count !== 1 ? 's' : ''}</span>
                <span>${radios}</span>
            </div>
        </div>`;
    });

    container.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════
// WiFi History Chart
// ═══════════════════════════════════════════════════════════════

let wifiChart = null;

async function updateWifiChart() {
    const data = await fetchJSON(WIFI_API.history);
    if (!data || data.length === 0) return;

    // Group data by SSID
    const ssidMap = {};
    data.forEach(d => {
        if (!ssidMap[d.ssid]) ssidMap[d.ssid] = [];
        ssidMap[d.ssid].push({ x: d.time, y: d.clients });
    });

    const ssidNames = Object.keys(ssidMap);
    const datasets = ssidNames.map((name, i) => ({
        label: name,
        data: ssidMap[name],
        borderColor: getSsidColor(i),
        backgroundColor: getSsidColor(i) + '20',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 2,
    }));

    const ctx = document.getElementById('chart-wifi-history');
    if (!ctx) return;

    if (wifiChart) {
        wifiChart.data.datasets = datasets;
        wifiChart.update('none');
    } else {
        wifiChart = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { usePointStyle: true, pointStyle: 'circle', padding: 16 },
                    },
                    tooltip: {
                        backgroundColor: '#1e1e24',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        titleColor: '#f4f4f5',
                        bodyColor: '#a1a1aa',
                        padding: 10,
                        cornerRadius: 8,
                    },
                },
                scales: {
                    x: {
                        type: 'category',
                        ticks: {
                            callback: function(val) {
                                const label = this.getLabelForValue(val);
                                if (!label) return '';
                                const d = new Date(label);
                                return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
                            },
                            maxTicksLimit: 12,
                        },
                    },
                    y: {
                        beginAtZero: true,
                        title: { display: true, text: 'Clients' },
                    },
                },
            },
        });
    }
}

// ═══════════════════════════════════════════════════════════════
// AP Status Table
// ═══════════════════════════════════════════════════════════════

async function updateApTable() {
    const data = await fetchJSON(WIFI_API.aps);
    if (!data) return;

    const tbody = document.getElementById('table-aps');
    const countEl = document.getElementById('count-aps');
    if (!tbody) return;
    if (countEl) countEl.textContent = data.length;

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state"><p>No hay APs configurados</p></td></tr>';
        return;
    }

    tbody.innerHTML = data.map(ap => {
        const statusClass = ap.is_reachable ? 'online' : 'offline';
        const statusText = ap.is_reachable ? 'Online' : 'Offline';
        const cpu = ap.cpu_load != null ? `${ap.cpu_load}%` : '—';
        const ram = ap.ram_percent != null ? `${ap.ram_percent}%` : '—';
        const latency = ap.latency_ms != null ? `${ap.latency_ms.toFixed(0)}ms` : '—';

        return `<tr>
            <td><strong>${ap.name}</strong><br><small class="text-muted">${ap.host}</small></td>
            <td>${ap.model}</td>
            <td>${ap.firmware}</td>
            <td><strong>${ap.client_count}</strong></td>
            <td>${cpu}</td>
            <td>${ram}</td>
            <td>${latency}</td>
            <td><span class="badge-status ${statusClass}"><span class="status-dot ${statusClass}" style="width:7px;height:7px"></span> ${statusText}</span></td>
        </tr>`;
    }).join('');
}

// ═══════════════════════════════════════════════════════════════
// Refresh Loop
// ═══════════════════════════════════════════════════════════════

async function refreshAll() {
    await Promise.all([
        updateSsidCards(),
        updateWifiChart(),
        updateApTable(),
    ]);
}

// Initial load
refreshAll();

// Auto-refresh
setInterval(refreshAll, WIFI_REFRESH);

// Countdown timer
let countdown = WIFI_REFRESH / 1000;
setInterval(() => {
    countdown--;
    if (countdown <= 0) countdown = WIFI_REFRESH / 1000;
    const el = document.getElementById('wifi-refresh-countdown');
    if (el) el.textContent = `${countdown}s`;
}, 1000);
