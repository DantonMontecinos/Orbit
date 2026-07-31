"""
WiFi data service — aggregates WiFi metrics across APs.

Provides pre-computed data for the WiFi dashboard view,
aggregating per-SSID client counts across all APs.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_snapshot import DeviceSnapshot
from app.models.wifi_snapshot import WifiSnapshot
from app.utils.formatters import format_bytes, utcnow


def get_wifi_summary(db: Session) -> dict[str, Any]:
    """
    Get aggregated WiFi summary across all APs.

    Returns SSIDs with total client counts (summed across APs),
    plus global WiFi KPIs.
    """
    # Get the latest timestamp from wifi_snapshots
    latest_ts = (
        db.query(func.max(WifiSnapshot.timestamp))
        .scalar()
    )

    if not latest_ts:
        return {
            "ssids": [],
            "total_clients": 0,
            "total_aps": 0,
            "total_ssids": 0,
        }

    # Get all WiFi snapshots from the latest cycle
    # (within 60s window to account for collection timing differences)
    window_start = latest_ts - timedelta(seconds=60)

    latest_snaps = (
        db.query(WifiSnapshot)
        .filter(WifiSnapshot.timestamp >= window_start)
        .all()
    )

    # Aggregate by SSID (sum clients across all APs, combine 2.4+5GHz)
    ssid_data: dict[str, dict[str, Any]] = {}
    ap_ids: set[int] = set()

    for snap in latest_snaps:
        ap_ids.add(snap.device_id)
        key = snap.ssid
        if key not in ssid_data:
            ssid_data[key] = {
                "name": snap.ssid,
                "client_count": 0,
                "ap_count": 0,
                "tx_bytes": 0,
                "rx_bytes": 0,
                "ap_ids": set(),
                "radios": set(),
            }
        ssid_data[key]["client_count"] += snap.client_count
        ssid_data[key]["tx_bytes"] += snap.tx_bytes
        ssid_data[key]["rx_bytes"] += snap.rx_bytes
        ssid_data[key]["ap_ids"].add(snap.device_id)
        ssid_data[key]["radios"].add(snap.radio)

    ssids = []
    for name, data in sorted(ssid_data.items(), key=lambda x: x[1]["client_count"], reverse=True):
        ssids.append({
            "name": name,
            "client_count": data["client_count"],
            "ap_count": len(data["ap_ids"]),
            "radios": sorted(data["radios"]),
            "tx_bytes_fmt": format_bytes(data["tx_bytes"]),
            "rx_bytes_fmt": format_bytes(data["rx_bytes"]),
        })

    total_clients = sum(s["client_count"] for s in ssids)

    return {
        "ssids": ssids,
        "total_clients": total_clients,
        "total_aps": len(ap_ids),
        "total_ssids": len(ssids),
    }


def get_wifi_history(
    db: Session,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """
    Get WiFi client count history aggregated per SSID per hour.

    Returns data points for Chart.js time series.
    """
    since = utcnow() - timedelta(hours=hours)

    # Get aggregated data per SSID per hour
    results = (
        db.query(
            func.strftime("%Y-%m-%dT%H:00:00", WifiSnapshot.timestamp).label("hour"),
            WifiSnapshot.ssid,
            func.sum(WifiSnapshot.client_count).label("total_clients"),
        )
        .filter(WifiSnapshot.timestamp >= since)
        .group_by("hour", WifiSnapshot.ssid)
        .order_by("hour")
        .all()
    )

    return [
        {
            "time": r.hour,
            "ssid": r.ssid,
            "clients": r.total_clients or 0,
        }
        for r in results
    ]


def get_ap_status(db: Session) -> list[dict[str, Any]]:
    """Get current status of all Ubiquiti APs."""
    devices = (
        db.query(Device)
        .filter_by(device_type="ubiquiti", is_managed=True)
        .all()
    )

    result = []
    for device in devices:
        # Get latest device snapshot
        snap = (
            db.query(DeviceSnapshot)
            .filter_by(device_id=device.id)
            .order_by(DeviceSnapshot.timestamp.desc())
            .first()
        )

        # Get latest WiFi snapshots for this AP
        wifi_snaps = []
        if snap:
            window_start = snap.timestamp - timedelta(seconds=60)
            wifi_snaps = (
                db.query(WifiSnapshot)
                .filter(
                    WifiSnapshot.device_id == device.id,
                    WifiSnapshot.timestamp >= window_start,
                )
                .all()
            )

        total_clients = sum(w.client_count for w in wifi_snaps)
        ssids = list({w.ssid for w in wifi_snaps})

        result.append({
            "id": device.id,
            "name": device.name,
            "host": device.host,
            "model": device.model or "—",
            "firmware": device.firmware or "—",
            "is_reachable": device.is_reachable,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "cpu_load": snap.cpu_load if snap else None,
            "ram_percent": snap.ram_percent if snap else None,
            "uptime_seconds": snap.uptime_seconds if snap else None,
            "client_count": total_clients,
            "ssids": ssids,
            "latency_ms": snap.latency_ms if snap else None,
        })

    return result
