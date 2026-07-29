"""
Collection tasks — transforms raw API data into DB snapshots.

Orchestrates the full collection cycle:
1. Fetch all metrics from the router
2. Parse and normalize the data
3. Calculate traffic deltas (bytes → bps)
4. Store snapshots in the database
5. Update client device registry
6. Trigger alert evaluation
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.collector.client import MikroTikClient
from app.config import settings
from app.database import SessionLocal
from app.models.client_device import ClientDevice
from app.models.interface import InterfaceSnapshot
from app.models.router import Router
from app.models.snapshot import ResourceSnapshot
from app.services.alerts import evaluate_alerts
from app.utils.formatters import parse_uptime, safe_float, safe_int, utcnow
from app.utils.logger import get_logger

log = get_logger("collector.tasks")


def _get_or_create_router(db: Session) -> Router:
    """Get the router record, creating it if it doesn't exist."""
    router = db.query(Router).filter_by(name=settings.router_name).first()
    if not router:
        router = Router(
            name=settings.router_name,
            host=settings.router_host,
            port=settings.router_port,
        )
        db.add(router)
        db.commit()
        db.refresh(router)
        log.info("Registered new router: %s", router.name)
    return router


def _get_previous_snapshot(db: Session, router_id: int) -> ResourceSnapshot | None:
    """Get the most recent snapshot for delta calculations."""
    return (
        db.query(ResourceSnapshot)
        .filter_by(router_id=router_id)
        .order_by(ResourceSnapshot.timestamp.desc())
        .first()
    )


def _calculate_bps(
    current_bytes: int,
    previous_bytes: int,
    interval_seconds: float,
) -> int:
    """
    Calculate bits per second from byte counter deltas.

    Handles counter resets (e.g. router reboot) and initial baseline by returning 0.
    """
    if interval_seconds <= 0 or previous_bytes <= 0 or current_bytes < previous_bytes:
        return 0
    delta_bytes = current_bytes - previous_bytes
    return int((delta_bytes * 8) / interval_seconds)


def _parse_health_data(health_list: list[dict[str, Any]]) -> dict[str, float | None]:
    """
    Extract temperature and voltage from health data.

    RouterOS v6 and v7 return different formats:
    - v6: [{"voltage": "24.5", "temperature": "40"}]
    - v7: [{"name": "voltage", "value": "24.5"}, {"name": "temperature", "value": "40"}]
    """
    result: dict[str, float | None] = {"temperature": None, "voltage": None}

    if not health_list:
        return result

    # v6 format: single dict with named keys
    if len(health_list) == 1 and "temperature" in health_list[0]:
        result["temperature"] = safe_float(health_list[0].get("temperature"))
        result["voltage"] = safe_float(health_list[0].get("voltage"))
        return result

    # v7 format: list of {name, value} pairs
    for item in health_list:
        name = item.get("name", "").lower()
        value = item.get("value")
        if "temperature" in name and result["temperature"] is None:
            result["temperature"] = safe_float(value)
        elif "voltage" in name and result["voltage"] is None:
            result["voltage"] = safe_float(value)

    return result


