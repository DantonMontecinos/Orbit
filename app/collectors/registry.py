"""
Collector registry — maps device types to their collectors.
"""

from app.collectors.base import BaseCollector
from app.collectors.mikrotik.collector import MikroTikCollector
from app.collectors.ubiquiti.collector import UnifiCollector
from app.collectors.ping.collector import PingCollector

# Vendor-specific collectors
COLLECTORS: dict[str, BaseCollector] = {
    "mikrotik": MikroTikCollector(),
    "ubiquiti": UnifiCollector(),
}

# Universal ping collector
PING_COLLECTOR = PingCollector()


def get_collector(device_type: str) -> BaseCollector | None:
    """Get the appropriate collector for a device type."""
    return COLLECTORS.get(device_type)
