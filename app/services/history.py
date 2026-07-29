"""
History and maintenance service.

Provides outage history queries and data retention management.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.alert import Alert
from app.models.interface import InterfaceSnapshot
from app.models.snapshot import ResourceSnapshot
from app.utils.formatters import format_uptime, utcnow
from app.utils.logger import get_logger

log = get_logger("services.history")


def get_outage_history(
    db: Session,
    router_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Get history of connectivity outages (resolved alerts).

    Returns internet_down and router_unreachable alerts with
    calculated durations.
    """
    outage_types = ("internet_down", "router_unreachable")

    outages = (
        db.query(Alert)
        .filter(
            Alert.router_id == router_id,
            Alert.alert_type.in_(outage_types),
        )
        .order_by(Alert.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "type": o.alert_type,
            "severity": o.severity,
            "message": o.message,
            "started_at": o.started_at.isoformat() if o.started_at else None,
            "ended_at": o.ended_at.isoformat() if o.ended_at else None,
            "duration": o.duration_seconds,
            "duration_fmt": format_uptime(o.duration_seconds) if o.duration_seconds else "ongoing",
            "is_active": o.is_active,
        }
        for o in outages
    ]


def purge_old_data() -> None:
    """
    Delete snapshots and interface data older than retention period.

    Called daily by the scheduler. Keeps alerts indefinitely for
    audit purposes.
    """
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(
            days=settings.data_retention_days
        )

        # Delete old interface snapshots
        iface_deleted = (
            db.query(InterfaceSnapshot)
            .filter(InterfaceSnapshot.timestamp < cutoff)
            .delete()
        )

        # Delete old resource snapshots
        snap_deleted = (
            db.query(ResourceSnapshot)
            .filter(ResourceSnapshot.timestamp < cutoff)
            .delete()
        )

        db.commit()

        if iface_deleted or snap_deleted:
            log.info(
                "Purged %d snapshots and %d interface records (older than %d days)",
                snap_deleted,
                iface_deleted,
                settings.data_retention_days,
            )
    except Exception:
        log.exception("Failed to purge old data")
        db.rollback()
    finally:
        db.close()
