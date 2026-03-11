"""
Smart day-boundary resolution for capture storage.

Instead of splitting at midnight, OpenCapture uses a configurable
"day start hour" (default 04:00) and an inactivity threshold to
decide when a new logical day begins.  This keeps late-night
sessions in one directory as long as the user remains active.
"""

import threading
from datetime import datetime, timedelta
from typing import Optional


class DateResolver:
    """Stateful date resolver: day-start hour + inactivity threshold.

    Used by capture components (KeyLogger, MouseCapture, MicCapture)
    to determine which date directory an event belongs to.
    """

    def __init__(self, day_start_hour: int = 4, inactivity_threshold_minutes: int = 180):
        self.day_start_hour = day_start_hour
        self.inactivity_threshold = timedelta(minutes=inactivity_threshold_minutes)
        self._current_date: Optional[str] = None
        self._last_event_time: Optional[datetime] = None
        self._lock = threading.Lock()

    def get_logical_date(self, now: Optional[datetime] = None) -> str:
        """Return the logical date (YYYY-MM-DD) for the current event.

        Rules:
        1. Compute base_date from ``now`` using day_start_hour.
        2. First call: adopt base_date.
        3. Same base_date as current: stay, update last_event_time.
        4. Different base_date (day boundary crossed):
           - If inactive >= threshold: switch to base_date.
           - Otherwise (continuous activity): stick with current date.
        5. Update last_event_time and return.
        """
        if now is None:
            now = datetime.now()

        base_date = self.compute_base_date(now, self.day_start_hour)

        with self._lock:
            if self._current_date is None:
                # First call
                self._current_date = base_date
                self._last_event_time = now
                return self._current_date

            if base_date == self._current_date:
                # Same logical day
                self._last_event_time = now
                return self._current_date

            # Day boundary crossed — check inactivity
            if self._last_event_time is not None:
                gap = now - self._last_event_time
                if gap >= self.inactivity_threshold:
                    # Long enough gap — switch to new day
                    self._current_date = base_date
            else:
                # No previous event time — switch
                self._current_date = base_date

            self._last_event_time = now
            return self._current_date

    @staticmethod
    def compute_base_date(dt: Optional[datetime] = None, day_start_hour: int = 4) -> str:
        """Pure function: compute logical date from day-start hour.

        If the current hour is before ``day_start_hour``, the event
        belongs to the previous calendar day.

        Used by CLI, analyzer, and GUI where no activity tracking is
        needed.
        """
        if dt is None:
            dt = datetime.now()
        if dt.hour < day_start_hour:
            dt = dt - timedelta(days=1)
        return dt.strftime("%Y-%m-%d")
