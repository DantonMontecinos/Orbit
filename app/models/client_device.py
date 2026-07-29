"""
Client device model — tracks DHCP/ARP/PPP connected devices.

This is NOT historical — it stores the last-known state of each
device (identified by MAC address per router). Updated in-place
on each collection cycle.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.utils.formatters import utcnow


class ClientDevice(Base):
    """Last-known state of a connected device."""

    __tablename__ = "client_devices"
    __table_args__ = (
        UniqueConstraint("router_id", "mac_address", name="uq_router_mac"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    router_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routers.id"), nullable=False, index=True
    )

    # Identity
    mac_address: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Source of discovery and classification
    source: Mapped[str] = mapped_column(
        String(20), default="arp"
    )  # "dhcp" | "arp" | "ppp" | "wireguard"
    device_type: Mapped[str] = mapped_column(
        String(20), default="lan"
    )  # "lan" | "vpn" | "vm" | "offline"
    interface: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # VPN Details (if applicable)
    vpn_user: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vpn_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "WireGuard" | "L2TP" | "PPTP" | "SSTP" | "OpenVPN"
    session_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Simple Queue (if associated)
    queue_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    queue_max_limit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    queue_rx_bps: Mapped[int] = mapped_column(Integer, default=0)
    queue_tx_bps: Mapped[int] = mapped_column(Integer, default=0)
    queue_rx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    queue_tx_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow
    )

    # Traffic (if available from DHCP lease or queue stats)
    total_rx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_tx_bytes: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<Client {self.ip_address} type={self.device_type} mac={self.mac_address!r}>"
