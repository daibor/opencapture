"""macOS platform backend — AppKit, Quartz, Core Audio."""

import threading
from typing import Callable, Optional

import AppKit
import Quartz

from ._base import PlatformBackend


class MacOSBackend(PlatformBackend):

    def __init__(self):
        self._observer = None  # NSNotification observer
        self._observer_callback = None

    # ── Window information ───────────────────────────────────

    def get_active_window_info(self) -> tuple[str, str, str]:
        try:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            app_name = active_app.localizedName() or "Unknown"
            bundle_id = active_app.bundleIdentifier() or "Unknown"
            pid = active_app.processIdentifier()
            window_title = self._get_window_title(pid)
            return app_name, window_title, bundle_id
        except Exception:
            return "Unknown", "", "Unknown"

    def _get_window_title(self, pid: int) -> str:
        try:
            app_ref = Quartz.AXUIElementCreateApplication(pid)
            error, focused_window = Quartz.AXUIElementCopyAttributeValue(
                app_ref, Quartz.kAXFocusedWindowAttribute, None
            )
            if error == 0 and focused_window:
                error, title = Quartz.AXUIElementCopyAttributeValue(
                    focused_window, Quartz.kAXTitleAttribute, None
                )
                if error == 0 and title:
                    return str(title)
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

    def get_window_at_point(self, x: int, y: int) -> tuple[str, str, str]:
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
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

                layer = window.get(Quartz.kCGWindowLayer, -1)
                if layer != 0:
                    continue
                if ww < 50 or wh < 50:
                    continue

                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    pid = window.get(Quartz.kCGWindowOwnerPID, 0)
                    owner_name = window.get(Quartz.kCGWindowOwnerName, "Unknown")
                    window_name = window.get(Quartz.kCGWindowName, "") or ""

                    bundle_id = "Unknown"
                    try:
                        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                        if app:
                            bundle_id = app.bundleIdentifier() or "Unknown"
                            owner_name = app.localizedName() or owner_name
                    except Exception:
                        pass

                    return owner_name, window_name, bundle_id

            # Fallback to frontmost app
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

    def get_active_window_bounds(self) -> Optional[tuple[int, int, int, int]]:
        try:
            workspace = AppKit.NSWorkspace.sharedWorkspace()
            active_app = workspace.frontmostApplication()
            pid = active_app.processIdentifier()

            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )

            for window in window_list:
                if window.get(Quartz.kCGWindowOwnerPID) == pid:
                    bounds = window.get(Quartz.kCGWindowBounds)
                    if not bounds:
                        continue
                    width = int(bounds.get("Width", 0))
                    height = int(bounds.get("Height", 0))
                    if width < 100 or height < 100:
                        continue
                    x = int(bounds.get("X", 0))
                    y = int(bounds.get("Y", 0))
                    return (x, y, width, height)
            return None
        except Exception:
            return None

    # ── Window observation ───────────────────────────────────

    def start_window_observer(self, callback: Callable[[str, str, str], None]):
        self._observer_callback = callback
        nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        self._observer = nc.addObserverForName_object_queue_usingBlock_(
            AppKit.NSWorkspaceDidActivateApplicationNotification,
            None,
            AppKit.NSOperationQueue.mainQueue(),
            lambda note: self._on_activation(note),
        )

    def _on_activation(self, notification):
        if self._observer_callback:
            info = self.get_active_window_info()
            self._observer_callback(*info)

    def stop_window_observer(self):
        if self._observer:
            nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
            nc.removeObserver_(self._observer)
            self._observer = None
        self._observer_callback = None

    # ── Accessibility / permissions ──────────────────────────

    def check_accessibility(self, prompt: bool = False) -> bool:
        try:
            import ctypes as _ct
            lib = _ct.cdll.LoadLibrary(
                '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
            )
            if prompt:
                cf = _ct.cdll.LoadLibrary(
                    '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
                )
                kAXTrustedCheckOptionPrompt = _ct.c_void_p.in_dll(
                    lib, 'kAXTrustedCheckOptionPrompt'
                )
                kCFBooleanTrue = _ct.c_void_p.in_dll(cf, 'kCFBooleanTrue')

                cf.CFDictionaryCreate.restype = _ct.c_void_p
                cf.CFDictionaryCreate.argtypes = [
                    _ct.c_void_p, _ct.POINTER(_ct.c_void_p),
                    _ct.POINTER(_ct.c_void_p), _ct.c_long,
                    _ct.c_void_p, _ct.c_void_p,
                ]
                keys = (_ct.c_void_p * 1)(kAXTrustedCheckOptionPrompt)
                values = (_ct.c_void_p * 1)(kCFBooleanTrue)
                options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)

                lib.AXIsProcessTrustedWithOptions.restype = _ct.c_bool
                lib.AXIsProcessTrustedWithOptions.argtypes = [_ct.c_void_p]
                result = lib.AXIsProcessTrustedWithOptions(options)
                cf.CFRelease.argtypes = [_ct.c_void_p]
                cf.CFRelease(options)
                return result
            else:
                lib.AXIsProcessTrusted.restype = _ct.c_bool
                return lib.AXIsProcessTrusted()
        except Exception:
            return True

    # ── Event loop ───────────────────────────────────────────

    def run_event_loop(self, should_run: Callable[[], bool]):
        run_loop = AppKit.NSRunLoop.currentRunLoop()
        while should_run():
            until = AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.1)
            run_loop.runUntilDate_(until)
