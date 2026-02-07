#!/usr/bin/env python3
"""
Microphone Capture - Records audio when the microphone is in use by other applications.

Uses Core Audio (via ctypes) to monitor microphone state and identify which
processes are using the mic. Records audio via sounddevice when active.

All monitoring is event-driven via AudioObjectAddPropertyListener:
  1. kAudioDevicePropertyDeviceIsRunningSomewhere — mic on/off (recording trigger)
  2. kAudioHardwarePropertyProcessObjectList — audio process added/removed
  3. kAudioProcessPropertyIsRunningInput — per-process input state change (join/leave)

Requires macOS 14+ (Sonoma) for process identification.
"""

import ctypes
import ctypes.util
import os
import queue
import struct
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

import sounddevice as sd
import AppKit

# ============================================================
# Core Audio ctypes bindings
# ============================================================

_CoreAudio = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
)
_CoreFoundation = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)

AudioObjectID = ctypes.c_uint32
OSStatus = ctypes.c_int32


class AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


def _fourcc(s: str) -> int:
    """Convert a 4-char code to UInt32 (big-endian)."""
    return struct.unpack(">I", s.encode("ascii"))[0]


# Core Audio constants
kAudioObjectSystemObject = 1
kAudioHardwarePropertyDefaultInputDevice = _fourcc("dIn ")
kAudioObjectPropertyScopeGlobal = _fourcc("glob")
kAudioObjectPropertyScopeInput = _fourcc("inpt")
kAudioObjectPropertyElementMain = 0
kAudioDevicePropertyDeviceIsRunningSomewhere = _fourcc("gone")

# AudioProcess constants (macOS 14+)
kAudioHardwarePropertyProcessObjectList = _fourcc("prs#")
kAudioProcessPropertyPID = _fourcc("ppid")
kAudioProcessPropertyBundleID = _fourcc("pbid")
kAudioProcessPropertyIsRunningInput = _fourcc("piri")
kAudioProcessPropertyDevices = _fourcc("pdv#")

# Listener callback type
AudioObjectPropertyListenerProc = ctypes.CFUNCTYPE(
    OSStatus,
    AudioObjectID,
    ctypes.c_uint32,
    ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_void_p,
)

# Configure function signatures
_CoreAudio.AudioObjectGetPropertyDataSize.restype = OSStatus
_CoreAudio.AudioObjectGetPropertyDataSize.argtypes = [
    AudioObjectID,
    ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint32),
]

_CoreAudio.AudioObjectGetPropertyData.restype = OSStatus
_CoreAudio.AudioObjectGetPropertyData.argtypes = [
    AudioObjectID,
    ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint32,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.c_void_p,
]

_CoreAudio.AudioObjectAddPropertyListener.restype = OSStatus
_CoreAudio.AudioObjectAddPropertyListener.argtypes = [
    AudioObjectID,
    ctypes.POINTER(AudioObjectPropertyAddress),
    AudioObjectPropertyListenerProc,
    ctypes.c_void_p,
]

_CoreAudio.AudioObjectRemovePropertyListener.restype = OSStatus
_CoreAudio.AudioObjectRemovePropertyListener.argtypes = [
    AudioObjectID,
    ctypes.POINTER(AudioObjectPropertyAddress),
    AudioObjectPropertyListenerProc,
    ctypes.c_void_p,
]

# CoreFoundation helpers for CFString
_CoreFoundation.CFStringGetLength.restype = ctypes.c_long
_CoreFoundation.CFStringGetLength.argtypes = [ctypes.c_void_p]
_CoreFoundation.CFStringGetCString.restype = ctypes.c_bool
_CoreFoundation.CFStringGetCString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.c_long,
    ctypes.c_uint32,
]
_CoreFoundation.CFRelease.argtypes = [ctypes.c_void_p]
_kCFStringEncodingUTF8 = 0x08000100

# CFRunLoop support (needed to pump Core Audio property listener notifications)
_kCFRunLoopDefaultMode = ctypes.c_void_p.in_dll(
    _CoreFoundation, "kCFRunLoopDefaultMode"
)
_CoreFoundation.CFRunLoopRunInMode.restype = ctypes.c_int32
_CoreFoundation.CFRunLoopRunInMode.argtypes = [
    ctypes.c_void_p,   # mode (CFStringRef)
    ctypes.c_double,    # seconds
    ctypes.c_bool,      # returnAfterSourceHandled
]
_kCFRunLoopRunFinished = 1
_kCFRunLoopRunTimedOut = 3


