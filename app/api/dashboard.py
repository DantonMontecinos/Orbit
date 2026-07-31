"""
Dashboard JSON API endpoints.

Provides data for the frontend Chart.js graphs and dynamic
table updates. All endpoints are GET-only and read from SQLite.
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.router import Router
from app.config import settings
from app.services.dashboard import (
    get_active_alerts,
    get_cpu_history,
    get_current_status,
    get_daily_consumption,
    get_interfaces_status,
    get_ram_history,
    get_top_consumers,
    get_traffic_history,
    get_unified_users,
    get_users_history,
    get_vpn_summary,
)
from app.services.history import get_outage_history

router = APIRouter(prefix="/api", tags=["dashboard"])


def _get_router_id(db: Session) -> int | None:
    """Get the current router ID by name."""
    r = db.query(Router).filter_by(name=settings.router_name).first()
    return r.id if r else None


@router.get("/status")
def api_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Current system status — KPI cards data."""
    router_id = _get_router_id(db)
    if router_id is None:
        return {"error": "No router configured", "is_online": False}
    return get_current_status(db, router_id)


@router.get("/traffic/24h")
def api_traffic_24h(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Traffic data points for the last 24 hours."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_traffic_history(db, router_id, hours=24)


@router.get("/traffic/7d")
def api_traffic_7d(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Traffic data points for the last 7 days."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_traffic_history(db, router_id, hours=168)


@router.get("/traffic/daily")
def api_traffic_daily(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Daily traffic consumption totals."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_daily_consumption(db, router_id)


@router.get("/cpu/history")
def api_cpu_history(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """CPU load data points for the last 24 hours."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_cpu_history(db, router_id)


@router.get("/ram/history")
def api_ram_history(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """RAM usage data points for the last 24 hours."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_ram_history(db, router_id)


@router.get("/users/history")
def api_users_history(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Concurrent user count over the last 24 hours."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_users_history(db, router_id)


@router.get("/users/unified")
def api_users_unified(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Unified users merged from DHCP, ARP, PPP, WireGuard, and Simple Queues."""
    router_id = _get_router_id(db)
    if router_id is None:
        return {
            "counts": {"oficina": 0, "vpn": 0, "vm": 0, "offline": 0, "total_active": 0, "total_all": 0},
            "oficina": [],
            "vpn": [],
            "vm": [],
            "offline": [],
            "all": [],
        }
    return get_unified_users(db, router_id)


@router.get("/vpn/summary")
def api_vpn_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """VPN summary card metrics."""
    router_id = _get_router_id(db)
    if router_id is None:
        return {
            "connected_users": 0,
            "avg_session_time": "0s",
            "max_session_time": {"user": "—", "time": "—"},
            "last_connection": {"user": "—", "ip": "—", "time": None},
            "protocols_detected": [],
            "vpn_alerts_count": 0,
        }
    return get_vpn_summary(db, router_id)


@router.get("/top-consumers")
def api_top_consumers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Top 10 client devices by traffic volume."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_top_consumers(db, router_id)


@router.get("/interfaces")
def api_interfaces(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Current interface status and traffic."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_interfaces_status(db, router_id)


@router.get("/alerts")
def api_alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Active and recent alerts."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_active_alerts(db, router_id)


@router.get("/outages")
def api_outages(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Historical connectivity outages."""
    router_id = _get_router_id(db)
    if router_id is None:
        return []
    return get_outage_history(db, router_id)


# ── New Multi-Device Endpoints ──────────────────────────────────

@router.get("/infrastructure/kpis")
def api_infrastructure_kpis(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Global infrastructure KPIs (APs, WiFi clients, SSIDs, availability)."""
    from app.services.wifi_service import get_wifi_summary, get_ap_status

    wifi = get_wifi_summary(db)
    aps = get_ap_status(db)

    total_aps = len(aps)
    online_aps = sum(1 for a in aps if a["is_reachable"])
    availability = round((online_aps / total_aps) * 100) if total_aps > 0 else 0

    return {
        "total_aps": total_aps,
        "online_aps": online_aps,
        "wifi_clients": wifi["total_clients"],
        "total_ssids": wifi["total_ssids"],
        "availability": availability,
    }


@router.get("/devices")
def api_devices(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all managed devices."""
    from app.models.device import Device

    devices = db.query(Device).filter_by(is_managed=True).all()
    return [
        {
            "id": d.id,
            "name": d.name,
            "type": d.device_type,
            "host": d.host,
            "model": d.model,
            "firmware": d.firmware,
            "is_reachable": d.is_reachable,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in devices
    ]


@router.get("/wifi/summary")
def api_wifi_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """WiFi SSIDs with aggregated client counts across all APs."""
    from app.services.wifi_service import get_wifi_summary
    return get_wifi_summary(db)


@router.get("/wifi/history")
def api_wifi_history(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """WiFi client count history per SSID (24h, hourly)."""
    from app.services.wifi_service import get_wifi_history
    return get_wifi_history(db)


@router.get("/wifi/aps")
def api_wifi_aps(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Status of all Ubiquiti APs."""
    from app.services.wifi_service import get_ap_status
    return get_ap_status(db)


@router.get("/networks")
def api_networks(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List of networks with device counts."""
    from app.services.network_service import get_networks_overview
    return get_networks_overview(db)


@router.get("/topology")
def api_topology(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Infrastructure topology tree data."""
    from app.services.network_service import get_topology
    return get_topology(db)


@router.get("/wan/status")
def api_wan_status(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Multi-ISP WAN status cards data."""
    from app.services.wan_service import get_current_wan_status
    return get_current_wan_status(db)

