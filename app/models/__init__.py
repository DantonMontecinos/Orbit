"""
ORM Models package.

All models share a single declarative Base so SQLAlchemy can
manage the schema in one `create_all()` call.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Import all models so Base.metadata registers them.
from app.models.alert import Alert  # noqa: E402, F401
from app.models.client_device import ClientDevice  # noqa: E402, F401
from app.models.interface import InterfaceSnapshot  # noqa: E402, F401
from app.models.router import Router  # noqa: E402, F401
from app.models.snapshot import ResourceSnapshot  # noqa: E402, F401

__all__ = [
    "Base",
    "Alert",
    "ClientDevice",
    "InterfaceSnapshot",
    "Router",
    "ResourceSnapshot",
]
