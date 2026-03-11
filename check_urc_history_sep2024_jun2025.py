#!/usr/bin/env python3
"""
Check URC historical games for Sep 2024 – Jun 2025 season.
Reports games by month and whether they exist in the database.
"""

import sqlite3
import os
from datetime import datetime
from collections import defaultdict

URC_LEAGUE_ID = 4446
START_DATE = "2024-09-01"
END_DATE = "2025-06-30"

# Month labels for display
MONTH_LABELS = {
    9: "Sep 2024", 10: "Oct 2024", 11: "Nov 2024", 12: "Dec 2024",
    1: "Jan 2025", 2: "Feb 2025", 3: "Mar 2025", 4: "Apr 2025",
    5: "May 2025", 6: "Jun 2025",
}


def find_db() -> str:
    """Find data.sqlite in project root or rugby-ai-predictor."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "data.sqlite"),
        os.path.join(os.path.dirname(__file__), "rugby-ai-predictor", "data.sqlite"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def check_urc_history():
    db_path = find_db()
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print("=" * 70)
    print("URC Historical Games: Sep 2024 - Jun 2025")
    print("=" * 70)
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Total count in date range
    cur.execute(
        """
        SELECT COUNT(*) FROM event
        WHERE league_id = ?
          AND date(date_event) >= date(?)
          AND date(date_event) <= date(?)
        """,
        (URC_LEAGUE_ID, START_DATE, END_DATE),
    )
    total = cur.fetchone()[0]

    # Count completed (have scores)
    cur.execute(
        """
        SELECT COUNT(*) FROM event
        WHERE league_id = ?
          AND date(date_event) >= date(?)
          AND date(date_event) <= date(?)
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        """,
        (URC_LEAGUE_ID, START_DATE, END_DATE),
    )
    completed = cur.fetchone()[0]

    print(f"Total games in range: {total}")
    print(f"Completed (with scores): {completed}")
    print(f"Upcoming/TBD: {total - completed}\n")

    # By month
    cur.execute(
        """
        SELECT
          strftime('%Y', date_event) AS year,
          strftime('%m', date_event) AS month,
          COUNT(*) AS cnt,
          SUM(CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN 1 ELSE 0 END) AS completed
        FROM event
        WHERE league_id = ?
          AND date(date_event) >= date(?)
          AND date(date_event) <= date(?)
        GROUP BY year, month
        ORDER BY year, month
        """,
        (URC_LEAGUE_ID, START_DATE, END_DATE),
    )
    rows = cur.fetchall()

    print("-" * 70)
    print("BY MONTH")
    print("-" * 70)

    by_month = {}
    for r in rows:
        y, m = int(r["year"]), int(r["month"])
        key = (y, m)
        by_month[key] = {"total": r["cnt"], "completed": r["completed"]}

    # Expected months: Sep 2024 (9), Oct–Dec 2024 (10–12), Jan–Jun 2025 (1–6)
    expected = [
        (2024, 9), (2024, 10), (2024, 11), (2024, 12),
        (2025, 1), (2025, 2), (2025, 3), (2025, 4), (2025, 5), (2025, 6),
    ]

    for (y, m) in expected:
        label = MONTH_LABELS.get(m, f"{m}/{y}")
        data = by_month.get((y, m), {"total": 0, "completed": 0})
        t, c = data["total"], data["completed"]
        status = "[OK]" if t > 0 else "[--]"
        score_status = f"({c}/{t} completed)" if t > 0 else "(no games)"
        print(f"  {status} {label}: {t} games {score_status}")

    # Sample games per month (first 2 per month)
    print("\n" + "-" * 70)
    print("SAMPLE GAMES (first 2 per month)")
    print("-" * 70)

    cur.execute(
        """
        SELECT e.id, e.date_event, e.home_score, e.away_score,
               t1.name AS home_team, t2.name AS away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = ?
          AND date(e.date_event) >= date(?)
          AND date(e.date_event) <= date(?)
        ORDER BY e.date_event ASC
        """,
        (URC_LEAGUE_ID, START_DATE, END_DATE),
    )
    all_games = cur.fetchall()

    current_month = None
    count_in_month = 0
    for g in all_games:
        dt = g["date_event"]
        if isinstance(dt, str):
            dt = dt[:10]
        try:
            d = datetime.strptime(dt[:10], "%Y-%m-%d")
            month_key = (d.year, d.month)
        except Exception:
            month_key = None

        if month_key != current_month:
            current_month = month_key
            count_in_month = 0
            label = MONTH_LABELS.get(month_key[1], f"{month_key[1]}/{month_key[0]}") if month_key else "?"
            print(f"\n  {label}:")

        if count_in_month < 2:
            home = g["home_team"] or "?"
            away = g["away_team"] or "?"
            if g["home_score"] is not None and g["away_score"] is not None:
                score = f"{g['home_score']}-{g['away_score']}"
            else:
                score = "TBD"
            print(f"    {dt[:10]}  {home} vs {away}  ({score})")
            count_in_month += 1

    conn.close()

    print("\n" + "=" * 70)
    if total == 0:
        print("WARNING: No URC games found for Sep 2024 - Jun 2025. Run enhanced_auto_update or sync.")
    else:
        print(f"Found {total} URC games ({completed} with scores)")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    exit(check_urc_history())
