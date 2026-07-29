"""
Router model — stores connection configuration and identity.

Designed with multi-router support in mind: every metric snapshot
references a specific router via `router_id` FK.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class Router(Base):
    """MikroTik router device registration."""

    __tablename__ = "routers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=8728)
    identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    board_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Relationships
    snapshots: Mapped[list["ResourceSnapshot"]] = relationship(  # noqa: F821
        back_populates="router", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        back_populates="router", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Router name={self.name!r} host={self.host!r}>"
