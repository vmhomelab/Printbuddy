from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app import main


class _AsyncSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _state_with_cfs_remain(remain: int):
    return SimpleNamespace(
        connected=True,
        state="IDLE",
        progress=0,
        layer_num=0,
        temperatures={},
        stg_cur=0,
        cooling_fan_speed=None,
        big_fan1_speed=None,
        big_fan2_speed=None,
        chamber_light=None,
        active_extruder=None,
        tray_now=0,
        door_open=None,
        raw_data={
            "ams": [
                {
                    "id": 0,
                    "name": "CFS T1",
                    "module_type": "cfs",
                    "dry_time": 0,
                    "tray": [
                        {
                            "id": 0,
                            "slot": "T1A",
                            "tray_type": "PLA",
                            "tray_color": "#0A2989",
                            "remain": remain,
                            "active": True,
                            "state": 11,
                            "vendor": "unknown",
                        }
                    ],
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_printer_status_broadcasts_when_cfs_remain_changes():
    """CFS remain_len updates must reach the UI even if material/state stay stable."""

    main._last_status_broadcast.pop(4242, None)

    with (
        patch.object(main, "mqtt_relay") as mqtt_relay,
        patch.object(main, "printer_manager") as printer_manager,
        patch.object(main, "notification_service") as notification_service,
        patch.object(main, "smart_plug_manager") as smart_plug_manager,
        patch.object(main.ws_manager, "send_printer_status", new_callable=AsyncMock) as send_status,
        patch.object(main, "printer_state_to_dict", return_value={"connected": True}) as _state_to_dict,
    ):
        mqtt_relay.on_printer_status = AsyncMock()
        printer_manager.get_printer.return_value = None
        printer_manager.get_model.return_value = "K2 Plus"
        notification_service.on_print_progress = AsyncMock()
        smart_plug_manager.handle_print_state_change = AsyncMock()

        await main.on_printer_status_change(4242, _state_with_cfs_remain(100))
        await main.on_printer_status_change(4242, _state_with_cfs_remain(34))

    assert send_status.await_count == 2


def _printing_state(*, progress: float, layer_num: int, total_layers: int, connected: bool = True):
    return SimpleNamespace(
        connected=connected,
        state="RUNNING",
        progress=progress,
        layer_num=layer_num,
        total_layers=total_layers,
        subtask_name="half_test_cube",
        subtask_id="1057596979",
        gcode_file="half_test_cube.3mf",
        current_print="half_test_cube.3mf",
        remaining_time=6,
        temperatures={},
        stg_cur=0,
        cooling_fan_speed=None,
        big_fan1_speed=None,
        big_fan2_speed=None,
        chamber_light=None,
        active_extruder=None,
        tray_now=0,
        door_open=None,
        hms_errors=[],
        raw_data={"subtask_id": "1057596979"},
    )


@pytest.mark.asyncio
async def test_live_activity_updates_on_layer_change_without_progress_milestone():
    """Live Activities must follow status/layer changes, not only 25/50/75 push milestones."""

    printer_id = 5252
    main._last_status_broadcast.pop(printer_id, None)
    main._last_progress_milestone.pop(printer_id, None)
    main._last_progress_value.pop(printer_id, None)
    main._progress_job_key.pop(printer_id, None)
    main._pending_progress_milestone.pop(printer_id, None)
    main._print_almost_done_notified.pop(printer_id, None)
    main._first_layer_notified.pop(printer_id, None)

    db = AsyncMock()
    printer = SimpleNamespace(name="Bambu Lab P1S")
    result = MagicMock()
    result.scalar_one_or_none.return_value = printer
    db.execute = AsyncMock(return_value=result)

    with (
        patch.object(main, "mqtt_relay") as mqtt_relay,
        patch.object(main, "printer_manager") as printer_manager,
        patch.object(main, "notification_service") as notification_service,
        patch.object(main, "notify_live_activity_service") as live_activity_service,
        patch.object(main, "smart_plug_manager") as smart_plug_manager,
        patch.object(main, "async_session", return_value=_AsyncSessionContext(db)),
        patch.object(main.ws_manager, "send_printer_status", new_callable=AsyncMock),
        patch.object(main, "printer_state_to_dict", return_value={"connected": True}),
    ):
        mqtt_relay.on_printer_status = AsyncMock()
        printer_manager.get_printer.return_value = printer
        printer_manager.get_model.return_value = "P1S"
        notification_service.on_print_progress = AsyncMock()
        live_activity_service.on_print_progress = AsyncMock()
        smart_plug_manager.handle_print_state_change = AsyncMock()

        await main.on_printer_status_change(
            printer_id,
            _printing_state(progress=6, layer_num=3, total_layers=56),
        )

    notification_service.on_print_progress.assert_not_awaited()
    live_activity_service.on_print_progress.assert_awaited_once_with(
        db,
        printer_id=printer_id,
        printer_name="Bambu Lab P1S",
        filename="half_test_cube",
        progress=5.36,
        remaining_time=360,
        subtask_id="1057596979",
        layer_num=3,
        total_layers=56,
    )


@pytest.mark.asyncio
async def test_disconnected_running_state_does_not_update_live_activity_from_stale_values():
    """Disconnected printer frames carry last-seen values and must not advance Live Activities."""

    printer_id = 5454
    main._last_status_broadcast.pop(printer_id, None)
    main._last_progress_milestone.pop(printer_id, None)
    main._last_progress_value.pop(printer_id, None)
    main._progress_job_key.pop(printer_id, None)
    main._pending_progress_milestone.pop(printer_id, None)
    main._print_almost_done_notified.pop(printer_id, None)
    main._first_layer_notified.pop(printer_id, None)

    printer = SimpleNamespace(name="Bambu Lab P1S")
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = printer
    db.execute = AsyncMock(return_value=result)

    with (
        patch.object(main, "mqtt_relay") as mqtt_relay,
        patch.object(main, "printer_manager") as printer_manager,
        patch.object(main, "notification_service") as notification_service,
        patch.object(main, "notify_live_activity_service") as live_activity_service,
        patch.object(main, "smart_plug_manager") as smart_plug_manager,
        patch.object(main, "async_session", return_value=_AsyncSessionContext(db)),
        patch.object(main.ws_manager, "send_printer_status", new_callable=AsyncMock),
        patch.object(main, "printer_state_to_dict", return_value={"connected": False}),
    ):
        mqtt_relay.on_printer_status = AsyncMock()
        printer_manager.get_printer.return_value = printer
        printer_manager.get_model.return_value = "P1S"
        notification_service.on_print_progress = AsyncMock()
        live_activity_service.on_print_progress = AsyncMock()
        smart_plug_manager.handle_print_state_change = AsyncMock()

        await main.on_printer_status_change(
            printer_id,
            _printing_state(progress=75, layer_num=42, total_layers=56, connected=False),
        )

    live_activity_service.on_print_progress.assert_not_awaited()
    notification_service.on_print_progress.assert_not_awaited()


@pytest.mark.asyncio
async def test_milestone_notification_does_not_send_second_live_activity_update():
    """Milestone push notifications must not overwrite real Live Activity layer progress."""

    printer_id = 5353
    main._last_status_broadcast.pop(printer_id, None)
    main._last_progress_milestone.pop(printer_id, None)
    main._last_progress_value.pop(printer_id, None)
    main._progress_job_key.pop(printer_id, None)
    main._pending_progress_milestone.pop(printer_id, None)
    main._print_almost_done_notified.pop(printer_id, None)
    main._first_layer_notified.pop(printer_id, None)

    db = AsyncMock()
    printer = SimpleNamespace(name="Bambu Lab P1S")
    result = MagicMock()
    result.scalar_one_or_none.return_value = printer
    db.execute = AsyncMock(return_value=result)

    with (
        patch.object(main, "mqtt_relay") as mqtt_relay,
        patch.object(main, "printer_manager") as printer_manager,
        patch.object(main, "notification_service") as notification_service,
        patch.object(main, "notify_live_activity_service") as live_activity_service,
        patch.object(main, "smart_plug_manager") as smart_plug_manager,
        patch.object(main, "_capture_snapshot_for_notification", new_callable=AsyncMock) as snapshot,
        patch.object(main, "async_session", return_value=_AsyncSessionContext(db)),
        patch.object(main.ws_manager, "send_printer_status", new_callable=AsyncMock),
        patch.object(main, "printer_state_to_dict", return_value={"connected": True}),
    ):
        mqtt_relay.on_printer_status = AsyncMock()
        printer_manager.get_printer.return_value = printer
        printer_manager.get_model.return_value = "P1S"
        notification_service.on_print_progress = AsyncMock()
        live_activity_service.on_print_progress = AsyncMock()
        smart_plug_manager.handle_print_state_change = AsyncMock()
        snapshot.return_value = None

        await main.on_printer_status_change(
            printer_id,
            _printing_state(progress=52, layer_num=29, total_layers=56),
        )

    live_activity_service.on_print_progress.assert_awaited_once_with(
        db,
        printer_id=printer_id,
        printer_name="Bambu Lab P1S",
        filename="half_test_cube",
        progress=51.79,
        remaining_time=360,
        subtask_id="1057596979",
        layer_num=29,
        total_layers=56,
    )
    notification_service.on_print_progress.assert_awaited_once()
    assert notification_service.on_print_progress.await_args.args[:5] == (
        printer_id,
        "Bambu Lab P1S",
        "half_test_cube",
        50,
        db,
    )
    assert notification_service.on_print_progress.await_args.kwargs["update_live_activity"] is False
