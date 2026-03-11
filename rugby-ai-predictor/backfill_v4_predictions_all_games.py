"""
One-time backfill for V4 prediction snapshots across all completed matches.

Usage:
  python backfill_v4_predictions_all_games.py --db data.sqlite
  python backfill_v4_predictions_all_games.py --db data.sqlite --league-id 4446
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional
import types

from prediction.hybrid_predictor import MultiLeaguePredictor
from prediction.db import connect
from prediction.sportdevs_client import SportDevsClient


def get_model_version() -> str:
    explicit = str(os.getenv("LIVE_MODEL_VERSION", "")).strip()
    if explicit:
        return explicit
    family = str(os.getenv("LIVE_MODEL_FAMILY", "v4")).strip() or "v4"
    channel = str(os.getenv("LIVE_MODEL_CHANNEL", "prod_100")).strip() or "prod_100"
    return f"{family}:{channel}"


def ensure_prediction_snapshot_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            league_id INTEGER,
            model_version TEXT NOT NULL,
            snapshot_type TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            kickoff_at TEXT,
            home_team TEXT,
            away_team TEXT,
            predicted_winner TEXT,
            predicted_home_score REAL,
            predicted_away_score REAL,
            confidence REAL,
            home_win_prob REAL,
            away_win_prob REAL,
            actual_home_score INTEGER,
            actual_away_score INTEGER,
            actual_winner TEXT,
            prediction_correct INTEGER,
            score_error REAL,
            source_note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_id, model_version, snapshot_type)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_match ON prediction_snapshot(match_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_league ON prediction_snapshot(league_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_model ON prediction_snapshot(model_version, snapshot_type)")
    conn.commit()


def upsert_snapshot(
    conn: sqlite3.Connection,
    *,
    match_id: int,
    league_id: Optional[int],
    model_version: str,
    predicted_at: str,
    kickoff_at: Optional[str],
    home_team: str,
    away_team: str,
    predicted_winner: Optional[str],
    predicted_home_score: Optional[float],
    predicted_away_score: Optional[float],
    confidence: Optional[float],
    home_win_prob: Optional[float],
    away_win_prob: Optional[float],
    actual_home_score: Optional[int],
    actual_away_score: Optional[int],
    actual_winner: Optional[str],
    prediction_correct: Optional[int],
    score_error: Optional[float],
) -> None:
    conn.execute(
        """
        INSERT INTO prediction_snapshot (
            match_id, league_id, model_version, snapshot_type, predicted_at, kickoff_at,
            home_team, away_team, predicted_winner, predicted_home_score, predicted_away_score,
            confidence, home_win_prob, away_win_prob, actual_home_score, actual_away_score,
            actual_winner, prediction_correct, score_error, source_note, updated_at
        ) VALUES (?, ?, ?, 'historical_backfill', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(match_id, model_version, snapshot_type)
        DO UPDATE SET
            league_id=excluded.league_id,
            predicted_at=excluded.predicted_at,
            kickoff_at=excluded.kickoff_at,
            home_team=excluded.home_team,
            away_team=excluded.away_team,
            predicted_winner=excluded.predicted_winner,
            predicted_home_score=excluded.predicted_home_score,
            predicted_away_score=excluded.predicted_away_score,
            confidence=excluded.confidence,
            home_win_prob=excluded.home_win_prob,
            away_win_prob=excluded.away_win_prob,
            actual_home_score=excluded.actual_home_score,
            actual_away_score=excluded.actual_away_score,
            actual_winner=excluded.actual_winner,
            prediction_correct=excluded.prediction_correct,
            score_error=excluded.score_error,
            source_note=excluded.source_note,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            match_id,
            league_id,
            model_version,
            predicted_at,
            kickoff_at,
            home_team,
            away_team,
            predicted_winner,
            predicted_home_score,
            predicted_away_score,
            confidence,
            home_win_prob,
            away_win_prob,
            actual_home_score,
            actual_away_score,
            actual_winner,
            prediction_correct,
            score_error,
            "one_time_backfill_all_completed_matches",
        ),
    )


