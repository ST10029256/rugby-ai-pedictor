"""Rules that keep a stored prediction honest.

A prediction is a claim made *before* a match. Once the ball is kicked the
result becomes knowable, and a number produced after that point is not a
forecast however it was computed.

Nightly retraining makes this concrete. Production training fits on every
completed game, so re-scoring a finished match asks a model what it thinks of a
result it was trained on. It answers well, and the app would then show a
confident "prediction" that nobody ever made. That is the difference between a
product that forecasts and one that reports the past as though it had.

`refuse_reason` is the single chokepoint. Every writer of a `pre_kickoff_live`
row calls it, so the guarantee holds no matter which path - the daily freeze,
batch predict, or a webhook - reaches the table first for a given fixture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

SNAPSHOT_PRE_KICKOFF = "pre_kickoff_live"


def utcnow() -> datetime:
    """Naive UTC, matching how kickoff times are stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_moment(value: Any) -> Optional[datetime]:
    """Parse a stored timestamp into naive UTC, or None if unusable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value

    raw = str(value).strip()
    if not raw:
        return None

    # Unix epoch seconds appear in the `event.timestamp` column for some feeds.
    if raw.isdigit() and len(raw) >= 9:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def is_date_only(value: Any) -> bool:
    """True when the feed gave a calendar date with no kickoff time."""
    raw = str(value or "").strip()
    return len(raw) == 10 and raw.count("-") == 2


def refuse_reason(
    *,
    kickoff_at: Any,
    has_actual_score: bool,
    predicted_at: Any = None,
    date_event: Any = None,
) -> Optional[str]:
    """Why this fixture must not receive a pre-kickoff prediction, or None.

    A caller that gets a string back should skip the write and count it, rather
    than storing a prediction that would misrepresent when it was made.
    """
    if has_actual_score:
        return "match already has a final score"

    now = parse_moment(predicted_at) or utcnow()
    kickoff = parse_moment(kickoff_at)

    if kickoff is not None and not is_date_only(kickoff_at):
        if now >= kickoff:
            return f"kickoff already passed ({kickoff.isoformat()})"
        return None

    # Only a calendar date is known, so the kickoff time within that day is not.
    # Allowing writes during the day would let a fixture be "predicted" hours
    # after it finished, so the day itself is the cutoff.
    day = parse_moment(kickoff_at) or parse_moment(date_event)
    if day is None:
        return "no kickoff time recorded"
    if now.date() > day.date():
        return f"match date already passed ({day.date().isoformat()})"
    if now.date() == day.date():
        return f"kickoff time unknown and match day already started ({day.date().isoformat()})"
    return None


def is_pre_kickoff(**kwargs: Any) -> bool:
    """Convenience wrapper: True when a pre-kickoff write is allowed."""
    return refuse_reason(**kwargs) is None
