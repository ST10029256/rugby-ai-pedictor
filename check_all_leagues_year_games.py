#!/usr/bin/env python3
"""
Summarize matches for a calendar year across all configured leagues in data.sqlite.

This answers questions like:
- "Do I have any completed 2026 matches for URC/Premiership/etc?"
- "Is 2026 present but only as upcoming schedule?"

Usage:
  python .\\check_all_leagues_year_games.py
  python .\\check_all_leagues_year_games.py --year 2026 --db .\\data.sqlite
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime


LEAGUES = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_date(d: str | None):
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize league matches for a calendar year.")
    ap.add_argument("--db", default="data.sqlite", help="Path to SQLite DB (default: data.sqlite)")
    ap.add_argument("--year", default=str(datetime.now().year), help="Calendar year (YYYY). Default: current year")
    args = ap.parse_args()

    db_path = args.db
    year = str(args.year).strip()

    if not os.path.exists(db_path):
        print(f"❌ DB not found: {db_path}")
        return 2

    conn = _connect(db_path)
    cur = conn.cursor()

    print("=" * 110)
    print(f"League year summary for {year}")
    print(f"DB: {os.path.abspath(db_path)}")
    print("=" * 110)
    print(f"{'League':36} {'ID':>6} {'Total':>7} {'Completed':>10} {'Upcoming':>9} {'First':>12} {'Last':>12} {'LastCompleted':>13}")
    print("-" * 110)

    grand_total = grand_completed = grand_upcoming = 0

    for league_id, league_name in LEAGUES.items():
        cur.execute(
            """
            SELECT
              COUNT(1) AS total,
              SUM(CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN 1 ELSE 0 END) AS completed,
              MIN(date_event) AS min_date,
              MAX(date_event) AS max_date,
              MAX(CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN date_event ELSE NULL END) AS max_completed_date
            FROM event
            WHERE league_id = ?
              AND date_event IS NOT NULL
              AND substr(date_event, 1, 4) = ?
            """,
            (league_id, year),
        )
        r = cur.fetchone() or {}
        total = int(r["total"] or 0)
        completed = int(r["completed"] or 0)
        upcoming = total - completed

        min_d = _parse_date(r["min_date"])
        max_d = _parse_date(r["max_date"])
        max_c = _parse_date(r["max_completed_date"])

        grand_total += total
        grand_completed += completed
        grand_upcoming += upcoming

        print(
            f"{league_name[:36]:36} {league_id:>6} {total:>7} {completed:>10} {upcoming:>9} "
            f"{str(min_d) if min_d else '-':>12} {str(max_d) if max_d else '-':>12} {str(max_c) if max_c else '-':>13}"
        )

    print("-" * 110)
    print(f"{'TOTAL':36} {'':>6} {grand_total:>7} {grand_completed:>10} {grand_upcoming:>9}")
    print("=" * 110)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

