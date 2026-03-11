#!/usr/bin/env python3
"""
API-Sports rugby history pull with request-budget guard.

This script fetches games season-by-season (not per game), counts completed rows,
and enforces a hard request cap so you stay under a chosen budget.

Usage:
  python .\check_urc_apisports_history.py --api-key YOUR_KEY --league-id 16
  python .\check_urc_apisports_history.py --league-id 16 --start-season 2008 --end-season 2026

Env var alternative:
  set APISPORTS_RUGBY_KEY=YOUR_KEY
  python .\check_urc_apisports_history.py --league-id 16
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "https://v1.rugby.api-sports.io"


@dataclass
class SeasonStats:
    season: int
    total: int
    completed: int
    unscored: int
    requests: int
    note: str = ""


def _completed(game: Dict[str, Any]) -> bool:
    score = game.get("scores") or {}
    home = score.get("home")
    away = score.get("away")
    return home is not None and away is not None


def _pull_season(
    session: requests.Session,
    api_key: str,
    league_id: int,
    season: int,
    max_requests: int,
    request_counter: List[int],
    timeout_s: int = 25,
) -> SeasonStats:
    if request_counter[0] >= max_requests:
        raise RuntimeError(
            f"Request budget exceeded before finishing season {season}. "
            f"Used={request_counter[0]}, max={max_requests}."
        )

    # Rugby API does not accept page for this endpoint on this plan.
    resp = session.get(
        f"{BASE_URL}/games",
        headers={"x-apisports-key": api_key},
        params={"league": league_id, "season": season},
        timeout=timeout_s,
    )
    request_counter[0] += 1

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for season {season}: {resp.text[:250]}")

    data = resp.json() if resp.content else {}
    response_rows = data.get("response") or []
    errors = data.get("errors")
    note = ""
    if isinstance(errors, dict) and errors:
        note = "; ".join(f"{k}={v}" for k, v in errors.items())
    elif isinstance(errors, list) and errors:
        note = "; ".join(str(x) for x in errors)
    elif isinstance(errors, str) and errors:
        note = errors

    completed_count = sum(1 for g in response_rows if _completed(g))
    total_count = len(response_rows)
    return SeasonStats(
        season=season,
        total=total_count,
        completed=completed_count,
        unscored=total_count - completed_count,
        requests=1,
        note=note,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch rugby history from API-Sports with request cap.")
    parser.add_argument("--api-key", default=os.getenv("APISPORTS_RUGBY_KEY", ""), help="API-Sports rugby key")
    parser.add_argument("--league-id", type=int, required=True, help="API-Sports league id (URC id in API-Sports)")
    parser.add_argument("--start-season", type=int, default=2008, help="Start season year (default: 2008)")
    parser.add_argument("--end-season", type=int, default=datetime.now().year, help="End season year inclusive")
    parser.add_argument("--max-requests", type=int, default=100, help="Hard request cap (default: 100)")
    args = parser.parse_args()

    if not args.api_key:
        print("Missing API key. Pass --api-key or set APISPORTS_RUGBY_KEY.")
        return 2
    if args.end_season < args.start_season:
        print("end-season must be >= start-season")
        return 2
    if args.max_requests <= 0:
        print("max-requests must be > 0")
        return 2

    print("=" * 96)
    print(
        f"API-Sports history check | league_id={args.league_id} | "
        f"seasons {args.start_season}..{args.end_season} | max_requests={args.max_requests}"
    )
    print("=" * 96)
    print(f"{'Season':>8} {'Total':>8} {'Completed':>10} {'NoScore':>8} {'Req':>5} {'ReqUsed':>8} {'Note':<40}")
    print("-" * 96)

    session = requests.Session()
    used = [0]
    grand_total = 0
    grand_completed = 0
    grand_unscored = 0

    try:
        for season in range(args.start_season, args.end_season + 1):
            stats = _pull_season(
                session=session,
                api_key=args.api_key,
                league_id=args.league_id,
                season=season,
                max_requests=args.max_requests,
                request_counter=used,
            )
            grand_total += stats.total
            grand_completed += stats.completed
            grand_unscored += stats.unscored
            print(
                f"{stats.season:>8} {stats.total:>8} {stats.completed:>10} "
                f"{stats.unscored:>8} {stats.requests:>5} {used[0]:>8} {stats.note[:40]:<40}"
            )
    except Exception as exc:
        print("-" * 96)
        print(f"STOPPED: {exc}")
        print(f"Requests used: {used[0]}/{args.max_requests}")
        return 1

    print("-" * 96)
    print(f"{'TOTAL':>8} {grand_total:>8} {grand_completed:>10} {grand_unscored:>8} {'-':>5} {used[0]:>8}")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

