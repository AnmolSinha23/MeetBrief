"""Unit tests for window calculation and timezone logic."""

import pytest
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from pydantic import ValidationError

from app.models import MeetingInput, EntityType, MeetingType
from app.steps.window import calculate_window

def test_meeting_in_past():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    past_meeting = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)

    window, warnings = calculate_window(past_meeting, window_days=30, now=now)

    assert window.meeting_in_past is True
    assert window.meeting_far_future is False
    assert window.end == date(2026, 10, 10)
    assert window.start == date(2026, 9, 10)
    assert any("past" in w.lower() for w in warnings)

def test_meeting_today():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    meeting_today = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)

    window, warnings = calculate_window(meeting_today, window_days=30, now=now)

    assert window.meeting_in_past is False
    assert window.meeting_far_future is False
    assert window.end == date(2026, 11, 14)
    assert window.start == date(2026, 10, 15)
    assert len(warnings) == 0

def test_meeting_in_3_days():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    meeting_future = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    window, warnings = calculate_window(meeting_future, window_days=30, now=now)

    # We cannot see the future, so end date is today (2026-11-14)
    assert window.meeting_in_past is False
    assert window.meeting_far_future is False
    assert window.end == date(2026, 11, 14)
    assert window.start == date(2026, 10, 15)

def test_meeting_far_future_45_days():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    meeting_far = now + timedelta(days=45)

    window, warnings = calculate_window(meeting_far, window_days=30, now=now)

    assert window.meeting_far_future is True
    assert window.end == date(2026, 11, 14)
    assert any("not up to the meeting date" in w.lower() for w in warnings)

def test_timezone_crossing_midnight():
    # 2026-11-15 01:30 JST is 2026-11-14 16:30 UTC
    jst = ZoneInfo("Asia/Tokyo")
    meeting_jst = datetime(2026, 11, 15, 1, 30, tzinfo=jst)
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

    window, warnings = calculate_window(meeting_jst, window_days=30, now=now)

    # When converted to UTC, the date is 2026-11-14
    assert window.end == date(2026, 11, 14)

def test_reject_naive_datetime():
    naive_dt = datetime(2026, 11, 14, 10, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        calculate_window(naive_dt)

    with pytest.raises(ValidationError):
        MeetingInput(
            entity="Stripe",
            meeting_time=naive_dt,
        )
