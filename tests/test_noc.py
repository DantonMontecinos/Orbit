"""
Integration and Unit Tests for MikroTik NOC System.
"""

import sys
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.collector.client import MikroTikClient
from app.collector.tasks import run_collection
from app.config import settings
from app.database import SessionLocal, engine, init_db
from app.models import Base
from app.main import app
from app.models.alert import Alert
from app.models.client_device import ClientDevice
from app.models.interface import InterfaceSnapshot
from app.models.router import Router
from app.models.snapshot import ResourceSnapshot
from app.services.alerts import evaluate_alerts
from app.services.dashboard import (
    get_active_alerts,
    get_cpu_history,
    get_current_status,
    get_daily_consumption,
    get_interfaces_status,
    get_ram_history,
    get_top_consumers,
    get_traffic_history,
    get_users_history,
)
from app.services.history import get_outage_history, purge_old_data
from app.collector.tasks import _is_virtual_machine, run_collection
from app.utils.formatters import (
    format_bps,
    format_bytes,
    format_queue_limit,
    format_uptime,
    parse_routeros_rate,
    parse_uptime,
    safe_float,
    safe_int,
    utcnow,
)


class TestFormatters(unittest.TestCase):
    """Test data formatting utilities."""

    def test_format_queue_limit(self) -> None:
        self.assertEqual(format_queue_limit("15000000/30000000"), "15/30")
        self.assertEqual(format_queue_limit("15M/30M"), "15/30")
        self.assertEqual(format_queue_limit("1000000/2000000"), "1/2")
        self.assertEqual(format_queue_limit("0/0"), "Sin límite")
        self.assertEqual(format_queue_limit(None), "Sin límite")

    def test_device_classification_rules(self) -> None:
        # Mock settings.vm_ips_set since we can't easily mock the property without mocking the class
        with patch("app.config.Settings.vm_ips_set", new_callable=unittest.mock.PropertyMock) as mock_vm_ips:
            mock_vm_ips.return_value = {"192.168.1.100", "10.0.0.5"}

            # 1. Configured IPs must be classified as Servers/VMs
            for ip in mock_vm_ips.return_value:
                self.assertTrue(
                    _is_virtual_machine("AA:BB:CC:DD:EE:FF", "some-host", ip),
                    f"Configured IP {ip} was not classified as Server/VM",
                )

            # 2. Server keywords or VM MACs should NOT be classified as VMs anymore
            self.assertFalse(
                _is_virtual_machine("00:50:56:11:22:33", "SRV GitLab", "192.168.1.200"),
                "Heuristics should not classify as VM",
            )
            
            # 3. Regular user devices should NOT be classified as Servers/VMs
            self.assertFalse(_is_virtual_machine("AA:BB:CC:11:22:34", "Notebook-Work", "192.168.1.151"))
            self.assertFalse(_is_virtual_machine("AA:BB:CC:11:22:36", "Galaxy-S21-User", "192.168.1.153"))

    """Test data formatting utilities."""

    def test_parse_uptime(self) -> None:
        self.assertEqual(parse_uptime("1w5d7h54m27s"), 1_065_267)
        self.assertEqual(parse_uptime("3d12h5m"), 302_700)
        self.assertEqual(parse_uptime("45m12s"), 2_712)
        self.assertEqual(parse_uptime(""), 0)
        self.assertEqual(parse_uptime("invalid"), 0)

    def test_format_uptime(self) -> None:
        self.assertEqual(format_uptime(1_073_667), "12d 10h 14m")
        self.assertEqual(format_uptime(0), "0s")
        self.assertEqual(format_uptime(45), "45s")

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")
        self.assertEqual(format_bytes(-10), "0 B")

    def test_format_bps(self) -> None:
        self.assertEqual(format_bps(500), "500 bps")
        self.assertEqual(format_bps(1000), "1.00 Kbps")
        self.assertEqual(format_bps(1_000_000), "1.00 Mbps")
        self.assertEqual(format_bps(1_000_000_000), "1.00 Gbps")

    def test_parse_routeros_rate(self) -> None:
        self.assertEqual(parse_routeros_rate("1000000"), 1_000_000)
        self.assertEqual(parse_routeros_rate("10Mbps"), 10_000_000)
        self.assertEqual(parse_routeros_rate("1.5Gbps"), 1_500_000_000)
        self.assertEqual(parse_routeros_rate(""), 0)

    def test_safe_helpers(self) -> None:
        self.assertEqual(safe_int("42"), 42)
        self.assertEqual(safe_int("invalid", default=99), 99)
        self.assertEqual(safe_float("3.14"), 3.14)
        self.assertEqual(safe_float(None, default=0.0), 0.0)


