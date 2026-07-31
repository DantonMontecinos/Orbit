"""
Base collector interface.

All vendor-specific collectors implement this ABC so the
orchestrator can treat them uniformly.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseCollector(ABC):
    """Abstract base class for infrastructure collectors."""

    name: str = "base"

    @abstractmethod
    def collect(self, device: Any) -> dict[str, Any]:
        """
        Collect metrics from a device.

        Returns a normalized dict with at minimum:
            - is_reachable: bool
        Additional keys depend on the collector type.
        Never raises — returns is_reachable=False on failure.
        """
        ...

    @abstractmethod
    def is_compatible(self, device: Any) -> bool:
        """Check if this collector can handle the given device type."""
        ...
