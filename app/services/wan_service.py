"""
WAN service — queries for Multi-ISP connectivity and status.

Provides data for the "Conectividad WAN" dashboard card grid
and topology ISP nodes. Reads from SQLite wan_snapshots.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.wan_snapshot import WanSnapshot
from app.utils.formatters import format_bps, utcnow


def get_current_wan_status(db: Session) -> list[dict[str, Any]]:
    """
    Get the current status of each configured ISP.

    Returns list of dicts:
    [
        {
            "name": "IPLAN",
            "interface": "ether10IPLAN",
            "status": "online", # "online" | "offline" | "unknown"
            "ip_wan": "190.x.x.x",
            "rx_bps": 12300000,
            "tx_bps": 4500000,
            "rx_fmt": "12.30 Mbps",
            "tx_fmt": "4.50 Mbps",
            "last_update": "2026-07-30T12:00:00",
        },
        ...
    ]
    """
    isp_configs = settings.isp_configs
    if not isp_configs:
        return []

    latest_ts = db.query(func.max(WanSnapshot.timestamp)).scalar()
    if not latest_ts:
        return [
            {
                "name": isp["name"],
                "interface": isp["interface"],
                "status": "unknown",
                "ip_wan": "—",
                "rx_bps": 0,
                "tx_bps": 0,
                "rx_fmt": "0 bps",
                "tx_fmt": "0 bps",
                "last_update": None,
            }
            for isp in isp_configs
        ]

    window_start = latest_ts - timedelta(seconds=60)
    latest_snaps = (
        db.query(WanSnapshot)
        .filter(WanSnapshot.timestamp >= window_start)
        .all()
    )
    snap_map = {s.isp_name: s for s in latest_snaps}

    result = []
    for isp in isp_configs:
        name = isp["name"]
        iface = isp["interface"]
        snap = snap_map.get(name)

        if snap:
            status = snap.status
            ip_wan = snap.ip_wan or "—"
            rx_bps = snap.rx_bps
            tx_bps = snap.tx_bps
            last_update = snap.timestamp.isoformat() if snap.timestamp else None
        else:
            status = "unknown"
            ip_wan = "—"
            rx_bps = 0
            tx_bps = 0
            last_update = None

        result.append({
            "name": name,
            "interface": iface,
            "status": status,
            "ip_wan": ip_wan,
            "rx_bps": rx_bps,
            "tx_bps": tx_bps,
            "rx_fmt": format_bps(rx_bps),
            "tx_fmt": format_bps(tx_bps),
            "last_update": last_update,
        })

    return result
