"""Backend retry worker for active printers that are offline or missing a client."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from backend.app.models.printer import Printer

logger = logging.getLogger(__name__)

DEFAULT_RECONNECT_INTERVAL_SECONDS = 30


class PrinterReconnectService:
    """Reconnect active offline printers without relying on an open browser tab."""

    def __init__(self, printer_manager: Any, session_factory: Callable[[], Any] | None) -> None:
        self._printer_manager = printer_manager
        self._session_factory = session_factory
        self._task: asyncio.Task[None] | None = None
        self.next_attempt_at: dict[int, float] = {}

    @staticmethod
    def _interval_seconds(printer: Any) -> int:
        value = getattr(printer, "reconnect_interval_seconds", DEFAULT_RECONNECT_INTERVAL_SECONDS)
        try:
            return max(10, min(int(value), 3600))
        except (TypeError, ValueError):
            return DEFAULT_RECONNECT_INTERVAL_SECONDS

    def _needs_reconnect(self, printer_id: int) -> bool:
        client = self._printer_manager.get_client(printer_id)
        return client is None or not bool(getattr(getattr(client, "state", None), "connected", False))

    async def reconnect_due_printers(self, printers: list[Any], *, now: float | None = None) -> None:
        """Attempt due active offline printers once; suitable for deterministic tests."""
        current = time.monotonic() if now is None else now
        active_ids = {printer.id for printer in printers if getattr(printer, "is_active", False)}
        for printer_id in tuple(self.next_attempt_at):
            if printer_id not in active_ids:
                self.next_attempt_at.pop(printer_id, None)

        for printer in printers:
            if not getattr(printer, "is_active", False):
                continue
            if not self._needs_reconnect(printer.id):
                self.next_attempt_at.pop(printer.id, None)
                continue
            if current < self.next_attempt_at.get(printer.id, 0):
                continue

            interval = self._interval_seconds(printer)
            self.next_attempt_at[printer.id] = current + interval
            try:
                connected = await self._printer_manager.connect_printer(printer)
                if connected:
                    logger.info("Recovered printer connection: %s (id=%s)", printer.name, printer.id)
                else:
                    logger.debug("Printer reconnect did not complete yet: %s (id=%s)", printer.name, printer.id)
            except Exception as exc:  # noqa: BLE001 - one offline printer must never stop the worker
                logger.debug("Printer reconnect failed for %s (id=%s): %s", printer.name, printer.id, type(exc).__name__)

    async def _run(self) -> None:
        assert self._session_factory is not None
        while True:
            try:
                async with self._session_factory() as db:
                    printers = (await db.scalars(select(Printer).where(Printer.is_active.is_(True)))).all()
                await self.reconnect_due_printers(printers)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - keep recovery available after transient DB errors
                logger.warning("Printer reconnect worker cycle failed: %s", type(exc).__name__)
            await asyncio.sleep(1)

    def start(self) -> None:
        if self._task is None or self._task.done():
            if self._session_factory is None:
                raise RuntimeError("PrinterReconnectService requires a session factory")
            self._task = asyncio.create_task(self._run(), name="printer-reconnect-worker")
            logger.info("Printer reconnect worker started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.next_attempt_at.clear()
        logger.info("Printer reconnect worker stopped")
