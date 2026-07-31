"""
Read-only MikroTik RouterOS API client.

This module wraps the routeros-api library and ONLY exposes
methods that execute 'print' (read) commands. No write operations
(add, set, remove, enable, disable) are ever called.

Safety guarantee: The underlying API resource's `.get()` method
maps to RouterOS `/print` command, which is strictly read-only.
"""

from typing import Any

import routeros_api
from routeros_api.exceptions import RouterOsApiCommunicationError

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("collector.client")


class MikroTikClient:
    """
    Read-only client for MikroTik RouterOS.

    NEVER executes write commands. All methods use `.get()` which
    maps to the RouterOS `print` command internally.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.host = host or settings.router_host
        self.port = port or settings.router_port
        self.username = username or settings.router_user
        self.password = password or settings.router_password
        self.use_ssl = use_ssl if use_ssl is not None else settings.router_use_ssl

        self._pool: routeros_api.RouterOsApiPool | None = None
        self._api: routeros_api.RouterOsApi | None = None

    def connect(self) -> bool:
        """
        Establish connection to the router.

        Handles login protocol differences across RouterOS v6 versions
        (plaintext_login=True for v6.43+, falling back to challenge-response for earlier builds).
        Returns True if successful, False otherwise.
        """
        for plaintext in (True, False):
            try:
                self._pool = routeros_api.RouterOsApiPool(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    use_ssl=self.use_ssl,
                    plaintext_login=plaintext,
                )
                self._api = self._pool.get_api()
                log.info(
                    "Connected to %s:%d (RouterOS v6 mode, plaintext=%s)",
                    self.host,
                    self.port,
                    plaintext,
                )
                return True
            except Exception as e:
                log.debug(
                    "Connection attempt with plaintext=%s failed: %s",
                    plaintext,
                    e,
                )
                self.disconnect()

        log.error("Failed to connect to %s:%d with all login methods", self.host, self.port)
        return False

    def disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool:
            try:
                self._pool.disconnect()
            except Exception:
                log.debug("Error during disconnect (ignored)")
            finally:
                self._pool = None
                self._api = None
                log.info("Disconnected from %s", self.host)

    def _get(self, path: str) -> list[dict[str, Any]]:
        """
        Execute a read-only GET (print) on the given resource path.

        This is the ONLY method that touches the API. It maps to
        RouterOS 'print' command — strictly read-only.
        """
        if not self._api:
            raise ConnectionError("Not connected to router")

        try:
            resource = self._api.get_resource(path)
            return resource.get()
        except RouterOsApiCommunicationError:
            log.warning("Communication error reading %s", path)
            raise
        except Exception:
            log.exception("Unexpected error reading %s", path)
            raise

    # ── System ─────────────────────────────────────────────────

    def get_system_resource(self) -> dict[str, Any]:
        """
        /system/resource/print

        Returns CPU load, RAM, uptime, version, board info.
        """
        result = self._get("/system/resource")
        return result[0] if result else {}

    def get_system_identity(self) -> dict[str, Any]:
        """
        /system/identity/print

        Returns the router's identity name.
        """
        result = self._get("/system/identity")
        return result[0] if result else {}

    def get_system_health(self) -> list[dict[str, Any]]:
        """
        /system/health/print

        Returns temperature, voltage, and other sensor data.
        Availability depends on hardware model.
        """
        try:
            return self._get("/system/health")
        except Exception:
            log.debug("System health not available on this device")
            return []

    # ── Interfaces ─────────────────────────────────────────────

    def get_interfaces(self) -> list[dict[str, Any]]:
        """
        /interface/print

        Returns all interfaces with traffic counters and status.
        """
        return self._get("/interface")

    # ── IP ─────────────────────────────────────────────────────

    def get_dhcp_leases(self) -> list[dict[str, Any]]:
        """
        /ip/dhcp-server/lease/print

        Returns all DHCP leases (active and expired).
        """
        try:
            return self._get("/ip/dhcp-server/lease")
        except Exception:
            log.debug("DHCP server not configured or unavailable")
            return []

    def get_arp_table(self) -> list[dict[str, Any]]:
        """
        /ip/arp/print

        Returns the ARP table entries.
        """
        return self._get("/ip/arp")

    def get_routes(self) -> list[dict[str, Any]]:
        """
        /ip/route/print

        Returns the routing table.
        """
        return self._get("/ip/route")

    def get_ip_addresses(self) -> list[dict[str, Any]]:
        """
        /ip/address/print

        Returns interface IP address assignments.
        """
        try:
            return self._get("/ip/address")
        except Exception:
            log.debug("IP addresses unavailable")
            return []

    # ── PPP & VPN ──────────────────────────────────────────────

    def get_ppp_active(self) -> list[dict[str, Any]]:
        """
        /ppp/active/print

        Returns currently connected PPP sessions (PPTP, L2TP, SSTP, OVPN).
        """
        try:
            return self._get("/ppp/active")
        except Exception:
            log.debug("PPP active sessions unavailable")
            return []

    def get_wireguard_peers(self) -> list[dict[str, Any]]:
        """
        /interface/wireguard/peers/print

        Returns WireGuard peer status and last handshake details.
        """
        try:
            return self._get("/interface/wireguard/peers")
        except Exception:
            log.debug("WireGuard peers unavailable or not configured")
            return []

    def get_wireguard_interfaces(self) -> list[dict[str, Any]]:
        """
        /interface/wireguard/print

        Returns configured WireGuard interfaces.
        """
        try:
            return self._get("/interface/wireguard")
        except Exception:
            log.debug("WireGuard interfaces unavailable")
            return []

    # ── Queues ──────────────────────────────────────────────────

    def get_simple_queues(self) -> list[dict[str, Any]]:
        """
        /queue/simple/print

        Returns all Simple Queues with bandwidth limits and current stats.
        """
        try:
            return self._get("/queue/simple")
        except Exception:
            log.debug("Simple Queues unavailable or empty")
            return []

    def detect_vpn_types(self) -> list[str]:
        """
        Auto-detect active or configured VPN protocols on the router.

        Checks PPP active sessions, WireGuard peers, and VPN server configurations.
        Does not assume a specific protocol.
        """
        detected: set[str] = set()

        # Check PPP active sessions
        for p in self.get_ppp_active():
            service = (p.get("service") or "").upper()
            if service:
                if "PPTP" in service:
                    detected.add("PPTP")
                elif "L2TP" in service:
                    detected.add("L2TP")
                elif "SSTP" in service:
                    detected.add("SSTP")
                elif "OVPN" in service or "OPENVPN" in service:
                    detected.add("OpenVPN")

        # Check WireGuard peers
        wg_peers = self.get_wireguard_peers()
        if wg_peers or self.get_wireguard_interfaces():
            detected.add("WireGuard")

        # Check VPN server configs if no active sessions found yet
        if not detected:
            vpn_checks = [
                ("/interface/ovpn-server/server", "OpenVPN"),
                ("/interface/l2tp-server/server", "L2TP"),
                ("/interface/pptp-server/server", "PPTP"),
                ("/interface/sstp-server/server", "SSTP"),
            ]
            for path, name in vpn_checks:
                try:
                    res = self._get(path)
                    if res and (res[0].get("enabled") == "true" or res[0].get("enabled") is True):
                        detected.add(name)
                except Exception:
                    pass

        return sorted(list(detected))

    # ── Convenience ────────────────────────────────────────────

    def collect_all(self) -> dict[str, Any]:
        """
        Collect all metrics in a single session.

        Returns a dictionary with all collected data, or partial
        data if some endpoints fail. Never raises — logs errors
        and continues with remaining endpoints.
        """
        data: dict[str, Any] = {
            "system_resource": {},
            "system_identity": {},
            "system_health": [],
            "interfaces": [],
            "dhcp_leases": [],
            "arp_table": [],
            "ppp_active": [],
            "wireguard_peers": [],
            "wireguard_interfaces": [],
            "simple_queues": [],
            "vpn_types_detected": [],
            "routes": [],
            "is_reachable": False,
        }

        if not self.connect():
            log.error("Router unreachable at %s:%d", self.host, self.port)
            return data

        data["is_reachable"] = True

        collectors = [
            ("system_resource", self.get_system_resource),
            ("system_identity", self.get_system_identity),
            ("system_health", self.get_system_health),
            ("interfaces", self.get_interfaces),
            ("dhcp_leases", self.get_dhcp_leases),
            ("arp_table", self.get_arp_table),
            ("ppp_active", self.get_ppp_active),
            ("wireguard_peers", self.get_wireguard_peers),
            ("wireguard_interfaces", self.get_wireguard_interfaces),
            ("simple_queues", self.get_simple_queues),
            ("vpn_types_detected", self.detect_vpn_types),
            ("routes", self.get_routes),
            ("ip_addresses", self.get_ip_addresses),
        ]

        for key, func in collectors:
            try:
                data[key] = func()
            except Exception:
                log.warning("Failed to collect %s", key)

        self.disconnect()
        return data
