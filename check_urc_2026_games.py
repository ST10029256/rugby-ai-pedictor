#!/usr/bin/env python3
"""
Check URC matches for a given calendar year (default: 2026) from the local SQLite DB.

This script is designed to answer: "Do I have 2026 URC games stored, and are they completed (scores present) yet?"

Usage (Windows / PowerShell):
  python .\check_urc_2026_games.py
  python .\check_urc_2026_games.py --year 2026
  python .\check_urc_2026_games.py --db .\data.sqlite --limit 50
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections import Counter
from datetime import datetime


DEFAULT_LEAGUE_ID = 4446  # United Rugby Championship (SportsDB)


def _fmt_score(v):
    return "?" if v is None else str(v)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> int:
    ap = argparse.ArgumentParser(description="Show URC matches for a calendar year from data.sqlite")
    ap.add_argument("--db", default="data.sqlite", help="Path to SQLite DB (default: data.sqlite)")
    ap.add_argument("--league-id", type=int, default=DEFAULT_LEAGUE_ID, help="League ID in DB (default: 4446 URC)")
    ap.add_argument("--year", default="2026", help="Calendar year (YYYY). Default: 2026")
    ap.add_argument("--limit", type=int, default=200, help="Max rows to print per section (default: 200)")
    args = ap.parse_args()

    db_path = args.db
    league_id = int(args.league_id)
    year = str(args.year).strip()

    if not os.path.exists(db_path):
        print(f"❌ DB not found: {db_path}")
        print("   Tip: run from repo root, or pass --db with a full path.")
        return 2

    conn = _connect(db_path)
    cur = conn.cursor()

    # Pull all matches for that year (completed + upcoming)
    cur.execute(
        """
        SELECT
          e.id AS match_id,
          e.league_id,
          COALESCE(l.name, 'Unknown League') AS league_name,
          e.date_event,
          e.season,
          e.round,
          e.status,
          COALESCE(t1.name, 'Unknown Home') AS home_team,
          COALESCE(t2.name, 'Unknown Away') AS away_team,
          e.home_score,
          e.away_score,
          e.venue
        FROM event e
        LEFT JOIN league l ON e.league_id = l.id
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = ?
          AND e.date_event IS NOT NULL
          AND substr(e.date_event, 1, 4) = ?
        ORDER BY e.date_event ASC, e.timestamp ASC, e.id ASC
        """,
        (league_id, year),
    )
    rows = cur.fetchall()

    total = len(rows)
    completed = [r for r in rows if r["home_score"] is not None and r["away_score"] is not None]
    upcoming = [r for r in rows if r["home_score"] is None or r["away_score"] is None]

    seasons = [str(r["season"]) for r in rows if r["season"]]
    seasons_counts = Counter(seasons)

    def _try_parse(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            return None

    dates = [r["date_event"] for r in rows if r["date_event"]]
    date_min = _try_parse(dates[0]) if dates else None
    date_max = _try_parse(dates[-1]) if dates else None

    print("=" * 92)
    print(f"URC year check (league_id={league_id}, year={year})")
    print(f"DB: {os.path.abspath(db_path)}")
    print("=" * 92)
    print(f"Total matches in {year}: {total}")
    print(f"Completed (both scores present): {len(completed)}")
    print(f"Upcoming / missing scores: {len(upcoming)}")
    if date_min or date_max:
        # Use ASCII arrow for Windows console compatibility.
        print(f"Date range: {date_min or '??'}  ->  {date_max or '??'}")
    if seasons_counts:
        seasons_str = ", ".join([f"{k} ({v})" for k, v in seasons_counts.most_common()])
        print(f"Seasons present: {seasons_str}")
    print()

    def print_section(title, items, limit, reverse=False):
        print("-" * 92)
        print(title)
        print("-" * 92)
        if not items:
            print("  (none)")
            print()
            return

        listed = list(items)
        if reverse:
            listed = list(reversed(listed))

        for i, r in enumerate(listed[:limit], start=1):
            de = r["date_event"] or "UnknownDate"
            home = r["home_team"]
            away = r["away_team"]
            hs = _fmt_score(r["home_score"])
            ays = _fmt_score(r["away_score"])
            rnd = r["round"]
            season = r["season"]
            status = r["status"]
            meta = []
            if season:
                meta.append(f"season={season}")
            if rnd is not None:
                meta.append(f"round={rnd}")
            if status:
                meta.append(f"status={status}")
            meta_str = (" | " + " ".join(meta)) if meta else ""
            print(f"{i:>3}. {de}  {home} {hs}-{ays} {away}{meta_str}")
        if len(items) > limit:
            print(f"... and {len(items) - limit} more")
        print()

    # Helpful view: latest completed + next upcoming
    print_section(f"Completed matches (latest {min(args.limit, len(completed))})", completed, args.limit, reverse=True)
    print_section(f"Upcoming / missing-score matches (next {min(args.limit, len(upcoming))})", upcoming, args.limit, reverse=False)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

