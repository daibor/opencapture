"""
macOS backend — native PyObjC menu bar application.

Uses NSStatusBar for the tray icon, NSWindow for the log viewer,
and NSAlert for dialogs. Preserves full native macOS experience.
"""

import objc
import AppKit
import Foundation
from datetime import datetime
from pathlib import Path

from ..engine import CaptureEngine
from .base import TrayAppBase


class LogWindowController(AppKit.NSObject):
    """Controls the log window — tails the actual log file."""

    window = objc.ivar()
    textView = objc.ivar()
    scrollView = objc.ivar()
    _logDir = objc.ivar()
    _fileOffset = objc.ivar()
    _tailTimer = objc.ivar()

    def initWithDataDir_(self, data_dir):
        self = objc.super(LogWindowController, self).init()
        if self is None:
            return None

        self._logDir = str(data_dir)
        self._fileOffset = 0
        self._tailTimer = None

        # Window
        frame = Foundation.NSMakeRect(200, 200, 700, 500)
        style = (
            AppKit.NSTitledWindowMask
            | AppKit.NSClosableWindowMask
            | AppKit.NSResizableWindowMask
            | AppKit.NSMiniaturizableWindowMask
        )
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("OpenCapture Log")
        self.window.setReleasedWhenClosed_(False)
        self.window.setMinSize_(Foundation.NSMakeSize(400, 300))

        # Scroll view
        content_frame = self.window.contentView().bounds()
        self.scrollView = AppKit.NSScrollView.alloc().initWithFrame_(content_frame)
        self.scrollView.setHasVerticalScroller_(True)
        self.scrollView.setHasHorizontalScroller_(False)
        self.scrollView.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )

        # Text view
        text_frame = Foundation.NSMakeRect(
            0, 0, content_frame.size.width, content_frame.size.height
        )
        self.textView = AppKit.NSTextView.alloc().initWithFrame_(text_frame)
        self.textView.setEditable_(False)
        self.textView.setSelectable_(True)
        self.textView.setRichText_(False)
        self.textView.setFont_(
            AppKit.NSFont.fontWithName_size_("Menlo", 12.0)
        )
        # Dark theme
        self.textView.setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.118, 0.118, 0.118, 1.0
            )
        )
        self.textView.setTextColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.831, 0.831, 0.831, 1.0
            )
        )
        self.textView.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        self.textView.textContainer().setWidthTracksTextView_(True)
        self.textView.setMaxSize_(Foundation.NSMakeSize(1e7, 1e7))
        self.textView.setVerticallyResizable_(True)
        self.textView.setHorizontallyResizable_(False)

        self.scrollView.setDocumentView_(self.textView)
        self.window.contentView().addSubview_(self.scrollView)

        self._loadExisting()
        return self

    def _logPath(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return Path(self._logDir) / today / f"{today}.log"

    def _textAttrs(self):
        return {
            AppKit.NSFontAttributeName: AppKit.NSFont.fontWithName_size_("Menlo", 12.0),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.831, 0.831, 0.831, 1.0
            ),
        }

    def _loadExisting(self):
        log_path = self._logPath()
        if not log_path.exists():
            self._fileOffset = 0
            return
        try:
            data = log_path.read_bytes()
            content = data.decode("utf-8", errors="replace")
            attr_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                content, self._textAttrs()
            )
            self.textView.textStorage().setAttributedString_(attr_str)
            self.textView.scrollRangeToVisible_(
                Foundation.NSMakeRange(self.textView.textStorage().length(), 0)
            )
            self._fileOffset = len(data)
        except Exception:
            self._fileOffset = 0

    @objc.typedSelector(b"v@:@")
    def pollLogFile_(self, timer):
        log_path = self._logPath()
        if not log_path.exists():
            return
        try:
            size = log_path.stat().st_size
            if size <= self._fileOffset:
                return
            with open(log_path, "rb") as f:
                f.seek(self._fileOffset)
                new_data = f.read()
            self._fileOffset += len(new_data)
            new_text = new_data.decode("utf-8", errors="replace")
            attr_str = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                new_text, self._textAttrs()
            )
            storage = self.textView.textStorage()
            storage.appendAttributedString_(attr_str)
            self.textView.scrollRangeToVisible_(
                Foundation.NSMakeRange(storage.length(), 0)
            )
        except Exception:
            pass

    def show(self):
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        if self._tailTimer is None:
            self._tailTimer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, "pollLogFile:", None, True
            )

    def hide(self):
        self.window.orderOut_(None)

    def stopTailing(self):
        if self._tailTimer:
            self._tailTimer.invalidate()
            self._tailTimer = None

    def isVisible(self):
        return self.window.isVisible()