def _get_wan_traffic_and_status(
    interfaces: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    configured_wan: str,
) -> tuple[int, int, str]:
    """
    Find WAN interface(s) and compute total cumulative RX/TX bytes and status.

    Supports:
    - Specific interface (e.g. "ether9FIBER")
    - Comma-separated interfaces (e.g. "ether9FIBER,ether10IPLAN")
    - "auto" or fallback: Auto-detects active WAN interface from default routes (0.0.0.0/0)
    """
    iface_map = {i.get("name"): i for i in interfaces if i.get("name")}
    target_names: list[str] = []

    if configured_wan and configured_wan.lower() != "auto":
        target_names = [n.strip() for n in configured_wan.split(",") if n.strip()]

    # Filter to interfaces that exist and are running
    valid_names = [
        n for n in target_names
        if n in iface_map and iface_map[n].get("running", "false").lower() == "true"
    ]

    has_default_route = any(
        r.get("dst-address", "") in ("0.0.0.0/0", "0.0.0.0") and r.get("active", "true").lower() in ("true", "")
        for r in routes
    )

    # Auto-detection fallback if configured WAN is not found/running
    if not valid_names:
        for r in routes:
            dst = r.get("dst-address", "")
            is_active = r.get("active", "true").lower() in ("true", "")
            if dst in ("0.0.0.0/0", "0.0.0.0") and is_active:
                gw_status = r.get("gateway-status", "")
                if "via " in gw_status:
                    iface_name = gw_status.split("via ")[-1].strip()
                    if iface_name in iface_map and iface_map[iface_name].get("running", "false").lower() == "true":
                        if iface_name not in valid_names:
                            valid_names.append(iface_name)
                elif r.get("gateway") in iface_map:
                    gw_iface = r.get("gateway")
                    if iface_map[gw_iface].get("running", "false").lower() == "true":
                        valid_names.append(gw_iface)

        # Ultimate fallback: pick the first running interface if default route exists
        if not valid_names and has_default_route:
            for i_name, i_data in iface_map.items():
                if i_data.get("running", "false").lower() == "true":
                    valid_names.append(i_name)
                    break

    total_rx = 0
    total_tx = 0
    any_running = False

    for name in valid_names:
        iface = iface_map[name]
        is_running = iface.get("running", "false").lower() == "true"
        if is_running:
            any_running = True
            total_rx += safe_int(iface.get("rx-byte", 0))
            total_tx += safe_int(iface.get("tx-byte", 0))

    if any_running and has_default_route:
        status = "up"
    elif any_running:
        status = "no-route"
    elif valid_names:
        status = "down"
    else:
        status = "down"

    return total_rx, total_tx, status


def _save_interface_snapshots(
    db: Session,
    router_id: int,
    snapshot_id: int,
    interfaces: list[dict[str, Any]],
    prev_snapshot: ResourceSnapshot | None,
    interval_seconds: float,
    now: datetime,
) -> None:
    """Store per-interface traffic data."""
    # Build lookup of previous interface data for delta calculation
    prev_iface_map: dict[str, InterfaceSnapshot] = {}
    if prev_snapshot:
        for pi in prev_snapshot.interfaces:
            prev_iface_map[pi.name] = pi

    for iface in interfaces:
        name = iface.get("name", "")
        if not name:
            continue

        rx_bytes = safe_int(iface.get("rx-byte", 0))
        tx_bytes = safe_int(iface.get("tx-byte", 0))

        # Calculate rates from deltas
        rx_bps = 0
        tx_bps = 0
        prev = prev_iface_map.get(name)
        if prev and interval_seconds > 0:
            rx_bps = _calculate_bps(rx_bytes, prev.rx_bytes, interval_seconds)
            tx_bps = _calculate_bps(tx_bytes, prev.tx_bytes, interval_seconds)

        iface_snap = InterfaceSnapshot(
            router_id=router_id,
            snapshot_id=snapshot_id,
            timestamp=now,
            name=name,
            iface_type=iface.get("type"),
            mac_address=iface.get("mac-address"),
            is_running=iface.get("running", "false").lower() == "true",
            is_disabled=iface.get("disabled", "false").lower() == "true",
            rx_bytes=rx_bytes,
            tx_bytes=tx_bytes,
            rx_bps=rx_bps,
            tx_bps=tx_bps,
            link_speed=iface.get("link-downs"),  # placeholder
        )
        db.add(iface_snap)


INFRASTRUCTURE_IPS = settings.infrastructure_ips_set

VM_MAC_OUIS = (
    "00:50:56", "00:0C:29", "00:05:69", "00:1C:14",  # VMware
    "52:54:00",                                     # QEMU / KVM / Proxmox
    "08:00:27",                                     # Oracle VirtualBox
    "00:15:5D",                                     # Microsoft Hyper-V
    "00:16:3E",                                     # Xen
    "00:1C:42",                                     # Parallels
)

SERVER_KEYWORDS = (
    "srv", "server", "sql", "db", "database", "gitlab", "nextcloud", "webapp",
    "vm", "hyperv", "proxmox", "docker", "kubernetes", "nas", "pve", "esxi",
    "vcenter", "qemu", "virt", "k8s", "container", "ubuntu-server", "debian-srv"
)


