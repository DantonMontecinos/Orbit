"""
Network model — represents a logical network segment.

Prepared for future VLAN support. Currently stores a single
LAN entry that is auto-seeded on first initialization.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class Network(Base):
    """Logical network segment (LAN, VLAN, etc.)."""

    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway: Mapped[str] = mapped_column(String(45), nullable=False)
    subnet: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    devices: Mapped[list["Device"]] = relationship(  # noqa: F821
        back_populates="network", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Network name={self.name!r} gateway={self.gateway!r}>"
