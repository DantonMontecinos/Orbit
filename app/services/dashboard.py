"""
Dashboard data aggregation service.

Provides pre-computed data structures for the dashboard UI.
All queries are read-only against the SQLite database.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.client_device import ClientDevice
from app.models.interface import InterfaceSnapshot
from app.models.router import Router
from app.models.snapshot import ResourceSnapshot
from app.utils.formatters import format_bps, format_bytes, format_queue_limit, format_uptime, utcnow



def get_current_status(db: Session, router_id: int) -> dict[str, Any]:
    """
    Get the complete current status for dashboard KPI cards.

    Returns the latest snapshot data plus router identity info.
    """
    router = db.query(Router).filter_by(id=router_id).first()
    snapshot = (
        db.query(ResourceSnapshot)
        .filter_by(router_id=router_id)
        .order_by(ResourceSnapshot.timestamp.desc())
        .first()
    )

    if not router or not snapshot:
        return {
            "router": None,
            "snapshot": None,
            "is_online": False,
        }

    # Active client count (excluding Servers/VMs infrastructure)
    from app.collector.tasks import _is_virtual_machine

    active_devices = (
        db.query(ClientDevice)
        .filter_by(router_id=router_id, is_active=True)
        .all()
    )
    active_clients = sum(
        1 for d in active_devices
        if d.device_type != "vm" and not _is_virtual_machine(d.mac_address, d.hostname, d.ip_address)
    )


    # Active alerts count
    active_alerts = (
        db.query(func.count(Alert.id))
        .filter_by(router_id=router_id, is_active=True)
        .scalar()
        or 0
    )

    return {
        "router": {
            "name": router.name,
            "identity": router.identity,
            "board": router.board_name,
            "version": router.version,
            "architecture": router.architecture,
        },
        "is_online": snapshot.is_reachable,
        "wan_status": snapshot.wan_status,
        "cpu_load": snapshot.cpu_load,
        "ram_percent": snapshot.ram_percent,
        "ram_used": snapshot.ram_used,
        "ram_total": snapshot.ram_total,
        "ram_used_fmt": format_bytes(snapshot.ram_used),
        "ram_total_fmt": format_bytes(snapshot.ram_total),
        "uptime": format_uptime(snapshot.uptime_seconds),
        "uptime_seconds": snapshot.uptime_seconds,
        "temperature": snapshot.temperature,
        "voltage": snapshot.voltage,
        "rx_bps": snapshot.rx_bps,
        "tx_bps": snapshot.tx_bps,
        "rx_fmt": format_bps(snapshot.rx_bps),
        "tx_fmt": format_bps(snapshot.tx_bps),
        "clients_total": active_clients,
        "dhcp_count": snapshot.dhcp_client_count,
        "ppp_count": snapshot.ppp_active_count,
        "arp_count": snapshot.arp_count,
        "active_alerts": active_alerts,
        "last_update": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
    }


def get_traffic_history(
    db: Session,
    router_id: int,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """
    Get traffic data points for the specified time window.

    Returns timestamps with RX/TX rates for charting.
    """
    since = utcnow() - timedelta(hours=hours)

    snapshots = (
        db.query(
            ResourceSnapshot.timestamp,
            ResourceSnapshot.rx_bps,
            ResourceSnapshot.tx_bps,
        )
        .filter(
            ResourceSnapshot.router_id == router_id,
            ResourceSnapshot.timestamp >= since,
        )
        .order_by(ResourceSnapshot.timestamp.asc())
        .all()
    )

    return [
        {
            "time": s.timestamp.isoformat(),
            "rx": s.rx_bps,
            "tx": s.tx_bps,
        }
        for s in snapshots
    ]


def get_cpu_history(
    db: Session,
    router_id: int,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Get CPU load data points for charting."""
    since = utcnow() - timedelta(hours=hours)

    snapshots = (
        db.query(
            ResourceSnapshot.timestamp,
            ResourceSnapshot.cpu_load,
        )
        .filter(
            ResourceSnapshot.router_id == router_id,
            ResourceSnapshot.timestamp >= since,
        )
        .order_by(ResourceSnapshot.timestamp.asc())
        .all()
    )

    return [
        {"time": s.timestamp.isoformat(), "value": s.cpu_load}
        for s in snapshots
    ]


