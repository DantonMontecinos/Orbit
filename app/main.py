"""
Orbit — FastAPI Application Entry Point.

Wires together all components:
- Database initialization
- APScheduler startup/shutdown via lifespan
- API route registration
- Static file serving
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as api_router
from app.api.views import router as views_router
from app.collector.scheduler import start_scheduler, stop_scheduler
from app.database import init_db
from app.utils.logger import get_logger

log = get_logger("main")

_BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.

    Startup:  Create DB tables → Start collection scheduler
    Shutdown: Stop scheduler gracefully
    """
    log.info("=" * 50)
    log.info("Orbit — Starting up")
    log.info("=" * 50)

    # Initialize database
    init_db()
    log.info("Database initialized")

    # Start the metric collection scheduler
    start_scheduler()

    yield

    # Shutdown
    stop_scheduler()
    log.info("Orbit — Shut down complete")


app = FastAPI(
    title="Orbit",
    description="Orbit — Read-Only Network Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

# Register routers
app.include_router(api_router)
app.include_router(views_router)


@app.get("/health")
def health_check():
    """Health check endpoint for Docker healthcheck."""
    return {"status": "ok"}

