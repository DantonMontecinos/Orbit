"""
Device model — generic multi-vendor network device.

Supports MikroTik, Ubiquiti, switches, and other devices.
Each device belongs to an optional Network and can be monitored
by the appropriate collector based on device_type.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class Device(Base):
    """Infrastructure device (router, AP, switch, etc.)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("networks.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "mikrotik" | "ubiquiti" | "switch" | "other"
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_managed: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    network: Mapped["Network | None"] = relationship(back_populates="devices")  # noqa: F821
    device_snapshots: Mapped[list["DeviceSnapshot"]] = relationship(  # noqa: F821
        back_populates="device", cascade="all, delete-orphan"
    )
    wifi_snapshots: Mapped[list["WifiSnapshot"]] = relationship(  # noqa: F821
        back_populates="device", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Device name={self.name!r} type={self.device_type!r} host={self.host!r}>"
