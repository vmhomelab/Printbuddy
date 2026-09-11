"""Tests for automatic recovery of active offline printer connections."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.services.printer_reconnect import PrinterReconnectService


@pytest.mark.asyncio
async def test_reconnects_an_active_printer_without_a_client_when_due():
    printer = SimpleNamespace(id=7, name="CORE One", is_active=True, reconnect_interval_seconds=30)
    manager = SimpleNamespace(get_client=lambda printer_id: None, connect_printer=AsyncMock(return_value=True))
    service = PrinterReconnectService(manager, session_factory=None)

    await service.reconnect_due_printers([printer], now=100.0)

    manager.connect_printer.assert_awaited_once_with(printer)
    assert service.next_attempt_at[printer.id] == 130.0


@pytest.mark.asyncio
async def test_does_not_reconnect_a_healthy_printer():
    printer = SimpleNamespace(id=7, name="CORE One", is_active=True, reconnect_interval_seconds=30)
    manager = SimpleNamespace(
        get_client=lambda printer_id: SimpleNamespace(state=SimpleNamespace(connected=True)),
        connect_printer=AsyncMock(),
    )
    service = PrinterReconnectService(manager, session_factory=None)

    await service.reconnect_due_printers([printer], now=100.0)

    manager.connect_printer.assert_not_awaited()
    assert printer.id not in service.next_attempt_at


@pytest.mark.asyncio
async def test_waits_for_the_printer_specific_interval_before_retrying_again():
    printer = SimpleNamespace(id=7, name="CORE One", is_active=True, reconnect_interval_seconds=45)
    manager = SimpleNamespace(get_client=lambda printer_id: None, connect_printer=AsyncMock(return_value=False))
    service = PrinterReconnectService(manager, session_factory=None)

    await service.reconnect_due_printers([printer], now=100.0)
    await service.reconnect_due_printers([printer], now=144.9)
    await service.reconnect_due_printers([printer], now=145.0)

    assert manager.connect_printer.await_count == 2


@pytest.mark.asyncio
async def test_drops_retry_schedule_for_inactive_printer():
    printer = SimpleNamespace(id=7, name="CORE One", is_active=False, reconnect_interval_seconds=30)
    manager = SimpleNamespace(get_client=lambda printer_id: None, connect_printer=AsyncMock())
    service = PrinterReconnectService(manager, session_factory=None)
    service.next_attempt_at[printer.id] = 20.0

    await service.reconnect_due_printers([printer], now=100.0)

    manager.connect_printer.assert_not_awaited()
    assert printer.id not in service.next_attempt_at