def _cfstring_to_str(cf_str_ptr) -> Optional[str]:
    """Convert a CFStringRef to a Python str."""
    if not cf_str_ptr:
        return None
    length = _CoreFoundation.CFStringGetLength(cf_str_ptr)
    buf = ctypes.create_string_buffer(length * 4 + 1)
    _CoreFoundation.CFStringGetCString(
        cf_str_ptr, buf, len(buf), _kCFStringEncodingUTF8
    )
    _CoreFoundation.CFRelease(cf_str_ptr)
    return buf.value.decode("utf-8")


# ============================================================
# Core Audio helper functions
# ============================================================


def _get_default_input_device() -> int:
    """Get the AudioObjectID of the default input (microphone) device."""
    prop = AudioObjectPropertyAddress(
        kAudioHardwarePropertyDefaultInputDevice,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    device_id = AudioObjectID(0)
    size = ctypes.c_uint32(ctypes.sizeof(AudioObjectID))
    status = _CoreAudio.AudioObjectGetPropertyData(
        kAudioObjectSystemObject,
        ctypes.byref(prop),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(device_id),
    )
    if status != 0:
        raise RuntimeError(f"Failed to get default input device: {status}")
    return device_id.value


def _is_device_running(device_id: int) -> bool:
    """Check if any process has an active I/O cycle on the device."""
    prop = AudioObjectPropertyAddress(
        kAudioDevicePropertyDeviceIsRunningSomewhere,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    running = ctypes.c_uint32(0)
    size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_uint32))
    status = _CoreAudio.AudioObjectGetPropertyData(
        device_id,
        ctypes.byref(prop),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(running),
    )
    if status != 0:
        return False
    return bool(running.value)


def _get_audio_process_list() -> list[int]:
    """Get all AudioProcess object IDs (macOS 14+)."""
    prop = AudioObjectPropertyAddress(
        kAudioHardwarePropertyProcessObjectList,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    size = ctypes.c_uint32(0)
    status = _CoreAudio.AudioObjectGetPropertyDataSize(
        kAudioObjectSystemObject, ctypes.byref(prop), 0, None, ctypes.byref(size)
    )
    if status != 0:
        return []

    count = size.value // ctypes.sizeof(AudioObjectID)
    if count == 0:
        return []

    arr = (AudioObjectID * count)()
    status = _CoreAudio.AudioObjectGetPropertyData(
        kAudioObjectSystemObject,
        ctypes.byref(prop),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(arr),
    )
    if status != 0:
        return []
    return list(arr)


def _get_process_pid(proc_obj_id: int) -> int:
    """Get the PID of an AudioProcess object."""
    prop = AudioObjectPropertyAddress(
        kAudioProcessPropertyPID,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    pid = ctypes.c_int32(0)
    size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_int32))
    status = _CoreAudio.AudioObjectGetPropertyData(
        proc_obj_id, ctypes.byref(prop), 0, None, ctypes.byref(size), ctypes.byref(pid)
    )
    if status != 0:
        return -1
    return pid.value


def _get_process_bundle_id(proc_obj_id: int) -> Optional[str]:
    """Get the bundle ID of an AudioProcess object."""
    prop = AudioObjectPropertyAddress(
        kAudioProcessPropertyBundleID,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    cf_str = ctypes.c_void_p(0)
    size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p))
    status = _CoreAudio.AudioObjectGetPropertyData(
        proc_obj_id,
        ctypes.byref(prop),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(cf_str),
    )
    if status != 0:
        return None
    return _cfstring_to_str(cf_str)


def _is_process_running_input(proc_obj_id: int) -> bool:
    """Check if an AudioProcess has active audio input."""
    prop = AudioObjectPropertyAddress(
        kAudioProcessPropertyIsRunningInput,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain,
    )
    running = ctypes.c_uint32(0)
    size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_uint32))
    status = _CoreAudio.AudioObjectGetPropertyData(
        proc_obj_id,
        ctypes.byref(prop),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(running),
    )
    if status != 0:
        return False
    return bool(running.value)


