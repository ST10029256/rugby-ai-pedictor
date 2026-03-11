#!/usr/bin/env python3
"""
Check whether TheSportsDB is returning kickoff times for fixtures.

Examples:
  python .\check_api_kickoff_times.py
  python .\check_api_kickoff_times.py --league-id 4414 --season 2025-2026
  python .\check_api_kickoff_times.py --endpoints eventsseason,eventsnextleague,eventsleague
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


DEFAULT_BASE_URL = "https://www.thesportsdb.com/api/v1/json"
TIME_FIELDS = (
    "strTimestamp",
    "dateEventTimestamp",
    "strTime",
    "strTimeLocal",
    "strTimeUTC",
)
LEAGUE_NAMES = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    5479: "Rugby Union International Friendlies",
}


def default_season(today: Optional[date] = None) -> str:
    d = today or date.today()
    if d.month >= 8:
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def parse_event_date(event: Dict[str, Any]) -> Optional[date]:
    date_candidates = (
        event.get("dateEvent"),
        event.get("dateEventLocal"),
        event.get("strTimestamp"),
        event.get("dateEventTimestamp"),
    )
    for candidate in date_candidates:
        if not candidate:
            continue
        raw = str(candidate).strip()
        if len(raw) < 10:
            continue
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def parse_score(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "null":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def is_upcoming(event: Dict[str, Any], today: date) -> bool:
    event_date = parse_event_date(event)
    if event_date is None or event_date < today:
        return False
    home_score = parse_score(event.get("intHomeScore"))
    away_score = parse_score(event.get("intAwayScore"))
    return home_score is None and away_score is None


def has_meaningful_time(raw: Any) -> bool:
    if raw is None:
        return False
    s = str(raw).strip()
    if not s:
        return False
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    if not m:
        return False
    hh = int(m.group(1))
    mm = int(m.group(2))
    return not (hh == 0 and mm == 0)


def kickoff_source(event: Dict[str, Any]) -> Tuple[str, str]:
    for field in TIME_FIELDS:
        v = event.get(field)
        if has_meaningful_time(v):
            return field, str(v)

    date_event = event.get("dateEvent")
    if date_event:
        if has_meaningful_time(event.get("strTime")):
            return "dateEvent+strTime", f"{date_event} {event.get('strTime')}"
        if has_meaningful_time(event.get("strTimeLocal")):
            return "dateEvent+strTimeLocal", f"{date_event} {event.get('strTimeLocal')}"

    return "", ""


def event_label(event: Dict[str, Any]) -> str:
    d = parse_event_date(event)
    date_part = d.isoformat() if d else str(event.get("dateEvent") or event.get("dateEventLocal") or "UnknownDate")
    home = event.get("strHomeTeam") or "Unknown Home"
    away = event.get("strAwayTeam") or "Unknown Away"
    return f"{date_part} | {home} vs {away}"


def fetch_events(
    base_url: str,
    api_key: str,
    endpoint: str,
    params: Dict[str, Any],
    timeout_sec: int = 30,
) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/{api_key}/{endpoint}.php"
    try:
        resp = requests.get(url, params=params, timeout=timeout_sec)
    except requests.RequestException as exc:
        print(f"[ERR] {endpoint}: request failed: {exc}")
        return []

    if resp.status_code != 200:
        print(f"[ERR] {endpoint}: HTTP {resp.status_code}")
        return []

    try:
        payload = resp.json()
    except ValueError:
        print(f"[ERR] {endpoint}: response is not valid JSON")
        return []

    events = payload.get("events") or []
    if not isinstance(events, list):
        print(f"[WARN] {endpoint}: 'events' is not a list")
        return []
    return events


def dedupe_events(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_id: Dict[str, Dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("idEvent") or "").strip()
        if not event_id:
            # Keep no-id events by synthetic key to avoid losing data.
            synthetic_key = f"noid::{event.get('dateEvent')}::{event.get('strHomeTeam')}::{event.get('strAwayTeam')}"
            best_by_id[synthetic_key] = event
            continue

        existing = best_by_id.get(event_id)
        if existing is None:
            best_by_id[event_id] = event
            continue

        existing_score = sum(1 for f in TIME_FIELDS if existing.get(f))
        current_score = sum(1 for f in TIME_FIELDS if event.get(f))
        if current_score > existing_score:
            best_by_id[event_id] = event
    return list(best_by_id.values())


def print_endpoint_summary(endpoint: str, events: List[Dict[str, Any]], today: date, sample_limit: int) -> None:
    upcoming = [e for e in events if is_upcoming(e, today)]
    with_time: List[Tuple[Dict[str, Any], str, str]] = []
    missing_time: List[Dict[str, Any]] = []

    for event in upcoming:
        source, value = kickoff_source(event)
        if source:
            with_time.append((event, source, value))
        else:
            missing_time.append(event)

    pct = (len(with_time) / len(upcoming) * 100.0) if upcoming else 0.0
    print(f"\n[{endpoint}]")
    print(f"  total events: {len(events)}")
    print(f"  upcoming events (no scores): {len(upcoming)}")
    print(f"  upcoming with kickoff time: {len(with_time)} ({pct:.1f}%)")
    print(f"  upcoming missing kickoff time: {len(missing_time)}")

    if with_time:
        print(f"  sample WITH kickoff (up to {sample_limit}):")
        for event, source, value in with_time[:sample_limit]:
            print(f"    [OK] {event_label(event)} | {source}={value}")

    if missing_time:
        print(f"  sample MISSING kickoff (up to {sample_limit}):")
        for event in missing_time[:sample_limit]:
            raw_fields = ", ".join(f"{f}={repr(event.get(f))}" for f in TIME_FIELDS)
            print(f"    [WARN] {event_label(event)} | {raw_fields}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether TheSportsDB returns kickoff times for fixtures."
    )
    parser.add_argument("--league-id", type=int, default=4414, help="TheSportsDB league ID (default: 4414).")
    parser.add_argument("--season", default=default_season(), help="Season string for eventsseason (default: current rugby season).")
    parser.add_argument(
        "--endpoints",
        default="eventsseason,eventsnextleague",
        help="Comma-separated endpoints to query (default: eventsseason,eventsnextleague).",
    )
    parser.add_argument("--sample-limit", type=int, default=8, help="How many sample fixtures to print per category.")
    parser.add_argument("--api-key", default=os.getenv("THESPORTSDB_API_KEY", "123"), help="TheSportsDB API key (default: env THESPORTSDB_API_KEY or 123).")
    parser.add_argument("--base-url", default=os.getenv("THESPORTSDB_BASE_URL", DEFAULT_BASE_URL), help="TheSportsDB base URL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    league_name = LEAGUE_NAMES.get(args.league_id, f"League {args.league_id}")
    today = date.today()
    endpoints = [e.strip() for e in args.endpoints.split(",") if e.strip()]
    if not endpoints:
        print("[ERR] No endpoints provided.")
        return 2

    print("=" * 88)
    print("TheSportsDB Kickoff Time Check")
    print("=" * 88)
    print(f"League: {league_name} ({args.league_id})")
    print(f"Season: {args.season}")
    print(f"Date:   {today.isoformat()}")
    print(f"API:    {args.base_url.rstrip('/')}/<key>/<endpoint>.php")
    print(f"Key:    {args.api_key[:4]}*** (len={len(args.api_key)})")
    print(f"Calls:  {', '.join(endpoints)}")

    all_events: List[Dict[str, Any]] = []

    for endpoint in endpoints:
        params: Dict[str, Any] = {"id": args.league_id}
        if endpoint == "eventsseason":
            params["s"] = args.season
        events = fetch_events(args.base_url, args.api_key, endpoint, params)
        print_endpoint_summary(endpoint, events, today, args.sample_limit)
        all_events.extend(events)

    deduped = dedupe_events(all_events)
    upcoming = [e for e in deduped if is_upcoming(e, today)]
    with_time = [e for e in upcoming if kickoff_source(e)[0]]
    missing_time = [e for e in upcoming if not kickoff_source(e)[0]]

    print("\n" + "=" * 88)
    print("Combined (deduped by idEvent)")
    print("=" * 88)
    pct = (len(with_time) / len(upcoming) * 100.0) if upcoming else 0.0
    print(f"Unique events across endpoints: {len(deduped)}")
    print(f"Upcoming events (no scores):    {len(upcoming)}")
    print(f"Upcoming with kickoff time:     {len(with_time)} ({pct:.1f}%)")
    print(f"Upcoming missing kickoff time:  {len(missing_time)}")

    if upcoming and len(with_time) == 0:
        print(
            "\n[WARN] Result: API responses appear to be date-only for upcoming fixtures "
            "(or time fields are empty/midnight)."
        )
        return 1

    print("\n[OK] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
