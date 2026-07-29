"""
Data formatting and parsing utilities.

Handles conversion of RouterOS-specific formats (uptime strings,
byte counts, etc.) into Python-native types for storage and display.
"""

from datetime import datetime, timezone
import re
from typing import Any


def utcnow() -> datetime:
    """Return current naive UTC datetime for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_uptime(uptime_str: str) -> int:
    """
    Parse RouterOS uptime string into total seconds.

    Examples:
        "1w5d7h54m27s" → 1_073_667
        "3d12h5m"      → 302_700
        "45m12s"        → 2_712
    """
    if not uptime_str:
        return 0

    pattern = re.compile(
        r"(?:(\d+)w)?"
        r"(?:(\d+)d)?"
        r"(?:(\d+)h)?"
        r"(?:(\d+)m)?"
        r"(?:(\d+)s)?"
    )
    match = pattern.match(uptime_str.strip())
    if not match:
        return 0

    weeks, days, hours, minutes, seconds = (
        int(g) if g else 0 for g in match.groups()
    )
    return (
        weeks * 604_800
        + days * 86_400
        + hours * 3_600
        + minutes * 60
        + seconds
    )


def format_uptime(seconds: int) -> str:
    """
    Format seconds into a human-readable uptime string.

    Example: 93784 → "1d 2h 3m"
    """
    if seconds <= 0:
        return "0s"

    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts and secs:
        parts.append(f"{secs}s")

    return " ".join(parts)


def format_bytes(value: int | float) -> str:
    """
    Format byte count into human-readable string.

    Example: 1_500_000_000 → "1.40 GB"
    """
    if value < 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(value)

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[unit_index]}"


def format_bps(bits_per_second: int | float) -> str:
    """
    Format bits-per-second into human-readable string.

    Example: 125_000_000 → "125.00 Mbps"
    """
    if bits_per_second < 0:
        return "0 bps"

    units = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"]
    unit_index = 0
    size = float(bits_per_second)

    while size >= 1000.0 and unit_index < len(units) - 1:
        size /= 1000.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} bps"
    return f"{size:.2f} {units[unit_index]}"


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int, returning default on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_routeros_rate(rate_str: str) -> int:
    """
    Parse RouterOS rate string to bits per second.

    Examples:
        "1000000"   → 1_000_000  (raw bps)
        "125.0Mbps" → 125_000_000
    """
    if not rate_str:
        return 0

    rate_str = rate_str.strip().lower()

    multipliers = {
        "tbps": 1_000_000_000_000,
        "gbps": 1_000_000_000,
        "mbps": 1_000_000,
        "kbps": 1_000,
        "bps": 1,
        "t": 1_000_000_000_000,
        "g": 1_000_000_000,
        "m": 1_000_000,
        "k": 1_000,
    }

    for suffix, mult in multipliers.items():
        if rate_str.endswith(suffix):
            num = rate_str[: -len(suffix)]
            return int(safe_float(num) * mult)

    return safe_int(rate_str)


def format_queue_limit(limit_str: str | None) -> str:
    """
    Format a RouterOS queue limit/rate string into concise Mbps (e.g. '15/30').

    Examples:
        "15000000/30000000" → "15/30"
        "15M/30M"           → "15/30"
        "0/0" or None       → "Sin límite"
    """
    if not limit_str or limit_str in ("0/0", "0", "unlimited"):
        return "Sin límite"

    parts = limit_str.strip().split("/")
    if len(parts) != 2:
        return limit_str

    formatted_parts = []
    for part in parts:
        part_clean = part.strip()
        if not part_clean or part_clean == "0":
            formatted_parts.append("0")
            continue
        bps = parse_routeros_rate(part_clean)
        if bps <= 0:
            formatted_parts.append("0")
            continue
        mbps = bps / 1_000_000.0
        if mbps >= 1:
            if mbps.is_integer():
                formatted_parts.append(str(int(mbps)))
            else:
                formatted_parts.append(f"{mbps:.1f}".rstrip("0").rstrip("."))
        else:
            kbps = bps / 1000.0
            if kbps.is_integer():
                formatted_parts.append(f"{int(kbps)}k")
            else:
                formatted_parts.append(f"{mbps:.2f}".rstrip("0").rstrip("."))

    return "/".join(formatted_parts)

