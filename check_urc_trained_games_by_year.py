#!/usr/bin/env python3
"""
Count URC training-eligible games by year.

This mirrors the V4 training data filters:
- home_team_id is not null
- away_team_id is not null
- date_event is not null
- home_score is not null
- away_score is not null

Usage:
  python .\check_urc_trained_games_by_year.py
  python .\check_urc_trained_games_by_year.py --league-id 4446
  python .\check_urc_trained_games_by_year.py --db .\data.sqlite
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_URC_LEAGUE_ID = 4446


def _default_db_path() -> Path:
    root = Path(__file__).resolve().parent
    p_main = root / "data.sqlite"
    if p_main.exists():
        return p_main
    p_alt = root / "rugby-ai-predictor" / "data.sqlite"
    return p_alt


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _print_rows(rows: Iterable[sqlite3.Row]) -> int:
    total = 0
    print("-" * 36)
    print(f"{'Year':>8} {'Games':>10}")
    print("-" * 36)
    for row in rows:
        year = str(row["year"])
        games = int(row["games"] or 0)
        total += games
        print(f"{year:>8} {games:>10}")
    print("-" * 36)
    print(f"{'TOTAL':>8} {total:>10}")
    print("-" * 36)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Count URC training-eligible games by year.")
    parser.add_argument("--db", default=None, help="Path to SQLite DB (default: auto-detect)")
    parser.add_argument("--league-id", type=int, default=DEFAULT_URC_LEAGUE_ID, help="League ID (default: 4446 for URC)")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else _default_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 2

    conn = _connect(db_path)
    cur = conn.cursor()

    # Exact filter parity with training table construction + completed rows.
    cur.execute(
        """
        SELECT
            substr(date_event, 1, 4) AS year,
            COUNT(*) AS games
        FROM event
        WHERE league_id = ?
          AND home_team_id IS NOT NULL
          AND away_team_id IS NOT NULL
          AND date_event IS NOT NULL
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        GROUP BY substr(date_event, 1, 4)
        ORDER BY year ASC
        """,
        (args.league_id,),
    )
    rows = cur.fetchall()

    print("=" * 72)
    print(f"Training-eligible game counts by year | league_id={args.league_id}")
    print(f"DB: {os.path.abspath(str(db_path))}")
    print("=" * 72)
    if not rows:
        print("No training-eligible games found for this league.")
        conn.close()
        return 0

    _print_rows(rows)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

