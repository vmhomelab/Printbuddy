"""
Bambu Lab printer discovery service using SSDP and subnet scanning.

Bambu Lab printers advertise themselves via SSDP (Simple Service Discovery Protocol)
on the local network. This service listens for these advertisements and provides
a list of discovered printers.

For Docker environments where SSDP multicast doesn't work, subnet scanning is
available as an alternative discovery method.
"""

import asyncio
import ipaddress
import logging
import os
import re
import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    # Check for .dockerenv file
    if Path("/.dockerenv").exists():
        return True

    # Check cgroup for docker/containerd
    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if "docker" in content or "containerd" in content or "kubepods" in content:
                return True
    except (FileNotFoundError, PermissionError):
        pass  # /proc/1/cgroup may not exist or be readable; fall through to env check

    # Check for container environment variable
    return bool(os.environ.get("CONTAINER") or os.environ.get("DOCKER_CONTAINER"))


# SSDP multicast address - Bambu uses port 2021, not standard 1900
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 2021  # Bambu Lab uses non-standard port

# Bambu Lab SSDP search target
BAMBU_SEARCH_TARGET = "urn:bambulab-com:device:3dprinter:1"

# Virtual printer serial suffix to exclude from discovery (Printbuddy's own virtual printer)
# All virtual printer serials end with this suffix, regardless of model
VIRTUAL_PRINTER_SERIAL_SUFFIX = "391800001"

# SSDP M-SEARCH message
SSDP_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    f"ST: {BAMBU_SEARCH_TARGET}\r\n"
    "\r\n"
)


@dataclass
class DiscoveredPrinter:
    """Represents a discovered Bambu Lab printer."""

    serial: str
    name: str
    ip_address: str
    model: str | None = None
    discovered_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "name": self.name,
            "ip_address": self.ip_address,
            "model": self.model,
            "discovered_at": self.discovered_at,
        }


