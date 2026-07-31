"""
Ping collector — checks device reachability.

Uses system ping command (no extra dependencies).
Works on both Windows and Linux/Docker.
"""

import platform
import subprocess
import re
from typing import Any

from app.collectors.base import BaseCollector
from app.utils.logger import get_logger

log = get_logger("collectors.ping")


import time
import socket

class PingCollector(BaseCollector):
    """ICMP ping & TCP socket reachability collector."""

    name = "ping"

    def is_compatible(self, device: Any) -> bool:
        """Ping works for any device type."""
        return True

    def collect(self, device: Any) -> dict[str, Any]:
        """
        Ping a device and return reachability + latency.

        Tries ICMP ping CLI first; falls back to TCP socket probe if ping is not installed.
        Returns:
            {"is_reachable": bool, "latency_ms": float | None}
        """
        host = getattr(device, "host", str(device))
        port = getattr(device, "port", None) or (22 if getattr(device, "device_type", "") == "ubiquiti" else 8728)

        # 1. Try ICMP ping command
        try:
            is_windows = platform.system().lower() == "windows"
            cmd = ["ping", "-n", "1", "-w", "2000", host] if is_windows else ["ping", "-c", "1", "-W", "2", host]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                match = re.search(r"time[=<]([\d.]+)\s*ms", result.stdout, re.IGNORECASE)
                latency_ms = float(match.group(1)) if match else None
                return {"is_reachable": True, "latency_ms": latency_ms}
        except (FileNotFoundError, OSError):
            pass  # ping binary missing in slim container, fall through to socket probe
        except Exception:
            pass

        # 2. Fallback: TCP Socket Probe
        try:
            start_t = time.perf_counter()
            conn = socket.create_connection((host, port), timeout=3)
            elapsed_ms = round((time.perf_counter() - start_t) * 1000, 1)
            conn.close()
            return {"is_reachable": True, "latency_ms": elapsed_ms}
        except Exception as e:
            log.warning("Socket probe failed for %s:%s: %s", host, port, e)
            return {"is_reachable": False, "latency_ms": None}