def _is_virtual_machine(
    mac: str,
    hostname: str | None = None,
    ip: str | None = None,
) -> bool:
    """
    Determine if a device is a Server or Virtual Machine based on priority rules:
    1. Priority 1: Match IP against permanent infrastructure list.
    2. Exclusion: Mobile/user devices (Android, iPhone, etc.) are always user devices.
    3. Priority 2: Match name/hostname against Server/VM keywords.
    4. Priority 3: Match MAC OUI against VM hypervisor prefixes.
    """
    if ip and ip.strip() in INFRASTRUCTURE_IPS:
        return True

    if hostname:
        host_lower = hostname.lower()
        if any(mobile_kw in host_lower for mobile_kw in ("android", "iphone", "galaxy", "ipad", "phone", "mobile")):
            return False

        for kw in SERVER_KEYWORDS:
            if kw in host_lower:
                return True

    if mac:
        clean_mac = mac.upper().replace("-", ":")
        for oui in VM_MAC_OUIS:
            if clean_mac.startswith(oui):
                return True

    return False



def _find_matching_queue(
    ip: str,
    hostname: str | None,
    vpn_user: str | None,
    simple_queues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Match a device against RouterOS Simple Queues by target IP or name."""
    if not simple_queues:
        return None

    for q in simple_queues:
        target = q.get("target", "")
        q_name = (q.get("name") or "").lower()
        target_ip = target.split("/")[0].strip() if target else ""

        if ip and target_ip and ip == target_ip:
            return q
        if vpn_user and vpn_user.lower() in q_name:
            return q
        if hostname and hostname.lower() in q_name:
            return q

    return None


def _update_client_devices(
    db: Session,
    router_id: int,
    dhcp_leases: list[dict[str, Any]],
    arp_table: list[dict[str, Any]],
    ppp_active: list[dict[str, Any]],
    wireguard_peers: list[dict[str, Any]],
    simple_queues: list[dict[str, Any]],
    now: datetime,
) -> int:
    """
    Upsert client device records from DHCP, ARP, PPP, WireGuard, and Simple Queues.

    Classifies devices into: 'lan', 'vpn', 'vm', 'offline'.
    Returns count of active VPN sessions.
    """
    # Mark all devices inactive first, then re-activate found ones
    db.query(ClientDevice).filter_by(router_id=router_id).update(
        {"is_active": False}
    )

    seen_macs: set[str] = set()
    vpn_count = 0

    # 1. Process PPP Active Sessions (VPN: PPTP, L2TP, SSTP, OpenVPN)
    for session in ppp_active:
        user_name = session.get("name", "")
        ip = session.get("address", "")
        service_raw = (session.get("service") or "VPN").upper()
        if "PPTP" in service_raw:
            vpn_type = "PPTP"
        elif "L2TP" in service_raw:
            vpn_type = "L2TP"
        elif "SSTP" in service_raw:
            vpn_type = "SSTP"
        elif "OVPN" in service_raw or "OPENVPN" in service_raw:
            vpn_type = "OpenVPN"
        else:
            vpn_type = service_raw

        caller_id = session.get("caller-id", "")
        mac = caller_id.upper() if caller_id else f"PPP-{user_name}"
        if mac in seen_macs:
            continue
        seen_macs.add(mac)
        vpn_count += 1

        uptime_str = session.get("uptime", "")
        uptime_secs = parse_uptime(uptime_str)

        device = (
            db.query(ClientDevice)
            .filter_by(router_id=router_id, mac_address=mac)
            .first()
        )
        if not device:
            device = ClientDevice(router_id=router_id, mac_address=mac, first_seen=now)
            db.add(device)

        device.ip_address = ip or device.ip_address or "0.0.0.0"
        device.hostname = user_name
        device.source = "ppp"
        device.device_type = "vpn"
        device.vpn_user = user_name
        device.vpn_type = vpn_type
        device.session_time = uptime_str or format_uptime(uptime_secs)
        device.session_seconds = uptime_secs
        device.is_active = True
        device.last_seen = now

    # 2. Process WireGuard Peers (VPN: WireGuard)
    for peer in wireguard_peers:
        pub_key = peer.get("public-key", "")
        allowed = peer.get("allowed-address", "")
        ip = allowed.split("/")[0] if allowed else ""
        comment = peer.get("comment") or f"WG-{pub_key[:8]}"
        mac = f"WG-{pub_key[:12]}" if pub_key else f"WG-{ip}"

        if mac in seen_macs:
            continue
        seen_macs.add(mac)
        vpn_count += 1

        handshake = peer.get("last-handshake-time", "")
        rx_b = safe_int(peer.get("rx", 0))
        tx_b = safe_int(peer.get("tx", 0))

        device = (
            db.query(ClientDevice)
            .filter_by(router_id=router_id, mac_address=mac)
            .first()
        )
        if not device:
            device = ClientDevice(router_id=router_id, mac_address=mac, first_seen=now)
            db.add(device)

        device.ip_address = ip or device.ip_address or "0.0.0.0"
        device.hostname = comment
        device.source = "wireguard"
        device.device_type = "vpn"
        device.vpn_user = comment
        device.vpn_type = "WireGuard"
        device.session_time = handshake or "Active"
        device.is_active = True
        device.last_seen = now
        device.total_rx_bytes = rx_b
        device.total_tx_bytes = tx_b

    # 3. Process DHCP Leases (LAN / VM)
    for lease in dhcp_leases:
        mac = lease.get("mac-address", "").upper()
        if not mac or mac in seen_macs:
            continue
        seen_macs.add(mac)

        ip = lease.get("address", "")
        hostname = lease.get("host-name") or lease.get("comment") or None
        is_bound = lease.get("status", "") == "bound"
        is_vm = _is_virtual_machine(mac, hostname, ip)

        device = (
            db.query(ClientDevice)
            .filter_by(router_id=router_id, mac_address=mac)
            .first()
        )
        if not device:
            device = ClientDevice(router_id=router_id, mac_address=mac, first_seen=now)
            db.add(device)

        device.ip_address = ip or device.ip_address or "0.0.0.0"
        device.hostname = hostname or device.hostname
        device.source = "dhcp"
        device.device_type = "vm" if is_vm else "lan"
        device.is_active = is_bound
        device.last_seen = now

    # 4. Process ARP Table (LAN / VM)
    for entry in arp_table:
        mac = entry.get("mac-address", "").upper()
        if not mac or mac in seen_macs:
            continue
        seen_macs.add(mac)

        ip = entry.get("address", "")
        iface = entry.get("interface")
        is_vm = _is_virtual_machine(mac, None, ip)

        device = (
            db.query(ClientDevice)
            .filter_by(router_id=router_id, mac_address=mac)
            .first()
        )
        if not device:
            device = ClientDevice(router_id=router_id, mac_address=mac, first_seen=now)
            db.add(device)

        device.ip_address = ip or device.ip_address or "0.0.0.0"
        device.interface = iface
        device.source = "arp"
        if not device.device_type or device.device_type == "lan":
            device.device_type = "vm" if is_vm else "lan"
        device.is_active = True
        device.last_seen = now

    # 5. Enrich with Simple Queues and classify offline devices
    all_devices = db.query(ClientDevice).filter_by(router_id=router_id).all()
    for dev in all_devices:
        if _is_virtual_machine(dev.mac_address, dev.hostname, dev.ip_address):
            dev.device_type = "vm"
        elif not dev.is_active:
            dev.device_type = "offline"
        else:
            q = _find_matching_queue(dev.ip_address, dev.hostname, dev.vpn_user, simple_queues)
            if q:
                dev.queue_name = q.get("name")
                dev.queue_max_limit = q.get("max-limit") or q.get("limit-at")
                rates = (q.get("rate") or "").split("/")
                bytes_raw = (q.get("bytes") or "").split("/")
                if len(rates) == 2:
                    dev.queue_rx_bps = safe_int(rates[0])
                    dev.queue_tx_bps = safe_int(rates[1])
                if len(bytes_raw) == 2:
                    dev.queue_rx_bytes = safe_int(bytes_raw[0])
                    dev.queue_tx_bytes = safe_int(bytes_raw[1])
                    if dev.queue_rx_bytes > 0:
                        dev.total_rx_bytes = dev.queue_rx_bytes
                    if dev.queue_tx_bytes > 0:
                        dev.total_tx_bytes = dev.queue_tx_bytes

    return vpn_count


def run_collection() -> None:
    """
    Execute a full collection cycle.

    This is called by the scheduler every N seconds. It:
    1. Connects to the router (read-only)
    2. Fetches all metrics
    3. Stores a resource snapshot
    4. Updates interface data
    5. Updates client device registry
    6. Evaluates alert conditions
    """
    log.debug("Starting collection cycle")
    db = SessionLocal()

    try:
        router = _get_or_create_router(db)
        client = MikroTikClient()
        data = client.collect_all()

        now = utcnow()

        # Get previous snapshot for delta calculation
        prev_snapshot = _get_previous_snapshot(db, router.id)
        interval_seconds = settings.collect_interval_seconds
        if prev_snapshot and prev_snapshot.timestamp:
            interval_seconds = (now - prev_snapshot.timestamp).total_seconds()

        # Parse system resource
        res = data.get("system_resource", {})
        identity = data.get("system_identity", {})
        health = _parse_health_data(data.get("system_health", []))
        interfaces = data.get("interfaces", [])
        routes = data.get("routes", [])

        # Update router info
        if data["is_reachable"]:
            router.identity = identity.get("name")
            router.board_name = res.get("board-name")
            router.version = res.get("version")
            router.architecture = res.get("architecture-name")
            router.is_reachable = True
            router.last_seen = now
        else:
            router.is_reachable = False

        # Find WAN interface(s) and traffic tracking
        wan_rx, wan_tx, wan_status = _get_wan_traffic_and_status(
            interfaces, routes, settings.router_wan_interface
        )

        # Calculate WAN rates
        rx_bps = 0
        tx_bps = 0
        if prev_snapshot and interval_seconds > 0:
            rx_bps = _calculate_bps(wan_rx, prev_snapshot.total_rx_bytes, interval_seconds)
            tx_bps = _calculate_bps(wan_tx, prev_snapshot.total_tx_bytes, interval_seconds)

        # RAM calculation
        total_ram = safe_int(res.get("total-memory", 0))
        free_ram = safe_int(res.get("free-memory", 0))
        used_ram = total_ram - free_ram

        # DHCP / PPP / VPN / Queues counts
        dhcp_leases = data.get("dhcp_leases", [])
        ppp_active = data.get("ppp_active", [])
        wireguard_peers = data.get("wireguard_peers", [])
        simple_queues = data.get("simple_queues", [])
        vpn_types = data.get("vpn_types_detected", [])
        arp_table = data.get("arp_table", [])

        active_dhcp = [
            l for l in dhcp_leases if l.get("status") == "bound"
        ]

        # Update client devices & get active VPN count
        active_vpn_count = _update_client_devices(
            db, router.id, dhcp_leases, arp_table, ppp_active, wireguard_peers, simple_queues, now,
        )

        vpn_types_str = ", ".join(vpn_types) if vpn_types else None

        # Create resource snapshot
        snapshot = ResourceSnapshot(
            router_id=router.id,
            timestamp=now,
            cpu_load=safe_int(res.get("cpu-load", 0)),
            ram_used=used_ram,
            ram_total=total_ram,
            uptime=res.get("uptime", ""),
            uptime_seconds=parse_uptime(res.get("uptime", "")),
            temperature=health.get("temperature"),
            voltage=health.get("voltage"),
            is_reachable=data["is_reachable"],
            wan_status=wan_status,
            total_rx_bytes=wan_rx,
            total_tx_bytes=wan_tx,
            rx_bps=rx_bps,
            tx_bps=tx_bps,
            dhcp_client_count=len(active_dhcp),
            ppp_active_count=len(ppp_active),
            arp_count=len(arp_table),
            vpn_user_count=active_vpn_count,
            vpn_types_detected=vpn_types_str,
        )
        db.add(snapshot)
        db.flush()  # Get snapshot.id for interface FK

        # Save interface snapshots
        _save_interface_snapshots(
            db, router.id, snapshot.id, interfaces,
            prev_snapshot, interval_seconds, now,
        )

        db.commit()

        # Evaluate alerts (after commit so snapshot has an ID)
        evaluate_alerts(db, router.id, snapshot, prev_snapshot)

        log.info(
            "Collection OK | CPU=%d%% RAM=%d%% RX=%dbps TX=%dbps clients=%d (VPN=%d)",
            snapshot.cpu_load,
            snapshot.ram_percent,
            rx_bps,
            tx_bps,
            snapshot.dhcp_client_count + active_vpn_count,
            active_vpn_count,
        )

    except Exception:
        log.exception("Collection cycle failed")
        db.rollback()
    finally:
        db.close()
