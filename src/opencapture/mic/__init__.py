"""
Microphone capture abstraction.

Factory function returns the appropriate backend for the current platform,
or None if mic capture is not supported.
"""

import sys
from pathlib import Path
from typing import Optional

from ._base import MicCaptureBase


def create_mic_capture(
    storage_dir: Path,
    key_logger,
    mic_config: Optional[dict] = None,
) -> Optional[MicCaptureBase]:
    """Create a platform-appropriate mic capture instance.

    Returns None if mic capture is not available on this platform or
    if initialization fails.
    """
    cfg = mic_config or {}

    if sys.platform == "darwin":
        try:
            from .macos import MacOSMicCapture
            return MacOSMicCapture(
                storage_dir=storage_dir,
                key_logger=key_logger,
                sample_rate=cfg.get("mic_sample_rate", 16000),
                channels=cfg.get("mic_channels", 1),
                min_duration_ms=cfg.get("mic_min_duration_ms", cfg.get("mic_start_debounce_ms", 500)),
                stop_debounce_ms=cfg.get("mic_stop_debounce_ms", 300),
            )
        except ImportError as e:
            print(f"[MicCapture] Unavailable (missing dependency): {e}")
        except Exception as e:
            print(f"[MicCapture] Init failed: {e}")
    # elif sys.platform == "win32":
    #     from .windows import WindowsMicCapture
    #     ...

    return None


__all__ = ["MicCaptureBase", "create_mic_capture"]
