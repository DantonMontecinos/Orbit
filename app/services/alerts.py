"""
Alert detection and management service.

Evaluates incoming snapshots against configured thresholds and
manages alert lifecycle (create → active → resolved).

Alert types:
- router_unreachable: Cannot connect to the router
- internet_down: WAN interface or default route is down
- cpu_high: CPU exceeds threshold for sustained period
- ram_high: RAM exceeds threshold for sustained period
- interface_down: A previously-running interface went down
"""

from sqlalchemy.orm import Session

from app.config import settings
from app.models.alert import Alert
from app.models.snapshot import ResourceSnapshot
from app.utils.formatters import utcnow
from app.utils.logger import get_logger

log = get_logger("services.alerts")


def _get_active_alert(
    db: Session,
    router_id: int,
    alert_type: str,
) -> Alert | None:
    """Find an active (unresolved) alert of the given type."""
    return (
        db.query(Alert)
        .filter_by(router_id=router_id, alert_type=alert_type, is_active=True)
        .first()
    )


def _format_webex_alert_markdown(alert_type: str, severity: str, message: str) -> str:
    """Format rich Markdown for Webex Teams alert notification."""
    icon = "🚨" if severity == "critical" else "⚠️"
    title = "ALERTA NOC — EVENTO REGISTRADO"

    if alert_type.startswith("isp_down"):
        icon = "🔴"
        title = "ALERTA WAN — ENLACE ISP CAÍDO"
    elif alert_type.startswith("vpn_disconnect"):
        icon = "🔌"
        title = "NOTIFICACIÓN VPN — USUARIO DESCONECTADO"

    return (
        f"{icon} **{title}**\n\n"
        f"- **Tipo**: `{alert_type}`\n"
        f"- **Severidad**: `{severity.upper()}`\n"
        f"- **Detalle**: {message}\n"
        f"- **Hora**: `{utcnow().strftime('%H:%M:%S UTC')}`"
    )


def _format_webex_resolved_markdown(alert_type: str, message: str, duration_sec: int) -> str:
    """Format rich Markdown for Webex Teams resolution notification."""
    title = "EVENTO RESUELTO"
    if alert_type.startswith("isp_down"):
        title = "ENLACE ISP RESTABLECIDO"
    elif alert_type.startswith("vpn_disconnect"):
        title = "USUARIO VPN RE-CONECTADO"

    mins = duration_sec // 60
    secs = duration_sec % 60
    dur_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    return (
        f"🟢 **{title}**\n\n"
        f"- **Tipo**: `{alert_type}`\n"
        f"- **Detalle**: {message}\n"
        f"- **Duración del evento**: `{dur_str}`\n"
        f"- **Hora de resolución**: `{utcnow().strftime('%H:%M:%S UTC')}`"
    )


def _create_alert(
    db: Session,
    router_id: int,
    alert_type: str,
    severity: str,
    message: str,
) -> Alert:
    """Create a new active alert and dispatch Webex notification."""
    alert = Alert(
        router_id=router_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        started_at=utcnow(),
        is_active=True,
    )
    db.add(alert)
    db.commit()
    log.warning("ALERT [%s] %s: %s", severity.upper(), alert_type, message)

    # Dispatch Webex Teams notification
    from app.services.webex import send_webex_message
    md = _format_webex_alert_markdown(alert_type, severity, message)
    send_webex_message(md)

    return alert


def _resolve_alert(
    db: Session,
    router_id: int,
    alert_type: str,
) -> None:
    """Resolve an active alert if one exists and dispatch Webex notification."""
    alert = _get_active_alert(db, router_id, alert_type)
    if alert:
        alert.resolve()
        db.commit()
        log.info(
            "RESOLVED [%s] after %ds",
            alert_type,
            alert.duration_seconds or 0,
        )

        # Dispatch Webex Teams resolution notification
        from app.services.webex import send_webex_message
        md = _format_webex_resolved_markdown(
            alert_type, alert.message, alert.duration_seconds or 0
        )
        send_webex_message(md)


def evaluate_alerts(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
    previous: ResourceSnapshot | None,
) -> None:
    """
    Evaluate all alert conditions against the current snapshot.

    This runs after each collection cycle. It checks for new
    conditions and resolves existing alerts when conditions clear.
    """
    _check_router_reachable(db, router_id, snapshot)
    _check_internet_status(db, router_id, snapshot)
    _check_isps(db, router_id)
    _check_cpu(db, router_id, snapshot, previous)
    _check_ram(db, router_id, snapshot, previous)
    _check_interfaces(db, router_id, snapshot, previous)
    _check_vpn_disconnections(db, router_id)


