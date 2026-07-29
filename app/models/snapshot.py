"""
Resource snapshot model — periodic system metrics.

Each row represents a single collection cycle capturing CPU, RAM,
traffic counters, and aggregate client counts. These drive the
historical charts on the dashboard.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class ResourceSnapshot(Base):
    """Point-in-time system resource capture."""

    __tablename__ = "resource_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    router_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routers.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    # System resources
    cpu_load: Mapped[int] = mapped_column(Integer, default=0)
    ram_used: Mapped[int] = mapped_column(Integer, default=0)  # bytes
    ram_total: Mapped[int] = mapped_column(Integer, default=0)  # bytes
    uptime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Health sensors
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Connectivity
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=True)
    wan_status: Mapped[str] = mapped_column(String(20), default="unknown")

    # WAN traffic (cumulative counters from interface)
    total_rx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    total_tx_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Calculated rates (delta between snapshots)
    rx_bps: Mapped[int] = mapped_column(Integer, default=0)
    tx_bps: Mapped[int] = mapped_column(Integer, default=0)

    # Client counts
    dhcp_client_count: Mapped[int] = mapped_column(Integer, default=0)
    ppp_active_count: Mapped[int] = mapped_column(Integer, default=0)
    arp_count: Mapped[int] = mapped_column(Integer, default=0)
    vpn_user_count: Mapped[int] = mapped_column(Integer, default=0)
    vpn_types_detected: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    router: Mapped["Router"] = relationship(back_populates="snapshots")  # noqa: F821
    interfaces: Mapped[list["InterfaceSnapshot"]] = relationship(  # noqa: F821
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Snapshot router_id={self.router_id} ts={self.timestamp}>"

    @property
    def ram_percent(self) -> float:
        """RAM usage as a percentage."""
        if self.ram_total <= 0:
            return 0.0
        return round((self.ram_used / self.ram_total) * 100, 1)
