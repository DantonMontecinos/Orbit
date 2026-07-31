"""
MikroTik collector adapter.

Wraps the existing MikroTikClient as a BaseCollector so it can
be used by the new orchestrator. The original client.py and
tasks.py remain unchanged — this is purely an adapter layer.
"""

from typing import Any

from app.collectors.base import BaseCollector
from app.collector.client import MikroTikClient
from app.utils.logger import get_logger

log = get_logger("collectors.mikrotik")


class MikroTikCollector(BaseCollector):
    """Adapter that wraps the existing MikroTikClient as a BaseCollector."""

    name = "mikrotik"

    def is_compatible(self, device: Any) -> bool:
        """Check if device is a MikroTik."""
        return getattr(device, "device_type", "") == "mikrotik"

    def collect(self, device: Any) -> dict[str, Any]:
        """
        Collect metrics from a MikroTik device.

        Uses the existing MikroTikClient.collect_all() and returns
        the normalized data. Never raises.
        """
        try:
            client = MikroTikClient(
                host=device.host,
                port=device.port or 8728,
            )
            data = client.collect_all()

            # Extract system info
            res = data.get("system_resource", {})
            identity = data.get("system_identity", {})

            return {
                "is_reachable": data.get("is_reachable", False),
                "model": res.get("board-name"),
                "firmware": res.get("version"),
                "cpu_load": int(res.get("cpu-load", 0)),
                "ram_used": int(res.get("total-memory", 0)) - int(res.get("free-memory", 0)),
                "ram_total": int(res.get("total-memory", 0)),
                "uptime_seconds": None,  # Parsed by tasks.py
                "identity": identity.get("name"),
                "client_count": len([
                    l for l in data.get("dhcp_leases", [])
                    if l.get("status") == "bound"
                ]),
                # Pass through raw data for legacy tasks.py processing
                "_raw": data,
            }
        except Exception:
            log.exception("MikroTik collection failed for %s", device.host)
            return {"is_reachable": False}
