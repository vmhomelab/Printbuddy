"""Notify iOS Live Activity HTTP client."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


class NotifyLiveActivityError(Exception):
    """Raised when Notify Live Activity API requests fail."""

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class NotifyLiveActivityClient:
    """Small async client for Notify's Live Activity endpoints."""

    def __init__(self, config: dict[str, Any], *, http_client: Any):
        self.device_id = str(config.get("device_id", "")).strip()
        self.device_token = str(config.get("device_token", "")).strip()
        self.base_url = str(config.get("base_url") or "https://push.getnotifyapp.com").strip().rstrip("/")
        self.http_client = http_client

        if not self.device_id or not self.device_token:
            raise NotifyLiveActivityError("Device ID and device token are required", retryable=False)

    async def start(self, content: dict[str, Any]) -> str:
        """Create a new Live Activity and return its activity ID."""
        response = await self.http_client.post(
            self._activity_url(self.device_id, new=True),
            json=content,
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_error(response)
        data = self._json(response)
        self._raise_for_body_error(data, response)
        activity_id = data.get("id") or data.get("activity_id") or data.get("activityId")
        if not activity_id:
            raise NotifyLiveActivityError("Notify Live Activity start response did not include an activity ID")
        return str(activity_id)

    async def update(self, activity_id: str, content: dict[str, Any]) -> None:
        """Update an existing Live Activity."""
        response = await self.http_client.post(
            self._activity_url(activity_id),
            json=content,
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_error(response)
        self._raise_for_body_error(self._json(response), response)

    async def end(self, activity_id: str, content: dict[str, Any] | None = None, *, keep_for_seconds: int = 0) -> None:
        """End an existing Live Activity."""
        response = await self.http_client.request(
            "DELETE",
            self._activity_url(activity_id, keep_for_seconds=keep_for_seconds),
            json=content or {},
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_error(response)
        self._raise_for_body_error(self._json(response), response)

    async def status(self, activity_id: str) -> dict[str, Any]:
        """Fetch a Live Activity status document."""
        response = await self.http_client.get(self._activity_url(activity_id))
        self._raise_for_error(response)
        data = self._json(response)
        self._raise_for_body_error(data, response)
        return data

    def _activity_url(
        self,
        identifier: str,
        *,
        new: bool = False,
        keep_for_seconds: int | None = None,
    ) -> str:
        query = f"token={quote(self.device_token)}"
        if new:
            query += "&new=1"
        if keep_for_seconds is not None and keep_for_seconds > 0:
            query += f"&keepFor={int(keep_for_seconds)}"
        return f"{self.base_url}/live-activity/{quote(str(identifier))}?{query}"

    @staticmethod
    def _json(response: Any) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _raise_for_error(self, response: Any) -> None:
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in (200, 201, 202, 204):
            return

        retryable = status_code == 429 or status_code >= 500
        text = str(getattr(response, "text", ""))[:200]
        safe_text = self._redact(text)
        raise NotifyLiveActivityError(
            f"Notify Live Activity request failed with HTTP {status_code}: {safe_text}",
            status_code=status_code,
            retryable=retryable,
        )

    def _raise_for_body_error(self, data: dict[str, Any], response: Any) -> None:
        if data.get("success") is not False:
            return
        status_code = int(getattr(response, "status_code", 0) or 0)
        message = str(data.get("message") or data.get("error") or "Notify Live Activity request failed")
        raise NotifyLiveActivityError(self._redact(message), status_code=status_code, retryable=False)

    def _redact(self, value: str) -> str:
        safe = value
        if self.device_token:
            safe = safe.replace(self.device_token, "[REDACTED]")
        return safe