class _AppDelegate(AppKit.NSObject):
    """NSApplication delegate — bridges PyObjC events to TrayAppBase."""

    statusItem = objc.ivar()
    logController = objc.ivar()
    _trayApp = objc.ivar()
    _startStopItem = objc.ivar()
    _analyzeItem = objc.ivar()
    _statusLineItem = objc.ivar()
    _statusTimer = objc.ivar()

    def initWithTrayApp_(self, tray_app):
        self = objc.super(_AppDelegate, self).init()
        if self is None:
            return None
        self._trayApp = tray_app
        self.logController = None
        self._startStopItem = None
        self._analyzeItem = None
        self._statusLineItem = None
        self._statusTimer = None
        return self

    def applicationDidFinishLaunching_(self, notification):
        self._setupMenuBar()
        self._trayApp.analysis_engine.start()

        self._statusTimer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0, self, "updateStatusLine:", None, True
        )
        self._updateStatusLine()

        # Deferred permission check at launch
        self.performSelector_withObject_afterDelay_(
            "checkPermissionsOnLaunch:", None, 0.5
        )

    @objc.typedSelector(b"v@:@")
    def checkPermissionsOnLaunch_(self, sender):
        from ..onboarding import (
            is_first_run, mark_setup_complete,
            get_gui_welcome, get_permission_message, get_setup_complete_message,
        )

        first_run = is_first_run()
        if first_run:
            self._trayApp.show_alert("Welcome", get_gui_welcome())

        # Check Accessibility
        if not CaptureEngine.check_accessibility(prompt=False):
            CaptureEngine.check_accessibility(prompt=True)
            title, body = get_permission_message("accessibility")
            self._trayApp.show_alert(title, body)

        # Check Screen Recording
        if not CaptureEngine.check_screen_recording(prompt=False):
            CaptureEngine.check_screen_recording(prompt=True)
            title, body = get_permission_message("screen_recording")
            self._trayApp.show_alert(title, body)

        if first_run:
            mark_setup_complete()
            title, body = get_setup_complete_message()
            self._trayApp.show_alert(title, body)

    def applicationWillTerminate_(self, notification):
        if self._statusTimer:
            self._statusTimer.invalidate()
        if self.logController:
            self.logController.stopTailing()
        self._trayApp.shutdown()

    # ── Menu bar setup ──────────────────────────────────────

    def _setupMenuBar(self):
        statusBar = AppKit.NSStatusBar.systemStatusBar()
        self.statusItem = statusBar.statusItemWithLength_(
            AppKit.NSVariableStatusItemLength
        )
        self.statusItem.setTitle_("OpenCapture")
        self.statusItem.setHighlightMode_(True)

        menu = AppKit.NSMenu.alloc().init()

        self._startStopItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Start Capture", "toggleCapture:", ""
        )
        self._startStopItem.setTarget_(self)
        menu.addItem_(self._startStopItem)

        logItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Show Log", "showLog:", ""
        )
        logItem.setTarget_(self)
        menu.addItem_(logItem)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        self._analyzeItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Analyze Today", "analyzeToday:", ""
        )
        self._analyzeItem.setTarget_(self)
        menu.addItem_(self._analyzeItem)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        self._statusLineItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "No data yet", None, ""
        )
        self._statusLineItem.setEnabled_(False)
        menu.addItem_(self._statusLineItem)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quitItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "quitApp:", "q"
        )
        quitItem.setTarget_(self)
        menu.addItem_(quitItem)

        self.statusItem.setMenu_(menu)

    # ── Actions ─────────────────────────────────────────────

    @objc.typedSelector(b"v@:@")
    def toggleCapture_(self, sender):
        self._trayApp.toggle_capture()

    @objc.typedSelector(b"v@:@")
    def showLog_(self, sender):
        if self.logController is None:
            data_dir = self._trayApp.config.get(
                "capture.output_dir", str(Path.home() / "opencapture")
            )
            self.logController = LogWindowController.alloc().initWithDataDir_(data_dir)
        self.logController.show()

    @objc.typedSelector(b"v@:@")
    def analyzeToday_(self, sender):
        self._trayApp.request_analysis()

    @objc.typedSelector(b"v@:@")
    def handleAnalysisResult_(self, message):
        self._analyzeItem.setEnabled_(True)
        self._statusLineItem.setTitle_(str(message))
        alert = AppKit.NSAlert.alloc().init()
        if str(message).startswith("Error"):
            alert.setMessageText_("Analysis Failed")
        else:
            alert.setMessageText_("Analysis Complete")
        alert.setInformativeText_(str(message))
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    @objc.typedSelector(b"v@:@")
    def updateStatusLine_(self, text):
        self._statusLineItem.setTitle_(str(text))

    @objc.typedSelector(b"v@:@")
    def quitApp_(self, sender):
        self._trayApp.shutdown()
        AppKit.NSApp.terminate_(None)

    @objc.typedSelector(b"v@:@")
    def updateStatusLine_(self, timer):
        self._updateStatusLine()

    def _updateStatusLine(self):
        text = self._trayApp.get_status_text()
        self._statusLineItem.setTitle_(text)


