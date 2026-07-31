"""
Network data service — queries for network overview.

Currently returns a single LAN. Prepared for future VLAN support.
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.network import Network


def get_networks_overview(db: Session) -> list[dict[str, Any]]:
    """Get list of networks with device counts."""
    networks = db.query(Network).filter_by(is_active=True).all()

    result = []
    for net in networks:
        device_count = (
            db.query(func.count(Device.id))
            .filter_by(network_id=net.id)
            .scalar()
            or 0
        )

        result.append({
            "id": net.id,
            "name": net.name,
            "description": net.description,
            "gateway": net.gateway,
            "subnet": net.subnet,
            "vlan_id": net.vlan_id,
            "device_count": device_count,
        })

    return result


def get_topology(db: Session) -> dict[str, Any]:
    """
    Get infrastructure topology tree.

    Returns a structure representing:
    Internet → ISPs → MikroTik → APs
    """
    from app.services.wan_service import get_current_wan_status

    devices = db.query(Device).filter_by(is_managed=True).all()
    isps = get_current_wan_status(db)

    mikrotiks = []
    aps = []

    for d in devices:
        item = {
            "id": d.id,
            "name": d.name,
            "type": d.device_type,
            "host": d.host,
            "model": d.model,
            "is_reachable": d.is_reachable,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        if d.device_type == "mikrotik":
            mikrotiks.append(item)
        elif d.device_type == "ubiquiti":
            aps.append(item)

    return {
        "isps": isps,
        "mikrotiks": mikrotiks,
        "aps": aps,
    }
