"""
Interface snapshot model — per-interface traffic and status.

Stored alongside each ResourceSnapshot to track individual
interface performance over time.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class InterfaceSnapshot(Base):
    """Point-in-time interface state capture."""

    __tablename__ = "interface_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    router_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routers.id"), nullable=False, index=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resource_snapshots.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow
    )

    # Interface identity
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    iface_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Traffic counters (cumulative)
    rx_bytes: Mapped[int] = mapped_column(Integer, default=0)
    tx_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Calculated rates
    rx_bps: Mapped[int] = mapped_column(Integer, default=0)
    tx_bps: Mapped[int] = mapped_column(Integer, default=0)

    # Link info
    link_speed: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    snapshot: Mapped["ResourceSnapshot"] = relationship(  # noqa: F821
        back_populates="interfaces"
    )

    def __repr__(self) -> str:
        status = "up" if self.is_running else "down"
        return f"<Interface {self.name!r} {status}>"
