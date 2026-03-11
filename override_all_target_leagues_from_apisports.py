#!/usr/bin/env python3
"""
Overwrite local rugby leagues from API-Sports using all available historical seasons.

Target local->API-Sports league mapping:
  4430 -> 16   (Top 14)
  4574 -> 69   (Rugby World Cup)
  4714 -> 51   (Six Nations)
  4414 -> 13   (Aviva/Premiership Rugby)
  4551 -> 71   (Super Rugby)
  4986 -> 85   (Rugby Championship)
  5069 -> 37   (Currie Cup)
  5479 -> 84   (Friendly International)

Behavior:
  - Pulls seasons list from /leagues?id=<api_league_id>
  - Pulls /games for each season
  - Deletes existing rows for each local league_id
  - Reinserts API-Sports rows
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


TARGETS = {
    4430: {"name": "Top 14", "api_league_id": 16},
    4574: {"name": "Rugby World Cup", "api_league_id": 69},
    4714: {"name": "Six Nations", "api_league_id": 51},
    4414: {"name": "Premiership Rugby", "api_league_id": 13},
    4551: {"name": "Super Rugby", "api_league_id": 71},
    4986: {"name": "Rugby Championship", "api_league_id": 85},
    5069: {"name": "Currie Cup", "api_league_id": 37},
    5479: {"name": "Friendly International", "api_league_id": 84},
}


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


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    txt = str(value).strip()
    try:
        return datetime.fromisoformat(txt.replace("Z", "+00:00"))
    except Exception:
        if len(txt) >= 10:
            try:
                return datetime.strptime(txt[:10], "%Y-%m-%d")
            except Exception:
                return None
        return None


def _get_or_create_team_id(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM team WHERE name = ? ORDER BY id ASC LIMIT 1", (name,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    cur.execute("INSERT INTO team (name) VALUES (?)", (name,))
    return int(cur.lastrowid)


def _api_get(session: requests.Session, api_key: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    resp = session.get(
        f"https://v1.rugby.api-sports.io/{path.lstrip('/')}",
        headers={"x-apisports-key": api_key},
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} path={path} params={params}")
    payload = resp.json() if resp.content else {}
    errs = payload.get("errors")
    if errs:
        if isinstance(errs, dict) and len(errs) == 0:
            return payload
        if isinstance(errs, list) and len(errs) == 0:
            return payload
        raise RuntimeError(f"API error path={path} params={params}: {errs}")
    return payload


def _get_seasons(session: requests.Session, api_key: str, api_league_id: int) -> List[int]:
    payload = _api_get(session, api_key, "leagues", {"id": api_league_id})
    rows = payload.get("response") or []
    if not rows:
        return []
    league = rows[0]
    seasons = league.get("seasons") or []
    out: List[int] = []
    for s in seasons:
        val = s.get("season")
        if isinstance(val, int):
            out.append(val)
    out = sorted(set(out))
    return out


def main() -> int:
    _load_local_env_files()
    parser = argparse.ArgumentParser(description="Overwrite all target leagues from API-Sports history.")
    parser.add_argument("--api-key", default=None, help="API-Sports rugby key")
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument("--max-requests", type=int, default=7500)
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

    db_path = Path(args.db) if args.db else _default_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return 2

    session = requests.Session()
    requests_used = 0
    staged: Dict[int, List[Dict[str, Any]]] = {}

    print("=" * 120)
    print("API-Sports historical pull for target leagues (all available seasons)")
    print("=" * 120)

    for local_league_id, meta in TARGETS.items():
        name = str(meta["name"])
        api_league_id = int(meta["api_league_id"])
        seasons = _get_seasons(session, api_key, api_league_id)
        requests_used += 1
        if requests_used > args.max_requests:
            print(f"Stopped: exceeded max requests ({args.max_requests})")
            return 2
        print(f"[{local_league_id}] {name}: seasons={len(seasons)} -> {seasons[:3]} ... {seasons[-3:] if seasons else []}")

        rows_for_league: List[Dict[str, Any]] = []
        for season in seasons:
            payload = _api_get(session, api_key, "games", {"league": api_league_id, "season": season})
            requests_used += 1
            if requests_used > args.max_requests:
                print(f"Stopped: exceeded max requests ({args.max_requests})")
                return 2
            rows = payload.get("response") or []
            print(f"  season={season}: {len(rows)}")
            for r in rows:
                dt = _parse_dt(r.get("date"))
                if not dt:
                    continue
                teams = r.get("teams") or {}
                home = str((teams.get("home") or {}).get("name") or "").strip()
                away = str((teams.get("away") or {}).get("name") or "").strip()
                if not home or not away:
                    continue
                scores = r.get("scores") or {}
                status = r.get("status") or {}
                rows_for_league.append(
                    {
                        "season": f"{season}-{season + 1}",
                        "date_event": dt.date().isoformat(),
                        "timestamp": dt.isoformat(),
                        "home_team": home,
                        "away_team": away,
                        "home_score": scores.get("home"),
                        "away_score": scores.get("away"),
                        "status": status.get("short") or status.get("long"),
                    }
                )

        dedup: Dict[tuple, Dict[str, Any]] = {}
        for row in rows_for_league:
            dedup[(row["date_event"], row["home_team"], row["away_team"])] = row
        staged[local_league_id] = list(dedup.values())
        completed = sum(1 for x in staged[local_league_id] if x["home_score"] is not None and x["away_score"] is not None)
        print(f"  => unique fixtures: {len(staged[local_league_id])}, completed: {completed}")

    print("-" * 120)
    print(f"Total API requests used: {requests_used}")
    if args.dry_run:
        print("[dry-run] No DB writes performed.")
        return 0

    conn = _connect(db_path)
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        for local_league_id, rows in staged.items():
            cur.execute("SELECT COUNT(*) AS c FROM event WHERE league_id = ?", (local_league_id,))
            before_count = int(cur.fetchone()["c"])
            cur.execute("DELETE FROM event WHERE league_id = ?", (local_league_id,))
            inserted = 0
            for row in rows:
                home_id = _get_or_create_team_id(conn, row["home_team"])
                away_id = _get_or_create_team_id(conn, row["away_team"])
                cur.execute(
                    """
                    INSERT INTO event (league_id, season, date_event, timestamp, home_team_id, away_team_id, home_score, away_score, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        local_league_id,
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
            print(f"[{local_league_id}] before={before_count} inserted={inserted}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("=" * 120)
    print("DB overwrite complete for all target leagues.")
    print("=" * 120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