class MacOSTrayApp(TrayAppBase):
    """macOS system tray app using native PyObjC."""

    def __init__(self, config):
        super().__init__(config)
        self._delegate = None

    def run(self):
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._delegate = _AppDelegate.alloc().initWithTrayApp_(self)
        app.setDelegate_(self._delegate)
        app.run()

    def on_recording_changed(self, recording: bool):
        d = self._delegate
        if recording:
            d._startStopItem.setTitle_("Stop Capture")
            d.statusItem.setTitle_("OpenCapture \u25cf")
        else:
            d._startStopItem.setTitle_("Start Capture")
            d.statusItem.setTitle_("OpenCapture")

    def on_analysis_started(self):
        d = self._delegate
        d._analyzeItem.setEnabled_(False)
        d._statusLineItem.setTitle_("Analyzing...")

    def on_analysis_complete(self, message: str):
        self._delegate.performSelectorOnMainThread_withObject_waitUntilDone_(
            "handleAnalysisResult:", message, False
        )

    def show_alert(self, title: str, message: str):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()

    def on_status_update(self, text: str):
        self._delegate.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateStatusLine:", text, False
        )

    def refresh_status(self):
        text = self.get_status_text()
        self._delegate._statusLineItem.setTitle_(text)

    def check_capture_permissions(self) -> bool:
        from .base import TrayAppBase  # noqa: F811 — local re-import for clarity
        from ..onboarding import get_permission_message

        if not CaptureEngine.check_accessibility(prompt=False):
            CaptureEngine.check_accessibility(prompt=True)
            title, body = get_permission_message("accessibility")
            self.show_alert(title, body)
            if not CaptureEngine.check_accessibility(prompt=False):
                return False

        if not CaptureEngine.check_screen_recording(prompt=False):
            CaptureEngine.check_screen_recording(prompt=True)
            title, body = get_permission_message("screen_recording")
            self.show_alert(title, body)

        return True
