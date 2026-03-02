"""
OpenCapture GUI — macOS menu bar application.

Provides a status bar icon with Start/Stop toggle, log window,
and analysis trigger. Uses CaptureEngine + AnalysisEngine from
the engine layer.

Launch:
    opencapture gui          # via CLI subcommand
    opencapture-gui          # standalone entry point
"""

import sys

if sys.platform != "darwin":
    def main():
        """On non-macOS, launch the cross-platform tray GUI."""
        from .app_tray import main as tray_main
        tray_main()
else:
    import objc
    import AppKit
    import Foundation
    from datetime import datetime
    from pathlib import Path

    from .config import Config, init_config
    from .engine import CaptureEngine, AnalysisEngine

    class LogWindowController(AppKit.NSObject):
        """Controls the log window — tails the actual log file."""

        window = objc.ivar()
        textView = objc.ivar()
        scrollView = objc.ivar()
        _logDir = objc.ivar()
        _fileOffset = objc.ivar()  # int: bytes already displayed
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
                    0.118, 0.118, 0.118, 1.0  # #1e1e1e
                )
            )
            self.textView.setTextColor_(
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.831, 0.831, 0.831, 1.0  # #d4d4d4
                )
            )
            self.textView.setAutoresizingMask_(AppKit.NSViewWidthSizable)
            self.textView.textContainer().setWidthTracksTextView_(True)
            self.textView.setMaxSize_(Foundation.NSMakeSize(1e7, 1e7))
            self.textView.setVerticallyResizable_(True)
            self.textView.setHorizontallyResizable_(False)

            self.scrollView.setDocumentView_(self.textView)
            self.window.contentView().addSubview_(self.scrollView)

            # Load existing log content
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
            """Load full log file, set offset to end."""
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
            """Timer callback: read new bytes from log file and append."""
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
            # Start tailing
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


    class AppDelegate(AppKit.NSObject):
        """Main application delegate — owns menu bar, engines, and log window."""

        statusItem = objc.ivar()
        captureEngine = objc.ivar()
        analysisEngine = objc.ivar()
        logController = objc.ivar()
        config = objc.ivar()
        _startStopItem = objc.ivar()
        _analyzeItem = objc.ivar()
        _statusLineItem = objc.ivar()
        _statusTimer = objc.ivar()

        def initWithConfig_(self, config):
            self = objc.super(AppDelegate, self).init()
            if self is None:
                return None
            self.config = config
            self.captureEngine = CaptureEngine(config)
            self.analysisEngine = AnalysisEngine(config)
            self.logController = None
            self._startStopItem = None
            self._analyzeItem = None
            self._statusLineItem = None
            self._statusTimer = None
            return self

        def applicationDidFinishLaunching_(self, notification):
            self._setupMenuBar()
            self.analysisEngine.start()

            # First-run welcome
            from .onboarding import is_first_run, mark_setup_complete, get_gui_welcome
            if is_first_run():
                alert = AppKit.NSAlert.alloc().init()
                alert.setMessageText_("Welcome to OpenCapture")
                alert.setInformativeText_(get_gui_welcome())
                alert.addButtonWithTitle_("Get Started")
                alert.runModal()
                mark_setup_complete()

            # Periodic status update
            self._statusTimer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                5.0, self, "updateStatusLine:", None, True
            )
            self._updateStatusLine()

        def applicationWillTerminate_(self, notification):
            if self._statusTimer:
                self._statusTimer.invalidate()
            if self.logController:
                self.logController.stopTailing()
            if self.captureEngine.is_running:
                self.captureEngine.stop()
            self.analysisEngine.stop()

        # ── Menu bar setup ──────────────────────────────────────

        def _setupMenuBar(self):
            statusBar = AppKit.NSStatusBar.systemStatusBar()
            self.statusItem = statusBar.statusItemWithLength_(
                AppKit.NSVariableStatusItemLength
            )
            self.statusItem.setTitle_("OC")
            self.statusItem.setHighlightMode_(True)

            menu = AppKit.NSMenu.alloc().init()

            # Start / Stop
            self._startStopItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Start Capture", "toggleCapture:", ""
            )
            self._startStopItem.setTarget_(self)
            menu.addItem_(self._startStopItem)

            # Show Log
            logItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Show Log", "showLog:", ""
            )
            logItem.setTarget_(self)
            menu.addItem_(logItem)

            menu.addItem_(AppKit.NSMenuItem.separatorItem())

            # Analyze Today
            self._analyzeItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Analyze Today", "analyzeToday:", ""
            )
            self._analyzeItem.setTarget_(self)
            menu.addItem_(self._analyzeItem)

            menu.addItem_(AppKit.NSMenuItem.separatorItem())

            # Status line (disabled, informational)
            self._statusLineItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No data yet", None, ""
            )
            self._statusLineItem.setEnabled_(False)
            menu.addItem_(self._statusLineItem)

            menu.addItem_(AppKit.NSMenuItem.separatorItem())

            # Quit
            quitItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit", "quitApp:", "q"
            )
            quitItem.setTarget_(self)
            menu.addItem_(quitItem)

            self.statusItem.setMenu_(menu)

        # ── Actions ─────────────────────────────────────────────

        @objc.typedSelector(b"v@:@")
        def toggleCapture_(self, sender):
            if self.captureEngine.is_running:
                self.captureEngine.stop()
                self._startStopItem.setTitle_("Start Capture")
                self.statusItem.setTitle_("OC")
            else:
                # Check accessibility
                if not CaptureEngine.check_accessibility(prompt=False):
                    # Trigger system permission dialog
                    CaptureEngine.check_accessibility(prompt=True)
                    from .onboarding import get_permission_message
                    title, body = get_permission_message("accessibility")
                    alert = AppKit.NSAlert.alloc().init()
                    alert.setMessageText_(title)
                    alert.setInformativeText_(body + "\n\nClick OK after granting access.")
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
                    # Re-check after user dismissed the alert
                    if not CaptureEngine.check_accessibility(prompt=False):
                        return

                error = self.captureEngine.start()
                if error:
                    alert = AppKit.NSAlert.alloc().init()
                    alert.setMessageText_("Failed to Start Capture")
                    alert.setInformativeText_(error)
                    alert.addButtonWithTitle_("OK")
                    alert.runModal()
                    return

                self._startStopItem.setTitle_("Stop Capture")
                self.statusItem.setTitle_("OC \u25cf")  # ● recording indicator

            self._updateStatusLine()

        @objc.typedSelector(b"v@:@")
        def showLog_(self, sender):
            if self.logController is None:
                data_dir = self.config.get(
                    "capture.output_dir", str(Path.home() / "opencapture")
                )
                self.logController = LogWindowController.alloc().initWithDataDir_(data_dir)

            self.logController.show()

        @objc.typedSelector(b"v@:@")
        def analyzeToday_(self, sender):
            self._analyzeItem.setEnabled_(False)
            self._statusLineItem.setTitle_("Analyzing...")

            def on_result(result):
                # Normalize to a plain string for safe ObjC bridging.
                # Python dicts may not bridge cleanly through
                # performSelectorOnMainThread.
                try:
                    if isinstance(result, dict) and "error" in result:
                        msg = f"Error: {result['error']}"
                    elif isinstance(result, dict):
                        images = result.get("images_analyzed", 0)
                        audios = result.get("audios_transcribed", 0)
                        logs = result.get("logs_analyzed", 0)
                        msg = f"Done: {images} images, {audios} audios, {logs} logs analyzed"
                    else:
                        msg = str(result)
                except Exception as e:
                    msg = f"Error: {e}"
                # Pass a plain NSString to the main thread
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "handleAnalysisResult:", msg, False
                )

            provider = self.config.get_default_provider()
            self.analysisEngine.analyze_today(provider=provider, callback=on_result)

        @objc.typedSelector(b"v@:@")
        def handleAnalysisResult_(self, message):
            self._analyzeItem.setEnabled_(True)
            self._statusLineItem.setTitle_(str(message))
            # Show alert so user sees result even if menu is closed
            alert = AppKit.NSAlert.alloc().init()
            if str(message).startswith("Error"):
                alert.setMessageText_("Analysis Failed")
            else:
                alert.setMessageText_("Analysis Complete")
            alert.setInformativeText_(str(message))
            alert.addButtonWithTitle_("OK")
            alert.runModal()

        @objc.typedSelector(b"v@:@")
        def quitApp_(self, sender):
            if self.captureEngine.is_running:
                self.captureEngine.stop()
            self.analysisEngine.stop()
            AppKit.NSApp.terminate_(None)

        @objc.typedSelector(b"v@:@")
        def updateStatusLine_(self, timer):
            self._updateStatusLine()

        # ── Internal ────────────────────────────────────────────

        def _updateStatusLine(self):
            status = self.captureEngine.get_status()
            parts = []
            if status["screenshots"]:
                parts.append(f"{status['screenshots']} screenshots")
            if status["recordings"]:
                parts.append(f"{status['recordings']} recordings")
            if parts:
                text = ", ".join(parts)
            else:
                text = "No data yet"

            if status["running"]:
                text = f"Running — {text}"

            self._statusLineItem.setTitle_(text)


    def main():
        """Launch the macOS menu bar GUI."""
        config = init_config()
        app = AppKit.NSApplication.sharedApplication()
        # Activate as accessory (menu bar only, no dock icon)
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        delegate = AppDelegate.alloc().initWithConfig_(config)
        app.setDelegate_(delegate)
        app.run()
