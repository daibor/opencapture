#!/usr/bin/env python3
"""
Auto Capture - 自动收集键盘和鼠标行为的工具
"""

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pynput import keyboard, mouse
from PIL import Image, ImageDraw
import mss

# macOS 专用
import AppKit
import Quartz


class WindowTracker:
    """追踪当前活跃窗口"""

    def __init__(self, on_window_change):
        self.on_window_change = on_window_change
        self.current_app_name: Optional[str] = None
        self.current_window_title: Optional[str] = None
        self.current_bundle_id: Optional[str] = None
        self._running = False
        self._observer = None

    def _get_active_window_info(self) -> tuple[str, str, str]:
        """获取当前活跃窗口信息"""
        try:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()

            app_name = active_app.localizedName() or "Unknown"
            bundle_id = active_app.bundleIdentifier() or "Unknown"

            # 获取窗口标题 (通过 Accessibility API)
            window_title = self._get_window_title(active_app.processIdentifier())

            return app_name, window_title, bundle_id
        except Exception as e:
            return "Unknown", "Unknown", "Unknown"

    def _get_window_title(self, pid: int) -> str:
        """通过 Accessibility API 获取窗口标题"""
        try:
            app_ref = Quartz.AXUIElementCreateApplication(pid)

            # 获取焦点窗口
            error, focused_window = Quartz.AXUIElementCopyAttributeValue(
                app_ref, Quartz.kAXFocusedWindowAttribute, None
            )

            if error == 0 and focused_window:
                # 获取窗口标题
                error, title = Quartz.AXUIElementCopyAttributeValue(
                    focused_window, Quartz.kAXTitleAttribute, None
                )
                if error == 0 and title:
                    return str(title)

            return "Unknown"
        except Exception:
            return "Unknown"

    def _handle_app_activation(self, notification):
        """处理应用激活通知"""
        app_name, window_title, bundle_id = self._get_active_window_info()

        # 检查是否变化
        if (app_name != self.current_app_name or
            window_title != self.current_window_title):
            self.current_app_name = app_name
            self.current_window_title = window_title
            self.current_bundle_id = bundle_id

            self.on_window_change(app_name, window_title, bundle_id)

    def start(self):
        """开始监听窗口切换"""
        self._running = True

        # 获取初始窗口信息
        app_name, window_title, bundle_id = self._get_active_window_info()
        self.current_app_name = app_name
        self.current_window_title = window_title
        self.current_bundle_id = bundle_id
        self.on_window_change(app_name, window_title, bundle_id)

        # 注册通知观察者
        nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        self._observer = nc.addObserverForName_object_queue_usingBlock_(
            AppKit.NSWorkspaceDidActivateApplicationNotification,
            None,
            None,
            self._handle_app_activation
        )

    def stop(self):
        """停止监听"""
        self._running = False
        if self._observer:
            nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
            nc.removeObserver_(self._observer)
            self._observer = None


