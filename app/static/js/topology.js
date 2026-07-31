/**
 * Orbit — Topology Page Logic
 *
 * Renders infrastructure topology tree and device table.
 * Auto-refreshes to show real-time status.
 */

const TOPO_REFRESH = 15_000;
const TOPO_API = {
    topology: '/api/topology',
    devices: '/api/devices',
    wifiAps: '/api/wifi/aps',
};

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
// Topology Tree
// ═══════════════════════════════════════════════════════════════

async function updateTopology() {
    const topo = await fetchJSON(TOPO_API.topology);
    const apData = await fetchJSON(TOPO_API.wifiAps);
    if (!topo) return;

    // Build AP client map from WiFi data
    const apClientMap = {};
    if (apData) {
        apData.forEach(ap => {
            apClientMap[ap.id] = ap.client_count || 0;
        });
    }

    // Render ISP nodes
    const ispLayer = document.getElementById('topo-isp-layer');
    if (ispLayer && topo.isps) {
        if (topo.isps.length === 0) {
            ispLayer.innerHTML = '<div class="empty-state"><p>Sin ISPs configurados en .env</p></div>';
        } else {
            ispLayer.innerHTML = topo.isps.map(isp => {
                let statusClass = 'topo-unknown';
                let statusDot = '🟡';
                if (isp.status === 'online') {
                    statusClass = 'topo-online';
                    statusDot = '🟢';
                } else if (isp.status === 'offline') {
                    statusClass = 'topo-offline';
                    statusDot = '🔴';
                }
                return `
                <div class="topo-node topo-isp ${statusClass}">
                    <div class="topo-node-icon"><i class="bi bi-globe2"></i></div>
                    <div class="topo-node-label">${isp.name}</div>
                    <div class="topo-node-meta">${isp.interface}</div>
                    <div class="topo-node-status">${statusDot}</div>
                </div>`;
            }).join('');
        }
    }

    // Render MikroTik nodes
    const mkLayer = document.getElementById('topo-mikrotik-layer');
    if (mkLayer && topo.mikrotiks) {
        if (topo.mikrotiks.length === 0) {
            mkLayer.innerHTML = '<div class="topo-node topo-device topo-offline"><div class="topo-node-icon"><i class="bi bi-router-fill"></i></div><div class="topo-node-label">No MikroTik</div></div>';
        } else {
            mkLayer.innerHTML = topo.mikrotiks.map(mk => {
                const statusClass = mk.is_reachable ? 'topo-online' : 'topo-offline';
                const statusDot = mk.is_reachable ? '🟢' : '🔴';
                return `
                <div class="topo-node topo-device ${statusClass}">
                    <div class="topo-node-icon"><i class="bi bi-router-fill"></i></div>
                    <div class="topo-node-label">${mk.name}</div>
                    <div class="topo-node-meta">${mk.model || 'MikroTik'}</div>
                    <div class="topo-node-status">${statusDot}</div>
                </div>`;
            }).join('');
        }
    }

    // Render AP nodes
    const apLayer = document.getElementById('topo-ap-layer');
    if (apLayer && topo.aps) {
        if (topo.aps.length === 0) {
            apLayer.innerHTML = '<div class="empty-state"><p>No hay APs configurados</p></div>';
        } else {
            apLayer.innerHTML = topo.aps.map(ap => {
                const statusClass = ap.is_reachable ? 'topo-online' : 'topo-offline';
                const statusDot = ap.is_reachable ? '🟢' : '🔴';
                const clients = apClientMap[ap.id] || 0;
                return `
                <div class="topo-node topo-device ${statusClass}">
                    <div class="topo-node-icon"><i class="bi bi-wifi"></i></div>
                    <div class="topo-node-label">${ap.name}</div>
                    <div class="topo-node-meta">${clients} clients</div>
                    <div class="topo-node-status">${statusDot}</div>
                </div>`;
            }).join('');
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// Device Table
// ═══════════════════════════════════════════════════════════════

async function updateDeviceTable() {
    const devices = await fetchJSON(TOPO_API.devices);
    if (!devices) return;

    const tbody = document.getElementById('table-devices');
    const countEl = document.getElementById('count-devices');
    if (!tbody) return;
    if (countEl) countEl.textContent = devices.length;

    if (devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state"><p>No devices found</p></td></tr>';
        return;
    }

    const typeIcons = {
        mikrotik: '<i class="bi bi-router-fill text-indigo"></i>',
        ubiquiti: '<i class="bi bi-wifi text-cyan"></i>',
        switch: '<i class="bi bi-diagram-2 text-amber"></i>',
        other: '<i class="bi bi-hdd text-muted"></i>',
    };

    tbody.innerHTML = devices.map(d => {
        const statusClass = d.is_reachable ? 'online' : 'offline';
        const statusText = d.is_reachable ? 'Online' : 'Offline';
        const icon = typeIcons[d.type] || typeIcons.other;
        const typeName = d.type.charAt(0).toUpperCase() + d.type.slice(1);

        return `<tr>
            <td><strong>${d.name}</strong></td>
            <td>${icon} ${typeName}</td>
            <td><code>${d.host}</code></td>
            <td>${d.model || '—'}</td>
            <td><span class="badge-status ${statusClass}"><span class="status-dot ${statusClass}" style="width:7px;height:7px"></span> ${statusText}</span></td>
        </tr>`;
    }).join('');
}

// ═══════════════════════════════════════════════════════════════
// Refresh Loop
// ═══════════════════════════════════════════════════════════════

async function refreshAll() {
    await Promise.all([
        updateTopology(),
        updateDeviceTable(),
    ]);
}

refreshAll();
setInterval(refreshAll, TOPO_REFRESH);

let countdown = TOPO_REFRESH / 1000;
setInterval(() => {
    countdown--;
    if (countdown <= 0) countdown = TOPO_REFRESH / 1000;
    const el = document.getElementById('topo-refresh-countdown');
    if (el) el.textContent = `${countdown}s`;
}, 1000);
