#!/usr/bin/env python3
"""Export per-league team rosters from SQLite for frontend offline fallback."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUGBY_PREDICTOR_ROOT = PROJECT_ROOT / "rugby-ai-predictor"

ALL_LEAGUES = [
    4986,
    4446,
    5069,
    4574,
    4551,
    4430,
    4414,
    4714,
    5479,
    5480,
]

OUT = PROJECT_ROOT / "public" / "src" / "utils" / "leagueTeamsFallback.json"


def default_db_path() -> Path:
    for candidate in (PROJECT_ROOT / "data.sqlite", RUGBY_PREDICTOR_ROOT / "data.sqlite"):
        if candidate.exists():
            return candidate
    return RUGBY_PREDICTOR_ROOT / "data.sqlite"


def teams_for_league(conn: sqlite3.Connection, league_id: int) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT t.name
        FROM team t
        JOIN event e ON t.id IN (e.home_team_id, e.away_team_id)
        WHERE e.league_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (int(league_id),),
    )
    return [str(row[0]).strip() for row in cur.fetchall() if row[0]]


def main() -> int:
    db_path = default_db_path()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    payload = {str(league_id): teams_for_league(conn, league_id) for league_id in ALL_LEAGUES}
    conn.close()

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(names) for names in payload.values())
    print(f"Wrote {total} teams across {len(payload)} leagues -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
