"""Unit tests for Moonraker subnet scanner probe logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.discovery import (
    MoonrakerSubnetScanner,
    _looks_like_moonraker_info,
    _moonraker_base_url_for_port,
    _moonraker_serial_for_ip,
    parse_moonraker_scan_ports,
)


class TestMoonrakerHelpers:
    def test_serial_for_ip(self):
        assert _moonraker_serial_for_ip("10.0.0.89") == "KLIPPER-10-0-0-89"

    def test_looks_like_moonraker_info_wrapped(self):
        assert _looks_like_moonraker_info({"result": {"klippy_state": "ready", "moonraker_version": "0.9.0"}})

    def test_looks_like_moonraker_info_unwrapped(self):
        assert _looks_like_moonraker_info({"moonraker_version": "0.9.0"})

    def test_looks_like_moonraker_info_rejects_weak_or_other_json(self):
        assert not _looks_like_moonraker_info({"api_version": [1, 0, 0]})
        assert not _looks_like_moonraker_info({"websocket_port": 7125})
        assert not _looks_like_moonraker_info({"status": "ok"})
        assert not _looks_like_moonraker_info([])
        assert not _looks_like_moonraker_info(None)

    def test_parse_ports_default(self):
        assert parse_moonraker_scan_ports(None) == [7125, 80]
        assert parse_moonraker_scan_ports("") == [7125, 80]

    def test_parse_ports_custom(self):
        assert parse_moonraker_scan_ports("80") == [80]
        assert parse_moonraker_scan_ports("7125,80,8080") == [7125, 80, 8080]
        assert parse_moonraker_scan_ports([80, 7125, 80]) == [80, 7125]

    def test_base_url_omits_default_http_port(self):
        assert _moonraker_base_url_for_port("10.0.0.126", 80) == "http://10.0.0.126"
        assert _moonraker_base_url_for_port("10.0.0.126", 7125) == "http://10.0.0.126:7125"


def _mock_response(status_code: int, payload: object | None = None):
    response = MagicMock()
    response.status_code = status_code
    if payload is None:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = payload
    return response


@pytest.mark.asyncio
async def test_probe_hit_on_7125_server_info():
    scanner = MoonrakerSubnetScanner()
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_mock_response(200, {"result": {"klippy_state": "ready", "moonraker_version": "0.9.0"}})
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=client):
        await scanner._do_probe("10.0.0.89", timeout=0.5, ports=[7125, 80])

    assert len(scanner.discovered_printers) == 1
    hit = scanner.discovered_printers[0]
    assert hit.ip_address == "10.0.0.89"
    assert hit.api_url == "http://10.0.0.89:7125"
    assert hit.needs_auth is False
    assert hit.serial == "KLIPPER-10-0-0-89"
    client.get.assert_awaited_once_with("http://10.0.0.89:7125/server/info")


@pytest.mark.asyncio
async def test_probe_finds_cosmos_on_port_80():
    import httpx

    scanner = MoonrakerSubnetScanner()
    client = AsyncMock()

    async def get_side_effect(url: str):
        if ":7125" in url:
            raise httpx.ConnectError("refused")
        return _mock_response(200, {"result": {"klippy_state": "ready", "moonraker_version": "0.9.0"}})

    client.get = AsyncMock(side_effect=get_side_effect)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=client):
        await scanner._do_probe("10.0.0.126", timeout=0.5, ports=[7125, 80])

    assert len(scanner.discovered_printers) == 1
    assert scanner.discovered_printers[0].api_url == "http://10.0.0.126"
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_probe_401_is_not_a_hit():
    """Auth walls on unrelated LAN services must not count as Moonraker."""
    scanner = MoonrakerSubnetScanner()
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(401))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=client):
        await scanner._do_probe("10.2.0.8", timeout=0.5, ports=[7125, 80])

    assert scanner.discovered_printers == []


@pytest.mark.asyncio
async def test_probe_rejects_200_without_moonraker_shape():
    scanner = MoonrakerSubnetScanner()
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(200, {"status": "ok", "files": []}))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=client):
        await scanner._do_probe("10.2.0.8", timeout=0.5, ports=[80])

    assert scanner.discovered_printers == []
