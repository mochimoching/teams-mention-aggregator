"""HTTP client for sending notifications to the relay server."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 500
MAX_RETRIES = 5
BASE_BACKOFF = 2.0  # seconds


@dataclass
class PendingNotification:
    pc_name: str
    sender: str
    channel: str
    message: str
    retries: int = 0


class RelayClient:
    def __init__(self, relay_url: str, api_key: str, proxies: dict | None = None):
        self._url = relay_url.rstrip("/") + "/api/notifications"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._proxies = proxies or {}
        self._queue: deque[PendingNotification] = deque(maxlen=MAX_QUEUE_SIZE)
        self._lock = threading.Lock()

    def send(self, pc_name: str, sender: str, channel: str, message: str) -> bool:
        """Send a notification. Returns True if sent immediately, False if queued."""
        payload = {
            "pc_name": pc_name,
            "sender": sender,
            "channel": channel,
            "message": message[:80],
        }
        try:
            resp = requests.post(
                self._url,
                json=payload,
                headers=self._headers,
                proxies=self._proxies,
                timeout=15,
            )
            resp.raise_for_status()
            logger.info("Sent notification: %s / %s", sender, channel)
            return True
        except requests.RequestException as e:
            logger.warning("Failed to send notification: %s — queuing for retry", e)
            with self._lock:
                self._queue.append(
                    PendingNotification(
                        pc_name=pc_name,
                        sender=sender,
                        channel=channel,
                        message=message[:80],
                    )
                )
            return False

    def flush_queue(self) -> None:
        """Retry queued notifications with exponential backoff."""
        with self._lock:
            pending = list(self._queue)
            self._queue.clear()

        still_pending = []
        for notif in pending:
            payload = {
                "pc_name": notif.pc_name,
                "sender": notif.sender,
                "channel": notif.channel,
                "message": notif.message,
            }
            try:
                resp = requests.post(
                    self._url,
                    json=payload,
                    headers=self._headers,
                    proxies=self._proxies,
                    timeout=15,
                )
                resp.raise_for_status()
                logger.info("Retried notification OK: %s / %s", notif.sender, notif.channel)
            except requests.RequestException:
                notif.retries += 1
                if notif.retries < MAX_RETRIES:
                    still_pending.append(notif)
                    backoff = BASE_BACKOFF ** notif.retries
                    logger.warning(
                        "Retry %d/%d failed, next backoff %.0fs",
                        notif.retries,
                        MAX_RETRIES,
                        backoff,
                    )
                    time.sleep(min(backoff, 60))
                else:
                    logger.error("Dropped notification after %d retries: %s", MAX_RETRIES, notif.sender)

        if still_pending:
            with self._lock:
                self._queue.extendleft(reversed(still_pending))

    @property
    def queue_size(self) -> int:
        return len(self._queue)
