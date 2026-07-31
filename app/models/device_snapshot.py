"""
Device snapshot model — periodic device-level metrics.

Stores a point-in-time capture of CPU, RAM, uptime, and client
count for any managed device (MikroTik, Ubiquiti, etc.).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class DeviceSnapshot(Base):
    """Point-in-time device metrics capture."""

    __tablename__ = "device_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    # Connectivity
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # System resources (optional — not all devices expose these)
    cpu_load: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ram_used: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bytes
    ram_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bytes
    uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Aggregate client count
    client_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    device: Mapped["Device"] = relationship(back_populates="device_snapshots")  # noqa: F821

    def __repr__(self) -> str:
        return f"<DeviceSnapshot device_id={self.device_id} ts={self.timestamp}>"

    @property
    def ram_percent(self) -> float:
        """RAM usage as a percentage."""
        if not self.ram_total or self.ram_total <= 0 or not self.ram_used:
            return 0.0
        return round((self.ram_used / self.ram_total) * 100, 1)
