#!/usr/bin/env python3
"""
Auto Capture - 自动收集键盘和鼠标行为的工具
"""

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pynput import keyboard, mouse
from PIL import Image, ImageDraw
import mss

# macOS-only
if sys.platform == "darwin":
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
        """处理应用激活通知 - 所有通知都记录到日志"""
        app_name, window_title, bundle_id = self._get_active_window_info()

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

        # 注册通知观察者（显式指定 mainQueue，确保回调在主线程 RunLoop 上派发）
        nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        self._observer = nc.addObserverForName_object_queue_usingBlock_(
            AppKit.NSWorkspaceDidActivateApplicationNotification,
            None,
            AppKit.NSOperationQueue.mainQueue(),
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

    # 当前窗口状态
    _current_app_name: str = ""
    _current_window_title: str = ""
    _current_bundle_id: str = ""

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

    def __init__(self, storage_dir: Path, on_event=None):
        self.storage_dir = storage_dir
        self.current_line = ""
        self.last_key_time: Optional[float] = None
        self.line_start_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._on_event = on_event

        # 窗口状态
        self._current_app_name = ""
        self._current_window_title = ""
        self._current_bundle_id = ""
        self._last_flush_app = ""  # 上次 flush 时的应用名（用于键盘聚类分割）
        self._last_header_app = ""  # 上次写入窗口头的应用名（用于日志分组）

    def _get_log_file(self) -> Path:
        """获取当日日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{today}.log"

    def _ensure_app_header(self):
        """确保当前应用有窗口头（分组用）

        如果当前应用不同于上次写入窗口头的应用，则写入新的窗口头。
        窗口头用三个换行符分隔，形成应用分组。
        """
        if self._current_app_name and self._current_app_name != self._last_header_app:
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

            # 写入窗口分隔块（三个换行分隔）
            if self._current_window_title:
                header = f"\n\n\n[{timestamp}] {self._current_app_name} | {self._current_window_title} ({self._current_bundle_id})\n"
            else:
                header = f"\n\n\n[{timestamp}] {self._current_app_name} ({self._current_bundle_id})\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(header)

            self._last_header_app = self._current_app_name

    def _flush_line(self):
        """将当前行写入文件"""
        if self.current_line and self.line_start_time:
            # 确保已有窗口头（分组）
            self._ensure_app_header()

            # 只用时间戳，不重复应用名（已在窗口头显示）
            timestamp = self.line_start_time.strftime("%H:%M:%S")
            line = f"[{timestamp}] ⌨️ {self.current_line}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("keyboard", {"line": self.current_line, "app": self._current_app_name})

            self.current_line = ""
            self.line_start_time = None

    def _get_active_window_info(self) -> tuple[str, str, str]:
        """获取当前活跃窗口信息"""
        try:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()

            app_name = active_app.localizedName() or ""
            bundle_id = active_app.bundleIdentifier() or ""
            pid = active_app.processIdentifier()

            # 获取窗口标题
            window_title = self._get_window_title(pid)

            return app_name, window_title, bundle_id
        except Exception:
            return "", "", ""

    def _get_window_title(self, pid: int) -> str:
        """通过 Accessibility API 获取窗口标题"""
        try:
            app_ref = Quartz.AXUIElementCreateApplication(pid)

            # 尝试获取焦点窗口
            error, focused_window = Quartz.AXUIElementCopyAttributeValue(
                app_ref, Quartz.kAXFocusedWindowAttribute, None
            )
            if error == 0 and focused_window:
                error, title = Quartz.AXUIElementCopyAttributeValue(
                    focused_window, Quartz.kAXTitleAttribute, None
                )
                if error == 0 and title:
                    return str(title)

            # 备选：获取第一个窗口
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

    def _update_window_state(self, window_info=None):
        """更新当前窗口状态（不写日志）

        Args:
            window_info: 可选的 (app_name, window_title, bundle_id)。
                         如果提供则使用该值，否则轮询 frontmostApplication()。
        """
        if window_info:
            app_name, window_title, bundle_id = window_info
        else:
            app_name, window_title, bundle_id = self._get_active_window_info()

        self._current_app_name = app_name
        self._current_window_title = window_title
        self._current_bundle_id = bundle_id

    def log_screenshot(self, filename: str, action: str, x: int, y: int,
                       x2: Optional[int] = None, y2: Optional[int] = None,
                       window_info=None):
        """记录截图到日志

        Args:
            window_info: 点击时确定的 (app_name, window_title, bundle_id)。
                         由 MouseCapture 在点击发生时通过坐标查询获得。
        """
        with self._lock:
            # 更新窗口状态
            if window_info:
                self._update_window_state(window_info)

            # 确保已有窗口头（分组）
            self._ensure_app_header()

            now = datetime.now()
            # 只用时间戳，不重复应用名（已在窗口头显示）
            timestamp = now.strftime("%H:%M:%S")

            if action == "drag" and x2 is not None:
                line = f"[{timestamp}] 📷 {action} ({x},{y})->({x2},{y2}) {filename}\n"
            else:
                line = f"[{timestamp}] 📷 {action} ({x},{y}) {filename}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("screenshot", {"filename": filename, "action": action, "x": x, "y": y})

    def on_window_activated(self, app_name: str, window_title: str, bundle_id: str):
        """窗口激活通知回调 - 更新状态并在应用切换时写入窗口头

        由 WindowTracker 在收到 NSWorkspaceDidActivateApplicationNotification 时调用。
        只在应用真正切换时写入窗口头，避免重复。
        """
        with self._lock:
            # 检查是否真的切换了应用
            if app_name != self._current_app_name:
                # 刷新之前应用的键盘输入
                self._flush_line()

            # 更新窗口状态
            self._current_app_name = app_name
            self._current_window_title = window_title
            self._current_bundle_id = bundle_id

            # 确保窗口头（如果是新应用会写入窗口头）
            self._ensure_app_header()

            if self._on_event:
                self._on_event("window", {"app": app_name, "title": window_title, "bundle_id": bundle_id})

    def log_mic_event(self, event_type: str, detail: str, timestamp: str = None):
        """记录麦克风事件到日志

        注意：麦克风事件归属于实际占用麦克风的应用（已包含在 detail 参数中），
        而非当前前台窗口。
        """
        with self._lock:
            if timestamp is None:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if event_type == "mic_stop":
                line = f"[{timestamp}] 🎤 {event_type} {detail}\n"
            else:
                line = f"[{timestamp}] 🎤 {event_type} | {detail}\n"

            log_file = self._get_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)

            if self._on_event:
                self._on_event("mic", {"event_type": event_type, "detail": detail})

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
            # 更新当前窗口状态
            self._update_window_state()

            # 窗口变化或超过聚类间隔 → 先刷新当前行
            window_changed = (self._current_app_name != self._last_flush_app)
            time_gap = self.last_key_time and (now - self.last_key_time) > self.CLUSTER_INTERVAL

            if window_changed or time_gap:
                self._flush_line()

            # 如果是新行，记录开始时间
            if not self.line_start_time:
                self.line_start_time = now_dt
                self._last_flush_app = self._current_app_name

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

    def __init__(self, storage_dir: Path, key_logger: Optional['KeyLogger'] = None):
        self.storage_dir = storage_dir
        self.key_logger = key_logger
        self._lock = threading.Lock()

        # 按下状态记录
        self._press_time: float = 0
        self._press_x: int = 0
        self._press_y: int = 0
        self._press_button: str = ""

        # 上次点击记录（用于双击检测）
        self._last_click_time: float = 0
        self._last_click_x: int = 0
        self._last_click_y: int = 0

        # 延迟单击（等待双击判定窗口过期后再触发，避免双击产生冗余截图）
        self._pending_click_timer: Optional[threading.Timer] = None
        self._pending_click_args: Optional[tuple] = None  # (button_name, x, y, window_info)

        # 节流
        self._last_capture_time: float = 0

        # 活跃线程追踪
        self._active_threads: list[threading.Thread] = []

    def _get_day_dir(self) -> Path:
        """获取当日目录"""
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        """通过点击坐标确定被点击的窗口 (app_name, window_title, bundle_id)

        使用 CGWindowListCopyWindowInfo 按 z-order 遍历所有窗口，
        找到包含点击坐标的最上层窗口。这样即使 macOS 尚未完成窗口切换，
        也能正确识别被点击的窗口。
        """
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            if not window_list:
                return "Unknown", "", "Unknown"

            for window in window_list:
                bounds = window.get(Quartz.kCGWindowBounds)
                if not bounds:
                    continue

                wx = int(bounds.get("X", 0))
                wy = int(bounds.get("Y", 0))
                ww = int(bounds.get("Width", 0))
                wh = int(bounds.get("Height", 0))

                # 跳过非普通窗口层级（layer 0 = 正常窗口，高层级 = 系统覆盖层/光标等）
                layer = window.get(Quartz.kCGWindowLayer, -1)
                if layer != 0:
                    continue

                # 跳过太小的窗口（菜单、tooltip 等）
                if ww < 50 or wh < 50:
                    continue

                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    pid = window.get(Quartz.kCGWindowOwnerPID, 0)
                    owner_name = window.get(Quartz.kCGWindowOwnerName, "Unknown")
                    window_name = window.get(Quartz.kCGWindowName, "") or ""

                    # 通过 PID 获取 bundle_id
                    bundle_id = "Unknown"
                    try:
                        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                        if app:
                            bundle_id = app.bundleIdentifier() or "Unknown"
                            owner_name = app.localizedName() or owner_name
                    except Exception:
                        pass

                    return owner_name, window_name, bundle_id

            # 没有命中 layer=0 的窗口，回退到 frontmostApplication
            try:
                workspace = AppKit.NSWorkspace.sharedWorkspace()
                active_app = workspace.frontmostApplication()
                app_name = active_app.localizedName() or "Unknown"
                bundle_id = active_app.bundleIdentifier() or "Unknown"
                return app_name, "", bundle_id
            except Exception:
                pass

        except Exception:
            pass
        return "Unknown", "", "Unknown"

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
                          x2: Optional[int] = None, y2: Optional[int] = None,
                          window_info=None):
        """截图并保存"""
        try:
            # 获取活跃窗口边界（在截图前获取）
            window_bounds = self._get_active_window_bounds()

            # 每个线程创建独立的 mss 实例（mss 非线程安全）
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                screenshot = sct.grab(monitor)
                offset_x, offset_y = monitor["left"], monitor["top"]

            # 转换为 PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
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

            # 记录到日志
            if self.key_logger:
                self.key_logger.log_screenshot(filename, action, x1, y1, x2, y2,
                                               window_info=window_info)

            print(f"[Screenshot] {filename}")

        except Exception as e:
            print(f"[Error] Screenshot failed: {e}")

    def _distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """计算两点距离"""
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def _cancel_pending_click(self):
        """取消挂起的单击（调用者需持有 self._lock）"""
        if self._pending_click_timer:
            self._pending_click_timer.cancel()
            self._pending_click_timer = None
            self._pending_click_args = None

    def _fire_pending_click(self):
        """触发挂起的单击截图（由 Timer 线程调用）"""
        with self._lock:
            args = self._pending_click_args
            self._pending_click_timer = None
            self._pending_click_args = None
        if args:
            button_name, x, y, window_info = args
            self._start_capture_thread("click", button_name, x, y,
                                       window_info=window_info)

    def _start_capture_thread(self, action, button_name, x1, y1,
                              x2=None, y2=None, window_info=None):
        """启动截图线程"""
        if x2 is not None:
            thread = threading.Thread(
                target=self._capture_and_save,
                args=(action, button_name, x1, y1, x2, y2),
                kwargs={"window_info": window_info}
            )
        else:
            thread = threading.Thread(
                target=self._capture_and_save,
                args=(action, button_name, x1, y1),
                kwargs={"window_info": window_info}
            )
        thread.start()
        with self._lock:
            self._active_threads.append(thread)
            self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def wait_for_pending(self, timeout: float = 2.0):
        """等待所有截图线程完成"""
        # 先触发挂起的单击
        args = None
        with self._lock:
            if self._pending_click_timer:
                self._pending_click_timer.cancel()
                args = self._pending_click_args
                self._pending_click_timer = None
                self._pending_click_args = None
        if args:
            button_name, x, y, window_info = args
            self._start_capture_thread("click", button_name, x, y,
                                       window_info=window_info)
        for thread in self._active_threads:
            thread.join(timeout=timeout)

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

            # 在点击发生时立即确定被点击的窗口（避免截图线程中延迟查询导致窗口归属错误）
            window_info = self._get_window_at_point(x, y)

            # 计算拖拽距离
            drag_distance = self._distance(press_x, press_y, x, y)

            if drag_distance > self.DRAG_THRESHOLD:
                # 拖拽 - 取消挂起的单击，使用按下时的坐标确定窗口
                with self._lock:
                    self._cancel_pending_click()
                window_info = self._get_window_at_point(press_x, press_y)
                self._start_capture_thread("drag", button_name,
                                           press_x, press_y, x, y,
                                           window_info=window_info)
            else:
                # 点击 - 检查是否双击
                with self._lock:
                    time_since_last = now - self._last_click_time
                    dist_from_last = self._distance(
                        x, y, self._last_click_x, self._last_click_y
                    )

                    if (time_since_last < self.DOUBLE_CLICK_INTERVAL and
                        dist_from_last < self.DOUBLE_CLICK_DISTANCE):
                        # 双击 - 取消挂起的单击截图，只拍双击
                        self._cancel_pending_click()
                        self._last_click_time = 0
                        is_dblclick = True
                    else:
                        self._last_click_time = now
                        self._last_click_x = x
                        self._last_click_y = y
                        is_dblclick = False

                if is_dblclick:
                    self._start_capture_thread("dblclick", button_name, x, y,
                                               window_info=window_info)
                else:
                    # 单击 - 延迟触发，等待可能的双击
                    with self._lock:
                        self._cancel_pending_click()
                        self._pending_click_args = (button_name, x, y, window_info)
                        delay_s = self.DOUBLE_CLICK_INTERVAL / 1000.0
                        self._pending_click_timer = threading.Timer(
                            delay_s, self._fire_pending_click
                        )
                        self._pending_click_timer.daemon = True
                        self._pending_click_timer.start()


class AutoCapture:
    """主控制器"""

    def __init__(self, storage_dir: Optional[str] = None, mic_enabled: bool = False,
                 mic_config: Optional[dict] = None, on_event=None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).expanduser()
        else:
            self.storage_dir = Path.home() / "opencapture"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.key_logger = KeyLogger(self.storage_dir, on_event=on_event)
        self.mouse_capture = MouseCapture(self.storage_dir, self.key_logger)
        self.window_tracker = WindowTracker(self.key_logger.on_window_activated)
        self.mic_capture = None

        if mic_enabled:
            try:
                from opencapture.mic_capture import MicrophoneCapture
                cfg = mic_config or {}
                self.mic_capture = MicrophoneCapture(
                    storage_dir=self.storage_dir,
                    key_logger=self.key_logger,
                    sample_rate=cfg.get("mic_sample_rate", 16000),
                    channels=cfg.get("mic_channels", 1),
                    min_duration_ms=cfg.get("mic_min_duration_ms", cfg.get("mic_start_debounce_ms", 500)),
                    stop_debounce_ms=cfg.get("mic_stop_debounce_ms", 300),
                )
            except ImportError as e:
                print(f"[AutoCapture] Mic capture unavailable (missing dependency): {e}")
            except Exception as e:
                print(f"[AutoCapture] Mic capture init failed: {e}")

        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._running = False

    def start(self):
        """启动监听"""
        print(f"[AutoCapture] Starting... Storage: {self.storage_dir}")
        print("[AutoCapture] Press Ctrl+C to stop")

        self._running = True

        # 启动窗口切换监听
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

        # 启动麦克风监听
        if self.mic_capture:
            self.mic_capture.start()

        print("[AutoCapture] Running...")

    def stop(self):
        """停止监听"""
        print("\n[AutoCapture] Stopping...")

        self._running = False

        # 先停止监听器，防止新事件进入
        self.window_tracker.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

        # 停止麦克风录制（在刷新日志之前）
        if self.mic_capture:
            self.mic_capture.stop()

        # 等待截图线程完成
        self.mouse_capture.wait_for_pending()

        # 刷新键盘日志
        self.key_logger.flush()

        print("[AutoCapture] Stopped.")

    @staticmethod
    def _check_accessibility(prompt=False):
        """Check macOS Accessibility permission.

        Args:
            prompt: If True, trigger macOS native permission dialog.
        Returns True if granted.
        """
        import sys
        if sys.platform != 'darwin':
            return True
        try:
            import ctypes
            lib = ctypes.cdll.LoadLibrary(
                '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
            )
            if prompt:
                # AXIsProcessTrustedWithOptions triggers the macOS permission dialog
                cf = ctypes.cdll.LoadLibrary(
                    '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
                )
                kAXTrustedCheckOptionPrompt = ctypes.c_void_p.in_dll(
                    lib, 'kAXTrustedCheckOptionPrompt'
                )
                kCFBooleanTrue = ctypes.c_void_p.in_dll(cf, 'kCFBooleanTrue')

                cf.CFDictionaryCreate.restype = ctypes.c_void_p
                cf.CFDictionaryCreate.argtypes = [
                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                    ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                    ctypes.c_void_p, ctypes.c_void_p,
                ]
                keys = (ctypes.c_void_p * 1)(kAXTrustedCheckOptionPrompt)
                values = (ctypes.c_void_p * 1)(kCFBooleanTrue)
                options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)

                lib.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
                lib.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
                result = lib.AXIsProcessTrustedWithOptions(options)
                cf.CFRelease.argtypes = [ctypes.c_void_p]
                cf.CFRelease(options)
                return result
            else:
                lib.AXIsProcessTrusted.restype = ctypes.c_bool
                return lib.AXIsProcessTrusted()
        except Exception:
            return True  # Can't check, assume OK

    def run(self):
        """运行（阻塞）"""
        if sys.platform != "darwin":
            print("[AutoCapture] Capture is currently macOS-only.")
            print("Analysis works on all platforms: opencapture --analyze today")
            sys.exit(1)

        if not self._check_accessibility(prompt=False):
            print("[AutoCapture] Requesting Accessibility permission...")
            self._check_accessibility(prompt=True)
            print("[AutoCapture] Grant access to OpenCapture in System Settings → Accessibility")

            # Interactive: 5 min wait; background service: 2 min wait
            max_wait = 100 if sys.stdout.isatty() else 40
            print("[AutoCapture] Waiting for permission...")

            granted = False
            for i in range(max_wait):
                time.sleep(3)
                if self._check_accessibility(prompt=False):
                    granted = True
                    break
                if i % 10 == 9:
                    print("[AutoCapture] Still waiting for permission...")

            if not granted:
                print("[AutoCapture] Permission not granted.")
                sys.exit(1)
            print("[AutoCapture] Accessibility permission granted!")

        self.start()

        try:
            # 用 NSRunLoop 替代 time.sleep，确保 NSWorkspace 通知能正常派发
            run_loop = AppKit.NSRunLoop.currentRunLoop()
            while self._running:
                # 运转 RunLoop 0.1 秒，处理待派发的通知/事件
                until = AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.1)
                run_loop.runUntilDate_(until)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto Capture - 键鼠行为收集工具")
    parser.add_argument(
        "-d", "--dir",
        help="存储目录 (默认: ~/opencapture)",
        default=None
    )

    args = parser.parse_args()

    capture = AutoCapture(storage_dir=args.dir)
    capture.run()


if __name__ == "__main__":
    main()