def _get_process_input_devices(proc_obj_id: int) -> list[int]:
    """Get input device IDs used by an AudioProcess."""
    prop = AudioObjectPropertyAddress(
        kAudioProcessPropertyDevices,
        kAudioObjectPropertyScopeInput,
        kAudioObjectPropertyElementMain,
    )
    size = ctypes.c_uint32(0)
    status = _CoreAudio.AudioObjectGetPropertyDataSize(
        proc_obj_id, ctypes.byref(prop), 0, None, ctypes.byref(size)
    )
    if status != 0 or size.value == 0:
        return []

    count = size.value // ctypes.sizeof(AudioObjectID)
    arr = (AudioObjectID * count)()
    status = _CoreAudio.AudioObjectGetPropertyData(
        proc_obj_id, ctypes.byref(prop), 0, None, ctypes.byref(size), ctypes.byref(arr)
    )
    if status != 0:
        return []
    return list(arr)


def _pid_to_app_info(pid: int) -> tuple[str, str]:
    """Resolve PID to (app_name, bundle_id) via AppKit."""
    try:
        app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app:
            name = app.localizedName() or "unknown"
            bundle = app.bundleIdentifier() or "unknown"
            return name, bundle
    except Exception:
        pass
    return "unknown", "unknown"


def _add_property_listener(obj_id, prop_addr, callback):
    """Register a property listener. Returns OSStatus."""
    return _CoreAudio.AudioObjectAddPropertyListener(
        obj_id, ctypes.byref(prop_addr), callback, None
    )


def _remove_property_listener(obj_id, prop_addr, callback):
    """Remove a property listener. Returns OSStatus."""
    return _CoreAudio.AudioObjectRemovePropertyListener(
        obj_id, ctypes.byref(prop_addr), callback, None
    )


# ============================================================
# MicrophoneCapture class
# ============================================================


