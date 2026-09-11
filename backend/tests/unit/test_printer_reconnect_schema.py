"""Schema validation for per-printer offline reconnect intervals."""

import pytest
from pydantic import ValidationError

from backend.app.schemas.printer import PrinterCreate, PrinterUpdate


def _payload(**overrides):
    payload = {
        "name": "CORE One",
        "serial_number": "PRUSALINK-CORE-ONE",
        "ip_address": "coreone.local",
        "access_code": "prusalink",
        "provider": "prusalink",
    }
    payload.update(overrides)
    return payload


def test_printer_defaults_to_a_30_second_reconnect_interval():
    assert PrinterCreate(**_payload()).reconnect_interval_seconds == 30


def test_printer_accepts_a_configured_reconnect_interval():
    assert PrinterCreate(**_payload(reconnect_interval_seconds=90)).reconnect_interval_seconds == 90
    assert PrinterUpdate(reconnect_interval_seconds=3600).reconnect_interval_seconds == 3600


@pytest.mark.parametrize("interval", [0, 9, 3601])
def test_printer_rejects_unsafe_reconnect_intervals(interval):
    with pytest.raises(ValidationError):
        PrinterCreate(**_payload(reconnect_interval_seconds=interval))
