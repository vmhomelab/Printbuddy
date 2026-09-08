"""Persist active Notify Live Activities for print lifecycle updates."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class NotificationLiveActivity(Base):
    """Stores state for active Notify iOS Live Activities.

    A Live Activity is a stateful external resource. Keep its activity ID and
    print identity outside provider.config so restarts, duplicate starts, and
    cleanup can be handled safely.
    """

    __tablename__ = "notification_live_activities"
    __table_args__ = (Index("ix_notify_live_provider_printer_state", "provider_id", "printer_id", "state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("notification_providers.id", ondelete="CASCADE"), nullable=False
    )
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id", ondelete="CASCADE"), nullable=False)
    activity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subtask_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_remaining_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_layer_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_total_layers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    provider = relationship("NotificationProvider")
    printer = relationship("Printer")
