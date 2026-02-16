"""HTTP client for fetching/updating notifications from the relay server."""

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    id: str
    pc_name: str
    sender: str
    channel: str
    message: str
    timestamp: str
    status: str  # "unread" | "read"


class RelayClient:
    def __init__(self, relay_url: str, api_key: str, proxies: dict | None = None):
        self._base_url = relay_url.rstrip("/") + "/api/notifications"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._proxies = proxies or {}

    def get_notifications(
        self,
        since: str | None = None,
        status: str | None = None,
        pc_name: str | None = None,
    ) -> list[Notification]:
        """Fetch notifications from relay server."""
        params: dict[str, str] = {}
        if since:
            params["since"] = since
        if status:
            params["status"] = status
        if pc_name:
            params["pc_name"] = pc_name

        try:
            resp = requests.get(
                self._base_url,
                params=params,
                headers=self._headers,
                proxies=self._proxies,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [Notification(**n) for n in data.get("notifications", [])]
        except requests.RequestException as e:
            logger.error("Failed to fetch notifications: %s", e)
            return []

    def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        url = f"{self._base_url}/{notification_id}"
        try:
            resp = requests.patch(
                url,
                json={"status": "read"},
                headers=self._headers,
                proxies=self._proxies,
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Failed to mark read %s: %s", notification_id, e)
            return False
