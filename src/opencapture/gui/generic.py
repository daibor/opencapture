"""
Cross-platform backend — pystray system tray + tkinter log window.

Works on Windows, Linux, and macOS (fallback). Uses pystray for the
system tray icon/menu and tkinter for the log viewer and dialogs.
"""

import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from .base import TrayAppBase


def _create_icon_image(recording: bool = False) -> Image.Image:
    """Generate a simple tray icon (circle on transparent background)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (220, 50, 50, 255) if recording else (100, 100, 100, 255)
    margin = 8
    draw.ellipse([margin, margin, size - margin, size - margin], fill=color)
    return img


class LogWindow:
    """Tkinter-based log viewer that tails the daily log file."""

    def __init__(self, root: tk.Tk, log_path_fn):
        self._root = root
        self._log_path_fn = log_path_fn
        self._window = None
        self._text = None
        self._file_offset = 0
        self._poll_id = None

    def show(self):
        if self._window is not None and self._window.winfo_exists():
            self._window.lift()
            self._window.focus_force()
            return

        self._window = tk.Toplevel(self._root)
        self._window.title("OpenCapture Log")
        self._window.geometry("700x500")
        self._window.minsize(400, 300)
        self._window.protocol("WM_DELETE_WINDOW", self.hide)

        # Dark theme text area
        self._text = scrolledtext.ScrolledText(
            self._window,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            state=tk.DISABLED,
        )
        self._text.pack(fill=tk.BOTH, expand=True)

        self._file_offset = 0
        self._load_existing()
        self._start_polling()

    def hide(self):
        self._stop_polling()
        if self._window is not None and self._window.winfo_exists():
            self._window.destroy()
        self._window = None
        self._text = None

    def _load_existing(self):
        log_path = self._log_path_fn()
        if not log_path.exists():
            self._file_offset = 0
            return
        try:
            data = log_path.read_bytes()
            content = data.decode("utf-8", errors="replace")
            self._text.configure(state=tk.NORMAL)
            self._text.insert(tk.END, content)
            self._text.see(tk.END)
            self._text.configure(state=tk.DISABLED)
            self._file_offset = len(data)
        except Exception:
            self._file_offset = 0

    def _poll(self):
        if self._text is None:
            self._poll_id = None
            return
        log_path = self._log_path_fn()
        if log_path.exists():
            try:
                size = log_path.stat().st_size
                if size > self._file_offset:
                    with open(log_path, "rb") as f:
                        f.seek(self._file_offset)
                        new_data = f.read()
                    self._file_offset += len(new_data)
                    new_text = new_data.decode("utf-8", errors="replace")
                    self._text.configure(state=tk.NORMAL)
                    self._text.insert(tk.END, new_text)
                    self._text.see(tk.END)
                    self._text.configure(state=tk.DISABLED)
            except Exception:
                pass
        self._poll_id = self._root.after(500, self._poll)

    def _start_polling(self):
        if self._poll_id is None:
            self._poll_id = self._root.after(500, self._poll)

    def _stop_polling(self):
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None


class GenericTrayApp(TrayAppBase):
    """Cross-platform system tray app using pystray + tkinter."""

    def __init__(self, config):
        super().__init__(config)
        self._root = None
        self._icon = None
        self._log_window = None
        self._recording = False
        self._analyzing = False
        self._status_poll_id = None

    def run(self):
        # tkinter on main thread
        self._root = tk.Tk()
        self._root.withdraw()  # hidden root window
        self._root.title("OpenCapture")

        self._log_window = LogWindow(self._root, self.get_log_path)

        # Start analysis engine
        self.analysis_engine.start()

        # Start pystray in a background thread
        self._icon = pystray.Icon(
            "OpenCapture",
            icon=_create_icon_image(False),
            title="OpenCapture",
            menu=self._build_menu(),
        )
        icon_thread = threading.Thread(target=self._icon.run, daemon=True)
        icon_thread.start()

        # Periodic status refresh
        self._schedule_status_refresh()

        # tkinter mainloop (blocks)
        self._root.protocol("WM_DELETE_WINDOW", self._do_quit)
        self._root.mainloop()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "Stop Capture" if self._recording else "Start Capture",
                self._on_toggle_capture,
                default=True,
            ),
            pystray.MenuItem("Show Log", self._on_show_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Analyzing..." if self._analyzing else "Analyze Today",
                self._on_analyze,
                enabled=lambda item: not self._analyzing,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: self.get_status_text(),
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _schedule_status_refresh(self):
        if self._icon:
            self._icon.update_menu()
        self._status_poll_id = self._root.after(5000, self._schedule_status_refresh)

    # ── pystray callbacks (run in pystray thread) ───────────

    def _on_toggle_capture(self, icon, item):
        self._root.after(0, self.toggle_capture)

    def _on_show_log(self, icon, item):
        self._root.after(0, self._log_window.show)

    def _on_analyze(self, icon, item):
        self._root.after(0, self.request_analysis)

    def _on_quit(self, icon=None, item=None):
        # Always dispatch to main thread (may be called from pystray thread)
        self._root.after(0, self._do_quit)

    def _do_quit(self):
        self.shutdown()
        if self._status_poll_id is not None:
            self._root.after_cancel(self._status_poll_id)
        if self._log_window:
            self._log_window.hide()
        if self._icon:
            self._icon.stop()
        self._root.quit()

    # ── TrayAppBase abstract implementations ────────────────

    def on_recording_changed(self, recording: bool):
        self._recording = recording
        if self._icon:
            self._icon.icon = _create_icon_image(recording)
            self._icon.update_menu()

    def on_analysis_started(self):
        self._analyzing = True
        if self._icon:
            self._icon.title = "OpenCapture — Analyzing..."
            self._icon.update_menu()

    def on_analysis_complete(self, message: str):
        # Dispatch to main thread for messagebox
        self._root.after(0, self._show_analysis_result, message)

    def _show_analysis_result(self, message: str):
        self._analyzing = False
        if self._icon:
            self._icon.title = "OpenCapture"
            self._icon.update_menu()
        if message.startswith("Error"):
            messagebox.showerror("Analysis Failed", message)
        else:
            messagebox.showinfo("Analysis Complete", message)

    def on_status_update(self, text: str):
        if self._icon:
            self._icon.title = text

    def show_alert(self, title: str, message: str):
        messagebox.showwarning(title, message)

    def refresh_status(self):
        if self._icon:
            self._icon.update_menu()
