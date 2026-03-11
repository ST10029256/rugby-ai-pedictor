#!/usr/bin/env python3
"""
Pull and inspect URC upcoming fixtures for a specific target list.

Why this exists:
- We need to verify whether wrong times come from source data, storage, or UI conversion.
- This script fetches upcoming URC fixtures directly from TheSportsDB and prints
  all kickoff-related fields for the exact fixtures we care about.

Usage:
  python .\check_urc_specific_kickoffs.py
  python .\check_urc_specific_kickoffs.py --season 2025-2026
  python .\check_urc_specific_kickoffs.py --api-key 123
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - older Python fallback
    ZoneInfo = None


BASE_URL = "https://www.thesportsdb.com/api/v1/json"
URC_LEAGUE_ID = 4446

TIME_FIELDS = (
    "strTimestamp",
    "dateEventTimestamp",
    "strTime",
    "strTimeLocal",
    "strTimeUTC",
)


@dataclass(frozen=True)
class TargetFixture:
    date_event: str
    home_team: str
    away_team: str
    expected_time_label: str


TARGET_FIXTURES: List[TargetFixture] = [
    TargetFixture("2026-03-13", "Connacht", "Scarlets", "7:45 PM"),
    TargetFixture("2026-03-13", "Edinburgh", "Ulster", "7:45 PM"),
    TargetFixture("2026-03-20", "Scarlets", "Zebre", "12:30 PM"),
    TargetFixture("2026-03-20", "Ulster", "Connacht", "3:00 PM"),
    TargetFixture("2026-03-20", "Bulls", "Cardiff Rugby", "7:45 PM"),
    TargetFixture("2026-03-21", "Benetton", "Ospreys", "7:45 PM"),
    TargetFixture("2026-03-21", "The Sharks", "Munster", "5:00 PM"),
    TargetFixture("2026-03-21", "Glasgow", "Leinster", "3:00 PM"),
    TargetFixture("2026-03-21", "Stormers", "Dragons", "3:00 PM"),
    TargetFixture("2026-03-21", "Lions", "Edinburgh", "5:30 PM"),
]


def default_season(today: Optional[date] = None) -> str:
    d = today or date.today()
    if d.month >= 8:
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def normalize_team_name(name: Any) -> str:
    s = str(name or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\brugby\b", " ", s)
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def team_equal(a: Any, b: Any) -> bool:
    return normalize_team_name(a) == normalize_team_name(b)


def parse_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if len(raw) < 10:
        return None
    m = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return m.group(0) if m else None


def parse_score(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "null":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def is_upcoming(event: Dict[str, Any], today: date) -> bool:
    date_event = parse_date(event.get("dateEvent") or event.get("dateEventLocal") or event.get("strTimestamp"))
    if not date_event:
        return False
    if date_event < today.isoformat():
        return False
    home_score = parse_score(event.get("intHomeScore"))
    away_score = parse_score(event.get("intAwayScore"))
    return home_score is None and away_score is None


def fetch_events(api_key: str, endpoint: str, params: Dict[str, Any], timeout_sec: int = 30) -> List[Dict[str, Any]]:
    url = f"{BASE_URL.rstrip('/')}/{api_key}/{endpoint}.php"
    resp = requests.get(url, params=params, timeout=timeout_sec)
    resp.raise_for_status()
    payload = resp.json()
    events = payload.get("events") or []
    return events if isinstance(events, list) else []


def dedupe_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_id: Dict[str, Dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("idEvent") or "").strip()
        if not event_id:
            key = f"noid::{event.get('dateEvent')}::{event.get('strHomeTeam')}::{event.get('strAwayTeam')}"
            best_by_id[key] = event
            continue
        existing = best_by_id.get(event_id)
        if not existing:
            best_by_id[event_id] = event
            continue
        existing_fill = sum(1 for f in TIME_FIELDS if existing.get(f))
        current_fill = sum(1 for f in TIME_FIELDS if event.get(f))
        if current_fill > existing_fill:
            best_by_id[event_id] = event
    return list(best_by_id.values())


def parse_utc_timestamp(raw: Any) -> Optional[datetime]:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_as_ampm(raw_hhmmss: Any) -> str:
    s = str(raw_hhmmss or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", s)
    if not m:
        return ""
    hh = int(m.group(1))
    mm = int(m.group(2))
    suffix = "AM" if hh < 12 else "PM"
    hh12 = hh % 12
    if hh12 == 0:
        hh12 = 12
    return f"{hh12}:{mm:02d} {suffix}"


def find_target_match(target: TargetFixture, upcoming_events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for event in upcoming_events:
        event_date = parse_date(event.get("dateEvent") or event.get("dateEventLocal") or event.get("strTimestamp"))
        if event_date != target.date_event:
            continue
        if not team_equal(event.get("strHomeTeam"), target.home_team):
            continue
        if not team_equal(event.get("strAwayTeam"), target.away_team):
            continue
        return event
    return None


def print_fixture_report(target: TargetFixture, event: Optional[Dict[str, Any]]) -> None:
    title = f"{target.home_team} vs {target.away_team} ({target.date_event}, expected {target.expected_time_label})"
    print("-" * 96)
    print(title)
    if not event:
        print("  [MISSING] Fixture not found in upcoming API results.")
        return

    print("  [FOUND] idEvent:", event.get("idEvent"))
    print("  API dateEvent:", event.get("dateEvent"))
    print("  API home/away:", f"{event.get('strHomeTeam')} vs {event.get('strAwayTeam')}")

    for field in TIME_FIELDS:
        print(f"  {field:18}: {repr(event.get(field))}")

    str_time_ampm = format_as_ampm(event.get("strTime"))
    if str_time_ampm:
        print(f"  Parsed strTime (12h): {str_time_ampm}")

    ts_utc = parse_utc_timestamp(event.get("strTimestamp") or event.get("dateEventTimestamp"))
    if ts_utc and ZoneInfo:
        london = ts_utc.astimezone(ZoneInfo("Europe/London"))
        sast = ts_utc.astimezone(ZoneInfo("Africa/Johannesburg"))
        print("  strTimestamp as Europe/London:", london.strftime("%Y-%m-%d %I:%M %p %Z"))
        print("  strTimestamp as Africa/Johannesburg:", sast.strftime("%Y-%m-%d %I:%M %p %Z"))
    elif ts_utc:
        print("  strTimestamp parsed (UTC):", ts_utc.isoformat())
    else:
        print("  strTimestamp parse: unavailable")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Check kickoff times for specific URC fixtures.")
    ap.add_argument("--league-id", type=int, default=URC_LEAGUE_ID, help="SportsDB league id (default: 4446 URC)")
    ap.add_argument("--season", default=default_season(), help="Season string for eventsseason (default: current rugby season)")
    ap.add_argument("--api-key", default="123", help="TheSportsDB API key (default: 123)")
    ap.add_argument(
        "--no-rounds",
        action="store_true",
        help="Disable eventsround.php queries (not recommended for URC on free API).",
    )
    ap.add_argument("--round-min", type=int, default=1, help="First round to query when --include-rounds is enabled.")
    ap.add_argument("--round-max", type=int, default=18, help="Last round to query when --include-rounds is enabled.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    today = date.today()
    endpoints = [
        ("eventsnextleague", {"id": args.league_id}),
        ("eventsseason", {"id": args.league_id, "s": args.season}),
    ]
    include_rounds = not args.no_rounds
    if include_rounds:
        round_min = min(args.round_min, args.round_max)
        round_max = max(args.round_min, args.round_max)
        for round_num in range(round_min, round_max + 1):
            endpoints.append(
                ("eventsround", {"id": args.league_id, "s": args.season, "r": round_num})
            )

    print("=" * 96)
    print("URC SPECIFIC FIXTURE KICKOFF CHECK")
    print("=" * 96)
    print(f"League ID: {args.league_id}")
    print(f"Season:    {args.season}")
    print(f"Today:     {today.isoformat()}")
    print(f"API key:   {args.api_key[:4]}*** (len={len(args.api_key)})")
    print(f"Rounds:    {'enabled' if include_rounds else 'disabled'}")
    print()

    all_events: List[Dict[str, Any]] = []
    for endpoint, params in endpoints:
        try:
            events = fetch_events(api_key=args.api_key, endpoint=endpoint, params=params)
            if endpoint == "eventsround":
                print(f"[OK] {endpoint} r={params.get('r')}: fetched {len(events)} events")
            else:
                print(f"[OK] {endpoint}: fetched {len(events)} events")
            all_events.extend(events)
        except Exception as exc:
            if endpoint == "eventsround":
                print(f"[ERR] {endpoint} r={params.get('r')}: {exc}")
            else:
                print(f"[ERR] {endpoint}: {exc}")

    deduped = dedupe_events(all_events)
    upcoming_events = [e for e in deduped if is_upcoming(e, today)]
    print(f"\nUnique events (deduped): {len(deduped)}")
    print(f"Upcoming events:         {len(upcoming_events)}")
    print()

    found_count = 0
    for target in TARGET_FIXTURES:
        event = find_target_match(target, upcoming_events)
        if event:
            found_count += 1
        print_fixture_report(target, event)

    print("-" * 96)
    print(f"Matched fixtures: {found_count}/{len(TARGET_FIXTURES)}")
    print(
        "Note: URC on free API often needs eventsround.php; eventsseason/eventsnextleague alone can miss fixtures."
    )
    print("=" * 96)
    return 0 if found_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
