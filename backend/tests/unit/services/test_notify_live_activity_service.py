"""Tests for native Notify Live Activity lifecycle management."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.models.notification import NotificationProvider
from backend.app.models.notification_live_activity import NotificationLiveActivity
from backend.app.models.printer import Printer
from backend.app.services.notify_live_activity_client import NotifyLiveActivityError
from backend.app.services.notify_live_activity_service import NotifyLiveActivityService


@pytest.fixture
def live_config():
    return {
        "device_id": "DEVICE123",
        "device_token": "token",
        "base_url": "https://push.getnotifyapp.com",
        "live_activities_enabled": True,
        "live_activity_end_keep_for_seconds": 300,
    }


@pytest.fixture
async def notify_provider(db_session, live_config):
    provider = NotificationProvider(
        name="Notify",
        provider_type="notify",
        enabled=True,
        config=json.dumps(live_config),
        on_print_start=False,
        on_print_complete=True,
        on_print_failed=True,
        on_print_stopped=True,
        on_print_progress=False,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


@pytest.mark.asyncio
async def test_print_start_creates_live_activity_row(db_session, notify_provider):
    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-123")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "dragon.3mf", "subtask_id": "task-1", "remaining_time": 5400},
    )

    client.start.assert_awaited_once()
    activity = await db_session.scalar(select(NotificationLiveActivity))
    assert activity is not None
    assert activity.provider_id == notify_provider.id
    assert activity.printer_id == 7
    assert activity.activity_id == "activity-123"
    assert activity.subtask_id == "task-1"
    assert activity.filename == "dragon.3mf"
    assert activity.state == "active"


@pytest.mark.asyncio
async def test_print_start_uses_configured_progress_compact_display(db_session, notify_provider):
    notify_provider.config = json.dumps(
        {
            "device_id": "DEVICE123",
            "device_token": "token",
            "live_activities_enabled": True,
            "live_activity_compact_display": "progress",
        }
    )
    await db_session.commit()

    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-123")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={
            "filename": "dragon.3mf",
            "subtask_id": "task-1",
            "remaining_time": 5400,
            "layer_num": 8,
            "total_layers": 120,
        },
    )

    payload = client.start.await_args.args[0]
    assert payload["body"] == "6% · L8/120 · dragon"
    assert payload["status"] == "6%"
    assert payload["trailing"] == "1:30"
    assert payload["endsIn"] is None


@pytest.mark.asyncio
async def test_print_start_uses_configured_native_tile_countdown(db_session, notify_provider):
    notify_provider.config = json.dumps(
        {
            "device_id": "DEVICE123",
            "device_token": "token",
            "live_activities_enabled": True,
            "live_activity_compact_display": "progress",
            "live_activity_native_tile_countdown": "true",
        }
    )
    await db_session.commit()

    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-123")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={
            "filename": "dragon.3mf",
            "subtask_id": "task-1",
            "remaining_time": 5400,
            "layer_num": 8,
            "total_layers": 120,
        },
    )

    payload = client.start.await_args.args[0]
    assert payload["body"] == "6% · L8/120 · dragon"
    assert payload["status"] == "6%"
    assert payload["trailing"] is None
    assert payload["endsIn"] == 5400


@pytest.mark.asyncio
async def test_duplicate_print_start_ends_existing_activity_first(db_session, notify_provider):
    existing = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="old-activity",
        subtask_id="old-task",
        filename="old.3mf",
        state="active",
    )
    db_session.add(existing)
    await db_session.commit()

    client = AsyncMock()
    client.start = AsyncMock(return_value="new-activity")
    client.end = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "new.3mf", "subtask_id": "new-task"},
    )

    client.end.assert_awaited_once()
    activities = (
        await db_session.scalars(select(NotificationLiveActivity).order_by(NotificationLiveActivity.id))
    ).all()
    assert [activity.state for activity in activities] == ["ended", "active"]
    assert activities[-1].activity_id == "new-activity"


@pytest.mark.asyncio
async def test_print_start_reuses_existing_activity_for_same_print(db_session, notify_provider):
    existing = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="progress-created-activity",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=5.36,
        last_layer_num=3,
        last_total_layers=56,
    )
    db_session.add(existing)
    await db_session.commit()

    client = AsyncMock()
    client.start = AsyncMock(return_value="duplicate-activity")
    client.end = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "dragon.3mf", "subtask_id": "task-1", "progress": 0, "layer_num": 0, "total_layers": 56},
    )

    client.end.assert_not_awaited()
    client.start.assert_not_awaited()
    activities = (
        await db_session.scalars(select(NotificationLiveActivity).order_by(NotificationLiveActivity.id))
    ).all()
    assert len(activities) == 1
    assert activities[0].activity_id == "progress-created-activity"
    assert activities[0].state == "active"
    assert activities[0].last_progress == 5.36


@pytest.mark.asyncio
async def test_print_progress_updates_existing_activity(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=62,
        remaining_time=1800,
        subtask_id="task-1",
    )

    client.update.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.last_progress == 62
    assert activity.last_remaining_time == 1800


@pytest.mark.asyncio
async def test_print_progress_skips_unchanged_live_activity_payload(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=5.36,
        last_remaining_time=360,
        last_layer_num=3,
        last_total_layers=56,
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=5.36,
        remaining_time=360,
        subtask_id="task-1",
        layer_num=3,
        total_layers=56,
    )

    client.update.assert_not_awaited()
    await db_session.refresh(activity)
    assert activity.last_progress == 5.36
    assert activity.last_layer_num == 3


@pytest.mark.asyncio
async def test_print_progress_clamps_backwards_progress_for_same_print(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=30.36,
        last_remaining_time=240,
        last_layer_num=17,
        last_total_layers=56,
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=5.36,
        remaining_time=240,
        subtask_id="task-1",
        layer_num=3,
        total_layers=56,
    )

    client.update.assert_not_awaited()
    await db_session.refresh(activity)
    assert activity.last_progress == 30.36
    assert activity.last_layer_num == 17


@pytest.mark.asyncio
async def test_print_progress_does_not_resend_same_eta_inside_tolerance(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=30.36,
        last_remaining_time=240,
        last_layer_num=17,
        last_total_layers=56,
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=30.36,
        remaining_time=238,
        subtask_id="task-1",
        layer_num=17,
        total_layers=56,
    )

    client.update.assert_not_awaited()
    await db_session.refresh(activity)
    assert activity.last_remaining_time == 240


@pytest.mark.asyncio
async def test_print_progress_paces_routine_layer_updates_inside_apple_cooldown(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=7.14,
        last_remaining_time=720,
        last_layer_num=4,
        last_total_layers=56,
        updated_at=datetime.utcnow() - timedelta(seconds=5),
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=8.93,
        remaining_time=710,
        subtask_id="task-1",
        layer_num=5,
        total_layers=56,
    )

    client.update.assert_not_awaited()
    await db_session.refresh(activity)
    assert activity.last_progress == 7.14
    assert activity.last_layer_num == 4


@pytest.mark.asyncio
async def test_print_progress_sends_routine_layer_update_after_apple_cooldown(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=7.14,
        last_remaining_time=720,
        last_layer_num=4,
        last_total_layers=56,
        updated_at=datetime.utcnow() - timedelta(seconds=16),
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=8.93,
        remaining_time=710,
        subtask_id="task-1",
        layer_num=5,
        total_layers=56,
    )

    client.update.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.last_progress == 8.93
    assert activity.last_layer_num == 5


@pytest.mark.asyncio
async def test_print_progress_sends_first_real_layer_inside_apple_cooldown(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=0,
        last_remaining_time=720,
        last_layer_num=0,
        last_total_layers=56,
        updated_at=datetime.utcnow() - timedelta(seconds=5),
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=1.79,
        remaining_time=710,
        subtask_id="task-1",
        layer_num=1,
        total_layers=56,
    )

    client.update.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.last_progress == 1.79
    assert activity.last_layer_num == 1


@pytest.mark.asyncio
async def test_print_progress_sends_completion_inside_apple_cooldown(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
        last_progress=98.21,
        last_remaining_time=60,
        last_layer_num=55,
        last_total_layers=56,
        updated_at=datetime.utcnow() - timedelta(seconds=5),
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=100,
        remaining_time=0,
        subtask_id="task-1",
        layer_num=56,
        total_layers=56,
    )

    client.update.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.last_progress == 100
    assert activity.last_layer_num == 56


@pytest.mark.asyncio
async def test_print_progress_creates_missing_activity_for_running_print(db_session, notify_provider):
    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-created-by-progress")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=5.36,
        remaining_time=360,
        subtask_id="task-1",
        layer_num=3,
        total_layers=56,
    )

    client.start.assert_awaited_once()
    payload = client.start.await_args.args[0]
    assert payload["body"] == "5% · L3/56 · dragon"
    assert payload["status"] == "5%"
    assert payload["trailing"] == "6:00"
    assert payload["endsIn"] is None
    assert payload["progress"] == 5.36
    activity = await db_session.scalar(select(NotificationLiveActivity))
    assert activity is not None
    assert activity.provider_id == notify_provider.id
    assert activity.printer_id == 7
    assert activity.activity_id == "activity-created-by-progress"
    assert activity.subtask_id == "task-1"
    assert activity.last_progress == 5.36
    assert activity.last_layer_num == 3
    assert activity.last_total_layers == 56


@pytest.mark.asyncio
async def test_concurrent_print_progress_creates_only_one_missing_activity(test_engine, notify_provider):
    started = asyncio.Event()
    release = asyncio.Event()
    start_calls = 0

    async def start_activity(payload):
        nonlocal start_calls
        start_calls += 1
        started.set()
        await release.wait()
        return f"activity-{start_calls}"

    client = AsyncMock()
    client.start = AsyncMock(side_effect=start_activity)
    service = NotifyLiveActivityService(client_factory=lambda config: client)
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def send_progress():
        async with session_factory() as session:
            await service.on_print_progress(
                session,
                printer_id=7,
                printer_name="Prusa CORE One",
                filename="coreone-test.gcode",
                progress=1,
                remaining_time=300,
                subtask_id="coreone-test.gcode",
            )

    task1 = asyncio.create_task(send_progress())
    await started.wait()
    task2 = asyncio.create_task(send_progress())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(task1, task2)

    assert client.start.await_count == 1
    assert start_calls == 1
    async with session_factory() as session:
        activities = (await session.scalars(select(NotificationLiveActivity))).all()
    assert len(activities) == 1
    assert activities[0].activity_id == "activity-1"


@pytest.mark.asyncio
async def test_concurrent_recovery_serializes_missing_activity_creation():
    class FakeProvider:
        id = 2
        config = {}

    class FakeDb:
        commits = 0
        rollbacks = 0

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    class RaceService(NotifyLiveActivityService):
        def __init__(self, *, client):
            super().__init__(client_factory=lambda config: client)
            self.created_activity = None
            self.concurrent_readers = 0
            self.both_reading = asyncio.Event()

        async def _enabled_notify_providers(self, db, printer_id):
            return [(FakeProvider(), {"live_activities_enabled": True})]

        async def _active_activity(self, db, provider_id, printer_id, *, subtask_id=None):
            if self.created_activity is not None:
                return self.created_activity
            self.concurrent_readers += 1
            if self.concurrent_readers == 2:
                self.both_reading.set()
            await asyncio.sleep(0)
            return None

        async def _create_activity(self, db, **kwargs):
            self.created_activity = NotificationLiveActivity(
                provider_id=kwargs["provider_id"],
                printer_id=kwargs["printer_id"],
                activity_id=kwargs["activity_id"],
                subtask_id=kwargs["subtask_id"],
                filename=kwargs["filename"],
                state="active",
                last_progress=float(kwargs["progress"]),
                last_remaining_time=kwargs["remaining_time"],
                last_layer_num=kwargs["layer_num"],
                last_total_layers=kwargs["total_layers"],
            )

    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-created-by-progress")
    service = RaceService(client=client)
    db = FakeDb()

    async def send_progress():
        await service.on_print_progress(
            db,
            printer_id=4,
            printer_name="Prusa CORE One",
            filename="coreone-test.gcode",
            progress=1,
            remaining_time=300,
            subtask_id="coreone-test.gcode",
        )

    await asyncio.gather(send_progress(), send_progress())

    client.start.assert_awaited_once()
    assert db.commits == 1


@pytest.mark.asyncio
async def test_print_progress_replaces_gone_activity(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="overdue-activity",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.update = AsyncMock(
        side_effect=NotifyLiveActivityError(
            'Notify Live Activity request failed with HTTP 410: {"error":"Gone"}',
            status_code=410,
            retryable=False,
        )
    )
    client.start = AsyncMock(return_value="replacement-activity")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_progress(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        filename="dragon.3mf",
        progress=50,
        remaining_time=900,
        subtask_id="task-1",
        layer_num=1,
        total_layers=56,
    )

    client.update.assert_awaited_once()
    client.start.assert_awaited_once()
    activities = (
        await db_session.scalars(select(NotificationLiveActivity).order_by(NotificationLiveActivity.id))
    ).all()
    assert [row.state for row in activities] == ["ended", "active"]
    assert activities[-1].activity_id == "replacement-activity"
    assert activities[-1].last_progress == 50
    assert activities[-1].last_remaining_time == 900


@pytest.mark.asyncio
async def test_print_start_replaces_gone_existing_activity(db_session, notify_provider):
    existing = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="overdue-activity",
        subtask_id="old-task",
        filename="old.3mf",
        state="active",
    )
    db_session.add(existing)
    await db_session.commit()

    client = AsyncMock()
    client.end = AsyncMock(
        side_effect=NotifyLiveActivityError(
            'Notify Live Activity request failed with HTTP 410: {"error":"Gone"}',
            status_code=410,
            retryable=False,
        )
    )
    client.start = AsyncMock(return_value="new-activity")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "new.3mf", "subtask_id": "new-task", "progress": 0},
    )

    client.end.assert_awaited_once()
    client.start.assert_awaited_once()
    activities = (
        await db_session.scalars(select(NotificationLiveActivity).order_by(NotificationLiveActivity.id))
    ).all()
    assert [row.state for row in activities] == ["ended", "active"]
    assert activities[-1].activity_id == "new-activity"


@pytest.mark.asyncio
async def test_print_complete_ends_activity_and_marks_row_ended(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
    )
    db_session.add(activity)
    await db_session.commit()

    client = AsyncMock()
    client.end = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_end(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        status="completed",
        data={"filename": "dragon.3mf", "subtask_id": "task-1"},
    )

    client.end.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.state == "ended"
    assert activity.ended_at is not None


@pytest.mark.asyncio
async def test_keepalive_updates_active_activity_from_current_printer_state(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
    )
    db_session.add(activity)
    await db_session.commit()

    printer_state = type(
        "PrinterState",
        (),
        {
            "connected": True,
            "state": "RUNNING",
            "current_print": "dragon.3mf",
            "subtask_name": "dragon.3mf",
            "subtask_id": "task-1",
            "progress": 64,
            "remaining_time": 45,
            "layer_num": 32,
            "total_layers": 100,
        },
    )()
    client = AsyncMock()
    client.update = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(
        client_factory=lambda config: client,
        status_getter=lambda printer_id: printer_state,
        printer_name_getter=lambda printer_id: "Workshop P1S",
    )

    await service.keepalive_once(db_session)

    client.update.assert_awaited_once()
    payload = client.update.await_args.args[1]
    assert payload["progress"] == 32
    assert payload["endsIn"] is None
    assert payload["trailing"] == "45:00"
    assert payload["status"] == "32%"
    await db_session.refresh(activity)
    assert activity.last_progress == 32
    assert activity.last_remaining_time == 2700


@pytest.mark.asyncio
async def test_keepalive_creates_missing_activity_for_running_printer(db_session, notify_provider):
    printer = Printer(
        id=7,
        name="Workshop P1S",
        serial_number="SERIAL7",
        ip_address="10.0.0.7",
        access_code="12345678",
        provider="bambu",
        model="P1S",
        location="Workshop",
    )
    db_session.add(printer)
    await db_session.commit()

    printer_state = type(
        "PrinterState",
        (),
        {
            "connected": True,
            "state": "RUNNING",
            "current_print": "dragon.3mf",
            "subtask_name": "dragon.3mf",
            "subtask_id": "task-1",
            "progress": 35,
            "remaining_time": 11,
            "layer_num": 1,
            "total_layers": 128,
        },
    )()
    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-created-by-keepalive")
    service = NotifyLiveActivityService(
        client_factory=lambda config: client,
        status_getter=lambda printer_id: printer_state,
        printer_name_getter=lambda printer_id: "Workshop P1S",
    )

    await service.keepalive_once(db_session)

    client.start.assert_awaited_once()
    payload = client.start.await_args.args[0]
    assert payload["title"] == "Workshop P1S"
    assert payload["progress"] == 0.78
    activity = await db_session.scalar(select(NotificationLiveActivity))
    assert activity is not None
    assert activity.provider_id == notify_provider.id
    assert activity.printer_id == 7
    assert activity.activity_id == "activity-created-by-keepalive"
    assert activity.state == "active"


@pytest.mark.asyncio
async def test_keepalive_ends_activity_when_printer_is_no_longer_running(db_session, notify_provider):
    activity = NotificationLiveActivity(
        provider_id=notify_provider.id,
        printer_id=7,
        activity_id="activity-123",
        subtask_id="task-1",
        filename="dragon.3mf",
        state="active",
    )
    db_session.add(activity)
    await db_session.commit()

    printer_state = type("PrinterState", (), {"connected": True, "state": "IDLE"})()
    client = AsyncMock()
    client.end = AsyncMock(return_value=None)
    service = NotifyLiveActivityService(
        client_factory=lambda config: client,
        status_getter=lambda printer_id: printer_state,
        printer_name_getter=lambda printer_id: "Workshop P1S",
    )

    await service.keepalive_once(db_session)

    client.end.assert_awaited_once()
    await db_session.refresh(activity)
    assert activity.state == "ended"


@pytest.mark.asyncio
async def test_string_true_live_activity_config_enables_activity(db_session, notify_provider):
    notify_provider.config = json.dumps(
        {"device_id": "DEVICE123", "device_token": "token", "live_activities_enabled": "true"}
    )
    await db_session.commit()

    client = AsyncMock()
    client.start = AsyncMock(return_value="activity-123")
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "dragon.3mf"},
    )

    client.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_live_activity_config_does_not_call_notify(db_session, notify_provider):
    notify_provider.config = json.dumps(
        {"device_id": "DEVICE123", "device_token": "token", "live_activities_enabled": False}
    )
    await db_session.commit()

    client = AsyncMock()
    service = NotifyLiveActivityService(client_factory=lambda config: client)

    await service.on_print_start(
        db_session,
        printer_id=7,
        printer_name="Workshop P1S",
        data={"filename": "dragon.3mf"},
    )

    client.start.assert_not_called()
    activity = await db_session.scalar(select(NotificationLiveActivity))
    assert activity is None
