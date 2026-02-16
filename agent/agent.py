"""Teams Mention Agent — monitors local Teams notifications and forwards to relay server."""

import argparse
import asyncio
import logging
import os
import sys
import winreg
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import load_config
from notification_listener import NotificationListener
from relay_client import RelayClient

APP_NAME = "TeamsMentionAgent"
DEFAULT_LOG_DIR = Path(os.environ.get("APPDATA", ".")) / "teams-mention-agent"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "agent.log",
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


def install_startup() -> None:
    """Register this script to run at Windows logon via registry."""
    python = sys.executable
    # Use pythonw.exe for no console window
    pythonw = python.replace("python.exe", "pythonw.exe")
    if not Path(pythonw).exists():
        pythonw = python
    script = str(Path(__file__).resolve())
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{pythonw}" "{script}"')
    winreg.CloseKey(key)
    print(f"Installed startup entry: {APP_NAME}")


def uninstall_startup() -> None:
    """Remove the startup registry entry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        print(f"Removed startup entry: {APP_NAME}")
    except FileNotFoundError:
        print("Startup entry not found.")


async def discover_apps() -> None:
    """Print all notification app IDs (debug helper)."""
    listener = NotificationListener()
    if not await listener.request_access():
        print("Notification access denied.")
        return
    apps = await listener.discover_apps()
    print("Notification App IDs found:")
    for app_id in apps:
        print(f"  {app_id}")


async def run(cfg: dict) -> None:
    relay_cfg = cfg["relay"]
    agent_cfg = cfg.get("agent", {})
    proxy_cfg = cfg.get("proxy", {})

    proxies = {}
    if proxy_cfg.get("http"):
        proxies["http"] = proxy_cfg["http"]
    if proxy_cfg.get("https"):
        proxies["https"] = proxy_cfg["https"]

    pc_name = agent_cfg.get("pc_name", "unknown")
    poll_interval = agent_cfg.get("poll_interval", 3)

    client = RelayClient(
        relay_url=relay_cfg["url"],
        api_key=relay_cfg["api_key"],
        proxies=proxies or None,
    )

    listener = NotificationListener()
    if not await listener.request_access():
        logging.error("Cannot access notifications. Exiting.")
        return

    logging.info("Agent started for %s (poll every %ds)", pc_name, poll_interval)

    while True:
        try:
            new_notifs = await listener.get_new_teams_notifications()
            for n in new_notifs:
                client.send(pc_name, n.sender, n.channel, n.message)

            # Periodically flush retry queue
            if client.queue_size > 0:
                client.flush_queue()
        except Exception:
            logging.exception("Error in main loop")

        await asyncio.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Teams Mention Agent")
    parser.add_argument("--install", action="store_true", help="Register Windows startup")
    parser.add_argument("--uninstall", action="store_true", help="Remove Windows startup")
    parser.add_argument("--discover-apps", action="store_true", help="List all notification app IDs")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    args = parser.parse_args()

    if args.install:
        install_startup()
        return
    if args.uninstall:
        uninstall_startup()
        return
    if args.discover_apps:
        asyncio.run(discover_apps())
        return

    cfg = load_config(args.config)
    agent_cfg = cfg.get("agent", {})
    log_dir = Path(agent_cfg["log_dir"]) if agent_cfg.get("log_dir") else DEFAULT_LOG_DIR
    setup_logging(log_dir)

    asyncio.run(run(cfg))


if __name__ == "__main__":
    main()
