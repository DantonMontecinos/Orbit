"""
Ubiquiti UniFi collector.

Uses SSH to collect metrics from UAP devices via mca-dump.
Implements BaseCollector for use by the orchestrator.
"""

from typing import Any

from app.collectors.base import BaseCollector
from app.collectors.ubiquiti.ssh_client import UnifiSSHClient
from app.config import settings
from app.utils.logger import get_logger

log = get_logger("collectors.ubiquiti")


class UnifiCollector(BaseCollector):
    """Collector for Ubiquiti UniFi APs via SSH."""

    name = "ubiquiti"

    def is_compatible(self, device: Any) -> bool:
        """Check if device is a Ubiquiti AP."""
        return getattr(device, "device_type", "") == "ubiquiti"

    def _get_credentials(self, device: Any) -> dict[str, str]:
        """Get SSH credentials for the device from env config."""
        for cfg in settings.ubiquiti_devices:
            if cfg["host"] == device.host:
                return {"user": cfg["user"], "password": cfg["password"]}
        return {"user": "ubnt", "password": ""}

    def collect(self, device: Any) -> dict[str, Any]:
        """
        Collect metrics from a Ubiquiti AP.

        Returns normalized dict with system stats and vap_table.
        Never raises.
        """
        try:
            creds = self._get_credentials(device)
            client = UnifiSSHClient(
                host=device.host,
                username=creds["user"],
                password=creds["password"],
                port=device.port or 22,
            )
            return client.collect_all()
        except Exception:
            log.exception("Ubiquiti collection failed for %s", device.host)
            return {"is_reachable": False, "vap_table": []}
