"""Tests for DateResolver (date_resolver.py)."""

import threading
from datetime import datetime, timedelta

import pytest

from opencapture.date_resolver import DateResolver


# ---------------------------------------------------------------------------
# compute_base_date (static, pure function)
# ---------------------------------------------------------------------------

class TestComputeBaseDate:
    def test_before_day_start_belongs_to_previous_day(self):
        dt = datetime(2026, 3, 11, 3, 0, 0)  # 03:00
        assert DateResolver.compute_base_date(dt, day_start_hour=4) == "2026-03-10"

    def test_at_day_start_belongs_to_current_day(self):
        dt = datetime(2026, 3, 11, 4, 0, 0)  # 04:00
        assert DateResolver.compute_base_date(dt, day_start_hour=4) == "2026-03-11"

    def test_after_day_start_belongs_to_current_day(self):
        dt = datetime(2026, 3, 11, 14, 0, 0)  # 14:00
        assert DateResolver.compute_base_date(dt, day_start_hour=4) == "2026-03-11"

    def test_midnight_belongs_to_previous_day(self):
        dt = datetime(2026, 3, 11, 0, 0, 0)  # 00:00
        assert DateResolver.compute_base_date(dt, day_start_hour=4) == "2026-03-10"

    def test_custom_day_start_hour(self):
        dt = datetime(2026, 3, 11, 5, 0, 0)
        # With day_start_hour=6, 05:00 belongs to previous day
        assert DateResolver.compute_base_date(dt, day_start_hour=6) == "2026-03-10"
        # With day_start_hour=5, 05:00 belongs to current day
        assert DateResolver.compute_base_date(dt, day_start_hour=5) == "2026-03-11"

    def test_day_start_hour_zero_is_midnight(self):
        """day_start_hour=0 means no hour is before the start → always current day."""
        dt = datetime(2026, 3, 11, 23, 59, 59)
        assert DateResolver.compute_base_date(dt, day_start_hour=0) == "2026-03-11"
        dt2 = datetime(2026, 3, 11, 0, 0, 0)
        assert DateResolver.compute_base_date(dt2, day_start_hour=0) == "2026-03-11"

    def test_defaults_to_now(self):
        """Calling with no args should return a valid date string."""
        result = DateResolver.compute_base_date()
        datetime.strptime(result, "%Y-%m-%d")  # should not raise


# ---------------------------------------------------------------------------
# DateResolver (stateful, for capture)
# ---------------------------------------------------------------------------

class TestDateResolverStateful:
    def test_first_call_returns_base_date(self):
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        now = datetime(2026, 3, 11, 14, 0, 0)
        assert resolver.get_logical_date(now) == "2026-03-11"

    def test_same_day_stays_same(self):
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        resolver.get_logical_date(datetime(2026, 3, 11, 14, 0, 0))
        assert resolver.get_logical_date(datetime(2026, 3, 11, 23, 0, 0)) == "2026-03-11"

    def test_continuous_across_midnight_stays_same_day(self):
        """Working from 23:00 → 03:00 (before day_start_hour=4) stays on same day."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        # Start working at 23:00 on March 10
        resolver.get_logical_date(datetime(2026, 3, 10, 23, 0, 0))
        # Still working at 01:00 (1 min gaps)
        assert resolver.get_logical_date(datetime(2026, 3, 11, 1, 0, 0)) == "2026-03-10"
        # Still working at 03:00
        assert resolver.get_logical_date(datetime(2026, 3, 11, 3, 0, 0)) == "2026-03-10"

    def test_continuous_across_day_start_stays_same_day(self):
        """Working from 23:00 → 05:00 with short gap (<3h) stays on same day."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        # Start at 23:00
        resolver.get_logical_date(datetime(2026, 3, 10, 23, 0, 0))
        # Last event at 03:00
        resolver.get_logical_date(datetime(2026, 3, 11, 3, 0, 0))
        # Resume at 05:00 — gap is 2h, less than 3h threshold
        assert resolver.get_logical_date(datetime(2026, 3, 11, 5, 0, 0)) == "2026-03-10"

    def test_long_gap_after_day_start_switches_day(self):
        """Working at 23:00, then resume at 07:00 (>3h gap) → new day."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        # Work at 23:00
        resolver.get_logical_date(datetime(2026, 3, 10, 23, 0, 0))
        # Resume at 07:00 — gap is 8h, day boundary crossed
        assert resolver.get_logical_date(datetime(2026, 3, 11, 7, 0, 0)) == "2026-03-11"

    def test_long_gap_within_same_base_date_stays_same(self):
        """14:00 → 4h gap → 18:00 (same base_date) stays on same day."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        resolver.get_logical_date(datetime(2026, 3, 11, 14, 0, 0))
        # 4 hour gap, but same base_date
        assert resolver.get_logical_date(datetime(2026, 3, 11, 18, 0, 0)) == "2026-03-11"

    def test_exact_threshold_switches(self):
        """Gap exactly equal to threshold should switch."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        resolver.get_logical_date(datetime(2026, 3, 10, 23, 0, 0))
        # Resume at 05:00 with exactly 6h gap
        # base_date changes (05:00 → 2026-03-11), gap=6h >= 3h → switch
        assert resolver.get_logical_date(datetime(2026, 3, 11, 5, 0, 0)) == "2026-03-11"

    def test_just_under_threshold_stays(self):
        """Gap just under threshold should NOT switch."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        # Work at 02:00 → base_date 2026-03-10
        resolver.get_logical_date(datetime(2026, 3, 11, 2, 0, 0))
        # Resume at 04:59 → base_date 2026-03-11, gap=2h59m < 3h → stay
        assert resolver.get_logical_date(datetime(2026, 3, 11, 4, 59, 0)) == "2026-03-10"

    def test_multiple_day_transitions(self):
        """Test transitioning across multiple days."""
        resolver = DateResolver(day_start_hour=4, inactivity_threshold_minutes=180)
        # Day 1
        resolver.get_logical_date(datetime(2026, 3, 10, 10, 0, 0))
        assert resolver.get_logical_date(datetime(2026, 3, 10, 18, 0, 0)) == "2026-03-10"
        # Long gap → Day 2
        assert resolver.get_logical_date(datetime(2026, 3, 11, 10, 0, 0)) == "2026-03-11"
        # Long gap → Day 3
        assert resolver.get_logical_date(datetime(2026, 3, 12, 10, 0, 0)) == "2026-03-12"


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestDateResolverThreadSafety:
    def test_concurrent_access(self):
        """Multiple threads calling get_logical_date should not crash."""
        resolver = DateResolver(day_start_hour=4)
        errors = []
        results = []

        def worker():
            try:
                for i in range(100):
                    date = resolver.get_logical_date()
                    results.append(date)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 1000
        # All results should be valid date strings
        for r in results:
            datetime.strptime(r, "%Y-%m-%d")
