"""
Application configuration loaded from environment variables.

Uses pydantic-settings for validation and type coercion.
All values can be overridden via a .env file in the project root.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings with defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Router Connection ──────────────────────────────────────
    router_host: str = "192.168.88.1"
    router_port: int = 8728
    router_user: str = "admin"
    router_password: str = ""
    router_use_ssl: bool = False
    router_name: str = "main-router"
    router_wan_interface: str = "ether1"

    # ── Data Collection ────────────────────────────────────────
    collect_interval_seconds: int = 30

    # ── Database ───────────────────────────────────────────────
    db_path: str = "/data/orbit.db"

    # ── Data Retention ─────────────────────────────────────────
    data_retention_days: int = 30

    # ── Alert Thresholds ───────────────────────────────────────
    alert_cpu_threshold: int = 80
    alert_ram_threshold: int = 85

    # ── Application ────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    log_dir: str = "/logs"

    # ── Device Classification ──────────────────────────────────
    infrastructure_ips: str = ""

    @property
    def infrastructure_ips_set(self) -> set[str]:
        """Parse comma-separated INFRASTRUCTURE_IPS into a set."""
        if not self.infrastructure_ips.strip():
            return set()
        return {ip.strip() for ip in self.infrastructure_ips.split(",") if ip.strip()}

    @property
    def db_url(self) -> str:
        """SQLAlchemy connection URL for SQLite."""
        db = Path(self.db_path)
        db.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db.resolve()}"


settings = Settings()
