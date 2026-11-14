"""Date window calculation for pre-meeting briefing."""

from datetime import datetime, timedelta, timezone
from typing import Tuple, List, Optional
from app.models import Window

def calculate_window(
    meeting_time: datetime,
    window_days: int = 30,
    now: Optional[datetime] = None,
) -> Tuple[Window, List[str]]:
    """Calculates the 30-day research window bounded by meeting time and today.

    Args:
        meeting_time: Timezone-aware datetime of the planned meeting.
        window_days: Number of days before the end date to research (default: 30).
        now: Optional fixed current time (for deterministic testing).

    Returns:
        Tuple of (Window, list of warnings).

    Raises:
        ValueError: If meeting_time is naive (missing timezone).
    """
    if meeting_time.tzinfo is None or meeting_time.tzinfo.utcoffset(meeting_time) is None:
        raise ValueError("meeting_time must be timezone-aware")

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now reference must be timezone-aware")

    meeting_utc = meeting_time.astimezone(timezone.utc)
    meeting_date_utc = meeting_utc.date()
    now_date_utc = now.astimezone(timezone.utc).date()

    # We cannot see the future: end = min(meeting date, today)
    end = min(meeting_date_utc, now_date_utc)
    start = end - timedelta(days=window_days)

    meeting_in_past = meeting_utc < now
    meeting_far_future = meeting_utc > (now + timedelta(days=30))

    warnings: List[str] = []
    if meeting_far_future:
        warnings.append(
            f"Meeting is { (meeting_date_utc - now_date_utc).days } days in the future. "
            "Window covers the last 30 days up to today, not up to the meeting date."
        )
    if meeting_in_past:
        warnings.append("Meeting occurred in the past. Briefing covers the 30 days prior to that meeting date.")

    window = Window(
        start=start,
        end=end,
        meeting_in_past=meeting_in_past,
        meeting_far_future=meeting_far_future,
    )

    return window, warnings
