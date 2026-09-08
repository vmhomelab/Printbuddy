"""Tests for persisted Notify Live Activity state."""

import backend.app.models  # noqa: F401
from backend.app.core.database import Base
from backend.app.models.notification_live_activity import NotificationLiveActivity


def test_notification_live_activity_model_registers_expected_table():
    table = Base.metadata.tables["notification_live_activities"]

    assert NotificationLiveActivity.__tablename__ == "notification_live_activities"
    assert {column.name for column in table.columns} >= {
        "id",
        "provider_id",
        "printer_id",
        "activity_id",
        "subtask_id",
        "filename",
        "state",
        "last_progress",
        "last_remaining_time",
        "last_layer_num",
        "last_total_layers",
        "started_at",
        "updated_at",
        "expires_at",
        "ended_at",
    }
    assert any(index.name == "ix_notify_live_provider_printer_state" for index in table.indexes)
