"""Windows notification listener using the WPN notification database (SQLite).

Instead of the WinRT UserNotificationListener API (which requires packaged-app
privileges), this module reads the Windows Push Notification database directly.
The database is located at:
  %LOCALAPPDATA%\\Microsoft\\Windows\\Notifications\\wpndatabase.db
"""

import logging
import os
import shutil
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Known Teams handler PrimaryIds in NotificationHandler table
TEAMS_PRIMARY_IDS = {
    "MSTeams_8wekyb3d8bbwe!MSTeams",       # New Teams (MSIX)
    "com.squirrel.Teams.Teams",             # Classic Teams
    "Microsoft.Teams",                      # Alternative ID
}

WPN_DB_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "Windows", "Notifications", "wpndatabase.db",
)


@dataclass
class TeamsNotification:
    sender: str
    channel: str
    message: str
    notification_id: int


class NotificationListener:
    def __init__(self):
        self._seen_ids: set[int] = set()
        self._teams_handler_ids: set[int] = set()
        self._initialized = False

    async def request_access(self) -> bool:
        """Verify the notification database is accessible and find Teams handler IDs."""
        if not os.path.exists(WPN_DB_PATH):
            logger.error("Notification database not found: %s", WPN_DB_PATH)
            return False

        try:
            conn = self._open_db()
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT RecordId, PrimaryId FROM NotificationHandler"
            ).fetchall()
            conn.close()
            self._cleanup_tmp()

            for record_id, primary_id in rows:
                if any(tid in (primary_id or "") for tid in TEAMS_PRIMARY_IDS):
                    self._teams_handler_ids.add(record_id)
                    logger.info("Found Teams handler: %s (id=%d)", primary_id, record_id)

            if not self._teams_handler_ids:
                logger.warning(
                    "No Teams notification handlers found in DB. "
                    "Teams notifications will not be detected until Teams is installed/run."
                )
            self._initialized = True
            logger.info("Notification database access OK (%d Teams handlers)", len(self._teams_handler_ids))
            return True

        except Exception as e:
            logger.error("Failed to access notification database: %s", e)
            return False

    @staticmethod
    def _tmp_path() -> str:
        return os.path.join(tempfile.gettempdir(), "wpn_agent_copy.db")

    def _open_db(self) -> sqlite3.Connection:
        """Open a read-only copy of the WPN database.

        The database is locked by the system, so we copy it to a temp file first.
        """
        tmp = self._tmp_path()
        shutil.copy2(WPN_DB_PATH, tmp)
        conn = sqlite3.connect(tmp)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _cleanup_tmp(self) -> None:
        try:
            os.remove(self._tmp_path())
        except OSError:
            pass

    async def get_new_teams_notifications(self) -> list[TeamsNotification]:
        """Poll for new Teams toast notifications from the database."""
        if not self._initialized:
            return []

        results: list[TeamsNotification] = []
        try:
            conn = self._open_db()
            cur = conn.cursor()

            # Re-discover Teams handler IDs in case Teams was installed after startup
            if not self._teams_handler_ids:
                rows = cur.execute(
                    "SELECT RecordId, PrimaryId FROM NotificationHandler"
                ).fetchall()
                for record_id, primary_id in rows:
                    if any(tid in (primary_id or "") for tid in TEAMS_PRIMARY_IDS):
                        self._teams_handler_ids.add(record_id)
                        logger.info("Discovered Teams handler: %s (id=%d)", primary_id, record_id)

            if not self._teams_handler_ids:
                conn.close()
                self._cleanup_tmp()
                return []

            placeholders = ",".join("?" for _ in self._teams_handler_ids)
            toasts = cur.execute(
                f"SELECT Id, Payload FROM Notification "
                f"WHERE Type = 'toast' AND HandlerId IN ({placeholders}) "
                f"ORDER BY ArrivalTime DESC",
                list(self._teams_handler_ids),
            ).fetchall()
            conn.close()
            self._cleanup_tmp()

        except Exception as e:
            logger.error("Failed to read notification database: %s", e)
            self._cleanup_tmp()
            return []

        for notif_id, payload in toasts:
            if notif_id in self._seen_ids:
                continue

            self._seen_ids.add(notif_id)

            sender, channel, message = self._extract_text(payload)
            if not message:
                continue

            results.append(
                TeamsNotification(
                    sender=sender,
                    channel=channel,
                    message=message,
                    notification_id=notif_id,
                )
            )
            logger.debug("New Teams notification: %s / %s: %s", sender, channel, message)

        # Prevent seen_ids from growing unbounded
        if len(self._seen_ids) > 10000:
            current_ids = {t[0] for t in toasts} if toasts else set()
            self._seen_ids = current_ids

        return results

    def _extract_text(self, payload) -> tuple[str, str, str]:
        """Extract sender, channel, message from toast notification XML payload."""
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")

            root = ET.fromstring(payload)

            texts = []
            for text_el in root.iter("text"):
                t = text_el.text
                if t:
                    texts.append(t.strip())

        except Exception as e:
            logger.debug("Failed to parse toast XML: %s", e)
            return ("", "", "")

        # Typical Teams toast layout:
        # texts[0] = sender name
        # texts[1] = channel/chat name (sometimes absent)
        # texts[2] = message preview (or texts[1] if no channel)
        if len(texts) >= 3:
            return (texts[0], texts[1], texts[2])
        elif len(texts) == 2:
            return (texts[0], "", texts[1])
        elif len(texts) == 1:
            return ("", "", texts[0])
        return ("", "", "")

    async def discover_apps(self) -> list[str]:
        """List all app IDs from notification handlers (debug helper)."""
        try:
            conn = self._open_db()
            cur = conn.cursor()
            handlers = cur.execute(
                "SELECT PrimaryId FROM NotificationHandler ORDER BY PrimaryId"
            ).fetchall()
            conn.close()
            self._cleanup_tmp()
            return [h[0] for h in handlers if h[0]]
        except Exception as e:
            logger.error("Failed to discover apps: %s", e)
            return []
