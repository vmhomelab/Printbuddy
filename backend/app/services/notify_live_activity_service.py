"""Native Notify Live Activity lifecycle service."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.notification import NotificationProvider
from backend.app.models.notification_live_activity import NotificationLiveActivity
from backend.app.models.printer import Printer
from backend.app.services.notify_live_activity_client import NotifyLiveActivityClient, NotifyLiveActivityError
from backend.app.services.notify_live_activity_content import (
    build_end_content,
    build_start_content,
    build_update_content,
)
from backend.app.services.print_progress import effective_print_progress

logger = logging.getLogger(__name__)

APPLE_LIVE_ACTIVITY_PROGRESS_FLOOR_SECONDS = 15

ClientFactory = Callable[[dict[str, Any]], Any]
StatusGetter = Callable[[int], Any]
PrinterNameGetter = Callable[[int], str]


class NotifyLiveActivityService:
    """Manage stateful Notify Live Activities for active prints."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
        status_getter: StatusGetter | None = None,
        printer_name_getter: PrinterNameGetter | None = None,
    ):
        self.client_factory = client_factory
        self.status_getter = status_getter
        self.printer_name_getter = printer_name_getter
        self._scheduler_task: asyncio.Task | None = None
        self._activity_locks: dict[tuple[int, int], asyncio.Lock] = {}

    async def on_print_start(
        self,
        db: AsyncSession,
        *,
        printer_id: int,
        printer_name: str,
        data: dict[str, Any],
        archive_data: dict[str, Any] | None = None,
    ) -> None:
        """Create Live Activities for enabled Notify providers."""
        providers = await self._enabled_notify_providers(db, printer_id)
        if not providers:
            return

        filename = self._filename(data)
        remaining_time = self._remaining_time(data, archive_data=archive_data)
        progress = effective_print_progress(data)
        layer_num = self._optional_int(data.get("layer_num"))
        total_layers = self._optional_int(data.get("total_layers"))
        subtask_id = self._subtask_id(data)

        for provider, config in providers:
            provider_id = provider.id
            async with self._activity_lock(provider_id, printer_id):
                await self._on_print_start_for_provider(
                    db,
                    provider_id=provider_id,
                    printer_id=printer_id,
                    printer_name=printer_name,
                    config=config,
                    filename=filename,
                    remaining_time=remaining_time,
                    progress=progress,
                    layer_num=layer_num,
                    total_layers=total_layers,
                    subtask_id=subtask_id,
                )

    async def on_print_progress(
        self,
        db: AsyncSession,
        *,
        printer_id: int,
        printer_name: str,
        filename: str,
        progress: float | int,
        remaining_time: int | None = None,
        subtask_id: str | None = None,
        layer_num: int | None = None,
        total_layers: int | None = None,
        state: str = "running",
    ) -> None:
        """Update active Live Activities for a progress change."""
        providers = await self._enabled_notify_providers(db, printer_id)
        for provider, config in providers:
            provider_id = provider.id
            async with self._activity_lock(provider_id, printer_id):
                await self._on_print_progress_for_provider(
                    db,
                    provider_id=provider_id,
                    printer_id=printer_id,
                    printer_name=printer_name,
                    filename=filename,
                    progress=progress,
                    remaining_time=remaining_time,
                    subtask_id=subtask_id,
                    layer_num=layer_num,
                    total_layers=total_layers,
                    state=state,
                    config=config,
                )

    async def _on_print_start_for_provider(
        self,
        db: AsyncSession,
        *,
        provider_id: int,
        printer_id: int,
        printer_name: str,
        config: dict[str, Any],
        filename: str,
        remaining_time: int | None,
        progress: float | int,
        layer_num: int | None,
        total_layers: int | None,
        subtask_id: str | None,
    ) -> None:
        client = await self._client(config)
        try:
            existing = await self._active_activity(db, provider_id, printer_id)
            if existing:
                if self._same_print(existing, subtask_id=subtask_id, filename=filename):
                    logger.info(
                        "Notify Live Activity already active for provider %s printer %s print %s; reusing existing activity",
                        provider_id,
                        printer_id,
                        subtask_id or filename,
                    )
                    return
                try:
                    await self._end_existing(
                        client, existing, provider_config=config, printer_name=printer_name, status="stopped"
                    )
                except NotifyLiveActivityError as exc:
                    if not self._is_gone_error(exc):
                        raise
                    self._mark_ended(existing)

            await self._create_activity(
                db,
                provider_id=provider_id,
                printer_id=printer_id,
                activity_id=await client.start(
                    build_start_content(
                        printer_name=printer_name,
                        filename=filename,
                        progress=progress,
                        remaining_time=remaining_time,
                        layer_num=layer_num,
                        total_layers=total_layers,
                        compact_display=self._compact_display(config),
                        native_countdown=self._native_tile_countdown(config),
                    )
                ),
                subtask_id=subtask_id,
                filename=filename,
                progress=progress,
                remaining_time=remaining_time,
                layer_num=layer_num,
                total_layers=total_layers,
                config=config,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Notify Live Activity start failed for provider %s printer %s", provider_id, printer_id)

    async def _on_print_progress_for_provider(
        self,
        db: AsyncSession,
        *,
        provider_id: int,
        printer_id: int,
        printer_name: str,
        filename: str,
        progress: float | int,
        remaining_time: int | None,
        subtask_id: str | None,
        layer_num: int | None,
        total_layers: int | None,
        state: str,
        config: dict[str, Any],
    ) -> None:
        activity = await self._active_activity(db, provider_id, printer_id, subtask_id=subtask_id)
        if not activity:
            try:
                await self._create_activity(
                    db,
                    provider_id=provider_id,
                    printer_id=printer_id,
                    activity_id=await (await self._client(config)).start(
                        build_start_content(
                            printer_name=printer_name,
                            filename=filename or "Unknown print",
                            progress=progress,
                            remaining_time=remaining_time,
                            layer_num=layer_num,
                            total_layers=total_layers,
                            compact_display=self._compact_display(config),
                            native_countdown=self._native_tile_countdown(config),
                        )
                    ),
                    subtask_id=subtask_id,
                    filename=filename or "Unknown print",
                    progress=progress,
                    remaining_time=remaining_time,
                    layer_num=layer_num,
                    total_layers=total_layers,
                    config=config,
                )
                await db.commit()
                logger.info(
                    "Notify Live Activity created from progress update for provider %s printer %s",
                    provider_id,
                    printer_id,
                )
            except Exception:
                await db.rollback()
                logger.exception(
                    "Notify Live Activity progress recovery failed for provider %s printer %s",
                    provider_id,
                    printer_id,
                )
            return

        activity_db_id = activity.id
        activity_filename = activity.filename
        display_filename = filename or activity_filename or "Unknown print"
        progress, layer_num, total_layers = self._monotonic_progress_payload(
            activity,
            progress=progress,
            layer_num=layer_num,
            total_layers=total_layers,
        )
        if self._activity_payload_unchanged(
            activity,
            filename=display_filename,
            progress=progress,
            remaining_time=remaining_time,
            layer_num=layer_num,
            total_layers=total_layers,
        ):
            return
        if self._routine_progress_update_too_soon(
            activity,
            progress=progress,
            layer_num=layer_num,
            total_layers=total_layers,
        ):
            return

        client = await self._client(config)
        payload = build_update_content(
            printer_name=printer_name,
            filename=display_filename,
            progress=progress,
            remaining_time=remaining_time,
            layer_num=layer_num,
            total_layers=total_layers,
            state=state,
            compact_display=self._compact_display(config),
            native_countdown=self._native_tile_countdown(config),
        )
        try:
            await client.update(activity.activity_id, payload)
            activity.last_progress = float(progress)
            activity.last_remaining_time = remaining_time
            activity.last_layer_num = layer_num
            activity.last_total_layers = total_layers
            activity.updated_at = datetime.utcnow()
            await db.commit()
        except NotifyLiveActivityError as exc:
            if not self._is_gone_error(exc):
                await db.rollback()
                logger.exception(
                    "Notify Live Activity update failed for provider %s printer %s", provider_id, printer_id
                )
                return
            await db.rollback()
            stale_activity = await db.get(NotificationLiveActivity, activity_db_id)
            if stale_activity:
                self._mark_ended(stale_activity)
                await db.commit()
            await self._create_activity(
                db,
                provider_id=provider_id,
                printer_id=printer_id,
                activity_id=await client.start(
                    build_start_content(
                        printer_name=printer_name,
                        filename=filename or activity_filename or "Unknown print",
                        progress=progress,
                        remaining_time=remaining_time,
                        layer_num=layer_num,
                        total_layers=total_layers,
                        compact_display=self._compact_display(config),
                        native_countdown=self._native_tile_countdown(config),
                    )
                ),
                subtask_id=subtask_id,
                filename=filename or activity_filename or "Unknown print",
                progress=float(progress),
                remaining_time=remaining_time,
                layer_num=layer_num,
                total_layers=total_layers,
                config=config,
            )
            await db.commit()
            logger.info(
                "Notify Live Activity replaced expired activity for provider %s printer %s",
                provider_id,
                printer_id,
            )
        except Exception:
            await db.rollback()
            logger.exception("Notify Live Activity update failed for provider %s printer %s", provider_id, printer_id)

    def _activity_lock(self, provider_id: int, printer_id: int) -> asyncio.Lock:
        key = (provider_id, printer_id)
        lock = self._activity_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._activity_locks[key] = lock
        return lock

    async def on_print_end(
        self,
        db: AsyncSession,
        *,
        printer_id: int,
        printer_name: str,
        status: str,
        data: dict[str, Any],
    ) -> None:
        """End active Live Activities for a completed/failed/stopped print."""
        providers = await self._enabled_notify_providers(db, printer_id)
        filename = self._filename(data)
        subtask_id = self._subtask_id(data)
        reason = data.get("failure_reason") or data.get("reason")

        for provider, config in providers:
            provider_id = provider.id
            activity = await self._active_activity(db, provider_id, printer_id, subtask_id=subtask_id)
            if not activity:
                continue
            client = await self._client(config)
            try:
                payload = build_end_content(
                    printer_name=printer_name,
                    filename=filename or activity.filename or "Unknown print",
                    status=status,
                    reason=str(reason) if reason else None,
                )
                await client.end(
                    activity.activity_id,
                    payload,
                    keep_for_seconds=self._end_keep_for(config),
                )
                self._mark_ended(activity)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("Notify Live Activity end failed for provider %s printer %s", provider_id, printer_id)

    def start_scheduler(self, interval_seconds: int = 60) -> None:
        """Start background keepalive/reconciliation loop."""
        if self._scheduler_task and not self._scheduler_task.done():
            return
        self._scheduler_task = asyncio.create_task(self._scheduler_loop(interval_seconds))

    def stop_scheduler(self) -> None:
        """Stop background keepalive/reconciliation loop."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
        self._scheduler_task = None

    async def _scheduler_loop(self, interval_seconds: int) -> None:
        """Periodically reconcile active Live Activities from current printer state."""
        while True:
            await asyncio.sleep(max(interval_seconds, 10))
            try:
                from backend.app.core.database import async_session

                async with async_session() as db:
                    await self.keepalive_once(db)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Notify Live Activity keepalive failed")

    async def keepalive_once(self, db: AsyncSession) -> None:
        """Reconcile every active Live Activity against current printer state."""
        result = await db.scalars(select(NotificationLiveActivity).where(NotificationLiveActivity.state == "active"))
        for activity in result.all():
            provider = await db.get(NotificationProvider, activity.provider_id)
            if not provider or not provider.enabled:
                continue
            config = self._config(provider)
            if not self._truthy(config.get("live_activities_enabled")):
                continue

            state = self._printer_status(activity.printer_id)
            printer_name = self._printer_name(activity.printer_id)
            client = await self._client(config)
            try:
                if (
                    not state
                    or not getattr(state, "connected", True)
                    or str(getattr(state, "state", "")).upper()
                    not in {
                        "RUNNING",
                        "PAUSE",
                        "PAUSED",
                    }
                ):
                    payload = build_end_content(
                        printer_name=printer_name,
                        filename=activity.filename or "Unknown print",
                        status="stopped",
                        reason="Printer is no longer printing",
                    )
                    await client.end(activity.activity_id, payload, keep_for_seconds=self._end_keep_for(config))
                    self._mark_ended(activity)
                    await db.commit()
                    continue

                filename = (
                    getattr(state, "subtask_name", None) or getattr(state, "current_print", None) or activity.filename
                )
                remaining_time = self._state_remaining_time_seconds(state)
                progress = effective_print_progress(state)
                layer_num = self._optional_int(getattr(state, "layer_num", None))
                total_layers = self._optional_int(getattr(state, "total_layers", None))
                payload = build_update_content(
                    printer_name=printer_name,
                    filename=str(filename or "Unknown print"),
                    progress=progress,
                    remaining_time=remaining_time,
                    layer_num=layer_num,
                    total_layers=total_layers,
                    state=str(getattr(state, "state", "running")),
                    compact_display=self._compact_display(config),
                    native_countdown=self._native_tile_countdown(config),
                )
                await client.update(activity.activity_id, payload)
                activity.last_progress = progress
                activity.last_remaining_time = remaining_time
                activity.last_layer_num = layer_num
                activity.last_total_layers = total_layers
                activity.updated_at = datetime.utcnow()
                await db.commit()
            except NotifyLiveActivityError as exc:
                provider_id = provider.id
                activity_db_id = activity.id
                activity_printer_id = activity.printer_id
                if not self._is_gone_error(exc):
                    await db.rollback()
                    logger.exception(
                        "Notify Live Activity keepalive update failed for provider %s printer %s",
                        provider_id,
                        activity_printer_id,
                    )
                    continue
                await db.rollback()
                stale_activity = await db.get(NotificationLiveActivity, activity_db_id)
                if stale_activity:
                    self._mark_ended(stale_activity)
                    await db.commit()
                logger.info(
                    "Notify Live Activity keepalive marked expired activity ended for provider %s printer %s",
                    provider_id,
                    activity_printer_id,
                )
            except Exception:
                provider_id = provider.id
                printer_id = activity.printer_id
                await db.rollback()
                logger.exception(
                    "Notify Live Activity keepalive update failed for provider %s printer %s",
                    provider_id,
                    printer_id,
                )

        await self._ensure_running_printers_have_activities(db)

    async def _ensure_running_printers_have_activities(self, db: AsyncSession) -> None:
        """Create a missing Live Activity when reconciliation sees an active print.

        Print-start events can be missed during restarts, deployment windows, or a
        transient Notify gateway/device error. The keepalive loop already has the
        authoritative current printer state, so it should repair a missing tile
        instead of waiting for a future print-start edge.
        """
        providers = await self._all_enabled_live_notify_providers(db)
        if not providers:
            return

        printers = (await db.scalars(select(Printer).where(Printer.is_active.is_(True)))).all()
        printer_by_id = {printer.id: printer for printer in printers}
        printer_ids = {printer.id for printer in printers}
        printer_ids.update(provider.printer_id for provider, _ in providers if provider.printer_id is not None)

        for printer_id in sorted(printer_ids):
            state = self._printer_status(printer_id)
            if not self._is_running_state(state):
                continue
            printer = printer_by_id.get(printer_id)
            printer_name = getattr(printer, "name", None) or self._printer_name(printer_id)
            for provider, config in providers:
                if provider.printer_id is not None and provider.printer_id != printer_id:
                    continue
                if await self._active_activity(db, provider.id, printer_id):
                    continue
                await self._start_from_state(
                    db,
                    provider=provider,
                    config=config,
                    printer_id=printer_id,
                    printer_name=printer_name,
                    state=state,
                )

    async def _start_from_state(
        self,
        db: AsyncSession,
        *,
        provider: NotificationProvider,
        config: dict[str, Any],
        printer_id: int,
        printer_name: str,
        state: Any,
    ) -> None:
        filename = getattr(state, "subtask_name", None) or getattr(state, "current_print", None) or "Unknown print"
        subtask_id = getattr(state, "subtask_id", None)
        progress = effective_print_progress(state)
        remaining_time = self._state_remaining_time_seconds(state)
        layer_num = self._optional_int(getattr(state, "layer_num", None))
        total_layers = self._optional_int(getattr(state, "total_layers", None))
        provider_id = provider.id
        client = await self._client(config)
        try:
            activity_id = await client.start(
                build_start_content(
                    printer_name=printer_name,
                    filename=str(filename),
                    progress=progress,
                    remaining_time=remaining_time,
                    layer_num=layer_num,
                    total_layers=total_layers,
                    compact_display=self._compact_display(config),
                    native_countdown=self._native_tile_countdown(config),
                )
            )
            await self._create_activity(
                db,
                provider_id=provider_id,
                printer_id=printer_id,
                activity_id=activity_id,
                subtask_id=str(subtask_id) if subtask_id else None,
                filename=str(filename),
                progress=progress,
                remaining_time=remaining_time,
                layer_num=layer_num,
                total_layers=total_layers,
                config=config,
            )
            await db.commit()
            logger.info(
                "Notify Live Activity keepalive created missing activity for provider %s printer %s",
                provider_id,
                printer_id,
            )
        except Exception:
            await db.rollback()
            logger.exception(
                "Notify Live Activity keepalive start failed for provider %s printer %s",
                provider_id,
                printer_id,
            )

    async def _enabled_notify_providers(
        self,
        db: AsyncSession,
        printer_id: int,
    ) -> list[tuple[NotificationProvider, dict[str, Any]]]:
        providers = await self._all_enabled_live_notify_providers(db)
        return [
            (provider, config)
            for provider, config in providers
            if provider.printer_id is None or provider.printer_id == printer_id
        ]

    async def _all_enabled_live_notify_providers(
        self, db: AsyncSession
    ) -> list[tuple[NotificationProvider, dict[str, Any]]]:
        result = await db.scalars(
            select(NotificationProvider).where(
                NotificationProvider.enabled.is_(True),
                NotificationProvider.provider_type == "notify",
            )
        )
        providers: list[tuple[NotificationProvider, dict[str, Any]]] = []
        for provider in result.all():
            config = self._config(provider)
            if self._truthy(config.get("live_activities_enabled")):
                providers.append((provider, config))
        return providers

    async def _active_activity(
        self,
        db: AsyncSession,
        provider_id: int,
        printer_id: int,
        *,
        subtask_id: str | None = None,
    ) -> NotificationLiveActivity | None:
        stmt = select(NotificationLiveActivity).where(
            NotificationLiveActivity.provider_id == provider_id,
            NotificationLiveActivity.printer_id == printer_id,
            NotificationLiveActivity.state == "active",
        )
        if subtask_id:
            exact = await db.scalar(stmt.where(NotificationLiveActivity.subtask_id == subtask_id))
            if exact:
                return exact
        return await db.scalar(stmt.order_by(NotificationLiveActivity.id.desc()))

    async def _end_existing(
        self,
        client: Any,
        activity: NotificationLiveActivity,
        *,
        provider_config: dict[str, Any],
        printer_name: str,
        status: str,
    ) -> None:
        payload = build_end_content(
            printer_name=printer_name,
            filename=activity.filename or "Unknown print",
            status=status,
            reason="Replaced by a new print",
        )
        await client.end(activity.activity_id, payload, keep_for_seconds=self._end_keep_for(provider_config))
        self._mark_ended(activity)

    async def _create_activity(
        self,
        db: AsyncSession,
        *,
        provider_id: int,
        printer_id: int,
        activity_id: str,
        subtask_id: str | None,
        filename: str,
        progress: float | int,
        remaining_time: int | None,
        layer_num: int | None,
        total_layers: int | None,
        config: dict[str, Any],
    ) -> None:
        db.add(
            NotificationLiveActivity(
                provider_id=provider_id,
                printer_id=printer_id,
                activity_id=activity_id,
                subtask_id=subtask_id,
                filename=filename,
                state="active",
                last_progress=float(progress),
                last_remaining_time=remaining_time,
                last_layer_num=layer_num,
                last_total_layers=total_layers,
                expires_at=self._expires_at(config),
            )
        )

    async def _client(self, config: dict[str, Any]) -> Any:
        if self.client_factory:
            client = self.client_factory(config)
            if inspect.isawaitable(client):
                return await client
            return client
        from backend.app.services.notification_service import notification_service

        return NotifyLiveActivityClient(config, http_client=await notification_service._get_client())

    @staticmethod
    def _config(provider: NotificationProvider) -> dict[str, Any]:
        if isinstance(provider.config, str):
            return json.loads(provider.config or "{}")
        return dict(provider.config or {})

    @staticmethod
    def _filename(data: dict[str, Any]) -> str:
        subtask_name = data.get("subtask_name")
        if subtask_name:
            return str(subtask_name).replace("_", " ")
        return str(data.get("filename") or data.get("gcode_file") or "Unknown print")

    @staticmethod
    def _subtask_id(data: dict[str, Any]) -> str | None:
        value = data.get("subtask_id") or data.get("task_id")
        return str(value) if value else None

    @staticmethod
    def _same_print(activity: NotificationLiveActivity, *, subtask_id: str | None, filename: str | None) -> bool:
        if subtask_id and activity.subtask_id == subtask_id:
            return True
        return bool(filename and activity.filename == filename and not activity.subtask_id)

    @classmethod
    def _activity_payload_unchanged(
        cls,
        activity: NotificationLiveActivity,
        *,
        filename: str,
        progress: float | int,
        remaining_time: int | None,
        layer_num: int | None,
        total_layers: int | None,
    ) -> bool:
        return (
            activity.filename == filename
            and cls._float_equal(activity.last_progress, progress)
            and cls._remaining_time_equal(activity, remaining_time)
            and activity.last_layer_num == layer_num
            and activity.last_total_layers == total_layers
        )

    @staticmethod
    def _routine_progress_update_too_soon(
        activity: NotificationLiveActivity,
        *,
        progress: float | int,
        layer_num: int | None,
        total_layers: int | None,
    ) -> bool:
        """Respect Apple's Live Activity pacing for routine progress-only updates.

        Creation, first real layer, and completion remain immediate. Intermediate
        layer/progress frames can be coalesced safely; sending them too quickly
        causes iOS/Notify to batch or visibly lag behind.
        """
        updated_at = activity.updated_at
        if updated_at is None or activity.last_progress is None:
            return False
        if float(progress) >= 100:
            return False
        if total_layers is not None and layer_num is not None and total_layers > 0 and layer_num >= total_layers:
            return False
        if (activity.last_layer_num in (None, 0)) and layer_num is not None and layer_num > 0:
            return False
        elapsed = (datetime.utcnow() - updated_at).total_seconds()
        return elapsed < APPLE_LIVE_ACTIVITY_PROGRESS_FLOOR_SECONDS

    @staticmethod
    def _monotonic_progress_payload(
        activity: NotificationLiveActivity,
        *,
        progress: float | int,
        layer_num: int | None,
        total_layers: int | None,
    ) -> tuple[float | int, int | None, int | None]:
        """Keep one active Live Activity moving forward for a print.

        Bambu reports firmware progress, preparation stages, and layer counters
        at different times. If consecutive frames briefly switch scale/source,
        never publish an older visible progress/layer than the last successful
        Live Activity payload for this same activity.
        """
        last_progress = activity.last_progress
        if last_progress is not None and float(progress) < float(last_progress):
            progress = last_progress
            if activity.last_layer_num is not None and (layer_num is None or layer_num < activity.last_layer_num):
                layer_num = activity.last_layer_num
                total_layers = activity.last_total_layers

        if activity.last_layer_num is not None and layer_num is not None and layer_num < activity.last_layer_num:
            layer_num = activity.last_layer_num
            total_layers = activity.last_total_layers

        return progress, layer_num, total_layers

    @classmethod
    def _remaining_time_equal(cls, activity: NotificationLiveActivity, remaining_time: int | None) -> bool:
        if activity.last_remaining_time == remaining_time:
            return True
        if activity.last_remaining_time is None or remaining_time is None:
            return False
        return abs(cls._decayed_remaining_time(activity) - remaining_time) <= 15

    @staticmethod
    def _decayed_remaining_time(activity: NotificationLiveActivity) -> int:
        updated_at = activity.updated_at or datetime.utcnow()
        elapsed = max(int((datetime.utcnow() - updated_at).total_seconds()), 0)
        return max(int(activity.last_remaining_time or 0) - elapsed, 0)

    @staticmethod
    def _float_equal(left: float | int | None, right: float | int | None) -> bool:
        if left is None or right is None:
            return left is right
        return abs(float(left) - float(right)) < 0.01

    @staticmethod
    def _remaining_time(data: dict[str, Any], *, archive_data: dict[str, Any] | None = None) -> int | None:
        if archive_data and archive_data.get("print_time_seconds"):
            return int(archive_data["print_time_seconds"])
        value = data.get("remaining_time")
        if value:
            return int(value)
        raw_minutes = (
            data.get("raw_data", {}).get("mc_remaining_time") if isinstance(data.get("raw_data"), dict) else None
        )
        if raw_minutes:
            return int(raw_minutes) * 60
        return None

    def _printer_status(self, printer_id: int) -> Any:
        if self.status_getter:
            return self.status_getter(printer_id)
        from backend.app.services.printer_manager import printer_manager

        return printer_manager.get_status(printer_id)

    def _printer_name(self, printer_id: int) -> str:
        if self.printer_name_getter:
            return self.printer_name_getter(printer_id)
        from backend.app.services.printer_manager import printer_manager

        printer = printer_manager.get_printer(printer_id)
        return getattr(printer, "name", None) or f"Printer {printer_id}"

    @staticmethod
    def _is_running_state(state: Any) -> bool:
        if not state or not getattr(state, "connected", True):
            return False
        return str(getattr(state, "state", "")).upper() in {"RUNNING", "PRINTING", "PAUSE", "PAUSED"}

    @staticmethod
    def _state_remaining_time_seconds(state: Any) -> int | None:
        remaining = getattr(state, "remaining_time", None)
        if not remaining:
            return None
        # Provider state stores remaining_time in minutes; NotificationService
        # converts it to seconds before normal notifications, so do the same here.
        return int(remaining) * 60

    @staticmethod
    def _number(value: Any, *, default: float = 0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _compact_display(config: dict[str, Any]) -> str:
        value = str(config.get("live_activity_compact_display") or "progress").strip().lower()
        return "eta" if value in {"eta", "time", "remaining", "timer"} else "progress"

    @staticmethod
    def _native_tile_countdown(config: dict[str, Any]) -> bool:
        return NotifyLiveActivityService._truthy(config.get("live_activity_native_tile_countdown"))

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
        return bool(value)

    @staticmethod
    def _is_gone_error(exc: NotifyLiveActivityError) -> bool:
        return exc.status_code == 410

    @staticmethod
    def _end_keep_for(config: dict[str, Any]) -> int:
        try:
            return max(int(config.get("live_activity_end_keep_for_seconds", 300)), 0)
        except (TypeError, ValueError):
            return 300

    @staticmethod
    def _expires_at(config: dict[str, Any]) -> datetime | None:
        try:
            seconds = int(config.get("live_activity_expire_after_seconds", 12 * 60 * 60))
        except (TypeError, ValueError):
            seconds = 12 * 60 * 60
        if seconds <= 0:
            return None
        return datetime.utcnow() + timedelta(seconds=seconds)

    @staticmethod
    def _mark_ended(activity: NotificationLiveActivity) -> None:
        now = datetime.utcnow()
        activity.state = "ended"
        activity.ended_at = now
        activity.updated_at = now


notify_live_activity_service = NotifyLiveActivityService()
