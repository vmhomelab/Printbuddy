"""Tests for Notify Live Activity HTTP client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.notify_live_activity_client import NotifyLiveActivityClient, NotifyLiveActivityError


@pytest.fixture
def config():
    return {
        "device_id": "DEVICE 123",
        "device_token": "secret token",
        "base_url": "https://push.getnotifyapp.com",
    }


@pytest.fixture
def mock_client():
    client = AsyncMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"id": "activity-123"}
    response.text = '{"id":"activity-123"}'
    client.post = AsyncMock(return_value=response)
    client.delete = AsyncMock(return_value=response)
    client.request = AsyncMock(return_value=response)
    client.get = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_start_posts_new_activity_and_returns_activity_id(config, mock_client):
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    activity_id = await client.start({"title": "P1S", "progress": 0.25})

    assert activity_id == "activity-123"
    mock_client.post.assert_called_once_with(
        "https://push.getnotifyapp.com/live-activity/DEVICE%20123?token=secret%20token&new=1",
        json={"title": "P1S", "progress": 0.25},
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_update_posts_to_existing_activity_id(config, mock_client):
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    await client.update("activity 123", {"progress": 0.75})

    mock_client.post.assert_called_once_with(
        "https://push.getnotifyapp.com/live-activity/activity%20123?token=secret%20token",
        json={"progress": 0.75},
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_end_deletes_existing_activity_with_keep_for(config, mock_client):
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    await client.end("activity 123", {"status": "completed"}, keep_for_seconds=300)

    mock_client.request.assert_called_once_with(
        "DELETE",
        "https://push.getnotifyapp.com/live-activity/activity%20123?token=secret%20token&keepFor=300",
        json={"status": "completed"},
        headers={"Content-Type": "application/json"},
    )
    mock_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_errors_do_not_leak_device_token(config, mock_client):
    response = MagicMock()
    response.status_code = 403
    response.text = "forbidden for secret token"
    mock_client.post = AsyncMock(return_value=response)
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    with pytest.raises(NotifyLiveActivityError) as exc_info:
        await client.start({"title": "P1S"})

    message = str(exc_info.value)
    assert "secret token" not in message
    assert "[REDACTED]" in message
    assert exc_info.value.status_code == 403
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_rate_limit_error_is_retryable(config, mock_client):
    response = MagicMock()
    response.status_code = 429
    response.text = "slow down"
    mock_client.post = AsyncMock(return_value=response)
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    with pytest.raises(NotifyLiveActivityError) as exc_info:
        await client.update("activity-123", {"progress": 0.5})

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_success_false_body_is_treated_as_error(config, mock_client):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"success": False, "message": "Live Activities are disabled for this device"}
    response.text = '{"success":false,"message":"Live Activities are disabled for this device"}'
    mock_client.post = AsyncMock(return_value=response)
    client = NotifyLiveActivityClient(config, http_client=mock_client)

    with pytest.raises(NotifyLiveActivityError) as exc_info:
        await client.start({"title": "P1S"})

    assert "Live Activities are disabled for this device" in str(exc_info.value)
    assert exc_info.value.status_code == 200
    assert exc_info.value.retryable is False
