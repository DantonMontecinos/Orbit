"""
Collection orchestrator — runs all collectors for managed devices.

Executes independently of the legacy MikroTik collection cycle.
If any single device collector fails, the others continue.
"""

from typing import Any

from app.collectors.registry import get_collector, PING_COLLECTOR
from app.config import settings
from app.database import SessionLocal
from app.models.device import Device
from app.models.device_snapshot import DeviceSnapshot
from app.models.wifi_snapshot import WifiSnapshot
from app.utils.formatters import utcnow
from app.utils.logger import get_logger

log = get_logger("collectors.orchestrator")


def run_device_collection() -> None:
    """
    Execute a collection cycle for all non-MikroTik managed devices.

    MikroTik is handled by the legacy run_collection() in tasks.py.
    This orchestrator handles Ubiquiti APs and any future device types.
    """
    from app.database import _seed_devices
    _seed_devices()

    db = SessionLocal()
    try:
        devices = (
            db.query(Device)
            .filter(
                Device.is_managed == True,  # noqa: E712
                Device.device_type != "mikrotik",  # MikroTik handled by legacy
            )
            .all()
        )

        if not devices:
            return

        now = utcnow()

        for device in devices:
            try:
                _collect_device(db, device, now)
            except Exception:
                log.exception("Collection failed for device %s", device.name)
                # Continue with next device — never crash the loop

        db.commit()

    except Exception:
        log.exception("Device collection cycle failed")
        db.rollback()
    finally:
        db.close()


def _collect_device(db: Any, device: Device, now: Any) -> None:
    """Collect metrics for a single device."""
    # 1. Ping check
    ping_result = PING_COLLECTOR.collect(device)
    is_reachable = ping_result.get("is_reachable", False)
    latency_ms = ping_result.get("latency_ms")

    # 2. Vendor-specific collection
    collector = get_collector(device.device_type)
    data: dict[str, Any] = {}
    if collector:
        data = collector.collect(device)
        is_reachable = data.get("is_reachable", is_reachable)

    # 3. Update device record
    device.is_reachable = is_reachable
    if is_reachable:
        device.last_seen = now
        if data.get("model"):
            device.model = data["model"]
        if data.get("firmware"):
            device.firmware = data["firmware"]

    # 4. Save device snapshot
    total_clients = 0
    vap_table = data.get("vap_table", [])
    total_clients = sum(v.get("client_count", 0) for v in vap_table)

    snapshot = DeviceSnapshot(
        device_id=device.id,
        timestamp=now,
        is_reachable=is_reachable,
        latency_ms=latency_ms,
        cpu_load=data.get("cpu_load"),
        ram_used=data.get("ram_used"),
        ram_total=data.get("ram_total"),
        uptime_seconds=data.get("uptime_seconds"),
        client_count=total_clients,
    )
    db.add(snapshot)

    # 5. Save WiFi snapshots (for Ubiquiti APs)
    for vap in vap_table:
        wifi_snap = WifiSnapshot(
            device_id=device.id,
            timestamp=now,
            ssid=vap["ssid"],
            radio=vap.get("radio", "unknown"),
            bssid=vap.get("bssid"),
            channel=vap.get("channel"),
            client_count=vap.get("client_count", 0),
            tx_bytes=vap.get("tx_bytes", 0),
            rx_bytes=vap.get("rx_bytes", 0),
        )
        db.add(wifi_snap)

    status = "🟢" if is_reachable else "🔴"
    log.info(
        "%s %s | clients=%d latency=%s",
        status,
        device.name,
        total_clients,
        f"{latency_ms:.0f}ms" if latency_ms else "—",
    )