class TestReadOnlyClient(unittest.TestCase):
    """Verify that MikroTikClient ONLY contains read operations."""

    def test_client_has_no_write_methods(self) -> None:
        client = MikroTikClient()
        forbidden_words = ["add_", "set_", "remove_", "enable_", "disable_", "write_", "execute_", "run_"]

        for attr_name in dir(client):
            if attr_name.startswith("_"):
                continue
            for forbidden in forbidden_words:
                self.assertNotIn(
                    forbidden,
                    attr_name.lower(),
                    f"Forbidden write action '{forbidden}' found in method name '{attr_name}'",
                )


class TestDatabaseAndCollectorFlow(unittest.TestCase):
    """Test full data collection flow with mock router responses."""

    def setUp(self) -> None:
        init_db()
        self.db = SessionLocal()
        # Clean up database
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self) -> None:
        self.db.close()

    @patch.object(MikroTikClient, "collect_all")
    def test_collection_task_stores_data(self, mock_collect: MagicMock) -> None:
        mock_collect.return_value = {
            "is_reachable": True,
            "system_resource": {
                "cpu-load": "15",
                "free-memory": "104857600",
                "total-memory": "209715200",
                "uptime": "2d5h10m",
                "version": "7.12",
                "board-name": "hEX S",
                "architecture-name": "mmips",
            },
            "system_identity": {"name": "TestRouter-NOC"},
            "system_health": [{"name": "temperature", "value": "42"}],
            "interfaces": [
                {
                    "name": "ether1",
                    "type": "ether",
                    "mac-address": "AA:BB:CC:DD:EE:FF",
                    "running": "true",
                    "disabled": "false",
                    "rx-byte": "10000000",
                    "tx-byte": "5000000",
                },
                {
                    "name": "ether2",
                    "type": "ether",
                    "mac-address": "AA:BB:CC:DD:EE:02",
                    "running": "true",
                    "disabled": "false",
                    "rx-byte": "2000000",
                    "tx-byte": "1000000",
                },
            ],
            "dhcp_leases": [
                {
                    "address": "192.168.88.100",
                    "mac-address": "11:22:33:44:55:66",
                    "host-name": "iPhone-User",
                    "status": "bound",
                }
            ],
            "arp_table": [
                {
                    "address": "192.168.88.100",
                    "mac-address": "11:22:33:44:55:66",
                    "interface": "ether2",
                }
            ],
            "ppp_active": [],
            "routes": [{"dst-address": "0.0.0.0/0", "gateway": "192.168.1.1"}],
        }

        # Run collection cycle 1
        run_collection()

        router = self.db.query(Router).filter_by(name=settings.router_name).first()
        self.assertIsNotNone(router)
        self.assertEqual(router.identity, "TestRouter-NOC")
        self.assertEqual(router.board_name, "hEX S")
        self.assertTrue(router.is_reachable)

        snapshot = (
            self.db.query(ResourceSnapshot)
            .filter_by(router_id=router.id)
            .order_by(ResourceSnapshot.timestamp.desc())
            .first()
        )
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.cpu_load, 15)
        self.assertEqual(snapshot.ram_percent, 50.0)
        self.assertEqual(snapshot.dhcp_client_count, 1)
        self.assertEqual(snapshot.wan_status, "up")
        self.assertEqual(snapshot.temperature, 42.0)

        # Verify interfaces saved
        ifaces = self.db.query(InterfaceSnapshot).filter_by(snapshot_id=snapshot.id).all()
        self.assertEqual(len(ifaces), 2)

        # Verify client devices saved
        clients = self.db.query(ClientDevice).filter_by(router_id=router.id).all()
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].ip_address, "192.168.88.100")
        self.assertEqual(clients[0].hostname, "iPhone-User")