class PrinterDiscoveryService:
    """Service for discovering Bambu Lab printers on the network."""

    def __init__(self):
        self._discovered: dict[str, DiscoveredPrinter] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_printers(self) -> list[DiscoveredPrinter]:
        return list(self._discovered.values())

    def clear(self):
        """Clear discovered printers."""
        self._discovered.clear()

    async def start(self, duration: float = 10.0):
        """Start discovery for a specified duration."""
        if self._running:
            return

        self._running = True
        self._discovered.clear()
        self._task = asyncio.create_task(self._discover(duration))

    async def stop(self):
        """Stop discovery."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected when cancelling the discovery task
        self._task = None

    async def _discover(self, duration: float):
        """Run discovery for the specified duration.

        Bambu printers broadcast NOTIFY messages periodically on port 2021.
        We need to bind to that port and listen for broadcasts.
        """
        sock = None
        try:
            # Create UDP socket for SSDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Try to set SO_REUSEPORT if available (Linux/macOS)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # SO_REUSEPORT not available on all platforms; non-critical

            # Set non-blocking mode
            sock.setblocking(False)

            # Bind to the SSDP port to receive NOTIFY broadcasts from printers
            sock.bind(("", SSDP_PORT))

            # Join multicast group to receive multicast messages
            mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            # Enable broadcast
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            logger.info("Starting SSDP discovery on port %s for Bambu Lab printers...", SSDP_PORT)

            # Send initial M-SEARCH request to trigger responses
            try:
                sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
            except OSError as e:
                logger.debug("M-SEARCH send error: %s", e)

            start_time = asyncio.get_event_loop().time()
            last_send = start_time

            while self._running and (asyncio.get_event_loop().time() - start_time) < duration:
                # Try to receive data
                try:
                    data, addr = sock.recvfrom(4096)
                    message = data.decode("utf-8", errors="ignore")
                    logger.debug("Received from %s: %s...", addr[0], message[:100])
                    self._handle_response(message, addr[0])
                except BlockingIOError:
                    # No data available, that's fine
                    pass
                except OSError as e:
                    logger.debug("SSDP receive error: %s", e)

                # Re-send M-SEARCH every 3 seconds
                now = asyncio.get_event_loop().time()
                if now - last_send >= 3.0:
                    try:
                        sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
                        last_send = now
                    except OSError as e:
                        logger.debug("SSDP send error: %s", e)

                await asyncio.sleep(0.1)

            logger.info("Discovery complete. Found %s printers.", len(self._discovered))

        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning("Port %s is in use, trying alternative discovery...", SSDP_PORT)
                await self._discover_alternative(duration)
            else:
                logger.error("Discovery error: %s", e)
        except Exception as e:
            logger.error("Discovery error: %s", e)
        finally:
            self._running = False
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass  # Best-effort socket cleanup

    async def _discover_alternative(self, duration: float):
        """Alternative discovery using a random port (less reliable)."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            sock.bind(("", 0))

            # Join multicast group
            mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            logger.info("Using alternative discovery method...")

            start_time = asyncio.get_event_loop().time()
            last_send = start_time

            while self._running and (asyncio.get_event_loop().time() - start_time) < duration:
                try:
                    data, addr = sock.recvfrom(4096)
                    self._handle_response(data.decode("utf-8", errors="ignore"), addr[0])
                except BlockingIOError:
                    pass  # No data available yet on non-blocking socket
                except OSError as e:
                    logger.debug("SSDP receive error: %s", e)

                now = asyncio.get_event_loop().time()
                if now - last_send >= 2.0:
                    try:
                        sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
                        last_send = now
                    except OSError:
                        pass  # Best-effort M-SEARCH resend; will retry next interval

                await asyncio.sleep(0.1)

            logger.info("Alternative discovery complete. Found %s printers.", len(self._discovered))
        except Exception as e:
            logger.error("Alternative discovery error: %s", e)
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass  # Best-effort socket cleanup

    def _handle_response(self, response: str, ip_address: str):
        """Parse SSDP response and extract printer info."""
        # Check if it's a Bambu Lab printer response
        if BAMBU_SEARCH_TARGET not in response and "bambulab" not in response.lower():
            logger.debug("Ignoring non-Bambu response from %s", ip_address)
            return

        # Extract USN (Unique Service Name) which contains the serial
        # Bambu format is just "USN: SERIALNUMBER" (no uuid: prefix)
        usn_match = re.search(r"USN:\s*(?:uuid:)?([^\s\r\n]+)", response, re.IGNORECASE)
        if not usn_match:
            logger.debug("No USN found in response from %s", ip_address)
            return

        serial = usn_match.group(1).strip()

        # Skip Printbuddy's own virtual printer (any model variant)
        if serial.endswith(VIRTUAL_PRINTER_SERIAL_SUFFIX):
            logger.debug("Ignoring Printbuddy virtual printer at %s", ip_address)
            return

        # Extract device name from LOCATION or DevName header
        name = serial  # Default to serial if no name found
        name_match = re.search(r"DevName\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()

        # Try to extract model from DevModel header
        model = None
        model_match = re.search(r"DevModel\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
        if model_match:
            model = model_match.group(1).strip()

        # Also try NT header for model
        if not model:
            nt_match = re.search(r"NT:\s*urn:bambulab-com:device:([^:]+)", response, re.IGNORECASE)
            if nt_match:
                model = nt_match.group(1).strip()

        # Skip if already discovered
        if serial in self._discovered:
            return

        printer = DiscoveredPrinter(
            serial=serial,
            name=name,
            ip_address=ip_address,
            model=model,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

        self._discovered[serial] = printer
        logger.info("Discovered printer: %s (%s) at %s", name, serial, ip_address)


class SubnetScanner:
    """Scanner for discovering Bambu printers by probing IP addresses."""

    # Bambu printer ports
    MQTT_PORT = 8883
    FTP_PORT = 990

    def __init__(self):
        self._discovered: dict[str, DiscoveredPrinter] = {}
        self._running = False
        self._scanned = 0
        self._total = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_printers(self) -> list[DiscoveredPrinter]:
        return list(self._discovered.values())

    @property
    def progress(self) -> tuple[int, int]:
        """Return (scanned, total) counts."""
        return self._scanned, self._total

    async def scan_subnet(self, subnet: str, timeout: float = 1.0) -> list[DiscoveredPrinter]:
        """Scan a subnet for Bambu printers.

        Args:
            subnet: CIDR notation subnet (e.g., "192.168.1.0/24")
            timeout: Connection timeout per host in seconds

        Returns:
            List of discovered printers
        """
        if self._running:
            return []

        self._running = True
        self._discovered.clear()
        self._scanned = 0

        try:
            network = ipaddress.ip_network(subnet, strict=False)
            hosts = list(network.hosts())
            self._total = len(hosts)

            if self._total > 1024:
                logger.warning("Subnet %s has %s hosts, limiting to /22 (1024 hosts)", subnet, self._total)
                self._total = 1024
                hosts = hosts[:1024]

            logger.info("Starting subnet scan of %s (%s hosts)", subnet, self._total)

            # Scan in batches to avoid overwhelming the network
            batch_size = 50
            for i in range(0, len(hosts), batch_size):
                if not self._running:
                    break

                batch = hosts[i : i + batch_size]
                tasks = [self._probe_host(str(ip), timeout) for ip in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                self._scanned = min(i + batch_size, len(hosts))

            logger.info("Subnet scan complete. Found %s printers.", len(self._discovered))
            return self.discovered_printers

        except ValueError as e:
            logger.error("Invalid subnet format: %s", e)
            return []
        finally:
            self._running = False

    async def _probe_host(self, ip: str, timeout: float):
        """Probe a single host for Bambu printer ports."""
        # Check FTP port (990) - more reliable indicator
        ftp_open = await self._check_port(ip, self.FTP_PORT, timeout)
        if not ftp_open:
            return

        # Also check MQTT port (8883) for confirmation
        mqtt_open = await self._check_port(ip, self.MQTT_PORT, timeout)
        if not mqtt_open:
            return

        # Both ports open - likely a Bambu printer
        logger.info("Found potential Bambu printer at %s", ip)

        # Try to get printer info via SSDP unicast
        serial, name, model = await self._get_printer_info_ssdp(ip, timeout)

        # Skip Printbuddy's own virtual printer (any model variant)
        if serial and serial.endswith(VIRTUAL_PRINTER_SERIAL_SUFFIX):
            logger.debug("Ignoring Printbuddy virtual printer at %s", ip)
            return

        printer = DiscoveredPrinter(
            serial=serial or f"unknown-{ip.replace('.', '-')}",
            name=name or f"Printer at {ip}",
            ip_address=ip,
            model=model,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        self._discovered[ip] = printer

    async def _get_printer_info_ssdp(self, ip: str, timeout: float) -> tuple[str | None, str | None, str | None]:
        """Try to get printer info via SSDP unicast query."""
        loop = asyncio.get_event_loop()

        def _query():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.settimeout(timeout)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # Send M-SEARCH directly to the printer
                msearch = (
                    "M-SEARCH * HTTP/1.1\r\n"
                    f"HOST: {ip}:{SSDP_PORT}\r\n"
                    'MAN: "ssdp:discover"\r\n'
                    "MX: 1\r\n"
                    f"ST: {BAMBU_SEARCH_TARGET}\r\n"
                    "\r\n"
                )
                sock.sendto(msearch.encode(), (ip, SSDP_PORT))

                # Wait for response
                data, _ = sock.recvfrom(4096)
                response = data.decode("utf-8", errors="ignore")
                sock.close()

                # Parse response
                serial = None
                name = None
                model = None

                usn_match = re.search(r"USN:\s*(?:uuid:)?([^\s\r\n]+)", response, re.IGNORECASE)
                if usn_match:
                    serial = usn_match.group(1).strip()

                name_match = re.search(r"DevName\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1).strip()

                model_match = re.search(r"DevModel\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
                if model_match:
                    model = model_match.group(1).strip()

                logger.debug("SSDP info from %s: serial=%s, name=%s, model=%s", ip, serial, name, model)
                return serial, name, model

            except OSError as e:
                logger.debug("SSDP query to %s failed: %s", ip, e)
                return None, None, None

        return await loop.run_in_executor(None, _query)

    async def _check_port(self, ip: str, port: int, timeout: float) -> bool:
        """Check if a port is open on the given IP."""
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            logger.debug("Port %s open on %s", port, ip)
            return True
        except TimeoutError:
            return False
        except ConnectionRefusedError:
            return False
        except OSError as e:
            # Log first few errors to help debug network issues
            if self._scanned < 5:
                logger.debug("OSError checking %s:%s: %s", ip, port, e)
            return False

    def stop(self):
        """Stop the current scan."""
        self._running = False


class TasmotaScanner:
    """Scanner for discovering Tasmota devices by probing IP addresses."""

    HTTP_PORT = 80

    def __init__(self):
        self._discovered: dict[str, dict] = {}
        self._running = False
        self._scanned = 0
        self._total = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_devices(self) -> list[dict]:
        return list(self._discovered.values())

    @property
    def progress(self) -> tuple[int, int]:
        """Return (scanned, total) counts."""
        return self._scanned, self._total

    async def scan_range(self, from_ip: str, to_ip: str, timeout: float = 1.0) -> list[dict]:
        """Scan an IP range for Tasmota devices.

        Args:
            from_ip: Starting IP address (e.g., "192.168.1.1")
            to_ip: Ending IP address (e.g., "192.168.1.254")
            timeout: Connection timeout per host in seconds

        Returns:
            List of discovered Tasmota devices
        """
        if self._running:
            return []

        self._running = True
        self._discovered.clear()
        self._scanned = 0

        try:
            start = ipaddress.ip_address(from_ip)
            end = ipaddress.ip_address(to_ip)

            # Generate list of IPs in range
            hosts = []
            current = start
            while current <= end:
                hosts.append(str(current))
                current = ipaddress.ip_address(int(current) + 1)

            self._total = len(hosts)

            if self._total > 1024:
                logger.warning("IP range has %s hosts, limiting to 1024", self._total)
                self._total = 1024
                hosts = hosts[:1024]

            logger.info("Starting Tasmota scan from %s to %s (%s hosts)", from_ip, to_ip, self._total)

            # Scan in batches to avoid overwhelming the network
            batch_size = 50
            for i in range(0, len(hosts), batch_size):
                if not self._running:
                    logger.info("Tasmota scan stopped by user")
                    break

                batch = hosts[i : i + batch_size]
                tasks = [self._probe_host(ip) for ip in batch]
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as e:
                    logger.warning("Batch %s error: %s", i // batch_size, e)
                self._scanned = min(i + batch_size, len(hosts))

            logger.info("Tasmota scan complete. Found %s devices.", len(self._discovered))
            return self.discovered_devices

        except ValueError as e:
            logger.error("Invalid IP address format: %s", e)
            return []
        finally:
            self._running = False

    async def _probe_host(self, ip: str):
        """Probe a single host for Tasmota HTTP API."""
        try:
            # Hard timeout of 5 seconds max per host
            await asyncio.wait_for(self._do_probe(ip), timeout=5.0)
        except TimeoutError:
            pass  # Host did not respond in time; skip
        except Exception:
            pass  # Probe failed for this host; skip silently

    async def _do_probe(self, ip: str):
        """Actually probe the host."""
        import httpx

        try:
            # Reasonable timeouts for network scanning
            client_timeout = httpx.Timeout(3.0, connect=1.0)
            async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=False) as client:
                # First try simple Power command - most reliable indicator of Tasmota
                power_url = f"http://{ip}/cm?cmnd=Power"
                try:
                    power_response = await client.get(power_url)
                    if power_response.status_code == 401:
                        # Device requires auth - still a Tasmota device!
                        logger.info("Discovered Tasmota at %s (requires auth - 401)", ip)
                        device = {
                            "ip_address": ip,
                            "name": f"Tasmota ({ip})",
                            "module": None,
                            "state": "UNKNOWN",
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        self._discovered[ip] = device
                        return

                    if power_response.status_code != 200:
                        return

                    power_data = power_response.json()

                    # Check for Tasmota auth warning (returns 200 with WARNING)
                    if "WARNING" in power_data:
                        logger.info("Discovered Tasmota at %s (requires auth)", ip)
                        device = {
                            "ip_address": ip,
                            "name": f"Tasmota ({ip})",
                            "module": None,
                            "state": "UNKNOWN",
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        self._discovered[ip] = device
                        return

                    # Check if response looks like Tasmota (has POWER or POWER1 key)
                    power_state = power_data.get("POWER") or power_data.get("POWER1")
                    if power_state is None:
                        return

                except Exception as e:
                    logger.debug("Error probing %s: %s", ip, e)
                    return

                # It's a Tasmota device! Now get more info
                device_name = f"Tasmota ({ip})"
                module = None

                # Try to get device name from Status 0
                try:
                    status_url = f"http://{ip}/cm?cmnd=Status%200"
                    status_response = await client.get(status_url)
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        if "Status" in status_data:
                            status = status_data["Status"]
                            device_name = status.get("DeviceName") or device_name
                            if not device_name or device_name == f"Tasmota ({ip})":
                                # Try FriendlyName
                                friendly = status.get("FriendlyName")
                                if friendly and isinstance(friendly, list) and friendly[0]:
                                    device_name = friendly[0]
                            module = status.get("Module")
                except Exception:
                    pass  # Status query is optional; proceed with defaults

                device = {
                    "ip_address": ip,
                    "name": device_name,
                    "module": module,
                    "state": power_state,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                }

                self._discovered[ip] = device
                logger.info("Discovered Tasmota device: %s at %s", device_name, ip)

        except httpx.TimeoutException:
            pass  # Host unreachable or too slow; not a Tasmota device
        except httpx.ConnectError:
            pass  # Connection refused; no HTTP server on this host
        except Exception:
            pass  # Unexpected error probing host; skip silently

    def stop(self):
        """Stop the current scan."""
        self._running = False


@dataclass
class DiscoveredMoonraker:
    """Represents a discovered Moonraker / Klipper instance."""

    serial: str
    name: str
    ip_address: str
    api_url: str
    needs_auth: bool = False
    model: str | None = None
    discovered_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "name": self.name,
            "ip_address": self.ip_address,
            "api_url": self.api_url,
            "needs_auth": self.needs_auth,
            "model": self.model,
            "discovered_at": self.discovered_at,
        }


def _moonraker_serial_for_ip(ip: str) -> str:
    """Build a synthetic serial matching printer schema conventions."""
    from backend.app.schemas.printer import _synthetic_moonraker_serial

    return _synthetic_moonraker_serial(ip)


def _looks_like_moonraker_info(payload: object) -> bool:
    """Return True if JSON looks like Moonraker ``server/info``.

    Requires Klipper/Moonraker-specific fields so unrelated HTTP services
    (file servers, reverse proxies, auth walls) are not treated as hits.
    """
    if not isinstance(payload, dict):
        return False
    data = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    if not isinstance(data, dict):
        return False
    # Prefer strong identifiers; avoid generic keys like api_version alone.
    return any(key in data for key in ("klippy_state", "moonraker_version", "klippy_connected"))


def parse_moonraker_scan_ports(raw: str | list[int] | None = None) -> list[int]:
    """Parse Moonraker probe ports from request/env (default ``7125,80``).

    Port 80 is included for Cosmos / Fluidd reverse-proxies that expose the
    Moonraker API on the UI port. Hits still require Moonraker-shaped JSON, so
    unrelated :80 services (e.g. copyparty auth walls) are not matched.
    """
    if isinstance(raw, list):
        ports = [int(p) for p in raw if isinstance(p, int) or str(p).strip().isdigit()]
    else:
        value = raw if raw is not None else os.environ.get("DISCOVERY_MOONRAKER_PORTS", "7125,80")
        ports = []
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                port = int(part)
            except ValueError:
                logger.warning("Ignoring invalid DISCOVERY_MOONRAKER_PORTS entry: %s", part)
                continue
            if 1 <= port <= 65535:
                ports.append(port)
            else:
                logger.warning("Ignoring out-of-range Moonraker scan port: %s", port)

    # Preserve order, drop duplicates
    seen: set[int] = set()
    ordered: list[int] = []
    for port in ports:
        if port not in seen:
            seen.add(port)
            ordered.append(port)
    return ordered or [7125, 80]


def _moonraker_base_url_for_port(ip: str, port: int) -> str:
    """Build a Moonraker base URL; omit ``:80`` so CosmOS/Fluidd URLs stay clean."""
    if port == 80:
        return f"http://{ip}"
    return f"http://{ip}:{port}"


class MoonrakerSubnetScanner:
    """Scanner for discovering Moonraker instances via HTTP ``server/info``.

    Probes configurable ports (default 7125 then 80). Only HTTP 200 responses
    with Moonraker/Klipper-shaped JSON count as hits — bare 401/403 auth walls
    on unrelated LAN services are ignored.
    """

    def __init__(self):
        self._discovered: dict[str, DiscoveredMoonraker] = {}
        self._running = False
        self._scanned = 0
        self._total = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_printers(self) -> list[DiscoveredMoonraker]:
        return list(self._discovered.values())

    @property
    def progress(self) -> tuple[int, int]:
        """Return (scanned, total) counts."""
        return self._scanned, self._total

    async def scan_subnet(
        self,
        subnet: str,
        timeout: float = 1.0,
        ports: list[int] | None = None,
    ) -> list[DiscoveredMoonraker]:
        """Scan a subnet for Moonraker HTTP APIs.

        Args:
            subnet: CIDR notation subnet (e.g., "192.168.1.0/24")
            timeout: Connect timeout per host in seconds
            ports: Ports to probe per host (default from DISCOVERY_MOONRAKER_PORTS)

        Returns:
            List of discovered Moonraker instances
        """
        if self._running:
            return []

        self._running = True
        self._discovered.clear()
        self._scanned = 0
        probe_ports = parse_moonraker_scan_ports(ports)

        try:
            network = ipaddress.ip_network(subnet, strict=False)
            hosts = list(network.hosts())
            self._total = len(hosts)

            if self._total > 1024:
                logger.warning("Subnet %s has %s hosts, limiting to 1024", subnet, self._total)
                self._total = 1024
                hosts = hosts[:1024]

            logger.info(
                "Starting Moonraker subnet scan of %s (%s hosts, ports=%s)",
                subnet,
                self._total,
                probe_ports,
            )

            batch_size = 50
            for i in range(0, len(hosts), batch_size):
                if not self._running:
                    logger.info("Moonraker scan stopped by user")
                    break

                batch = hosts[i : i + batch_size]
                tasks = [self._probe_host(str(ip), timeout, probe_ports) for ip in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                self._scanned = min(i + batch_size, len(hosts))

            logger.info("Moonraker scan complete. Found %s instances.", len(self._discovered))
            return self.discovered_printers

        except ValueError as e:
            logger.error("Invalid subnet format: %s", e)
            return []
        finally:
            self._running = False

    async def _probe_host(self, ip: str, timeout: float, ports: list[int]):
        """Probe a single host for Moonraker on the configured ports."""
        try:
            # Extra room when multiple ports are tried per host.
            await asyncio.wait_for(
                self._do_probe(ip, timeout, ports),
                timeout=max(timeout * (2 + len(ports)), 5.0),
            )
        except TimeoutError:
            pass
        except Exception:
            pass

    async def _do_probe(self, ip: str, timeout: float, ports: list[int]):
        import httpx

        client_timeout = httpx.Timeout(max(timeout * 2, 2.0), connect=timeout)

        async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=False) as client:
            for port in ports:
                base_url = _moonraker_base_url_for_port(ip, port)
                url = f"{base_url}/server/info"
                try:
                    response = await client.get(url)
                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
                    continue
                except Exception:
                    continue

                if response.status_code != 200:
                    # Do not treat generic 401/403 as Moonraker — many LAN services
                    # auth-wall unknown paths (copyparty, NAS UI, etc.).
                    continue

                try:
                    payload = response.json()
                except Exception:
                    continue

                if not _looks_like_moonraker_info(payload):
                    continue

                self._record_hit(ip, base_url, needs_auth=False, payload=payload)
                return

    def _record_hit(
        self,
        ip: str,
        base_url: str,
        *,
        needs_auth: bool,
        payload: object | None = None,
    ):
        if ip in self._discovered:
            return

        name = f"Moonraker ({ip})"
        if isinstance(payload, dict):
            data = payload.get("result") if isinstance(payload.get("result"), dict) else payload
            if isinstance(data, dict):
                hostname = data.get("hostname") or data.get("device_name")
                if isinstance(hostname, str) and hostname.strip():
                    name = hostname.strip()

        printer = DiscoveredMoonraker(
            serial=_moonraker_serial_for_ip(ip),
            name=name,
            ip_address=ip,
            api_url=base_url,
            needs_auth=needs_auth,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        self._discovered[ip] = printer
        if needs_auth:
            logger.info("Discovered Moonraker at %s (requires auth)", ip)
        else:
            logger.info("Discovered Moonraker at %s (%s)", ip, base_url)

    def stop(self):
        """Stop the current scan."""
        self._running = False


# Global instances
discovery_service = PrinterDiscoveryService()
subnet_scanner = SubnetScanner()
tasmota_scanner = TasmotaScanner()
moonraker_subnet_scanner = MoonrakerSubnetScanner()
