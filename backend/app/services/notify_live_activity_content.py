"""Build Notify Live Activity payloads from Printbuddy print state."""

from __future__ import annotations

import os
import re
from typing import Any

_PRINTBUDDY_SYMBOL = "printer"
_ACTIVE_COLOR = "#0a84ff"
_PAUSED_COLOR = "#f59e0b"
_FAILED_COLOR = "#dc2626"
_DONE_COLOR = "#2563eb"
_STOPPED_COLOR = "#64748b"
_EXTENSIONS = (".gcode.3mf", ".gcode", ".3mf", ".stl")
_MEANINGLESS_NAME = re.compile(r"^plate[_\-]?\d+$", re.IGNORECASE)
_BODY_MAX_CHARS = 35


def build_start_content(
    *,
    printer_name: str,
    filename: str,
    progress: float | int | None = 0,
    remaining_time: int | None = None,
    layer_num: int | None = None,
    total_layers: int | None = None,
    state: str = "running",
    compact_display: str = "progress",
    native_countdown: bool = False,
) -> dict[str, Any]:
    """Build payload for creating a Live Activity."""
    return build_update_content(
        printer_name=printer_name,
        filename=filename,
        progress=progress,
        remaining_time=remaining_time,
        layer_num=layer_num,
        total_layers=total_layers,
        state=state,
        compact_display=compact_display,
        native_countdown=native_countdown,
    )


def build_update_content(
    *,
    printer_name: str,
    filename: str,
    progress: float | int | None,
    remaining_time: int | None = None,
    layer_num: int | None = None,
    total_layers: int | None = None,
    state: str = "running",
    compact_display: str = "progress",
    native_countdown: bool = False,
) -> dict[str, Any]:
    """Build payload for updating a Live Activity."""
    progress_value = _normalize_progress_percent(progress)
    percent_text = _percent_text(progress_value)
    state_key = (state or "running").lower()
    display_mode = _compact_display(compact_display)
    progress_detail = _compact_progress_text(progress_value, layer_num=layer_num, total_layers=total_layers)
    job_name = _job_display_name(filename) or "Unknown print"
    body = job_name
    if (
        state_key not in {"pause", "paused"}
        and display_mode == "eta"
        and remaining_time is not None
        and remaining_time > 0
    ):
        body = f"{body} · {progress_detail}"

    content: dict[str, Any] = {
        "title": printer_name,
        "body": body,
        "progress": progress_value,
        "status": progress_detail,
        "symbol": _PRINTBUDDY_SYMBOL,
        "tint": _ACTIVE_COLOR,
    }

    if state_key in {"pause", "paused"}:
        content["status"] = f"Paused · {percent_text}"
        content["trailing"] = f"Paused · {percent_text}"
        content["endsIn"] = None
        content["tint"] = _PAUSED_COLOR
    elif display_mode == "progress":
        content["status"] = percent_text
        content["endsIn"] = None
        if remaining_time is not None and remaining_time > 0:
            if native_countdown:
                content["endsIn"] = int(remaining_time)
                content["trailing"] = None
            else:
                content["trailing"] = _remaining_time_text(remaining_time)
            content["body"] = _progress_body(
                job_name,
                remaining_time=remaining_time,
                progress_detail=progress_detail,
            )
        else:
            content["trailing"] = progress_detail
    elif remaining_time is not None and remaining_time > 0:
        content["endsIn"] = int(remaining_time)
        content["trailing"] = None
    else:
        content["trailing"] = progress_detail

    return content


def build_end_content(
    *,
    printer_name: str,
    filename: str,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build payload for ending a Live Activity."""
    status_key = (status or "completed").lower()
    if status_key == "failed":
        label = "Failed"
        color = _FAILED_COLOR
    elif status_key in {"aborted", "cancelled", "stopped"}:
        label = "Stopped"
        color = _STOPPED_COLOR
    else:
        label = "Completed"
        color = _DONE_COLOR

    body = label
    if reason:
        body = f"{label} · {reason}"

    return {
        "title": printer_name,
        "body": _job_display_name(filename) or "Unknown print",
        "status": body,
        "progress": 100,
        "symbol": _PRINTBUDDY_SYMBOL,
        "tint": color,
    }


def _normalize_progress_percent(progress: float | int | None) -> float:
    if progress is None:
        return 0
    value = float(progress)
    return round(min(max(value, 0), 100), 2)


def _percent_text(progress: float) -> str:
    return f"{int(progress)}%"


def _compact_progress_text(progress: float, *, layer_num: int | None, total_layers: int | None) -> str:
    percent = _percent_text(progress)
    if layer_num is not None and total_layers:
        return f"{percent} · L{layer_num}/{total_layers}"
    return percent


def _progress_body(job_name: str, *, remaining_time: int, progress_detail: str) -> str:
    prefix = f"{progress_detail} · "
    available = max(_BODY_MAX_CHARS - len(prefix), 1)
    return f"{prefix}{_truncate(job_name, available)}"


def _remaining_time_text(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}"
    return f"{minutes}:{seconds:02d}"


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return f"{value[: max_chars - 3]}..."


def _compact_display(value: str | None) -> str:
    return "eta" if str(value or "").lower() in {"eta", "time", "remaining", "timer"} else "progress"


def _job_display_name(filename: str | None) -> str | None:
    if not filename or not filename.strip():
        return None
    base = os.path.basename(filename.strip().replace("\\", "/"))
    for extension in _EXTENSIONS:
        if base.lower().endswith(extension):
            base = base[: -len(extension)]
            break
    base = " ".join(base.split())
    if not base or _MEANINGLESS_NAME.match(base):
        return None
    return base
