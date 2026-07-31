"""
SQLAlchemy engine and session factory.

Uses SQLite with WAL mode for concurrent read/write access
without blocking. The engine is configured for optimal
performance with a single-file database.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:  # noqa: ANN001
    """Enable WAL mode and optimize SQLite for our workload."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64 MB cache
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session, ensuring cleanup on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables if they don't exist and migrate missing columns."""
    from sqlalchemy import text
    from app.models import Base  # noqa: F811

    Base.metadata.create_all(bind=engine)

    # Automatic schema migration for existing SQLite databases
    with engine.connect() as conn:
        # Check columns of client_devices
        res = conn.execute(text("PRAGMA table_info(client_devices)"))
        existing_cols = {row[1] for row in res.fetchall()}

        new_cols_client = [
            ("device_type", "VARCHAR(20) DEFAULT 'lan'"),
            ("vpn_user", "VARCHAR(100) NULL"),
            ("vpn_type", "VARCHAR(20) NULL"),
            ("session_time", "VARCHAR(100) NULL"),
            ("session_seconds", "INTEGER DEFAULT 0"),
            ("queue_name", "VARCHAR(100) NULL"),
            ("queue_max_limit", "VARCHAR(50) NULL"),
            ("queue_rx_bps", "INTEGER DEFAULT 0"),
            ("queue_tx_bps", "INTEGER DEFAULT 0"),
            ("queue_rx_bytes", "INTEGER DEFAULT 0"),
            ("queue_tx_bytes", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in new_cols_client:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE client_devices ADD COLUMN {col_name} {col_type}"))

        # Check columns of resource_snapshots
        res = conn.execute(text("PRAGMA table_info(resource_snapshots)"))
        existing_cols_snap = {row[1] for row in res.fetchall()}

        new_cols_snap = [
            ("vpn_user_count", "INTEGER DEFAULT 0"),
            ("vpn_types_detected", "VARCHAR(100) NULL"),
        ]
        for col_name, col_type in new_cols_snap:
            if col_name not in existing_cols_snap:
                conn.execute(text(f"ALTER TABLE resource_snapshots ADD COLUMN {col_name} {col_type}"))

        conn.commit()

    # Seed default network and devices from config
    _seed_devices()


def _seed_devices() -> None:
    """Register default network and devices from environment config."""
    from app.config import settings
    from app.models.device import Device
    from app.models.network import Network

    db = SessionLocal()
    try:
        # Seed default network if none exists
        network = db.query(Network).first()
        if not network:
            network = Network(
                name="LAN Principal",
                description="Red local principal",
                gateway=settings.router_host,
                subnet="192.168.0.0/21",
            )
            db.add(network)
            db.flush()

        # Seed MikroTik device
        mk_device = (
            db.query(Device)
            .filter_by(device_type="mikrotik", host=settings.router_host)
            .first()
        )
        if not mk_device:
            mk_device = Device(
                network_id=network.id if network else None,
                name=settings.router_name,
                device_type="mikrotik",
                host=settings.router_host,
                port=settings.router_port,
                is_managed=True,
            )
            db.add(mk_device)

        # Seed Ubiquiti devices from env vars
        for ubnt_cfg in settings.ubiquiti_devices:
            existing = (
                db.query(Device)
                .filter_by(device_type="ubiquiti", host=ubnt_cfg["host"])
                .first()
            )
            if not existing:
                db.add(Device(
                    network_id=network.id if network else None,
                    name=ubnt_cfg["name"],
                    device_type="ubiquiti",
                    host=ubnt_cfg["host"],
                    port=22,
                    is_managed=True,
                ))

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

