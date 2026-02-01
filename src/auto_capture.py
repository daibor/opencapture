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

            # 备选：尝试获取所有窗口的第一个标题
            error, windows = Quartz.AXUIElementCopyAttributeValue(
                app_ref, Quartz.kAXWindowsAttribute, None
            )
            if error == 0 and windows and len(windows) > 0:
                error, title = Quartz.AXUIElementCopyAttributeValue(
                    windows[0], Quartz.kAXTitleAttribute, None
                )
                if error == 0 and title:
                    return str(title)

            return ""
        except Exception:
            return ""

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

    # 特殊键映射 (使用 macOS 键盘符号)
    SPECIAL_KEYS = {
        keyboard.Key.enter: '↩',
        keyboard.Key.tab: '⇥',
        keyboard.Key.space: ' ',
        keyboard.Key.backspace: '⌫',
        keyboard.Key.delete: '⌦',
        keyboard.Key.esc: '⎋',
        keyboard.Key.shift: '⇧',
        keyboard.Key.shift_l: '⇧',
        keyboard.Key.shift_r: '⇧',
        keyboard.Key.ctrl: '⌃',
        keyboard.Key.ctrl_l: '⌃',
        keyboard.Key.ctrl_r: '⌃',
        keyboard.Key.alt: '⌥',
        keyboard.Key.alt_l: '⌥',
        keyboard.Key.alt_r: '⌥',
        keyboard.Key.alt_gr: '⌥',
        keyboard.Key.cmd: '⌘',
        keyboard.Key.cmd_l: '⌘',
        keyboard.Key.cmd_r: '⌘',
        keyboard.Key.caps_lock: '⇪',
        keyboard.Key.up: '↑',
        keyboard.Key.down: '↓',
        keyboard.Key.left: '←',
        keyboard.Key.right: '→',
        keyboard.Key.home: '↖',
        keyboard.Key.end: '↘',
        keyboard.Key.page_up: '⇞',
        keyboard.Key.page_down: '⇟',
        keyboard.Key.f1: 'F1',
        keyboard.Key.f2: 'F2',
        keyboard.Key.f3: 'F3',
        keyboard.Key.f4: 'F4',
        keyboard.Key.f5: 'F5',
        keyboard.Key.f6: 'F6',
        keyboard.Key.f7: 'F7',
        keyboard.Key.f8: 'F8',
        keyboard.Key.f9: 'F9',
        keyboard.Key.f10: 'F10',
        keyboard.Key.f11: 'F11',
        keyboard.Key.f12: 'F12',
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
            if window_title:
                header = f"\n{separator}\n[{timestamp}] {app_name} | {window_title}\n"
            else:
                header = f"\n{separator}\n[{timestamp}] {app_name}\n"
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
    """鼠标行为截图 - 支持单击、双击、拖拽"""

    THROTTLE_MS = 100           # 节流间隔
    DRAG_THRESHOLD = 10         # 拖拽判定距离阈值
    DOUBLE_CLICK_INTERVAL = 400 # 双击判定时间间隔 (ms)
    DOUBLE_CLICK_DISTANCE = 5   # 双击判定距离阈值
    WINDOW_BORDER_COLOR = (0, 120, 255)  # 蓝色边框
    WINDOW_BORDER_WIDTH = 3     # 边框宽度
    IMAGE_FORMAT = "webp"       # 图片格式
    IMAGE_QUALITY = 80          # 压缩质量 (1-100)

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self._lock = threading.Lock()
        self._sct = mss.mss()

        # 按下状态记录
        self._press_time: float = 0
        self._press_x: int = 0
        self._press_y: int = 0
        self._press_button: str = ""

        # 上次点击记录（用于双击检测）
        self._last_click_time: float = 0
        self._last_click_x: int = 0
        self._last_click_y: int = 0

        # 节流
        self._last_capture_time: float = 0

    def _get_day_dir(self) -> Path:
        """获取当日目录"""
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _get_monitor_offset(self) -> tuple[int, int]:
        """获取拼接图像的坐标偏移"""
        monitor = self._sct.monitors[0]
        return monitor["left"], monitor["top"]

    def _get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        """获取当前活跃窗口的边界 (x, y, width, height)"""
        try:
            # 获取当前活跃应用的 PID
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            pid = active_app.processIdentifier()

            # 获取所有窗口列表
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )

            # 找到属于当前应用的窗口
            for window in window_list:
                if window.get(Quartz.kCGWindowOwnerPID) == pid:
                    # 跳过没有边界的窗口
                    bounds = window.get(Quartz.kCGWindowBounds)
                    if not bounds:
                        continue

                    # 跳过太小的窗口（可能是菜单、tooltip等）
                    width = int(bounds.get("Width", 0))
                    height = int(bounds.get("Height", 0))
                    if width < 100 or height < 100:
                        continue

                    x = int(bounds.get("X", 0))
                    y = int(bounds.get("Y", 0))
                    return (x, y, width, height)

            return None
        except Exception as e:
            print(f"[Warning] Failed to get window bounds: {e}")
            return None

    def _capture_and_save(self, action: str, button: str,
                          x1: int, y1: int,
                          x2: Optional[int] = None, y2: Optional[int] = None):
        """截图并保存"""
        try:
            # 获取活跃窗口边界（在截图前获取）
            window_bounds = self._get_active_window_bounds()

            # 截取所有显示器
            monitor = self._sct.monitors[0]
            screenshot = self._sct.grab(monitor)

            # 转换为 PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # 获取坐标偏移并转换
            offset_x, offset_y = self._get_monitor_offset()
            img_x1 = x1 - offset_x
            img_y1 = y1 - offset_y

            # 绘制活跃窗口蓝色边框
            if window_bounds:
                win_x, win_y, win_w, win_h = window_bounds
                # 转换为图像坐标
                win_img_x = win_x - offset_x
                win_img_y = win_y - offset_y

                draw = ImageDraw.Draw(img)
                draw.rectangle(
                    [win_img_x, win_img_y, win_img_x + win_w, win_img_y + win_h],
                    outline=self.WINDOW_BORDER_COLOR,
                    width=self.WINDOW_BORDER_WIDTH
                )

            # 如果是拖拽，绘制半透明矩形
            if action == "drag" and x2 is not None and y2 is not None:
                img_x2 = x2 - offset_x
                img_y2 = y2 - offset_y

                # 创建半透明覆盖层
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                # 确保坐标顺序正确
                left = min(img_x1, img_x2)
                top = min(img_y1, img_y2)
                right = max(img_x1, img_x2)
                bottom = max(img_y1, img_y2)

                # 绘制半透明灰色矩形
                draw.rectangle(
                    [left, top, right, bottom],
                    fill=(128, 128, 128, 77),  # 30% 透明度
                    outline=(80, 80, 80, 200),
                    width=2
                )

                # 合并图层
                img = img.convert("RGBA")
                img = Image.alpha_composite(img, overlay)
                img = img.convert("RGB")

            # 生成文件名
            now = datetime.now()
            timestamp = now.strftime("%H%M%S")
            ms = now.strftime("%f")[:3]
            ext = self.IMAGE_FORMAT

            if action == "drag":
                filename = f"drag_{timestamp}_{ms}_{button}_x{x1}_y{y1}_to_x{x2}_y{y2}.{ext}"
            elif action == "dblclick":
                filename = f"dblclick_{timestamp}_{ms}_{button}_x{x1}_y{y1}.{ext}"
            else:
                filename = f"click_{timestamp}_{ms}_{button}_x{x1}_y{y1}.{ext}"

            # 保存 (WebP 格式，有损压缩)
            filepath = self._get_day_dir() / filename
            img.save(filepath, "WEBP", quality=self.IMAGE_QUALITY)

            print(f"[Screenshot] {filename}")

        except Exception as e:
            print(f"[Error] Screenshot failed: {e}")

    def _distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """计算两点距离"""
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def on_click(self, x: float, y: float, button, pressed: bool):
        """鼠标事件处理"""
        x, y = int(x), int(y)
        now = time.time() * 1000  # 毫秒
        button_name = str(button).split(".")[-1]

        if pressed:
            # 鼠标按下 - 记录状态
            with self._lock:
                self._press_time = now
                self._press_x = x
                self._press_y = y
                self._press_button = button_name
        else:
            # 鼠标释放 - 判断行为类型
            with self._lock:
                # 节流检查
                if now - self._last_capture_time < self.THROTTLE_MS:
                    return
                self._last_capture_time = now

                press_x = self._press_x
                press_y = self._press_y
                press_button = self._press_button

            # 计算拖拽距离
            drag_distance = self._distance(press_x, press_y, x, y)

            if drag_distance > self.DRAG_THRESHOLD:
                # 拖拽
                action = "drag"
                thread = threading.Thread(
                    target=self._capture_and_save,
                    args=(action, button_name, press_x, press_y, x, y)
                )
            else:
                # 点击 - 检查是否双击
                with self._lock:
                    time_since_last = now - self._last_click_time
                    dist_from_last = self._distance(
                        x, y, self._last_click_x, self._last_click_y
                    )

                    if (time_since_last < self.DOUBLE_CLICK_INTERVAL and
                        dist_from_last < self.DOUBLE_CLICK_DISTANCE):
                        action = "dblclick"
                        # 重置以避免三击变成两次双击
                        self._last_click_time = 0
                    else:
                        action = "click"
                        self._last_click_time = now
                        self._last_click_x = x
                        self._last_click_y = y

                thread = threading.Thread(
                    target=self._capture_and_save,
                    args=(action, button_name, x, y)
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
