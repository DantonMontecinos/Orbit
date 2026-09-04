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
        extra="ignore",
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

    # ── Webex Bot Notifications ────────────────────────────────
    webex_bot_token: str = ""
    webex_room_it_id: str = ""
    webex_room_test_id: str = ""
    webex_room_default: str = "it"  # "test" | "it" | "both"

    # ── Device Classification ──────────────────────────────────
    @property
    def vm_configs(self) -> list[dict[str, str]]:
        """Parse VM{N}_NAME and VM{N}_IP env vars (up to 20)."""
        import os

        vms: list[dict[str, str]] = []
        for i in range(1, 21):
            name = os.getenv(f"VM{i}_NAME", "").strip()
            ip = os.getenv(f"VM{i}_IP", "").strip()
            if not name or not ip:
                continue
            vms.append({
                "name": name,
                "ip": ip,
            })
        return vms

    @property
    def vm_ips_set(self) -> set[str]:
        """Set of all VM IPs."""
        return {vm["ip"] for vm in self.vm_configs}

    @property
    def ubiquiti_devices(self) -> list[dict[str, str]]:
        """Parse UBNT_{N}_* env vars into device configs (up to 10)."""
        import os

        devices: list[dict[str, str]] = []
        for i in range(1, 11):
            host = os.getenv(f"UBNT_{i}_HOST", "").strip()
            if not host:
                continue
            devices.append({
                "host": host,
                "user": os.getenv(f"UBNT_{i}_USER", "ubnt").strip(),
                "password": os.getenv(f"UBNT_{i}_PASSWORD", "").strip(),
                "name": os.getenv(f"UBNT_{i}_NAME", f"Ubiquiti-{i}").strip(),
            })
        return devices

    @property
    def isp_configs(self) -> list[dict[str, str]]:
        """Parse ISP{N}_NAME and ISP{N}_INTERFACE env vars (up to 10)."""
        import os

        isps: list[dict[str, str]] = []
        for i in range(1, 11):
            name = os.getenv(f"ISP{i}_NAME", "").strip()
            iface = os.getenv(f"ISP{i}_INTERFACE", "").strip()
            if not name or not iface:
                continue
            isps.append({
                "name": name,
                "interface": iface,
            })
        return isps

    @property
    def db_url(self) -> str:
        """SQLAlchemy connection URL for SQLite."""
        db = Path(self.db_path)
        db.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db.resolve()}"


settings = Settings()