class KeyLogger:
    """键盘记录器，支持时间聚类和窗口聚合"""

    CLUSTER_INTERVAL = 20  # 20秒聚类间隔

    # 特殊键映射
    SPECIAL_KEYS = {
        keyboard.Key.enter: '[Enter]',
        keyboard.Key.tab: '[Tab]',
        keyboard.Key.space: ' ',
        keyboard.Key.backspace: '[Backspace]',
        keyboard.Key.delete: '[Delete]',
        keyboard.Key.esc: '[Esc]',
        keyboard.Key.shift: '[Shift]',
        keyboard.Key.shift_l: '[Shift]',
        keyboard.Key.shift_r: '[Shift]',
        keyboard.Key.ctrl: '[Ctrl]',
        keyboard.Key.ctrl_l: '[Ctrl]',
        keyboard.Key.ctrl_r: '[Ctrl]',
        keyboard.Key.alt: '[Alt]',
        keyboard.Key.alt_l: '[Alt]',
        keyboard.Key.alt_r: '[Alt]',
        keyboard.Key.alt_gr: '[AltGr]',
        keyboard.Key.cmd: '[Cmd]',
        keyboard.Key.cmd_l: '[Cmd]',
        keyboard.Key.cmd_r: '[Cmd]',
        keyboard.Key.caps_lock: '[CapsLock]',
        keyboard.Key.up: '[Up]',
        keyboard.Key.down: '[Down]',
        keyboard.Key.left: '[Left]',
        keyboard.Key.right: '[Right]',
        keyboard.Key.home: '[Home]',
        keyboard.Key.end: '[End]',
        keyboard.Key.page_up: '[PageUp]',
        keyboard.Key.page_down: '[PageDown]',
        keyboard.Key.f1: '[F1]',
        keyboard.Key.f2: '[F2]',
        keyboard.Key.f3: '[F3]',
        keyboard.Key.f4: '[F4]',
        keyboard.Key.f5: '[F5]',
        keyboard.Key.f6: '[F6]',
        keyboard.Key.f7: '[F7]',
        keyboard.Key.f8: '[F8]',
        keyboard.Key.f9: '[F9]',
        keyboard.Key.f10: '[F10]',
        keyboard.Key.f11: '[F11]',
        keyboard.Key.f12: '[F12]',
    }

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.current_line = ""
        self.last_key_time: Optional[float] = None
        self.line_start_time: Optional[datetime] = None
        self._lock = threading.Lock()

    def _get_log_file(self) -> Path:
        """获取当日日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / "keys.log"

    def _flush_line(self):
        """将当前行写入文件"""
        if self.current_line and self.line_start_time:
            timestamp = self.line_start_time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{timestamp}] {self.current_line}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            self.current_line = ""
            self.line_start_time = None

    def on_window_change(self, app_name: str, window_title: str, bundle_id: str):
        """窗口切换时调用"""
        with self._lock:
            # 先刷新当前行
            self._flush_line()

            # 写入窗口分隔块
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

            separator = "=" * 80
            header = f"\n{separator}\n[{timestamp}] {app_name} | {window_title}\n"
            header += f"                      {bundle_id}\n{separator}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(header)

    def on_key_press(self, key):
        """按键事件处理"""
        now = time.time()
        now_dt = datetime.now()

        # 获取按键字符
        if key in self.SPECIAL_KEYS:
            char = self.SPECIAL_KEYS[key]
        elif hasattr(key, 'char') and key.char:
            char = key.char
        else:
            # 未知按键
            char = f'[{key}]'

        with self._lock:
            # 检查是否需要新起一行（超过聚类间隔）
            if self.last_key_time and (now - self.last_key_time) > self.CLUSTER_INTERVAL:
                self._flush_line()

            # 如果是新行，记录开始时间
            if not self.line_start_time:
                self.line_start_time = now_dt

            # 追加字符
            self.current_line += char
            self.last_key_time = now

    def flush(self):
        """强制刷新"""
        with self._lock:
            self._flush_line()


class MouseCapture:
    """鼠标点击截图"""

    THROTTLE_MS = 100  # 节流间隔
    MARKER_SIZE = 24   # 红点直径
    MARKER_COLOR = (255, 0, 0, 255)  # 红色

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.last_capture_time = 0
        self._lock = threading.Lock()
        self._sct = mss.mss()

    def _get_day_dir(self) -> Path:
        """获取当日目录"""
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _capture_screen(self, x: int, y: int, button: str):
        """截图并标记点击位置"""
        try:
            # 截取整个屏幕
            monitor = self._sct.monitors[0]  # 所有显示器
            screenshot = self._sct.grab(monitor)

            # 转换为 PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # 绘制红点
            draw = ImageDraw.Draw(img)
            radius = self.MARKER_SIZE // 2

            # 调整坐标（mss 的坐标可能需要偏移）
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius],
                fill=self.MARKER_COLOR[:3],
                outline=(200, 0, 0)
            )

            # 生成文件名
            now = datetime.now()
            timestamp = now.strftime("%H%M%S")
            ms = now.strftime("%f")[:3]
            filename = f"click_{timestamp}_{ms}_{button}_x{x}_y{y}.png"

            # 保存
            filepath = self._get_day_dir() / filename
            img.save(filepath, "PNG")

            print(f"[Screenshot] {filename}")

        except Exception as e:
            print(f"[Error] Screenshot failed: {e}")

    def on_click(self, x: int, y: int, button, pressed: bool):
        """鼠标点击事件"""
        if not pressed:  # 只处理按下事件
            return

        now = time.time() * 1000  # 转为毫秒

        with self._lock:
            # 节流
            if now - self.last_capture_time < self.THROTTLE_MS:
                return
            self.last_capture_time = now

        # 获取按键类型
        button_name = str(button).split(".")[-1]  # left, right, middle

        # 异步截图
        thread = threading.Thread(
            target=self._capture_screen,
            args=(x, y, button_name)
        )
        thread.daemon = True
        thread.start()


class AutoCapture:
    """主控制器"""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).expanduser()
        else:
            self.storage_dir = Path.home() / "auto-capture"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.key_logger = KeyLogger(self.storage_dir)
        self.mouse_capture = MouseCapture(self.storage_dir)
        self.window_tracker = WindowTracker(self.key_logger.on_window_change)

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._running = False

    def start(self):
        """启动监听"""
        print(f"[AutoCapture] Starting... Storage: {self.storage_dir}")
        print("[AutoCapture] Press Ctrl+C to stop")

        self._running = True

        # 启动窗口追踪
        self.window_tracker.start()

        # 启动键盘监听
        self._keyboard_listener = keyboard.Listener(
            on_press=self.key_logger.on_key_press
        )
        self._keyboard_listener.start()

        # 启动鼠标监听
        self._mouse_listener = mouse.Listener(
            on_click=self.mouse_capture.on_click
        )
        self._mouse_listener.start()

        print("[AutoCapture] Running...")

    def stop(self):
        """停止监听"""
        print("\n[AutoCapture] Stopping...")

        self._running = False

        # 刷新键盘日志
        self.key_logger.flush()

        # 停止监听器
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

        self.window_tracker.stop()

        print("[AutoCapture] Stopped.")

    def run(self):
        """运行（阻塞）"""
        self.start()

        try:
            # 保持运行
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto Capture - 键鼠行为收集工具")
    parser.add_argument(
        "-d", "--dir",
        help="存储目录 (默认: ~/auto-capture)",
        default=None
    )

    args = parser.parse_args()

    capture = AutoCapture(storage_dir=args.dir)
    capture.run()


if __name__ == "__main__":
    main()
