"""
APScheduler configuration for periodic data collection.

Uses BackgroundScheduler (threaded) integrated with FastAPI's
lifespan context manager. Jobs:
- collect: runs every N seconds (configurable)
- purge: runs daily at 03:00 to clean old data
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("collector.scheduler")

scheduler = BackgroundScheduler(
    job_defaults={
        "coalesce": True,       # Merge missed runs into one
        "max_instances": 1,     # Never overlap
        "misfire_grace_time": 30,
    },
    timezone="UTC",
)


def start_scheduler() -> None:
    """Register jobs and start the scheduler."""
    from app.collector.tasks import run_collection
    from app.collectors.orchestrator import run_device_collection
    from app.services.history import purge_old_data

    # Main MikroTik collection job (legacy — unchanged)
    scheduler.add_job(
        run_collection,
        trigger="interval",
        seconds=settings.collect_interval_seconds,
        id="collect_metrics",
        name="Collect MikroTik metrics",
        replace_existing=True,
    )

    # Multi-device collection (Ubiquiti, Ping, future vendors)
    scheduler.add_job(
        run_device_collection,
        trigger="interval",
        seconds=settings.collect_interval_seconds,
        id="collect_devices",
        name="Collect device metrics (Ubiquiti/Ping)",
        replace_existing=True,
    )

    # Daily data purge
    scheduler.add_job(
        purge_old_data,
        trigger="cron",
        hour=3,
        minute=0,
        id="purge_old_data",
        name="Purge old snapshots",
        replace_existing=True,
    )

    scheduler.start()
    log.info(
        "Scheduler started — collecting every %ds",
        settings.collect_interval_seconds,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
