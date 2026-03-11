#!/usr/bin/env python3
"""
Overwrite local URC events in SQLite from API-Sports Rugby.

This script DELETES all rows in `event` for local URC league_id (default 4446),
then inserts fresh rows from API-Sports URC league_id (default 76) by season.

Usage:
  python .\override_urc_games_from_apisports.py --api-key YOUR_KEY
  python .\override_urc_games_from_apisports.py --api-key YOUR_KEY --start-season 2008 --end-season 2026
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore


def _default_db_path() -> Path:
    root = Path(__file__).resolve().parent
    p_main = root / "data.sqlite"
    if p_main.exists():
        return p_main
    return root / "rugby-ai-predictor" / "data.sqlite"


def _load_local_env_files() -> None:
    if load_dotenv is None:
        return
    root = Path(__file__).resolve().parent
    for p in (root / ".env", root / "rugby-ai-predictor" / ".env"):
        if p.exists():
            load_dotenv(dotenv_path=p, override=False)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _get_or_create_team_id(conn: sqlite3.Connection, team_name: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM team WHERE name = ? ORDER BY id ASC LIMIT 1", (team_name,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    cur.execute("INSERT INTO team (name) VALUES (?)", (team_name,))
    return int(cur.lastrowid)


def _fetch_season_games(
    session: requests.Session,
    api_key: str,
    apisports_league_id: int,
    season: int,
) -> List[Dict[str, Any]]:
    resp = session.get(
        "https://v1.rugby.api-sports.io/games",
        headers={"x-apisports-key": api_key},
        params={"league": apisports_league_id, "season": season},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} season={season}: {resp.text[:200]}")
    payload = resp.json() if resp.content else {}
    errors = payload.get("errors")
    if errors:
        # Surface plan or query issues immediately.
        raise RuntimeError(f"API error season={season}: {errors}")
    return payload.get("response") or []


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        if len(text) >= 10:
            try:
                return datetime.strptime(text[:10], "%Y-%m-%d")
            except Exception:
                return None
        return None


def main() -> int:
    _load_local_env_files()
    parser = argparse.ArgumentParser(description="Overwrite URC local games from API-Sports Rugby.")
    parser.add_argument("--api-key", default=None, help="API-Sports rugby key")
    parser.add_argument("--db", default=None, help="SQLite DB path (default: auto detect)")
    parser.add_argument("--local-league-id", type=int, default=4446, help="Local URC league_id in event table")
    parser.add_argument("--api-league-id", type=int, default=76, help="API-Sports URC league id")
    parser.add_argument("--start-season", type=int, default=2008)
    parser.add_argument("--end-season", type=int, default=2026)
    parser.add_argument("--max-requests", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = (
        args.api_key
        or os.getenv("APISPORTS_RUGBY_KEY", "")
        or os.getenv("APISPORTS_API_KEY", "")
    ).strip()
    if not api_key:
        print("Missing API key. Set APISPORTS_RUGBY_KEY once in .env (or pass --api-key).")
        return 2

    if args.end_season < args.start_season:
        print("end-season must be >= start-season")
        return 2

    db_path = Path(args.db) if args.db else _default_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 2

    seasons = list(range(args.start_season, args.end_season + 1))
    if len(seasons) > args.max_requests:
        print(f"Would exceed request budget: seasons={len(seasons)} > max-requests={args.max_requests}")
        return 2

    session = requests.Session()
    staged_rows: List[Dict[str, Any]] = []
    request_used = 0

    print("=" * 100)
    print(
        f"Pulling API-Sports URC history | api_league_id={args.api_league_id} | "
        f"seasons {args.start_season}..{args.end_season}"
    )
    print("=" * 100)

    for season in seasons:
        rows = _fetch_season_games(session, api_key, args.api_league_id, season)
        request_used += 1
        print(f"season={season}: fetched {len(rows)} rows (requests used: {request_used})")
        for r in rows:
            dt = _parse_dt(r.get("date"))
            if not dt:
                continue
            teams = r.get("teams") or {}
            home_name = str((teams.get("home") or {}).get("name") or "").strip()
            away_name = str((teams.get("away") or {}).get("name") or "").strip()
            if not home_name or not away_name:
                continue
            scores = r.get("scores") or {}
            status = r.get("status") or {}
            staged_rows.append(
                {
                    "season": f"{season}-{season + 1}",
                    "date_event": dt.date().isoformat(),
                    "timestamp": dt.isoformat(),
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_score": scores.get("home"),
                    "away_score": scores.get("away"),
                    "status": status.get("short") or status.get("long"),
                }
            )

    # De-duplicate by date + teams (source sometimes repeats in edge cases).
    dedup: Dict[tuple, Dict[str, Any]] = {}
    for row in staged_rows:
        key = (row["date_event"], row["home_team"], row["away_team"])
        dedup[key] = row
    rows_final = list(dedup.values())
    completed = sum(1 for r in rows_final if r["home_score"] is not None and r["away_score"] is not None)
    print(f"Fetched rows: {len(staged_rows)} | unique fixtures: {len(rows_final)} | completed: {completed}")

    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM event WHERE league_id = ?", (args.local_league_id,))
    before_count = int(cur.fetchone()["c"])

    if args.dry_run:
        print(f"[dry-run] DB unchanged. Existing URC rows: {before_count}")
        conn.close()
        return 0

    try:
        conn.execute("BEGIN")
        cur.execute("DELETE FROM event WHERE league_id = ?", (args.local_league_id,))
        inserted = 0
        for row in rows_final:
            home_id = _get_or_create_team_id(conn, row["home_team"])
            away_id = _get_or_create_team_id(conn, row["away_team"])
            cur.execute(
                """
                INSERT INTO event (league_id, season, date_event, timestamp, home_team_id, away_team_id, home_score, away_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.local_league_id,
                    row["season"],
                    row["date_event"],
                    row["timestamp"],
                    home_id,
                    away_id,
                    row["home_score"],
                    row["away_score"],
                    row["status"],
                ),
            )
            inserted += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.execute("SELECT COUNT(*) AS c FROM event WHERE league_id = ?", (args.local_league_id,))
        after_count = int(cur.fetchone()["c"])
        conn.close()

    print("=" * 100)
    print(f"DB overwrite complete for league_id={args.local_league_id}")
    print(f"Before rows: {before_count}")
    print(f"Inserted rows: {inserted}")
    print(f"After rows:  {after_count}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

