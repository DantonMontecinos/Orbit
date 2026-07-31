"""
Read-only SSH client for Ubiquiti UniFi APs.

Connects via SSH, runs `mca-dump` to get a full JSON snapshot
of the AP state including system stats, radio info, and per-SSID
client counts via the vap_table.

Safety guarantee: Only executes read-only commands. Never modifies
configuration, reboots, or changes any setting.
"""

import json
from typing import Any

import paramiko

from app.utils.logger import get_logger

log = get_logger("collectors.ubiquiti.ssh")


class UnifiSSHClient:
    """Read-only SSH client for Ubiquiti UniFi Access Points."""

    def __init__(
        self,
        host: str,
        username: str = "ubnt",
        password: str = "",
        port: int = 22,
        timeout: int = 15,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout

    def _exec_command(self, command: str) -> str:
        """Execute a single read-only command via SSH."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            _, stdout, stderr = client.exec_command(command, timeout=self.timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            return output
        finally:
            client.close()

    def collect_all(self) -> dict[str, Any]:
        """
        Collect all metrics from the AP via mca-dump.

        Returns a normalized dict with:
            - is_reachable: bool
            - model, firmware, uptime_seconds
            - cpu_load, ram_used, ram_total
            - vap_table: [{ssid, radio, channel, client_count, bssid, tx_bytes, rx_bytes}]
        """
        result: dict[str, Any] = {
            "is_reachable": False,
            "model": None,
            "firmware": None,
            "uptime_seconds": None,
            "cpu_load": None,
            "ram_used": None,
            "ram_total": None,
            "vap_table": [],
        }

        try:
            raw_json = self._exec_command("mca-dump")
            if not raw_json.strip():
                log.warning("Empty mca-dump response from %s", self.host)
                return result

            data = json.loads(raw_json)
            result["is_reachable"] = True

            # System info
            result["model"] = (
                data.get("model_display")
                or data.get("model")
                or data.get("board_rev")
            )
            result["firmware"] = data.get("version")
            result["uptime_seconds"] = data.get("uptime")

            # System stats (CPU / RAM)
            sys_stats = data.get("system-stats", {})
            if sys_stats:
                # CPU: mca-dump reports cpu as percentage string or loadavg
                cpu_raw = sys_stats.get("cpu")
                if cpu_raw is not None:
                    try:
                        result["cpu_load"] = int(float(str(cpu_raw).rstrip("%")))
                    except (ValueError, TypeError):
                        pass

                mem = sys_stats.get("mem", {})
                if isinstance(mem, dict):
                    total = mem.get("total")
                    free = mem.get("free")
                    if total is not None:
                        result["ram_total"] = int(total) * 1024  # KB → bytes
                    if total is not None and free is not None:
                        result["ram_used"] = (int(total) - int(free)) * 1024

            # VAP table (WiFi SSIDs with client counts)
            vap_table = data.get("vap_table", [])
            for vap in vap_table:
                essid = vap.get("essid", "")
                if not essid or essid.startswith("vwire-"):
                    continue

                # Determine radio band from radio field or interface name
                radio_name = str(vap.get("radio", "")).lower()
                if "na" in radio_name or "5g" in radio_name or "wifi1" in radio_name or "ath1" in radio_name:
                    radio = "5GHz"
                elif "ng" in radio_name or "2g" in radio_name or "wifi0" in radio_name or "ath0" in radio_name:
                    radio = "2.4GHz"
                else:
                    radio = radio_name.upper() or "WiFi"

                result["vap_table"].append({
                    "ssid": essid,
                    "radio": radio,
                    "channel": vap.get("channel"),
                    "client_count": vap.get("num_sta", 0),
                    "bssid": vap.get("bssid"),
                    "tx_bytes": vap.get("tx_bytes", 0),
                    "rx_bytes": vap.get("rx_bytes", 0),
                })

            log.info(
                "Collected from %s: model=%s, %d VAPs, %d total clients",
                self.host,
                result["model"],
                len(result["vap_table"]),
                sum(v["client_count"] for v in result["vap_table"]),
            )

        except json.JSONDecodeError:
            log.warning("Invalid JSON from mca-dump on %s", self.host)
        except paramiko.AuthenticationException:
            log.error("SSH authentication failed for %s", self.host)
        except paramiko.SSHException as e:
            log.warning("SSH error connecting to %s: %s", self.host, e)
        except OSError as e:
            log.warning("Cannot reach %s via SSH: %s", self.host, e)
        except Exception:
            log.exception("Unexpected error collecting from %s", self.host)

        return result
