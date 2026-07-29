"""
Orbit — Entry Point

Usage:
    python run.py
"""

import uvicorn

from app.config import settings


def main() -> None:
    """Start the Orbit application."""
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
