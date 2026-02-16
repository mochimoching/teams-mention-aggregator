"""Teams Mention Collector — aggregates notifications from relay server with Tkinter UI."""

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os

from config import load_config
from relay_client import RelayClient
from tray import TrayIcon
from ui import CollectorUI

DEFAULT_LOG_DIR = Path(os.environ.get("APPDATA", ".")) / "teams-mention-collector"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "collector.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Teams Mention Collector")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(DEFAULT_LOG_DIR)

    relay_cfg = cfg["relay"]
    collector_cfg = cfg.get("collector", {})
    proxy_cfg = cfg.get("proxy", {})

    proxies = {}
    if proxy_cfg.get("http"):
        proxies["http"] = proxy_cfg["http"]
    if proxy_cfg.get("https"):
        proxies["https"] = proxy_cfg["https"]

    client = RelayClient(
        relay_url=relay_cfg["url"],
        api_key=relay_cfg["api_key"],
        proxies=proxies or None,
    )

    # Build UI first (needed for tray callbacks)
    ui = CollectorUI(
        relay_client=client,
        poll_interval=collector_cfg.get("poll_interval", 10),
        notify_sound=collector_cfg.get("notify_sound", True),
        notify_toast=collector_cfg.get("notify_toast", True),
    )

    # System tray
    tray = TrayIcon(
        on_show=ui.show,
        on_quit=lambda: (tray.stop(), ui.quit()),
    )
    tray.start()

    # Periodically update tray icon based on unread status
    def update_tray():
        tray.update_unread(ui.has_unread)
        ui._root.after(2000, update_tray)

    ui._root.after(2000, update_tray)

    # When window is minimized to tray, don't actually close
    ui._on_close = lambda: None  # tray handles show/quit

    logging.info("Collector started")
    ui.run()


if __name__ == "__main__":
    main()
