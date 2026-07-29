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
