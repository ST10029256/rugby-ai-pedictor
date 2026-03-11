#!/usr/bin/env python3
"""
URC API-only history debug (no local DB usage).

For each URC season starting at a given year (e.g. 2008 -> season 2008-2009),
this script calls TheSportsDB eventsseason endpoint and reports:
- total events returned by API
- completed events (both scores present)
- unscored events
- calendar-year split inside the season (start year vs next year)

Usage:
  python .\check_urc_api_history_by_year.py
  python .\check_urc_api_history_by_year.py --start-year 2008 --end-year 2026
  python .\check_urc_api_history_by_year.py --league-id 4446
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_LEAGUE_ID = 4446  # URC in this project mapping
DEFAULT_START_YEAR = 2008
BASE_TEMPLATE = "https://www.thesportsdb.com/api/v1/json/{api_key}/eventsseason.php"


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10:
        text = text[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _is_completed(event: Dict[str, Any]) -> bool:
    return event.get("intHomeScore") is not None and event.get("intAwayScore") is not None


def _fetch_eventsseason(league_id: int, season: str, timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], str]:
    """
    Returns (events, api_key_used).
    Tries free key '123' first, then '1' fallback.
    """
    keys_to_try = ["123", "1"]
    last_error = None
    for key in keys_to_try:
        url = BASE_TEMPLATE.format(api_key=key)
        try:
            resp = requests.get(url, params={"id": league_id, "s": season}, timeout=timeout_s)
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue
            data = resp.json() if resp.content else {}
            events = data.get("events") or []
            if isinstance(events, list):
                return events, key
            return [], key
        except Exception as exc:
            last_error = str(exc)
            continue
    raise RuntimeError(f"Failed to fetch season {season}: {last_error or 'unknown error'}")


def _summarize(events: List[Dict[str, Any]], start_year: int) -> Dict[str, Any]:
    today = date.today()
    total = len(events)
    completed = 0
    unscored = 0
    past_unscored = 0
    future_unscored = 0
    by_calendar_year = defaultdict(int)
    min_d: Optional[date] = None
    max_d: Optional[date] = None

    for ev in events:
        d = _parse_date(ev.get("dateEvent") or ev.get("dateEventLocal"))
        if d:
            by_calendar_year[str(d.year)] += 1
            min_d = d if min_d is None else min(min_d, d)
            max_d = d if max_d is None else max(max_d, d)

        if _is_completed(ev):
            completed += 1
        else:
            unscored += 1
            if d and d < today:
                past_unscored += 1
            elif d and d >= today:
                future_unscored += 1

    return {
        "total": total,
        "completed": completed,
        "unscored": unscored,
        "past_unscored": past_unscored,
        "future_unscored": future_unscored,
        "year_a": by_calendar_year.get(str(start_year), 0),
        "year_b": by_calendar_year.get(str(start_year + 1), 0),
        "min_date": str(min_d) if min_d else "-",
        "max_date": str(max_d) if max_d else "-",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="API-only URC season history debug.")
    parser.add_argument("--league-id", type=int, default=DEFAULT_LEAGUE_ID, help="League ID (default: 4446 URC)")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR, help="Start year (default: 2008)")
    parser.add_argument("--end-year", type=int, default=datetime.now().year, help="End year inclusive (default: current year)")
    args = parser.parse_args()

    if args.end_year < args.start_year:
        print("end-year must be >= start-year")
        return 2

    print("=" * 132)
    print(f"TheSportsDB API debug | league_id={args.league_id} | seasons {args.start_year}..{args.end_year}")
    print("Endpoint: eventsseason.php (API only; no local DB)")
    print("=" * 132)
    print(
        f"{'Season':12} {'API':>4} {'Total':>7} {'Completed':>10} {'NoScore':>8} "
        f"{'PastNoScore':>12} {'FutureNoScore':>14} {'Y(start)':>9} {'Y(next)':>8} {'FirstDate':>12} {'LastDate':>12}"
    )
    print("-" * 132)

    grand_total = 0
    grand_completed = 0
    grand_unscored = 0
    grand_past_unscored = 0
    grand_future_unscored = 0

    for y in range(args.start_year, args.end_year + 1):
        season = f"{y}-{y + 1}"
        try:
            events, api_key_used = _fetch_eventsseason(args.league_id, season)
            s = _summarize(events, y)
            grand_total += int(s["total"])
            grand_completed += int(s["completed"])
            grand_unscored += int(s["unscored"])
            grand_past_unscored += int(s["past_unscored"])
            grand_future_unscored += int(s["future_unscored"])
            print(
                f"{season:12} {api_key_used:>4} {int(s['total']):>7} {int(s['completed']):>10} {int(s['unscored']):>8} "
                f"{int(s['past_unscored']):>12} {int(s['future_unscored']):>14} "
                f"{int(s['year_a']):>9} {int(s['year_b']):>8} {str(s['min_date']):>12} {str(s['max_date']):>12}"
            )
        except Exception as exc:
            print(f"{season:12} {'-':>4} {'ERR':>7} {'ERR':>10} {'ERR':>8} {'ERR':>12} {'ERR':>14} {'ERR':>9} {'ERR':>8} {'-':>12} {'-':>12}  ({exc})")

    print("-" * 132)
    print(
        f"{'TOTAL':12} {'':>4} {grand_total:>7} {grand_completed:>10} {grand_unscored:>8} "
        f"{grand_past_unscored:>12} {grand_future_unscored:>14}"
    )
    print("=" * 132)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

