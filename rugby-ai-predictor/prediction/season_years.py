"""Season-year rules shared by standings, Highlightly fetches, and History.

Only URC, Premiership and Top 14 cross two calendar years.
Everything else is a single calendar year / World Cup edition year.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Tuple

SUPER_RUGBY = 4551
SIX_NATIONS = 4714
RUGBY_CHAMPIONSHIP = 4986
CURRIE_CUP = 5069
NATIONS_CHAMPIONSHIP = 5480
RWC = 4574
FRIENDLIES = 5479
URC = 4446
PREMIERSHIP = 4414
TOP14 = 4430

CALENDAR_YEAR_LEAGUE_IDS = {
    SUPER_RUGBY,
    SIX_NATIONS,
    RUGBY_CHAMPIONSHIP,
    CURRIE_CUP,
    NATIONS_CHAMPIONSHIP,
    RWC,
    FRIENDLIES,
}

CROSS_YEAR_LEAGUE_IDS = {URC, PREMIERSHIP, TOP14}


def cross_year_season_start_month(league_id: Any) -> Optional[int]:
    lid = int(league_id)
    if lid == TOP14:
        return 8
    if lid in (URC, PREMIERSHIP):
        return 9
    return None


def _year_month(value: Any) -> Tuple[int, int]:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.year, dt.month
    text = str(value or "")
    if len(text) >= 7 and text[4] == "-":
        return int(text[:4]), int(text[5:7])
    now = datetime.now(timezone.utc)
    return now.year, now.month


def resolve_season_start_year(league_id: Any, kickoff: Any = None) -> int:
    year, month = _year_month(kickoff if kickoff is not None else datetime.now(timezone.utc))
    start_month = cross_year_season_start_month(league_id)
    if start_month is None:
        return year
    return year if month >= start_month else year - 1


def resolve_season_label(league_id: Any, kickoff: Any = None) -> str:
    start_year = resolve_season_start_year(league_id, kickoff)
    if int(league_id) in CROSS_YEAR_LEAGUE_IDS:
        return f"{start_year}-{str(start_year + 1)[-2:]}"
    return str(start_year)