class MicrophoneCapture:
    """Records microphone audio when another application is using the mic.

    Architecture:
      - A dedicated monitor thread runs a CFRunLoop to dispatch Core Audio callbacks
      - Three layers of Core Audio property listeners for event-driven detection
      - Periodic polling (every 2s) as a fallback in case listeners miss events
      - Stop detection uses client tracking (not device-is-running, since our own
        recording keeps the device active)

    Core Audio listeners:
      1. Device listener:  kAudioDevicePropertyDeviceIsRunningSomewhere
         → triggers recording start (with debounce)
      2. System listener:  kAudioHardwarePropertyProcessObjectList
         → fires when audio processes are added/removed
      3. Per-process listeners: kAudioProcessPropertyIsRunningInput
         → fires when a specific process starts/stops audio input
         → used for mic_join / mic_leave events and stop detection
    """

    def __init__(
        self,
        storage_dir: Path,
        key_logger=None,
        sample_rate: int = 16000,
        channels: int = 1,
        start_debounce_ms: int = 500,
        stop_debounce_ms: int = 2000,
    ):
        self.storage_dir = storage_dir
        self.key_logger = key_logger
        self.sample_rate = sample_rate
        self.channels = channels
        self.start_debounce_s = start_debounce_ms / 1000.0
        self.stop_debounce_s = stop_debounce_ms / 1000.0

        self._lock = threading.Lock()
        self._device_id: int = 0
        self._running = False
        self._recording = False

        # Monitor thread
        self._monitor_thread: Optional[threading.Thread] = None

        # Debounce timers
        self._start_timer: Optional[threading.Timer] = None
        self._stop_timer: Optional[threading.Timer] = None

        # Recording state
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.RawInputStream] = None
        self._wav_file: Optional[wave.Wave_write] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_running = False
        self._record_start_time: Optional[datetime] = None
        self._temp_filepath: Optional[Path] = None
        self._primary_app: str = "unknown"
        self._primary_bundle: str = "unknown"

        # Current mic client set: {bundle_id: app_name}
        self._current_clients: dict[str, str] = {}

        # Tracked AudioProcess object IDs with active listeners
        self._watched_procs: set[int] = set()

        # ---- Callback references (must be stored to prevent GC) ----

        # 0) Default input device change listener (hot-swap mic support)
        self._default_device_listener = AudioObjectPropertyListenerProc(
            self._on_default_device_changed
        )
        self._default_device_prop = AudioObjectPropertyAddress(
            kAudioHardwarePropertyDefaultInputDevice,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain,
        )

        # 1) Device running state listener
        self._device_listener = AudioObjectPropertyListenerProc(
            self._on_device_running_changed
        )
        self._device_prop = AudioObjectPropertyAddress(
            kAudioDevicePropertyDeviceIsRunningSomewhere,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain,
        )

        # 2) System process list listener
        self._proclist_listener = AudioObjectPropertyListenerProc(
            self._on_process_list_changed
        )
        self._proclist_prop = AudioObjectPropertyAddress(
            kAudioHardwarePropertyProcessObjectList,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain,
        )

        # 3) Per-process IsRunningInput listener (single callback, registered on many objects)
        self._proc_input_listener = AudioObjectPropertyListenerProc(
            self._on_process_input_changed
        )
        self._proc_input_prop = AudioObjectPropertyAddress(
            kAudioProcessPropertyIsRunningInput,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain,
        )

    # ============================================================
    # Lifecycle
    # ============================================================

    def start(self):
        """Start monitoring the microphone device."""
        try:
            self._device_id = _get_default_input_device()
        except RuntimeError as e:
            print(f"[Mic] Failed to get input device: {e}")
            return

        self._running = True
        print(f"[Mic] Monitoring default input device (id={self._device_id})")

        # Launch monitor thread (registers listeners + runs event loop + polls)
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="mic-monitor"
        )
        self._monitor_thread.start()

    def stop(self):
        """Stop monitoring and finalize any active recording."""
        self._running = False

        # Cancel pending debounce timers
        self._cancel_timer("start")
        self._cancel_timer("stop")

        # Stop active recording
        if self._recording:
            self._stop_recording()

        # Wait for monitor thread to exit (it will clean up listeners)
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3.0)
            self._monitor_thread = None

        print("[Mic] Stopped.")

    # ============================================================
    # Monitor thread (CFRunLoop + polling)
    # ============================================================

    def _monitor_loop(self):
        """Monitor thread: register Core Audio listeners, run CFRunLoop, poll as fallback."""
        # Register all listeners on THIS thread

        # Listen for default input device changes (mic hot-swap)
        _add_property_listener(
            kAudioObjectSystemObject, self._default_device_prop, self._default_device_listener
        )

        # Listen for device running state
        status = _add_property_listener(
            self._device_id, self._device_prop, self._device_listener
        )
        if status != 0:
            print(f"[Mic] Failed to register device listener: {status}")

        _add_property_listener(
            kAudioObjectSystemObject, self._proclist_prop, self._proclist_listener
        )
        self._sync_process_listeners()

        # Check initial mic state
        if _is_device_running(self._device_id):
            print("[Mic] Device already active at start")
            self._handle_mic_active()

        # Main loop: pump CFRunLoop (for Core Audio callbacks) + periodic polling
        last_poll = time.time()

        while self._running:
            # Run the CFRunLoop for up to 1 second, dispatching any pending callbacks
            result = _CoreFoundation.CFRunLoopRunInMode(
                _kCFRunLoopDefaultMode, 1.0, False
            )

            # If run loop has no sources (returns immediately), sleep to avoid spinning
            if result == _kCFRunLoopRunFinished:
                time.sleep(1.0)

            # Periodic fallback polling every 2 seconds
            now = time.time()
            if now - last_poll >= 2.0:
                last_poll = now
                self._poll_mic_state()

        # Cleanup: remove all listeners before thread exits
        self._remove_all_listeners()

    def _remove_all_listeners(self):
        """Remove all registered Core Audio property listeners."""
        for proc_id in list(self._watched_procs):
            _remove_property_listener(
                proc_id, self._proc_input_prop, self._proc_input_listener
            )
        self._watched_procs.clear()

        _remove_property_listener(
            kAudioObjectSystemObject, self._proclist_prop, self._proclist_listener
        )
        _remove_property_listener(
            kAudioObjectSystemObject, self._default_device_prop, self._default_device_listener
        )
        _remove_property_listener(
            self._device_id, self._device_prop, self._device_listener
        )

    def _poll_mic_state(self):
        """Fallback polling: detect mic active/inactive and client changes."""
        try:
            is_active = _is_device_running(self._device_id)

            if is_active and not self._recording:
                print("[Mic] Poll: device active, not recording → scheduling start")
                self._handle_mic_active()

            if self._recording:
                # Check if external clients are still present
                clients = self._get_mic_clients()
                if not clients:
                    # All external clients gone → schedule stop
                    print("[Mic] Poll: no external clients remain → scheduling stop")
                    self._handle_all_clients_left()
                else:
                    # Update join/leave tracking
                    self._update_client_tracking(clients)
        except Exception as e:
            print(f"[Mic] Poll error: {e}")

    def _handle_mic_active(self):
        """Handle mic becoming active — schedule recording start."""
        self._cancel_timer("stop")
        if not self._recording:
            self._schedule_start()

    def _handle_all_clients_left(self):
        """Handle all external mic clients leaving — schedule recording stop."""
        self._cancel_timer("start")
        if self._recording:
            self._schedule_stop()

    def _update_client_tracking(self, new_clients: dict[str, str]):
        """Compare new client set with current and emit join/leave events."""
        with self._lock:
            if not self._recording:
                return

            old_bundles = set(self._current_clients.keys())
            new_bundles = set(new_clients.keys())

            for bundle in new_bundles - old_bundles:
                name = new_clients[bundle]
                self._current_clients[bundle] = name
                self._log_event("mic_join", f"{name} ({bundle})")
                print(f"[Mic] Join (poll): {name}")

            for bundle in old_bundles - new_bundles:
                name = self._current_clients.pop(bundle, "unknown")
                self._log_event("mic_leave", f"{name} ({bundle})")
                print(f"[Mic] Leave (poll): {name}")

    # ============================================================
    # Callback 0: Default input device changed (mic hot-swap)
    # ============================================================

    def _on_default_device_changed(self, obj_id, num_addr, addresses, client_data):
        """System default input device changed (user plugged/unplugged a mic)."""
        if not self._running:
            return 0
        try:
            new_device = _get_default_input_device()
            if new_device != self._device_id:
                print(f"[Mic] Default input device changed: {self._device_id} → {new_device}")

                # Remove listener from old device
                _remove_property_listener(
                    self._device_id, self._device_prop, self._device_listener
                )

                # Stop any active recording (device is changing)
                if self._recording:
                    self._stop_recording()

                # Switch to new device
                self._device_id = new_device

                # Register listener on new device
                _add_property_listener(
                    self._device_id, self._device_prop, self._device_listener
                )

                # Check if new device is already active
                if _is_device_running(self._device_id):
                    print("[Mic] New device is already active")
                    self._handle_mic_active()

                print(f"[Mic] Now monitoring device id={self._device_id}")
        except Exception as e:
            print(f"[Mic] Error handling device change: {e}")
        return 0

    # ============================================================
    # Callback 1: Device running state (START trigger)
    # ============================================================

    def _on_device_running_changed(self, obj_id, num_addr, addresses, client_data):
        """Mic device became active or inactive."""
        if not self._running:
            return 0

        is_active = _is_device_running(self._device_id)
        print(f"[Mic] Device running changed: active={is_active}")

        if is_active:
            self._handle_mic_active()
        else:
            # Device truly not running (no process has it, including us)
            # This fires when we're NOT recording and the last external user stopped,
            # or if the device is physically disconnected.
            self._cancel_timer("start")
            if self._recording:
                self._handle_all_clients_left()

        return 0  # noErr

    # ============================================================
    # Callback 2: System process list changed
    # ============================================================

    def _on_process_list_changed(self, obj_id, num_addr, addresses, client_data):
        """An audio process was added or removed from the system."""
        if not self._running:
            return 0
        self._sync_process_listeners()
        return 0

    def _sync_process_listeners(self):
        """Add listeners for new AudioProcess objects, remove stale ones."""
        current_procs = set(_get_audio_process_list())

        # New processes — register listeners
        for proc_id in current_procs - self._watched_procs:
            _add_property_listener(
                proc_id, self._proc_input_prop, self._proc_input_listener
            )

        # Removed processes — unregister listeners + check if they were clients
        for proc_id in self._watched_procs - current_procs:
            _remove_property_listener(
                proc_id, self._proc_input_prop, self._proc_input_listener
            )

        self._watched_procs = current_procs

    # ============================================================
    # Callback 3: Per-process input state changed (join/leave + STOP trigger)
    # ============================================================

    def _on_process_input_changed(self, obj_id, num_addr, addresses, client_data):
        """A specific audio process started or stopped using audio input."""
        if not self._running:
            return 0

        pid = _get_process_pid(obj_id)
        if pid <= 0 or pid == os.getpid():
            return 0

        is_running_input = _is_process_running_input(obj_id)
        uses_our_mic = self._device_id in _get_process_input_devices(obj_id)

        app_name, bundle_id = _pid_to_app_info(pid)

        with self._lock:
            was_client = bundle_id in self._current_clients

            if is_running_input and uses_our_mic and not was_client:
                # New client joined
                self._current_clients[bundle_id] = app_name
                if self._recording:
                    self._log_event("mic_join", f"{app_name} ({bundle_id})")
                    # Cancel any pending stop — a new client joined
                    self._cancel_timer("stop")
                print(f"[Mic] Join: {app_name}")

            elif (not is_running_input or not uses_our_mic) and was_client:
                # Client left
                self._current_clients.pop(bundle_id, None)
                if self._recording:
                    self._log_event("mic_leave", f"{app_name} ({bundle_id})")
                print(f"[Mic] Leave: {app_name}")

                # If all external clients have left, schedule stop
                if self._recording and not self._current_clients:
                    print("[Mic] All clients left → scheduling stop")
                    self._schedule_stop()

        return 0

    # ============================================================
    # Debounce
    # ============================================================

    def _cancel_timer(self, which: str):
        with self._lock:
            if which == "start" and self._start_timer:
                self._start_timer.cancel()
                self._start_timer = None
            elif which == "stop" and self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None

    def _schedule_start(self):
        self._cancel_timer("start")
        with self._lock:
            self._start_timer = threading.Timer(
                self.start_debounce_s, self._debounced_start
            )
            self._start_timer.daemon = True
            self._start_timer.start()

    def _schedule_stop(self):
        self._cancel_timer("stop")
        with self._lock:
            self._stop_timer = threading.Timer(
                self.stop_debounce_s, self._debounced_stop
            )
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def _debounced_start(self):
        if not self._running:
            return
        if not self._recording and _is_device_running(self._device_id):
            self._start_recording()

    def _debounced_stop(self):
        if not self._running:
            return
        if self._recording:
            # Double-check: are there still external clients?
            clients = self._get_mic_clients()
            if not clients:
                self._stop_recording()
            else:
                print(f"[Mic] Stop cancelled: clients still present: {list(clients.values())}")

    # ============================================================
    # Process identification
    # ============================================================

    def _get_mic_clients(self) -> dict[str, str]:
        """Return {bundle_id: app_name} for external processes using the default input device.

        Returns empty dict if no external clients are found.
        """
        clients: dict[str, str] = {}
        try:
            for proc_id in _get_audio_process_list():
                if not _is_process_running_input(proc_id):
                    continue
                input_devices = _get_process_input_devices(proc_id)
                if self._device_id not in input_devices:
                    continue
                pid = _get_process_pid(proc_id)
                if pid <= 0 or pid == os.getpid():
                    continue
                app_name, bundle_id = _pid_to_app_info(pid)
                clients[bundle_id] = app_name
        except Exception as e:
            print(f"[Mic] Error querying audio processes: {e}")
        return clients

    def _format_clients(self, clients: dict[str, str]) -> str:
        """Format clients for log entry: 'App1 (bundle1), App2 (bundle2)'."""
        if not clients:
            return "unknown (unknown)"
        parts = []
        for bundle_id, app_name in sorted(clients.items(), key=lambda x: x[1]):
            parts.append(f"{app_name} ({bundle_id})")
        return ", ".join(parts)

    # ============================================================
    # Recording
    # ============================================================

    def _get_day_dir(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.storage_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def _sanitize_app_name(self, name: str) -> str:
        """Sanitize app name for use in filenames."""
        return name.lower().replace(" ", "-").replace("/", "-").replace(".", "-")

    def _start_recording(self):
        """Begin recording microphone audio."""
        with self._lock:
            if self._recording:
                return
            self._recording = True

        # Identify mic clients
        clients = self._get_mic_clients()
        if clients:
            self._current_clients = clients.copy()
        else:
            self._current_clients = {"unknown": "unknown"}

        # Pick primary app (first alphabetically by app name)
        first_bundle = sorted(self._current_clients.keys(), key=lambda b: self._current_clients[b])[0]
        self._primary_app = self._current_clients[first_bundle]
        self._primary_bundle = first_bundle

        # Log mic_start
        self._log_event("mic_start", self._format_clients(self._current_clients))

        # Prepare WAV file (temporary name without duration)
        self._record_start_time = datetime.now()
        ts = self._record_start_time.strftime("%H%M%S")
        ms = self._record_start_time.strftime("%f")[:3]
        app_slug = self._sanitize_app_name(self._primary_app)
        tmp_name = f"mic_{ts}_{ms}_{app_slug}.wav.tmp"
        self._temp_filepath = self._get_day_dir() / tmp_name

        try:
            self._wav_file = wave.open(str(self._temp_filepath), "wb")
            self._wav_file.setnchannels(self.channels)
            self._wav_file.setsampwidth(2)  # 16-bit
            self._wav_file.setframerate(self.sample_rate)
        except Exception as e:
            print(f"[Mic] Failed to open WAV file: {e}")
            self._recording = False
            return

        # Start writer thread
        self._writer_running = True
        self._writer_thread = threading.Thread(
            target=self._audio_writer, daemon=True
        )
        self._writer_thread.start()

        # Start sounddevice RawInputStream (no numpy dependency)
        try:
            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            print(f"[Mic] Failed to start audio stream: {e}")
            self._writer_running = False
            self._wav_file.close()
            self._wav_file = None
            # Clean up temp file
            if self._temp_filepath and self._temp_filepath.exists():
                try:
                    self._temp_filepath.unlink()
                except OSError:
                    pass
            self._temp_filepath = None
            self._recording = False
            return

        print(f"[Mic] Recording started: {self._primary_app}")

    def _stop_recording(self):
        """Stop recording and finalize the WAV file."""
        with self._lock:
            if not self._recording:
                return
            self._recording = False

        # Stop audio stream
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Stop writer thread
        self._writer_running = False
        self._audio_queue.put(None)  # sentinel
        if self._writer_thread:
            self._writer_thread.join(timeout=2.0)
            self._writer_thread = None

        # Close WAV file
        if self._wav_file:
            try:
                self._wav_file.close()
            except Exception:
                pass
            self._wav_file = None

        # Compute duration and rename file
        duration = 0
        final_path = self._temp_filepath
        if self._record_start_time and self._temp_filepath:
            duration = int((datetime.now() - self._record_start_time).total_seconds())
            if duration < 1:
                duration = 1
            # Rename: mic_HHmmss_ms_app.wav.tmp → mic_HHmmss_ms_app_durN.wav
            stem = self._temp_filepath.stem.replace(".wav", "")
            final_name = f"{stem}_dur{duration}.wav"
            final_path = self._temp_filepath.parent / final_name
            try:
                self._temp_filepath.rename(final_path)
            except Exception as e:
                print(f"[Mic] Failed to rename file: {e}")
                final_path = self._temp_filepath

        filename = final_path.name
        self._log_event("mic_stop", f"({duration}s) {filename}")

        print(f"[Mic] Recording stopped: {filename} ({duration}s)")

        # Reset state
        self._record_start_time = None
        self._temp_filepath = None
        self._current_clients.clear()

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice RawInputStream callback — runs on PortAudio thread.

        indata is a CFFI buffer (not numpy). Convert to bytes for WAV writing.
        """
        if status:
            print(f"[Mic] Audio status: {status}")
        self._audio_queue.put(bytes(indata))

    def _audio_writer(self):
        """Writer thread: drains audio queue and writes raw bytes to WAV."""
        while self._writer_running or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.5)
                if data is None:
                    break
                if self._wav_file:
                    self._wav_file.writeframes(data)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Mic] Writer error: {e}")
                break

    # ============================================================
    # Log integration
    # ============================================================

    def _log_event(self, event_type: str, detail: str):
        """Write a microphone event to the daily log file."""
        if self.key_logger:
            self.key_logger.log_mic_event(event_type, detail)
        else:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] 🎤 {event_type} | {detail}")
