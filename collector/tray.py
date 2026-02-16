"""System tray icon using pystray."""

import threading

import pystray
from PIL import Image, ImageDraw


def _create_icon_image(color: str) -> Image.Image:
    """Create a simple circle icon with the given color."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


class TrayIcon:
    def __init__(self, on_show: callable, on_quit: callable):
        self._on_show = on_show
        self._on_quit = on_quit
        self._icon: pystray.Icon | None = None
        self._has_unread = False

    def start(self) -> None:
        """Start the tray icon in a background thread."""
        menu = pystray.Menu(
            pystray.MenuItem("表示", self._on_show_click, default=True),
            pystray.MenuItem("終了", self._on_quit_click),
        )
        self._icon = pystray.Icon(
            "teams-mention-collector",
            icon=_create_icon_image("gray"),
            title="Teams Mention Collector",
            menu=menu,
        )
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def update_unread(self, has_unread: bool) -> None:
        """Update icon color based on unread status."""
        if has_unread == self._has_unread:
            return
        self._has_unread = has_unread
        if self._icon:
            color = "red" if has_unread else "gray"
            self._icon.icon = _create_icon_image(color)

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def _on_show_click(self, icon, item) -> None:
        self._on_show()

    def _on_quit_click(self, icon, item) -> None:
        self._on_quit()