def get_ram_history(
    db: Session,
    router_id: int,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Get RAM usage percentage data points for charting."""
    since = utcnow() - timedelta(hours=hours)

    snapshots = (
        db.query(
            ResourceSnapshot.timestamp,
            ResourceSnapshot.ram_used,
            ResourceSnapshot.ram_total,
        )
        .filter(
            ResourceSnapshot.router_id == router_id,
            ResourceSnapshot.timestamp >= since,
        )
        .order_by(ResourceSnapshot.timestamp.asc())
        .all()
    )

    return [
        {
            "time": s.timestamp.isoformat(),
            "value": round((s.ram_used / s.ram_total) * 100, 1) if s.ram_total > 0 else 0,
        }
        for s in snapshots
    ]


def get_users_history(
    db: Session,
    router_id: int,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Get concurrent user count over time."""
    since = utcnow() - timedelta(hours=hours)

    snapshots = (
        db.query(
            ResourceSnapshot.timestamp,
            ResourceSnapshot.dhcp_client_count,
            ResourceSnapshot.ppp_active_count,
        )
        .filter(
            ResourceSnapshot.router_id == router_id,
            ResourceSnapshot.timestamp >= since,
        )
        .order_by(ResourceSnapshot.timestamp.asc())
        .all()
    )

    return [
        {
            "time": s.timestamp.isoformat(),
            "value": s.dhcp_client_count + s.ppp_active_count,
        }
        for s in snapshots
    ]


def get_daily_consumption(
    db: Session,
    router_id: int,
    days: int = 30,
) -> list[dict[str, Any]]:
    """
    Get daily traffic totals (sum of deltas per day).

    Aggregates RX/TX bps readings into daily byte totals by
    multiplying average rate by measurement interval.
    """
    since = utcnow() - timedelta(days=days)

    # Group by date and sum the rates * interval
    results = (
        db.query(
            func.date(ResourceSnapshot.timestamp).label("day"),
            func.avg(ResourceSnapshot.rx_bps).label("avg_rx_bps"),
            func.avg(ResourceSnapshot.tx_bps).label("avg_tx_bps"),
            func.count(ResourceSnapshot.id).label("samples"),
        )
        .filter(
            ResourceSnapshot.router_id == router_id,
            ResourceSnapshot.timestamp >= since,
        )
        .group_by(func.date(ResourceSnapshot.timestamp))
        .order_by(func.date(ResourceSnapshot.timestamp).asc())
        .all()
    )

    from app.config import settings

    interval = settings.collect_interval_seconds

    return [
        {
            "day": r.day,
            "rx_bytes": int((r.avg_rx_bps / 8) * r.samples * interval) if r.avg_rx_bps else 0,
            "tx_bytes": int((r.avg_tx_bps / 8) * r.samples * interval) if r.avg_tx_bps else 0,
            "rx_fmt": format_bytes(
                int((r.avg_rx_bps / 8) * r.samples * interval) if r.avg_rx_bps else 0
            ),
            "tx_fmt": format_bytes(
                int((r.avg_tx_bps / 8) * r.samples * interval) if r.avg_tx_bps else 0
            ),
        }
        for r in results
    ]


def get_top_consumers(
    db: Session,
    router_id: int,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Get top N client devices by traffic volume."""
    devices = (
        db.query(ClientDevice)
        .filter_by(router_id=router_id, is_active=True)
        .order_by(
            (ClientDevice.total_rx_bytes + ClientDevice.total_tx_bytes).desc()
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "ip": d.ip_address,
            "mac": d.mac_address,
            "hostname": d.hostname or "—",
            "source": d.source,
            "rx": d.total_rx_bytes,
            "tx": d.total_tx_bytes,
            "rx_fmt": format_bytes(d.total_rx_bytes),
            "tx_fmt": format_bytes(d.total_tx_bytes),
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in devices
    ]


def get_interfaces_status(
    db: Session,
    router_id: int,
) -> list[dict[str, Any]]:
    """Get the latest status for all interfaces."""
    # Get the latest snapshot ID
    latest = (
        db.query(ResourceSnapshot.id)
        .filter_by(router_id=router_id)
        .order_by(ResourceSnapshot.timestamp.desc())
        .first()
    )

    if not latest:
        return []

    interfaces = (
        db.query(InterfaceSnapshot)
        .filter_by(snapshot_id=latest[0])
        .order_by(InterfaceSnapshot.name.asc())
        .all()
    )

    return [
        {
            "name": i.name,
            "type": i.iface_type or "—",
            "mac": i.mac_address or "—",
            "running": i.is_running,
            "disabled": i.is_disabled,
            "rx_bps": i.rx_bps,
            "tx_bps": i.tx_bps,
            "rx_fmt": format_bps(i.rx_bps),
            "tx_fmt": format_bps(i.tx_bps),
            "rx_bytes": format_bytes(i.rx_bytes),
            "tx_bytes": format_bytes(i.tx_bytes),
        }
        for i in interfaces
    ]


def get_active_alerts(
    db: Session,
    router_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get active and recent alerts."""
    alerts = (
        db.query(Alert)
        .filter_by(router_id=router_id)
        .order_by(Alert.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": a.id,
            "type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            "duration": a.duration_seconds,
            "is_active": a.is_active,
            "acknowledged": a.acknowledged,
        }
        for a in alerts
    ]


def get_unified_users(
    db: Session,
    router_id: int,
) -> dict[str, Any]:
    """
    Get unified user information merged from DHCP, ARP, PPP, WireGuard, and Simple Queues.

    Grouped into:
    - lan: 🟢 Oficina
    - vpn: 🔵 VPN
    - vm: 🟣 Máquinas Virtuales
    - offline: ⚪ Offline
    """
    devices = (
        db.query(ClientDevice)
        .filter_by(router_id=router_id)
        .order_by((ClientDevice.total_rx_bytes + ClientDevice.total_tx_bytes).desc())
        .all()
    )

    oficina_list = []
    vpn_list = []
    vm_list = []
    offline_list = []

    for d in devices:
        item = {
            "id": d.id,
            "hostname": d.hostname or "Host no identificado",
            "vpn_user": d.vpn_user or "—",
            "vpn_type": d.vpn_type or "—",
            "ip": d.ip_address,
            "mac": d.mac_address,
            "device_type": d.device_type,
            "source": d.source,
            "interface": d.interface or "—",
            "is_active": d.is_active,
            "status": "Online" if d.is_active else "Offline",
            "session_time": d.session_time or "—",
            "session_seconds": d.session_seconds or 0,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "total_rx": d.total_rx_bytes,
            "total_tx": d.total_tx_bytes,
            "rx_fmt": format_bytes(d.total_rx_bytes),
            "tx_fmt": format_bytes(d.total_tx_bytes),
            "has_queue": bool(d.queue_name),
            "queue_name": d.queue_name or "—",
            "queue_limit": format_queue_limit(d.queue_max_limit),
            "queue_rx_bps": d.queue_rx_bps,
            "queue_tx_bps": d.queue_tx_bps,
            "queue_rx_fmt": format_bps(d.queue_rx_bps),
            "queue_tx_fmt": format_bps(d.queue_tx_bps),
            "queue_rx_bytes_fmt": format_bytes(d.queue_rx_bytes),
            "queue_tx_bytes_fmt": format_bytes(d.queue_tx_bytes),
        }

        from app.collector.tasks import _is_virtual_machine
        is_vm = d.device_type == "vm" or _is_virtual_machine(d.mac_address, d.hostname, d.ip_address)

        if is_vm:
            item["device_type"] = "vm"
            item["connection_type"] = "Servers / VMs"
            vm_list.append(item)
        elif not d.is_active or d.device_type == "offline":
            item["connection_type"] = "Offline"
            offline_list.append(item)
        elif d.device_type == "vpn":
            item["connection_type"] = f"VPN ({d.vpn_type or 'Remoto'})"
            vpn_list.append(item)
        else:
            item["connection_type"] = "LAN / Oficina"
            oficina_list.append(item)

    all_users = oficina_list + vpn_list + vm_list + offline_list

    return {
        "counts": {
            "oficina": len(oficina_list),
            "vpn": len(vpn_list),
            "vm": len(vm_list),
            "offline": len(offline_list),
            "total_active": len(oficina_list) + len(vpn_list),
            "total_all": len(all_users),
        },
        "oficina": oficina_list,
        "vpn": vpn_list,
        "vm": vm_list,
        "offline": offline_list,
        "all": all_users,
    }


def get_vpn_summary(
    db: Session,
    router_id: int,
) -> dict[str, Any]:
    """
    Get summary card metrics for VPN users.

    - Connected users count
    - Average session time
    - Longest connected session
    - Last connection established
    - Detected active VPN protocols
    """
    latest_snapshot = (
        db.query(ResourceSnapshot)
        .filter_by(router_id=router_id)
        .order_by(ResourceSnapshot.timestamp.desc())
        .first()
    )

    active_vpn_users = (
        db.query(ClientDevice)
        .filter(
            ClientDevice.router_id == router_id,
            ClientDevice.is_active == True,
            ClientDevice.device_type == "vpn",
        )
        .order_by(ClientDevice.last_seen.desc())
        .all()
    )

    connected_count = len(active_vpn_users)
    total_seconds = sum(u.session_seconds for u in active_vpn_users)
    avg_seconds = int(total_seconds / connected_count) if connected_count > 0 else 0

    max_user = max(active_vpn_users, key=lambda u: u.session_seconds) if active_vpn_users else None
    last_user = active_vpn_users[0] if active_vpn_users else None

    protocols = []
    if latest_snapshot and latest_snapshot.vpn_types_detected:
        protocols = [p.strip() for p in latest_snapshot.vpn_types_detected.split(",") if p.strip()]

    vpn_alerts = (
        db.query(Alert)
        .filter(
            Alert.router_id == router_id,
            Alert.is_active == True,
            Alert.alert_type.like("vpn_disconnect:%"),
        )
        .count()
    )

    return {
        "connected_users": connected_count,
        "avg_session_time": format_uptime(avg_seconds),
        "max_session_time": {
            "user": max_user.vpn_user or max_user.hostname if max_user else "—",
            "time": max_user.session_time or format_uptime(max_user.session_seconds) if max_user else "—",
        },
        "last_connection": {
            "user": last_user.vpn_user or last_user.hostname if last_user else "—",
            "ip": last_user.ip_address if last_user else "—",
            "time": last_user.last_seen.isoformat() if last_user and last_user.last_seen else None,
        },
        "protocols_detected": protocols,
        "vpn_alerts_count": vpn_alerts,
    }