def get_actual_winner(home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "Home"
    if away_score > home_score:
        return "Away"
    return "Draw"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill V4 snapshots for all completed matches.")
    parser.add_argument("--db", default="data.sqlite", help="Path to SQLite DB")
    parser.add_argument("--model-version", default=get_model_version(), help="Model version tag to write")
    parser.add_argument("--league-id", type=int, default=None, help="Optional league filter")
    parser.add_argument("--batch-size", type=int, default=250, help="Commit interval")
    parser.add_argument("--max-matches", type=int, default=0, help="Optional cap for testing")
    parser.add_argument(
        "--with-odds",
        action="store_true",
        help="Enable live bookmaker odds lookups (disabled by default for stable offline backfill).",
    )
    args = parser.parse_args()

    if not args.with_odds:
        # Global kill switch for odds calls (including V4RuntimePredictor internals).
        def _offline_get_match_odds(self: Any, *args: Any, **kwargs: Any) -> dict:
            return {"data": []}

        SportDevsClient.get_match_odds = _offline_get_match_odds  # type: ignore[assignment]

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = connect(db_path)
    ensure_prediction_snapshot_table(conn)
    cur = conn.cursor()

    sql = """
        SELECT
            e.id,
            e.league_id,
            e.date_event,
            e.timestamp,
            t1.name as home_team,
            t2.name as away_team,
            e.home_score,
            e.away_score,
            l.name as league_name
        FROM event e
        LEFT JOIN team t1 ON t1.id = e.home_team_id
        LEFT JOIN team t2 ON t2.id = e.away_team_id
        LEFT JOIN league l ON l.id = e.league_id
        WHERE e.home_score IS NOT NULL
          AND e.away_score IS NOT NULL
          AND e.date_event IS NOT NULL
          AND date(e.date_event) <= date('now')
    """
    params: list[Any] = []
    if args.league_id is not None:
        sql += " AND e.league_id = ?"
        params.append(args.league_id)
    sql += " ORDER BY e.date_event ASC, e.id ASC"
    if args.max_matches and args.max_matches > 0:
        sql += " LIMIT ?"
        params.append(args.max_matches)

    cur.execute(sql, params)
    rows = cur.fetchall()
    total = len(rows)
    if total == 0:
        print("No completed matches found.")
        conn.close()
        return

    storage_bucket = os.getenv("MODEL_STORAGE_BUCKET", "rugby-ai-61fd0.firebasestorage.app")
    predictor = MultiLeaguePredictor(
        db_path=db_path,
        sportdevs_api_key=(os.getenv("SPORTDEVS_API_KEY", "") if args.with_odds else ""),
        artifacts_dir="artifacts",
        storage_bucket=storage_bucket,
    )

    if not args.with_odds:
        # Hard-disable bookmaker API calls for deterministic offline backfill.
        def _no_odds(_self: Any, _match_id: int) -> dict:
            return {
                "home_win_prob": 0.5,
                "away_win_prob": 0.5,
                "draw_prob": 0.0,
                "confidence": 0.5,
                "bookmaker_count": 0,
            }

        predictor_map = getattr(predictor, "_predictors", None)
        if predictor_map is None:
            predictor_map = getattr(predictor, "predictors", None)
        if predictor_map is None:
            predictor_map = {}

        for _league_id, _pred in predictor_map.items():
            try:
                _pred.get_bookmaker_prediction = types.MethodType(_no_odds, _pred)
                _pred.sportdevs_client = None
            except Exception:
                pass

    processed = 0
    failed = 0
    for row in rows:
        (
            match_id,
            league_id,
            date_event,
            kickoff_ts,
            home_team,
            away_team,
            home_score,
            away_score,
            _league_name,
        ) = row
        processed += 1

        if not home_team or not away_team:
            failed += 1
            continue

        try:
            # Historical backfill should be deterministic and not depend on external APIs.
            # Passing match_id=None keeps predictor in AI-only mode (no live odds fetch).
            match_id_for_prediction = int(match_id) if args.with_odds else None
            pred = predictor.predict_match(
                home_team=home_team,
                away_team=away_team,
                league_id=int(league_id),
                match_date=str(date_event),
                match_id=match_id_for_prediction,
            )
            predicted_winner = pred.get("predicted_winner")
            predicted_home_score = pred.get("predicted_home_score")
            predicted_away_score = pred.get("predicted_away_score")
            actual_winner = get_actual_winner(home_score, away_score)

            prediction_correct: Optional[int] = None
            if predicted_winner in {"Home", "Away", "Draw"} and actual_winner is not None:
                prediction_correct = 1 if predicted_winner == actual_winner else 0

            score_error: Optional[float] = None
            if predicted_home_score is not None and predicted_away_score is not None:
                score_error = abs(float(predicted_home_score) - float(home_score)) + abs(float(predicted_away_score) - float(away_score))

            upsert_snapshot(
                conn,
                match_id=int(match_id),
                league_id=int(league_id) if league_id is not None else None,
                model_version=args.model_version,
                predicted_at=datetime.now(timezone.utc).isoformat(),
                kickoff_at=(str(kickoff_ts) if kickoff_ts else str(date_event)),
                home_team=str(home_team),
                away_team=str(away_team),
                predicted_winner=(str(predicted_winner) if predicted_winner is not None else None),
                predicted_home_score=(float(predicted_home_score) if predicted_home_score is not None else None),
                predicted_away_score=(float(predicted_away_score) if predicted_away_score is not None else None),
                confidence=(float(pred.get("confidence")) if pred.get("confidence") is not None else None),
                home_win_prob=(float(pred.get("home_win_prob")) if pred.get("home_win_prob") is not None else None),
                away_win_prob=(float(pred.get("away_win_prob")) if pred.get("away_win_prob") is not None else None),
                actual_home_score=(int(home_score) if home_score is not None else None),
                actual_away_score=(int(away_score) if away_score is not None else None),
                actual_winner=actual_winner,
                prediction_correct=prediction_correct,
                score_error=score_error,
            )
        except Exception as exc:
            failed += 1
            print(f"[WARN] match_id={match_id} failed: {exc}")

        if processed % max(1, args.batch_size) == 0:
            conn.commit()
            print(f"Progress: {processed}/{total} processed, failed={failed}")

    conn.commit()

    print("\nBackfill complete.")
    print(f"Processed: {processed}")
    print(f"Failed:    {failed}")
    print(f"Model:     {args.model_version}")

    summary_sql = """
        SELECT
            COALESCE(l.name, 'League ' || CAST(s.league_id AS TEXT)) AS league_name,
            s.league_id,
            COUNT(1) AS total_games,
            SUM(CASE WHEN s.prediction_correct = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN s.prediction_correct = 0 THEN 1 ELSE 0 END) AS losses,
            AVG(s.score_error) AS mae
        FROM prediction_snapshot s
        LEFT JOIN league l ON l.id = s.league_id
        WHERE s.model_version = ?
          AND s.snapshot_type = 'historical_backfill'
    """
    summary_params: list[Any] = [args.model_version]
    if args.league_id is not None:
        summary_sql += " AND s.league_id = ?"
        summary_params.append(args.league_id)
    summary_sql += " GROUP BY s.league_id, league_name ORDER BY total_games DESC, league_name ASC"

    cur.execute(summary_sql, summary_params)
    league_rows = cur.fetchall()

    print("\nPer-league results (historical_backfill):")
    print("league_id | league_name | games | wins | losses | accuracy | mae")
    for league_name, league_id, games, wins, losses, mae in league_rows:
        games_i = int(games or 0)
        wins_i = int(wins or 0)
        losses_i = int(losses or 0)
        acc = (wins_i / games_i * 100.0) if games_i > 0 else 0.0
        mae_val = float(mae) if mae is not None else None
        mae_text = f"{mae_val:.2f}" if mae_val is not None else "N/A"
        print(f"{league_id} | {league_name} | {games_i} | {wins_i} | {losses_i} | {acc:.2f}% | {mae_text}")

    conn.close()


if __name__ == "__main__":
    main()

