#!/usr/bin/env python3
"""Fetch bookmaker odds once, centrally, for fixtures about to be played.

Odds used to be fetched per viewer: opening a league fired one `predict_match`
call for every fixture on screen, so a thousand people looking at the same round
produced a thousand times the same lookups, and two of them could see different
prices depending on when they loaded the page.

This job fetches each fixture's odds once and stores them, so the app serves one
shared set of numbers to everybody and the API is hit a fixed number of times an
hour regardless of traffic.

It deliberately does not touch predictions. The AI forecast is frozen before
kickoff and never moves; odds are a separate, refreshable layer on top.

    python scripts/refresh_match_odds.py --db data.sqlite
    python scripts/refresh_match_odds.py --db data.sqlite --hours-ahead 48
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

from prediction.sportdevs_client import SportDevsClient, extract_odds_features  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("refresh_match_odds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS match_odds (
    match_id INTEGER PRIMARY KEY,
    league_id INTEGER,
    home_odds REAL,
    away_odds REAL,
    draw_odds REAL,
    home_win_probability REAL,
    away_win_probability REAL,
    bookmaker_count INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (match_id) REFERENCES event(id) ON DELETE CASCADE
)
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_match_odds_league ON match_odds(league_id)"
    )
    conn.commit()


def upcoming_fixtures(conn: sqlite3.Connection, hours_ahead: int) -> list:
    """Fixtures kicking off within the horizon that have not been played."""
    days = max(1, (max(1, hours_ahead) + 23) // 24)
    return conn.execute(
        """
        SELECT e.id, e.league_id, e.date_event, t1.name, t2.name, e.highlightly_match_id
        FROM event e
        LEFT JOIN team t1 ON t1.id = e.home_team_id
        LEFT JOIN team t2 ON t2.id = e.away_team_id
        WHERE (e.home_score IS NULL OR e.away_score IS NULL)
          AND e.date_event IS NOT NULL
          AND date(e.date_event) BETWEEN date('now') AND date('now', ?)
        ORDER BY e.date_event ASC
        """,
        (f"+{days} days",),
    ).fetchall()


def push_to_firestore(project_id: str, updates: Dict[str, Dict[str, Any]]) -> int:
    """Write odds onto the fixture documents the app already reads.

    Only the odds fields are touched, so this cannot disturb scores or kickoff
    times written by the nightly sync.
    """
    if not updates:
        return 0

    from google.cloud import firestore

    db = firestore.Client(project=project_id)
    collection = db.collection("matches")
    batch = db.batch()
    pending = written = 0

    for doc_id, fields in updates.items():
        batch.set(collection.document(doc_id), fields, merge=True)
        pending += 1
        written += 1
        if pending >= 400:
            batch.commit()
            batch = db.batch()
            pending = 0

    if pending:
        batch.commit()
    return written


def store_odds(
    conn: sqlite3.Connection,
    match_id: int,
    league_id: Optional[int],
    features: Dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO match_odds (
            match_id, league_id, home_odds, away_odds, draw_odds,
            home_win_probability, away_win_probability, bookmaker_count, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            league_id=excluded.league_id,
            home_odds=excluded.home_odds,
            away_odds=excluded.away_odds,
            draw_odds=excluded.draw_odds,
            home_win_probability=excluded.home_win_probability,
            away_win_probability=excluded.away_win_probability,
            bookmaker_count=excluded.bookmaker_count,
            fetched_at=excluded.fetched_at
        """,
        (
            int(match_id),
            league_id,
            float(features.get("avg_home_odds") or 0) or None,
            float(features.get("avg_away_odds") or 0) or None,
            float(features.get("avg_draw_odds") or 0) or None,
            float(features.get("home_win_probability") or 0) or None,
            float(features.get("away_win_probability") or 0) or None,
            int(features.get("bookmaker_count") or 0),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data.sqlite")
    parser.add_argument(
        "--hours-ahead",
        type=int,
        default=48,
        help="Only refresh fixtures kicking off within this window (default: 48)",
    )
    parser.add_argument(
        "--push-firestore",
        action="store_true",
        help="Write the refreshed odds onto the Firestore fixture documents",
    )
    parser.add_argument("--project-id", default="rugby-ai-61fd0")
    args = parser.parse_args()

    api_key = os.getenv("SPORTDEVS_API_KEY", "") or os.getenv("HIGHLIGHTLY_API_KEY", "")
    if not api_key:
        logger.error("No odds API key set (SPORTDEVS_API_KEY / HIGHLIGHTLY_API_KEY).")
        return 1

    if not os.path.exists(args.db):
        logger.error("Database not found: %s", args.db)
        return 1

    conn = sqlite3.connect(args.db)
    ensure_schema(conn)

    fixtures = upcoming_fixtures(conn, args.hours_ahead)
    logger.info(
        "Refreshing odds for %s fixture(s) within %sh", len(fixtures), args.hours_ahead
    )
    if not fixtures:
        conn.close()
        return 0

    client = SportDevsClient(api_key=api_key)
    stored = missing = failed = 0
    firestore_updates: Dict[str, Dict[str, Any]] = {}

    for match_id, league_id, date_event, home_team, away_team, hl_match_id in fixtures:
        try:
            odds = client.get_match_odds(
                match_id=match_id,
                league_id=league_id,
                match_date=date_event,
                home_team=home_team,
                away_team=away_team,
            )
            features = extract_odds_features(odds)
            if int(features.get("bookmaker_count") or 0) <= 0:
                missing += 1
                continue
            store_odds(conn, match_id, league_id, features)
            stored += 1

            # Document ids mirror sync_to_firestore: Highlightly id when known.
            doc_id = str(hl_match_id) if hl_match_id else str(match_id)
            firestore_updates[doc_id] = {
                "odds_home": round(float(features["avg_home_odds"]), 2),
                "odds_away": round(float(features["avg_away_odds"]), 2),
                "odds_bookmaker_count": int(features["bookmaker_count"]),
                "odds_fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            failed += 1
            logger.warning(
                "Odds fetch failed for %s (%s v %s): %s",
                match_id, home_team, away_team, exc,
            )

    conn.commit()
    conn.close()

    pushed = 0
    if args.push_firestore:
        try:
            pushed = push_to_firestore(args.project_id, firestore_updates)
        except Exception as exc:
            logger.error("Firestore odds push failed: %s", exc)
            return 1

    logger.info(
        "Odds refresh complete: stored=%s no_bookmaker=%s failed=%s pushed=%s",
        stored, missing, failed, pushed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
