"""
WAN snapshot model — stores ISP link status history.

Captures point-in-time state for each configured WAN link:
status (online/offline), IP WAN address, interface name,
and current throughput.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base
from app.utils.formatters import utcnow


class WanSnapshot(Base):
    """Point-in-time capture of ISP/WAN link status."""

    __tablename__ = "wan_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    isp_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    interface: Mapped[str] = mapped_column(String(100), nullable=False)

    # Link status: "online" | "offline" | "no-route" | "unknown"
    status: Mapped[str] = mapped_column(String(20), default="unknown")
    ip_wan: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Rates
    rx_bps: Mapped[int] = mapped_column(Integer, default=0)
    tx_bps: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<WanSnapshot isp={self.isp_name!r} status={self.status!r}>"
