"""Windows notification listener using WinRT UserNotificationListener."""

import logging
from dataclasses import dataclass

from winrt.windows.ui.notifications.management import UserNotificationListener
from winrt.windows.ui.notifications import (
    NotificationKinds,
    UserNotificationChangedKind,
)

logger = logging.getLogger(__name__)

# Known Teams App IDs
TEAMS_APP_IDS = {
    "MSTeams_8wekyb3d8bbwe!MSTeams",     # New Teams (MSIX)
    "com.squirrel.Teams.Teams",            # Classic Teams
    "Microsoft.Teams",                     # Alternative ID
}


@dataclass
class TeamsNotification:
    sender: str
    channel: str
    message: str
    notification_id: int


class NotificationListener:
    def __init__(self):
        self._listener = UserNotificationListener.current
        self._seen_ids: set[int] = set()
        self._initialized = False

    async def request_access(self) -> bool:
        """Request notification access. Returns True if granted."""
        access = await self._listener.request_access_async()
        # 0 = Allowed, 1 = Denied, 2 = Unspecified
        granted = access == 0
        if granted:
            logger.info("Notification access granted")
            self._initialized = True
        else:
            logger.error("Notification access denied (status=%d)", access)
        return granted

    async def get_new_teams_notifications(self) -> list[TeamsNotification]:
        """Poll for new Teams toast notifications."""
        if not self._initialized:
            return []

        results: list[TeamsNotification] = []
        try:
            notifications = await self._listener.get_notifications_async(
                NotificationKinds.TOAST
            )
        except Exception as e:
            logger.error("Failed to get notifications: %s", e)
            return []

        for notif in notifications:
            nid = notif.id
            if nid in self._seen_ids:
                continue

            self._seen_ids.add(nid)

            try:
                app_info = notif.app_info
                app_id = app_info.app_user_model_id if app_info else ""
            except Exception:
                app_id = ""

            if not any(teams_id in app_id for teams_id in TEAMS_APP_IDS):
                continue

            sender, channel, message = self._extract_text(notif)
            if not message:
                continue

            results.append(
                TeamsNotification(
                    sender=sender,
                    channel=channel,
                    message=message,
                    notification_id=nid,
                )
            )
            logger.debug("New Teams notification: %s / %s: %s", sender, channel, message)

        # Prevent seen_ids from growing unbounded
        if len(self._seen_ids) > 10000:
            current_ids = {n.id for n in notifications} if notifications else set()
            self._seen_ids = current_ids

        return results

    def _extract_text(self, notif) -> tuple[str, str, str]:
        """Extract sender, channel, message from toast notification binding."""
        try:
            toast_binding = notif.notification.visual.get_binding(
                "ToastGeneric"
            ) or notif.notification.visual.bindings[0]

            texts = [
                el.text
                for el in toast_binding.get_text_elements()
                if hasattr(el, "text") and el.text
            ]
        except Exception as e:
            logger.debug("Failed to extract toast text: %s", e)
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
        """List all app IDs from current notifications (debug helper)."""
        notifications = await self._listener.get_notifications_async(
            NotificationKinds.TOAST
        )
        app_ids = set()
        for notif in notifications:
            try:
                app_info = notif.app_info
                app_id = app_info.app_user_model_id if app_info else "(unknown)"
                app_ids.add(app_id)
            except Exception:
                app_ids.add("(error)")
        return sorted(app_ids)
