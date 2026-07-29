"""
Alert model — records detected anomalies and outages.

Alerts follow a lifecycle: created when a condition triggers,
updated while active, and closed (with duration) when resolved.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.utils.formatters import utcnow


class Alert(Base):
    """Infrastructure alert event."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    router_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("routers.id"), nullable=False, index=True
    )

    # Classification
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # internet_down, router_unreachable, cpu_high, ram_high, interface_down
    severity: Mapped[str] = mapped_column(
        String(20), default="warning"
    )  # critical, warning, info

    # Details
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Lifecycle
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    router: Mapped["Router"] = relationship(back_populates="alerts")  # noqa: F821

    def __repr__(self) -> str:
        status = "ACTIVE" if self.is_active else "RESOLVED"
        return f"<Alert {self.alert_type!r} [{status}]>"

    def resolve(self) -> None:
        """Mark alert as resolved and calculate duration."""
        now = utcnow()
        self.is_active = False
        self.ended_at = now
        if self.started_at:
            self.duration_seconds = int((now - self.started_at).total_seconds())