def _check_isps(db: Session, router_id: int) -> None:
    """Detect WAN ISP link outages (e.g. IPLAN, Fibertel down/online)."""
    from app.config import settings
    from app.models.wan_snapshot import WanSnapshot

    for isp in settings.isp_configs:
        name = isp["name"]
        iface = isp["interface"]
        alert_key = f"isp_down:{name}"

        # Get latest WanSnapshot for this ISP
        latest = (
            db.query(WanSnapshot)
            .filter_by(isp_name=name)
            .order_by(WanSnapshot.timestamp.desc())
            .first()
        )

        if latest:
            if latest.status in ("offline", "no-route", "down"):
                existing = _get_active_alert(db, router_id, alert_key)
                if not existing:
                    _create_alert(
                        db,
                        router_id,
                        alert_key,
                        "critical",
                        f"Enlace ISP '{name}' ({iface}) fuera de servicio. Estado: {latest.status.upper()}. IP WAN: {latest.ip_wan or '—'}",
                    )
            elif latest.status == "online":
                _resolve_alert(db, router_id, alert_key)


def _check_vpn_disconnections(
    db: Session,
    router_id: int,
) -> None:
    """Detect unexpected VPN user disconnections."""
    from app.models.client_device import ClientDevice

    vpn_devices = (
        db.query(ClientDevice)
        .filter(
            ClientDevice.router_id == router_id,
            ClientDevice.source.in_(["ppp", "wireguard"]),
        )
        .all()
    )

    for dev in vpn_devices:
        user_label = dev.vpn_user or dev.hostname or dev.mac_address
        alert_key = f"vpn_disconnect:{dev.mac_address}"

        if not dev.is_active:
            existing = _get_active_alert(db, router_id, alert_key)
            if not existing:
                vpn_type = dev.vpn_type or "VPN"
                _create_alert(
                    db,
                    router_id,
                    alert_key,
                    "warning",
                    f"Sesión VPN finalizada: Usuario '{user_label}' ({vpn_type}) desconectado. IP: {dev.ip_address}",
                )
        else:
            _resolve_alert(db, router_id, alert_key)


def _check_router_reachable(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
) -> None:
    """Detect router connectivity loss."""
    if not snapshot.is_reachable:
        existing = _get_active_alert(db, router_id, "router_unreachable")
        if not existing:
            _create_alert(
                db, router_id, "router_unreachable", "critical",
                "Router is unreachable — cannot establish API connection",
            )
    else:
        _resolve_alert(db, router_id, "router_unreachable")


def _check_internet_status(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
) -> None:
    """Detect WAN/Internet loss."""
    if snapshot.wan_status in ("down", "no-route"):
        existing = _get_active_alert(db, router_id, "internet_down")
        if not existing:
            _create_alert(
                db, router_id, "internet_down", "critical",
                f"Internet connection is {snapshot.wan_status} — WAN interface or default route unavailable",
            )
    else:
        _resolve_alert(db, router_id, "internet_down")


def _check_cpu(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
    previous: ResourceSnapshot | None,
) -> None:
    """
    Detect sustained high CPU usage.

    Uses hysteresis: triggers when BOTH current AND previous
    readings exceed the threshold. Resolves when below threshold.
    """
    threshold = settings.alert_cpu_threshold

    if snapshot.cpu_load >= threshold:
        # Require 2 consecutive high readings to avoid false positives
        if previous and previous.cpu_load >= threshold:
            existing = _get_active_alert(db, router_id, "cpu_high")
            if not existing:
                _create_alert(
                    db, router_id, "cpu_high", "warning",
                    f"CPU usage sustained at {snapshot.cpu_load}% (threshold: {threshold}%)",
                )
    elif snapshot.cpu_load < threshold - 10:  # 10% hysteresis band
        _resolve_alert(db, router_id, "cpu_high")


def _check_ram(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
    previous: ResourceSnapshot | None,
) -> None:
    """Detect sustained high RAM usage with hysteresis."""
    threshold = settings.alert_ram_threshold
    ram_pct = snapshot.ram_percent

    if ram_pct >= threshold:
        if previous and previous.ram_percent >= threshold:
            existing = _get_active_alert(db, router_id, "ram_high")
            if not existing:
                _create_alert(
                    db, router_id, "ram_high", "warning",
                    f"RAM usage sustained at {ram_pct:.1f}% (threshold: {threshold}%)",
                )
    elif ram_pct < threshold - 10:
        _resolve_alert(db, router_id, "ram_high")


def _check_interfaces(
    db: Session,
    router_id: int,
    snapshot: ResourceSnapshot,
    previous: ResourceSnapshot | None,
) -> None:
    """Detect interfaces that were running but went down."""
    if not previous or not previous.interfaces:
        return

    prev_map = {i.name: i for i in previous.interfaces}

    for iface in snapshot.interfaces:
        prev_iface = prev_map.get(iface.name)
        if not prev_iface:
            continue

        # Interface was running but is now down (and not disabled)
        if prev_iface.is_running and not iface.is_running and not iface.is_disabled:
            alert_key = f"interface_down:{iface.name}"
            existing = _get_active_alert(db, router_id, alert_key)
            if not existing:
                _create_alert(
                    db, router_id, alert_key, "warning",
                    f"Interface {iface.name!r} went down",
                )
        elif iface.is_running and not prev_iface.is_running:
            alert_key = f"interface_down:{iface.name}"
            _resolve_alert(db, router_id, alert_key)
