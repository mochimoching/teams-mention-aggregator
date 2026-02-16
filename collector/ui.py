"""Tkinter UI for the Collector — notification list with filters and polling."""

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timezone

from relay_client import RelayClient, Notification

logger = logging.getLogger(__name__)

COLUMNS = ("pc_name", "sender", "channel", "message", "timestamp", "status")
COLUMN_LABELS = {
    "pc_name": "PC名",
    "sender": "送信者",
    "channel": "チャネル",
    "message": "メッセージ",
    "timestamp": "時刻",
    "status": "状態",
}
COLUMN_WIDTHS = {
    "pc_name": 80,
    "sender": 120,
    "channel": 140,
    "message": 250,
    "timestamp": 140,
    "status": 60,
}


class CollectorUI:
    def __init__(
        self,
        relay_client: RelayClient,
        poll_interval: int = 10,
        notify_sound: bool = True,
        notify_toast: bool = True,
        on_close: callable = None,
    ):
        self._client = relay_client
        self._poll_interval = poll_interval
        self._notify_sound = notify_sound
        self._notify_toast = notify_toast
        self._on_close = on_close
        self._data_queue: queue.Queue[list[Notification]] = queue.Queue()
        self._known_ids: set[str] = set()
        self._all_notifications: list[Notification] = []

        self._root = tk.Tk()
        self._root.title("Teams Mention Collector")
        self._root.geometry("900x500")
        self._root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self._build_ui()
        self._start_polling()
        self._process_queue()

    def _build_ui(self) -> None:
        # Filter bar
        filter_frame = ttk.Frame(self._root)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(filter_frame, text="PC:").pack(side=tk.LEFT)
        self._pc_filter = ttk.Combobox(filter_frame, values=["(すべて)"], width=15, state="readonly")
        self._pc_filter.set("(すべて)")
        self._pc_filter.pack(side=tk.LEFT, padx=(2, 10))
        self._pc_filter.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        self._unread_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_frame, text="未読のみ", variable=self._unread_only, command=self._apply_filter
        ).pack(side=tk.LEFT)

        # Treeview
        tree_frame = ttk.Frame(self._root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self._tree = ttk.Treeview(tree_frame, columns=COLUMNS, show="headings", selectmode="browse")
        for col in COLUMNS:
            self._tree.heading(col, text=COLUMN_LABELS[col])
            self._tree.column(col, width=COLUMN_WIDTHS[col], minwidth=40)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<ButtonRelease-1>", self._on_row_click)

        # Tag for unread rows
        self._tree.tag_configure("unread", font=("", 10, "bold"))
        self._tree.tag_configure("read", foreground="gray")

        # Status bar
        self._status_var = tk.StringVar(value="起動中...")
        ttk.Label(self._root, textvariable=self._status_var).pack(fill=tk.X, padx=5, pady=(0, 5))

    def _start_polling(self) -> None:
        """Start a background thread that polls the relay server."""
        def poll_loop():
            while True:
                try:
                    notifications = self._client.get_notifications()
                    self._data_queue.put(notifications)
                except Exception:
                    logger.exception("Polling error")
                threading.Event().wait(self._poll_interval)

        thread = threading.Thread(target=poll_loop, daemon=True)
        thread.start()

    def _process_queue(self) -> None:
        """Process data from the polling thread on the main (UI) thread."""
        try:
            while True:
                notifications = self._data_queue.get_nowait()
                self._update_data(notifications)
        except queue.Empty:
            pass
        self._root.after(500, self._process_queue)

    def _update_data(self, notifications: list[Notification]) -> None:
        new_ids = {n.id for n in notifications}
        new_unread = [n for n in notifications if n.id not in self._known_ids and n.status == "unread"]

        self._all_notifications = notifications
        self._known_ids = new_ids

        # Notify for new unreads
        if new_unread:
            self._fire_notifications(new_unread)

        # Update PC filter dropdown
        pc_names = sorted({n.pc_name for n in notifications})
        self._pc_filter["values"] = ["(すべて)"] + pc_names

        self._apply_filter()

        unread_count = sum(1 for n in notifications if n.status == "unread")
        self._status_var.set(
            f"通知: {len(notifications)}件 (未読: {unread_count}件) — "
            f"最終更新: {datetime.now().strftime('%H:%M:%S')}"
        )

    def _apply_filter(self) -> None:
        """Re-render the Treeview based on current filters."""
        self._tree.delete(*self._tree.get_children())

        pc = self._pc_filter.get()
        unread_only = self._unread_only.get()

        for n in self._all_notifications:
            if pc != "(すべて)" and n.pc_name != pc:
                continue
            if unread_only and n.status != "unread":
                continue

            # Format timestamp for display
            try:
                dt = datetime.fromisoformat(n.timestamp.replace("Z", "+00:00"))
                ts_display = dt.astimezone().strftime("%m/%d %H:%M:%S")
            except Exception:
                ts_display = n.timestamp

            status_display = "未読" if n.status == "unread" else "既読"
            tag = "unread" if n.status == "unread" else "read"

            self._tree.insert(
                "",
                tk.END,
                iid=n.id,
                values=(n.pc_name, n.sender, n.channel, n.message, ts_display, status_display),
                tags=(tag,),
            )

    def _on_row_click(self, event) -> None:
        """Mark the clicked notification as read."""
        selected = self._tree.selection()
        if not selected:
            return
        notif_id = selected[0]

        # Find the notification
        notif = next((n for n in self._all_notifications if n.id == notif_id), None)
        if notif and notif.status == "unread":
            # Mark read in background
            threading.Thread(
                target=self._client.mark_read, args=(notif_id,), daemon=True
            ).start()
            notif.status = "read"
            self._apply_filter()

    def _fire_notifications(self, new_unreads: list[Notification]) -> None:
        """Show toast and play sound for new notifications."""
        if self._notify_sound:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

        if self._notify_toast:
            try:
                from win11toast import notify
                for n in new_unreads[:3]:  # Limit to 3 toasts at once
                    notify(
                        title=f"Teams: {n.sender} ({n.pc_name})",
                        body=f"{n.channel}\n{n.message}" if n.channel else n.message,
                        app_id="Teams Mention Collector",
                    )
            except Exception:
                logger.debug("Toast notification failed", exc_info=True)

    def _handle_close(self) -> None:
        """Minimize to tray instead of closing."""
        self._root.withdraw()
        if self._on_close:
            self._on_close()

    def show(self) -> None:
        self._root.deiconify()
        self._root.lift()

    def quit(self) -> None:
        self._root.quit()

    def run(self) -> None:
        self._root.mainloop()

    @property
    def has_unread(self) -> bool:
        return any(n.status == "unread" for n in self._all_notifications)
