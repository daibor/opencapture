"""MicCaptureBase — abstract interface for microphone capture backends."""

from abc import ABC, abstractmethod


class MicCaptureBase(ABC):
    """Abstract microphone capture backend."""

    @abstractmethod
    def start(self):
        """Start monitoring the microphone and recording when active."""

    @abstractmethod
    def stop(self):
        """Stop monitoring and finalize any in-progress recording."""
