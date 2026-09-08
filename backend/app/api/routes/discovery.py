"""
Printer discovery API endpoints.

Provides endpoints for discovering Bambu Lab printers on the local network.
Supports both SSDP discovery (for native installs) and subnet scanning (for Docker).
Also supports Moonraker/Klipper subnet scanning via HTTP ``server/info``.
"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.permissions import Permission
from backend.app.models.user import User
from backend.app.services.discovery import (
    discovery_service,
    is_running_in_docker,
    moonraker_subnet_scanner,
    subnet_scanner,
)
from backend.app.services.network_utils import get_discovery_subnets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])


class DiscoveryStatus(BaseModel):
    """Discovery status response."""

    running: bool


class DiscoveryInfo(BaseModel):
    """Discovery environment info."""

    is_docker: bool
    ssdp_running: bool
    scan_running: bool
    moonraker_scan_running: bool = False
    subnets: list[str] = []


class SubnetScanRequest(BaseModel):
    """Request to scan a subnet."""

    subnet: str  # CIDR notation, e.g., "192.168.1.0/24"
    timeout: float = 1.0  # Connection timeout per host


class MoonrakerSubnetScanRequest(BaseModel):
    """Request to scan a subnet for Moonraker instances."""

    subnet: str  # CIDR notation, e.g., "192.168.1.0/24"
    timeout: float = 1.0  # Connection timeout per host
    # Ports to probe per host. Default is DISCOVERY_MOONRAKER_PORTS or 7125,80.
    # Port 80 covers CosmOS / Fluidd reverse-proxies; hits still require
    # Moonraker-shaped JSON so unrelated HTTP services are ignored.
    ports: list[int] | None = None


class SubnetScanStatus(BaseModel):
    """Subnet scan status response."""

    running: bool
    scanned: int
    total: int


class DiscoveredPrinterResponse(BaseModel):
    """Discovered printer response."""

    serial: str
    name: str
    ip_address: str
    model: str | None = None
    discovered_at: str | None = None
    api_url: str | None = None
    needs_auth: bool = False


@router.get("/info", response_model=DiscoveryInfo)
async def get_discovery_info(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get discovery environment info (Docker detection, etc.)."""
    return DiscoveryInfo(
        is_docker=is_running_in_docker(),
        ssdp_running=discovery_service.is_running,
        scan_running=subnet_scanner.is_running,
        moonraker_scan_running=moonraker_subnet_scanner.is_running,
        subnets=get_discovery_subnets(),
    )


@router.get("/status", response_model=DiscoveryStatus)
async def get_discovery_status(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get the current SSDP discovery status."""
    return DiscoveryStatus(running=discovery_service.is_running)


@router.post("/start", response_model=DiscoveryStatus)
async def start_discovery(
    duration: float = 10.0,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Start SSDP printer discovery.

    Args:
        duration: Discovery duration in seconds (default 10)
    """
    await discovery_service.start(duration=duration)
    return DiscoveryStatus(running=discovery_service.is_running)


@router.post("/stop", response_model=DiscoveryStatus)
async def stop_discovery(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Stop SSDP printer discovery."""
    await discovery_service.stop()
    return DiscoveryStatus(running=discovery_service.is_running)


@router.get("/printers", response_model=list[DiscoveredPrinterResponse])
async def get_discovered_printers(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get list of discovered printers (from both SSDP and subnet scan)."""
    # Combine results from both discovery methods
    printers = {}

    # Add SSDP discovered printers
    for p in discovery_service.discovered_printers:
        printers[p.ip_address] = p

    # Add subnet scan discovered printers (may override if same IP)
    for p in subnet_scanner.discovered_printers:
        if p.ip_address not in printers:
            printers[p.ip_address] = p

    return [
        DiscoveredPrinterResponse(
            serial=p.serial,
            name=p.name,
            ip_address=p.ip_address,
            model=p.model,
            discovered_at=p.discovered_at,
        )
        for p in printers.values()
    ]


# Subnet scanning endpoints (for Docker environments)


@router.post("/scan", response_model=SubnetScanStatus)
async def start_subnet_scan(
    request: SubnetScanRequest,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Start a subnet scan for Bambu printers.

    Use this when running in Docker where SSDP multicast doesn't work.

    Args:
        request: Subnet to scan in CIDR notation (e.g., "192.168.1.0/24")
    """
    # Start scan in background
    asyncio.create_task(subnet_scanner.scan_subnet(request.subnet, request.timeout))

    # Return immediate status
    scanned, total = subnet_scanner.progress
    return SubnetScanStatus(
        running=subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.get("/scan/status", response_model=SubnetScanStatus)
async def get_scan_status(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get the current subnet scan status."""
    scanned, total = subnet_scanner.progress
    return SubnetScanStatus(
        running=subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.post("/scan/stop", response_model=SubnetScanStatus)
async def stop_subnet_scan(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Stop the current subnet scan."""
    subnet_scanner.stop()
    scanned, total = subnet_scanner.progress
    return SubnetScanStatus(
        running=subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


# Moonraker / Klipper subnet scanning


@router.post("/moonraker/scan", response_model=SubnetScanStatus)
async def start_moonraker_subnet_scan(
    request: MoonrakerSubnetScanRequest,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Start a subnet scan for Moonraker instances (HTTP ``server/info``)."""
    asyncio.create_task(
        moonraker_subnet_scanner.scan_subnet(
            request.subnet,
            request.timeout,
            ports=request.ports,
        )
    )
    scanned, total = moonraker_subnet_scanner.progress
    return SubnetScanStatus(
        running=moonraker_subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.get("/moonraker/scan/status", response_model=SubnetScanStatus)
async def get_moonraker_scan_status(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get the current Moonraker subnet scan status."""
    scanned, total = moonraker_subnet_scanner.progress
    return SubnetScanStatus(
        running=moonraker_subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.post("/moonraker/scan/stop", response_model=SubnetScanStatus)
async def stop_moonraker_subnet_scan(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Stop the current Moonraker subnet scan."""
    moonraker_subnet_scanner.stop()
    scanned, total = moonraker_subnet_scanner.progress
    return SubnetScanStatus(
        running=moonraker_subnet_scanner.is_running,
        scanned=scanned,
        total=total,
    )


@router.get("/moonraker/printers", response_model=list[DiscoveredPrinterResponse])
async def get_discovered_moonraker_printers(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.DISCOVERY_SCAN),
):
    """Get Moonraker instances found by the latest subnet scan."""
    return [
        DiscoveredPrinterResponse(
            serial=p.serial,
            name=p.name,
            ip_address=p.ip_address,
            model=p.model,
            discovered_at=p.discovered_at,
            api_url=p.api_url,
            needs_auth=p.needs_auth,
        )
        for p in moonraker_subnet_scanner.discovered_printers
    ]
