"""
WiFi snapshot model — per-VAP wireless metrics.

Each row represents a single SSID on a single radio of a single AP
at a point in time. Discovered automatically via mca-dump on
Ubiquiti APs.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class WifiSnapshot(Base):
    """Point-in-time WiFi VAP (Virtual AP) metrics."""

    __tablename__ = "wifi_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    # WiFi identity
    ssid: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    radio: Mapped[str] = mapped_column(String(10), nullable=False)  # "2.4GHz" | "5GHz"
    bssid: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metrics
    client_count: Mapped[int] = mapped_column(Integer, default=0)
    tx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    rx_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    device: Mapped["Device"] = relationship(back_populates="wifi_snapshots")  # noqa: F821

    def __repr__(self) -> str:
        return f"<WifiSnapshot ssid={self.ssid!r} clients={self.client_count}>"
