"""Regression tests for webhook routes reading live printer state.

`printer_manager.get_status()` returns provider state objects with attributes,
not dictionaries. The webhook status/stop/cancel routes must therefore not use
`dict.get()` on the returned state object.
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@dataclass
class DataclassPrinterState:
    connected: bool = True
    state: str = "RUNNING"
    current_print: str | None = "calibration_cube.3mf"
    progress: float | None = 42.5
    remaining_time: int | None = 37
    layer_num: int | None = 12
    total_layers: int | None = 80
    hms_errors: list[dict] | None = None
    subtask_id: str | None = "subtask-123"


@pytest.fixture
async def webhook_api_key(db_session):
    """Create an API key with status/control permissions for webhook routes."""
    from backend.app.core.auth import generate_api_key
    from backend.app.models.api_key import APIKey

    full_key, key_hash, key_prefix = generate_api_key()
    api_key = APIKey(
        name="webhook-status-test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        can_control_printer=True,
        can_read_status=True,
        enabled=True,
    )
    db_session.add(api_key)
    await db_session.commit()
    return full_key


@pytest.fixture
async def webhook_printer(printer_factory):
    return await printer_factory(name="Webhook Status Printer")


class TestWebhookPrinterStateDataclass:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_status_route_reads_dataclass_state_by_attribute(
        self, async_client: AsyncClient, webhook_api_key, webhook_printer
    ):
        """Connected dataclass state should return 200 instead of AttributeError/500."""
        with patch("backend.app.api.routes.webhook.printer_manager") as mock_pm:
            mock_pm.get_status.return_value = DataclassPrinterState(
                hms_errors=[{"code": "0x0300", "attr": 50331648, "severity": 2}]
            )

            resp = await async_client.get(
                f"/api/v1/webhook/printer/{webhook_printer.id}/status",
                headers={"X-API-Key": webhook_api_key},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "id": webhook_printer.id,
            "name": "Webhook Status Printer",
            "connected": True,
            "state": "RUNNING",
            "current_print": "calibration_cube.3mf",
            "progress": 42.5,
            "remaining_time": 37,
            "layer_num": 12,
            "total_layers": 80,
            "hms_errors": [{"code": "0x0300", "attr": 50331648, "severity": 2}],
            "subtask_id": "subtask-123",
            "serial_number": webhook_printer.serial_number,
        }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stop_route_reads_dataclass_state_by_attribute(
        self, async_client: AsyncClient, webhook_api_key, webhook_printer
    ):
        """Stop should accept a connected RUNNING dataclass state."""
        with patch("backend.app.api.routes.webhook.printer_manager") as mock_pm:
            mock_pm.get_status.return_value = DataclassPrinterState(state="RUNNING")
            mock_pm.stop_print = AsyncMock()

            resp = await async_client.post(
                f"/api/v1/webhook/printer/{webhook_printer.id}/stop",
                headers={"X-API-Key": webhook_api_key},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"message": "Print stopped"}
        mock_pm.stop_print.assert_awaited_once_with(webhook_printer.id)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cancel_route_reads_dataclass_state_by_attribute(
        self, async_client: AsyncClient, webhook_api_key, webhook_printer
    ):
        """Cancel should accept a connected PAUSE dataclass state."""
        with patch("backend.app.api.routes.webhook.printer_manager") as mock_pm:
            mock_pm.get_status.return_value = DataclassPrinterState(state="PAUSE")
            mock_pm.cancel_print = AsyncMock()

            resp = await async_client.post(
                f"/api/v1/webhook/printer/{webhook_printer.id}/cancel",
                headers={"X-API-Key": webhook_api_key},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"message": "Print cancelled"}
        mock_pm.cancel_print.assert_awaited_once_with(webhook_printer.id)
