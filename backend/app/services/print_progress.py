"""Shared print progress helpers for user-facing notifications and Live Activities."""

from __future__ import annotations

from typing import Any

# Bambu preparation/calibration stages where firmware mc_percent may include
# pre-print setup rather than actual model progress. Stage names are defined in
# bambu_mqtt.STAGE_NAMES; keep this module dependency-free so non-Bambu
# providers can safely use the fallback behavior.
PRE_PRINT_STAGE_IDS = frozenset(
    {
        1,  # Auto bed leveling
        2,  # Heatbed preheating
        3,  # Vibration compensation
        7,  # Heating nozzle
        8,  # Calibrating dynamic flow
        9,  # Scanning bed surface
        11,  # Identifying build plate type
        13,  # Homing toolhead
        14,  # Cleaning nozzle tip
        19,  # Calibrating flow ratio
        25,  # Motor noise cancellation
        40,  # High temperature auto bed leveling
        47,  # Auto bed leveling - phase 1
        48,  # Auto bed leveling - phase 2
        49,  # Heating chamber
        50,  # Cooling heatbed
        51,  # Printing calibration lines
        52,  # Auto Check: Material
        54,  # Waiting for heatbed temperature
        55,  # Auto Check: Material Position
        58,  # Thermal Preconditioning
        63,  # Waiting for Chamber temperature
        64,  # Preparing Hotend
        65,  # Calibrating nozzle clumping detection
        74,  # Preparing
        77,  # Preparing AMS
    }
)


def effective_print_progress(state: Any) -> float:
    """Return actual model progress as a percent in the 0-100 range.

    Firmware progress can include pre-print preparation on Bambu printers. When
    layer data is available, layer progress is a better user-facing signal. If
    the printer is still in a known preparation stage and no layer has started,
    report 0 so milestone notifications and Live Activities do not claim that
    the model itself is already 25%/50% done.
    """
    layer_num = _number(_get(state, "layer_num"), default=0)
    total_layers = _number(_get(state, "total_layers"), default=0)
    if total_layers > 0 and layer_num > 0:
        return round(min(max((layer_num / total_layers) * 100, 0), 100), 2)

    if is_pre_print_stage(state):
        return 0

    return round(min(max(_number(_get(state, "progress"), default=0), 0), 100), 2)


def is_pre_print_stage(state: Any) -> bool:
    """Return whether state is in a known Bambu pre-print preparation stage."""
    stage = _optional_int(_get(state, "stg_cur"))
    return stage in PRE_PRINT_STAGE_IDS if stage is not None else False


def _get(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        value = source.get(key)
        if value is not None:
            return value
        raw_data = source.get("raw_data")
        if isinstance(raw_data, dict):
            raw_key = {
                "progress": "mc_percent",
                "total_layers": "total_layer_num",
            }.get(key, key)
            return raw_data.get(raw_key)
        return None
    return getattr(source, key, None)


def _number(value: Any, *, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
