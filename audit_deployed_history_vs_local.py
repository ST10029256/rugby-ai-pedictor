#!/usr/bin/env python3
"""
Compare LOCAL DB (data.sqlite) vs DEPLOYED history endpoint year_summary for a given year.

This answers:
- "My midnight pipeline updates my local DB, but does the deployed Firebase Function see it?"
- "Why does the UI show 0 completed for 2026 when local DB has completed matches?"

Usage:
  python .\\audit_deployed_history_vs_local.py --year 2026
  python .\\audit_deployed_history_vs_local.py --db .\\data.sqlite --year 2026
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.request
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

HISTORY_REPLAY_URL = "https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_historical_predictions_http"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def local_counts(conn: sqlite3.Connection, league_id: int, year: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(1) AS total,
          SUM(CASE WHEN home_score IS NOT NULL AND away_score IS NOT NULL THEN 1 ELSE 0 END) AS completed
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
    return total, completed


def post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit deployed history endpoint vs local DB counts")
    ap.add_argument("--db", default="data.sqlite", help="Path to local DB (default: data.sqlite)")
    ap.add_argument("--year", default=str(datetime.now().year), help="Calendar year YYYY (default: current year)")
    ap.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default: 30)")
    args = ap.parse_args()

    db_path = args.db
    year = str(args.year).strip()

    if not os.path.exists(db_path):
        print(f"❌ Local DB not found: {db_path}")
        return 2

    conn = _connect(db_path)

    print("=" * 110)
    print(f"Audit LOCAL vs DEPLOYED history (year={year})")
    print(f"Local DB: {os.path.abspath(db_path)}")
    print(f"Deployed: {HISTORY_REPLAY_URL}")
    print("=" * 110)
    print(f"{'League':36} {'ID':>6} {'LocalCompleted':>14} {'DeployedCompleted':>16} {'Status':>10}")
    print("-" * 110)

    mismatches = 0

    for league_id, league_name in LEAGUES.items():
        local_total, local_completed = local_counts(conn, league_id, year)
        deployed_completed = None
        status = "OK"

        try:
            # limit=1 keeps the endpoint cheap; year_summary is computed independently.
            res = post_json(HISTORY_REPLAY_URL, {"league_id": league_id, "limit": 1}, timeout=args.timeout)
            ys = res.get("year_summary") or {}
            entry = ys.get(year) or {}
            deployed_completed = entry.get("completed", 0)
        except Exception as e:
            status = "FAIL"
            deployed_completed = f"ERR"

        if isinstance(deployed_completed, int):
            if deployed_completed != local_completed:
                status = "MISMATCH"
                mismatches += 1
        else:
            mismatches += 1

        print(f"{league_name[:36]:36} {league_id:>6} {local_completed:>14} {str(deployed_completed):>16} {status:>10}")

    print("-" * 110)
    if mismatches:
        print(f"WARNING: Mismatches found: {mismatches}")
        print("This usually means your midnight pipeline updates LOCAL data.sqlite, but the DEPLOYED Cloud Function is using a different DB snapshot.")
        print("To fix: run your update pipeline on the deploy machine AND redeploy, or change the function to download the DB from Storage/Firestore on each run.")
    else:
        print("✅ No mismatches detected.")
    print("=" * 110)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