class TestAlertEngine(unittest.TestCase):
    """Test alert detection, hysteresis, and auto-resolution."""

    def setUp(self) -> None:
        init_db()
        self.db = SessionLocal()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        self.router = Router(
            name="alert-test-router",
            host="192.168.1.1",
            is_reachable=True,
        )
        self.db.add(self.router)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_cpu_high_alert_hysteresis(self) -> None:
        # Snapshot 1: CPU high (first reading, should NOT trigger alert due to hysteresis)
        s1 = ResourceSnapshot(
            router_id=self.router.id,
            timestamp=utcnow() - timedelta(seconds=60),
            cpu_load=90,
            is_reachable=True,
            wan_status="up",
        )
        self.db.add(s1)
        self.db.commit()

        evaluate_alerts(self.db, self.router.id, s1, None)
        active = get_active_alerts(self.db, self.router.id)
        self.assertEqual(len(active), 0)

        # Snapshot 2: Second consecutive high CPU reading -> SHOULD trigger alert
        s2 = ResourceSnapshot(
            router_id=self.router.id,
            timestamp=utcnow(),
            cpu_load=95,
            is_reachable=True,
            wan_status="up",
        )
        self.db.add(s2)
        self.db.commit()

        evaluate_alerts(self.db, self.router.id, s2, s1)
        active = get_active_alerts(self.db, self.router.id)
        active_cpu = [a for a in active if a["type"] == "cpu_high" and a["is_active"]]
        self.assertEqual(len(active_cpu), 1)
        self.assertEqual(active_cpu[0]["severity"], "warning")

        # Snapshot 3: CPU drops back to 30% -> SHOULD resolve alert
        s3 = ResourceSnapshot(
            router_id=self.router.id,
            timestamp=utcnow() + timedelta(seconds=30),
            cpu_load=30,
            is_reachable=True,
            wan_status="up",
        )
        self.db.add(s3)
        self.db.commit()

        evaluate_alerts(self.db, self.router.id, s3, s2)
        active_after = get_active_alerts(self.db, self.router.id)
        active_cpu_after = [a for a in active_after if a["type"] == "cpu_high" and a["is_active"]]
        self.assertEqual(len(active_cpu_after), 0)

    def test_router_unreachable_alert(self) -> None:
        s1 = ResourceSnapshot(
            router_id=self.router.id,
            timestamp=utcnow(),
            is_reachable=False,
            wan_status="unknown",
        )
        self.db.add(s1)
        self.db.commit()

        evaluate_alerts(self.db, self.router.id, s1, None)
        active = get_active_alerts(self.db, self.router.id)
        unreachable = [a for a in active if a["type"] == "router_unreachable" and a["is_active"]]
        self.assertEqual(len(unreachable), 1)
        self.assertEqual(unreachable[0]["severity"], "critical")


class TestAPIEndpoints(unittest.TestCase):
    """Test REST API routes using FastAPI TestClient."""

    def setUp(self) -> None:
        init_db()
        self.client = TestClient(app)

    def test_dashboard_html_view(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Orbit", response.text)
        self.assertIn("chart-traffic-24h", response.text)

    def test_api_status(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("is_online", data)

    def test_api_charts_endpoints(self) -> None:
        endpoints = [
            "/api/traffic/24h",
            "/api/traffic/7d",
            "/api/traffic/daily",
            "/api/cpu/history",
            "/api/ram/history",
            "/api/users/history",
            "/api/top-consumers",
            "/api/interfaces",
            "/api/alerts",
            "/api/outages",
        ]
        for ep in endpoints:
            response = self.client.get(ep)
            self.assertEqual(response.status_code, 200, f"Endpoint {ep} failed with {response.status_code}")
            self.assertIsInstance(response.json(), list, f"Endpoint {ep} should return a JSON list")

    def test_api_unified_users_and_vpn_summary(self) -> None:
        r1 = self.client.get("/api/users/unified")
        self.assertEqual(r1.status_code, 200)
        data_users = r1.json()
        self.assertIn("counts", data_users)
        self.assertIn("oficina", data_users["counts"])
        self.assertIn("vpn", data_users["counts"])
        self.assertIn("vm", data_users["counts"])

        r2 = self.client.get("/api/vpn/summary")
        self.assertEqual(r2.status_code, 200)
        data_vpn = r2.json()
        self.assertIn("connected_users", data_vpn)
        self.assertIn("protocols_detected", data_vpn)


if __name__ == "__main__":
    unittest.main()
