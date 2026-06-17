#!/usr/bin/env python3
"""
Enhanced Auto-Update Script
Pulls results and upcoming games from Highlightly for all configured leagues.
"""

import argparse
import sqlite3
import os
import sys
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rugby-ai-predictor"))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in some local setups
    load_dotenv = None  # type: ignore

try:
    from prediction.hybrid_predictor import MultiLeaguePredictor
except Exception:  # pragma: no cover
    MultiLeaguePredictor = None  # type: ignore


def _load_local_env_files() -> None:
    """Load env vars from repo-level and functions-level .env files."""
    if load_dotenv is None:
        return
    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / ".env",
        root / "rugby-ai-predictor" / ".env",
        root / "rugby-ai-predictor" / ".env.local",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p, override=True)

from prediction.highlightly_client import HighlightlyRugbyAPI
from prediction.highlightly_leagues import (
    HIGHLIGHTLY_LEAGUE_MAPPINGS,
    ensure_highlightly_match_id_column,
    fetch_games_from_highlightly,
    parse_api_key,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure API keys can be sourced from local .env files.
_load_local_env_files()

LIVE_MODEL_FAMILY = os.getenv("LIVE_MODEL_FAMILY", "v4")
LIVE_MODEL_CHANNEL = os.getenv("LIVE_MODEL_CHANNEL", "prod_100")
LIVE_MODEL_VERSION = os.getenv("LIVE_MODEL_VERSION", f"{LIVE_MODEL_FAMILY}:{LIVE_MODEL_CHANNEL}")

# Local league IDs + Highlightly league IDs (all 9 leagues)
LEAGUE_MAPPINGS = {
    our_id: {"name": name, "highlightly_id": hl_id}
    for our_id, (name, hl_id) in HIGHLIGHTLY_LEAGUE_MAPPINGS.items()
}

YEAR_SPAN_LEAGUE_IDS = {4414, 4430, 4446}  # e.g. Premiership, Top 14, URC
SINGLE_YEAR_LEAGUE_IDS = {4551, 4714, 4986, 5069, 5479, 5480}  # e.g. Super Rugby, Six Nations, etc.

# Max rounds to scan (used with --scan-rounds). These are conservative caps.
MAX_ROUNDS_BY_LEAGUE: Dict[int, int] = {
    4446: 18,  # URC (regular season + some variations; cap for scanning)
    4414: 18,  # Premiership
    4430: 26,  # Top 14
    4551: 18,  # Super Rugby (varies)
    4714: 5,   # Six Nations
    4986: 6,   # Rugby Championship
    5069: 14,  # Currie Cup (varies)
    4574: 30,  # World Cup (placeholder cap)
    5479: 30,  # Friendlies (round scanning may not help much)
    5480: 4,   # Nations Championship (short round-robin window)
}

def compute_current_seasons(sportsdb_id: int, today: Optional[datetime] = None) -> List[str]:
    """
    Compute season strings to try for upcoming fixtures.

    TheSportsDB season formats vary by competition. We try a small set to maximize coverage:
    - Year-span leagues: try the "current season" and adjacent season (helps around season boundaries)
    - Single-year leagues: try current year and previous year (some APIs lag/labeling)
    """
    now = today or datetime.utcnow()
    year = now.year
    month = now.month

    seasons: List[str] = []

    # If league isn't classified, try both styles (still only a couple calls)
    is_year_span = sportsdb_id in YEAR_SPAN_LEAGUE_IDS
    is_single_year = sportsdb_id in SINGLE_YEAR_LEAGUE_IDS
    if not is_year_span and not is_single_year:
        is_year_span = True
        is_single_year = True

    if is_year_span:
        # Rugby seasons typically run Aug/Sept -> May/June. Use Aug (8) as boundary.
        current_span = f"{year}-{year + 1}" if month >= 8 else f"{year - 1}-{year}"
        adjacent_span = f"{year - 1}-{year}" if current_span == f"{year}-{year + 1}" else f"{year}-{year + 1}"
        seasons.extend([current_span, adjacent_span])

    if is_single_year:
        seasons.extend([str(year), str(year - 1)])

    # Deduplicate while preserving order
    deduped: List[str] = []
    for s in seasons:
        if s not in deduped:
            deduped.append(s)
    return deduped

def safe_to_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int with default fallback."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float with default fallback."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_team_id(conn: sqlite3.Connection, team_name: str, league_id: int) -> Optional[int]:
    """Get or create team ID for a team name."""
    cursor = conn.cursor()
    
    # Try to find existing team
    cursor.execute("SELECT id FROM team WHERE name = ?", (team_name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    
    # Create new team
    cursor.execute("INSERT INTO team (name) VALUES (?)", (team_name,))
    team_id = cursor.lastrowid
    conn.commit()
    
    logger.info(f"Created new team: {team_name} (ID: {team_id})")
    return team_id

def _ensure_prediction_snapshot_table(conn: sqlite3.Connection) -> None:
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_model ON prediction_snapshot(model_version, snapshot_type)")
    conn.commit()


class SnapshotRuntime:
    """Event-driven pre-kickoff snapshot + completed-game finalization."""

    def __init__(self, db_path: str, enabled: bool = True, before_kickoff_minutes: int = 20, after_kickoff_minutes: int = 5):
        self.db_path = db_path
        self.enabled = enabled and MultiLeaguePredictor is not None
        self.before_kickoff_minutes = max(0, int(before_kickoff_minutes))
        self.after_kickoff_minutes = max(0, int(after_kickoff_minutes))
        self.model_version = LIVE_MODEL_VERSION
        self._predictor = None
        self.stats = {"created": 0, "finalized": 0, "skipped_outside_window": 0, "skipped_existing": 0, "errors": 0}

    def _get_predictor(self):
        if self._predictor is None:
            if not self.enabled:
                return None
            storage_bucket = os.getenv("MODEL_STORAGE_BUCKET", "rugby-ai-61fd0.firebasestorage.app")
            self._predictor = MultiLeaguePredictor(
                db_path=self.db_path,
                sportdevs_api_key="",  # AI-only snapshots
                artifacts_dir="artifacts",
                storage_bucket=storage_bucket,
            )
        return self._predictor

    @staticmethod
    def _parse_kickoff(game: Dict[str, Any]) -> Optional[datetime]:
        kickoff_raw = game.get("timestamp") or game.get("date_event")
        if not kickoff_raw:
            return None
        try:
            dt = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            try:
                return datetime.fromisoformat(str(game.get("date_event")))
            except Exception:
                return None

    @staticmethod
    def _actual_winner(home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
        if home_score is None or away_score is None:
            return None
        if home_score > away_score:
            return "Home"
        if away_score > home_score:
            return "Away"
        return "Draw"

    def process_event(self, conn: sqlite3.Connection, event_id: int, game: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            _ensure_prediction_snapshot_table(conn)
            cur = conn.cursor()
            home_score = game.get("home_score")
            away_score = game.get("away_score")
            has_actual = home_score is not None and away_score is not None

            if has_actual:
                cur.execute(
                    """
                    SELECT predicted_home_score, predicted_away_score, predicted_winner
                    FROM prediction_snapshot
                    WHERE match_id = ? AND model_version = ? AND snapshot_type = 'pre_kickoff_live'
                    LIMIT 1
                    """,
                    (int(event_id), self.model_version),
                )
                row = cur.fetchone()
                if row:
                    pred_home, pred_away, pred_winner = row
                    actual_winner = self._actual_winner(home_score, away_score)
                    prediction_correct = None
                    if pred_winner in {"Home", "Away", "Draw"} and actual_winner:
                        prediction_correct = 1 if pred_winner == actual_winner else 0
                    score_error = None
                    if pred_home is not None and pred_away is not None:
                        score_error = abs(float(pred_home) - float(home_score)) + abs(float(pred_away) - float(away_score))
                    cur.execute(
                        """
                        UPDATE prediction_snapshot
                        SET actual_home_score=?, actual_away_score=?, actual_winner=?, prediction_correct=?, score_error=?, updated_at=CURRENT_TIMESTAMP
                        WHERE match_id=? AND model_version=? AND snapshot_type='pre_kickoff_live'
                        """,
                        (int(home_score), int(away_score), actual_winner, prediction_correct, score_error, int(event_id), self.model_version),
                    )
                    self.stats["finalized"] += 1
                return

            kickoff_dt = self._parse_kickoff(game)
            if kickoff_dt is None:
                self.stats["skipped_outside_window"] += 1
                return
            minutes_to_kickoff = (kickoff_dt - datetime.utcnow()).total_seconds() / 60.0
            if not (-float(self.after_kickoff_minutes) <= minutes_to_kickoff <= float(self.before_kickoff_minutes)):
                self.stats["skipped_outside_window"] += 1
                return

            cur.execute(
                """
                SELECT 1 FROM prediction_snapshot
                WHERE match_id = ? AND model_version = ? AND snapshot_type = 'pre_kickoff_live'
                LIMIT 1
                """,
                (int(event_id), self.model_version),
            )
            if cur.fetchone() is not None:
                self.stats["skipped_existing"] += 1
                return

            predictor = self._get_predictor()
            if predictor is None:
                self.stats["errors"] += 1
                return
            home_team = str(game.get("home_team") or "").strip()
            away_team = str(game.get("away_team") or "").strip()
            league_id = int(game.get("league_id"))
            if not home_team or not away_team:
                self.stats["errors"] += 1
                return

            pred = predictor.predict_match(
                home_team=home_team,
                away_team=away_team,
                league_id=league_id,
                match_date=str(game.get("date_event")),
                match_id=None,
            )
            cur.execute(
                """
                INSERT INTO prediction_snapshot (
                    match_id, league_id, model_version, snapshot_type, predicted_at, kickoff_at, home_team, away_team,
                    predicted_winner, predicted_home_score, predicted_away_score, confidence, home_win_prob, away_win_prob,
                    source_note, updated_at
                ) VALUES (?, ?, ?, 'pre_kickoff_live', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(match_id, model_version, snapshot_type)
                DO UPDATE SET
                    league_id=excluded.league_id, predicted_at=excluded.predicted_at, kickoff_at=excluded.kickoff_at,
                    home_team=excluded.home_team, away_team=excluded.away_team, predicted_winner=excluded.predicted_winner,
                    predicted_home_score=excluded.predicted_home_score, predicted_away_score=excluded.predicted_away_score,
                    confidence=excluded.confidence, home_win_prob=excluded.home_win_prob, away_win_prob=excluded.away_win_prob,
                    source_note=excluded.source_note, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(event_id),
                    league_id,
                    self.model_version,
                    datetime.utcnow().isoformat(),
                    kickoff_dt.isoformat(),
                    home_team,
                    away_team,
                    pred.get("predicted_winner"),
                    float(pred.get("predicted_home_score")) if pred.get("predicted_home_score") is not None else None,
                    float(pred.get("predicted_away_score")) if pred.get("predicted_away_score") is not None else None,
                    float(pred.get("confidence")) if pred.get("confidence") is not None else None,
                    float(pred.get("home_win_prob")) if pred.get("home_win_prob") is not None else None,
                    float(pred.get("away_win_prob")) if pred.get("away_win_prob") is not None else None,
                    "event_driven_pre_kickoff",
                ),
            )
            self.stats["created"] += 1
        except Exception as e:
            self.stats["errors"] += 1
            logger.debug(f"SnapshotRuntime error for event {event_id}: {e}")

def detect_and_add_missing_games(
    conn: sqlite3.Connection,
    league_id: int,
    league_name: str,
    snapshot_runtime: Optional[SnapshotRuntime] = None,
) -> int:
    """Detect and add missing games by checking TheSportsDB website data."""
    logger.info(f"Checking for missing games in {league_name}...")
    
    # For URC, try manual fixtures if API fails
    if league_id == 4446:
        logger.info("Checking for URC manual fixtures as fallback...")
        manual_games = get_manual_urc_fixtures()
        if manual_games:
            # Use update_database_with_games to add them (handles duplicates)
            added = update_database_with_games(conn, manual_games, snapshot_runtime=snapshot_runtime)
            if added > 0:
                logger.info(f"Added {added} URC games from manual fixtures")
            return added
    
    # No manual games for other leagues - only use real API data
    missing_games_map = {
        4414: [],  # English Premiership
        4430: [],  # French Top 14
        4986: [],  # Rugby Championship
        5069: [],  # Currie Cup
        4574: [],  # Rugby World Cup
        4551: [],  # Super Rugby
        4714: [],  # Six Nations Championship
    }
    
    missing_games = missing_games_map.get(league_id, [])
    if not missing_games:
        return 0
    
    added_count = 0
    cursor = conn.cursor()
    
    for game in missing_games:
        try:
            # Get team IDs
            home_team_id = get_team_id(conn, game["home"], league_id)
            away_team_id = get_team_id(conn, game["away"], league_id)
            
            # Check if event already exists
            cursor.execute("""
                SELECT id FROM event 
                WHERE home_team_id = ? AND away_team_id = ? AND date_event = ?
            """, (home_team_id, away_team_id, game["date"]))
            
            if cursor.fetchone():
                continue  # Game already exists
            
            # Insert new event
            cursor.execute("""
                INSERT INTO event (home_team_id, away_team_id, date_event, home_score, away_score, league_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (home_team_id, away_team_id, game["date"], None, None, league_id))
            
            added_count += 1
            logger.info(f"Auto-added missing game: {game['home']} vs {game['away']} ({game['date']})")
            
        except Exception as e:
            logger.error(f"Error adding missing game {game}: {e}")
            continue
    
    conn.commit()
    return added_count


def get_manual_urc_fixtures() -> List[Dict[str, Any]]:
    """Manual URC fixtures as fallback when API fails."""
    logger.info("Using manual URC fixtures fallback")
    
    # Known URC fixtures for 2025 (these should be updated regularly)
    # Update these dates to current/future dates
    today = datetime.utcnow().date()
    manual_fixtures = [
        # Add current and upcoming fixtures here
        # Example format:
        # {"date": "2025-01-15", "home": "Leinster", "away": "Munster"},
        # {"date": "2025-01-15", "home": "Ulster", "away": "Connacht"},
    ]
    
    # Filter to only future fixtures
    games = []
    for fixture in manual_fixtures:
        try:
            event_date = datetime.strptime(fixture["date"], '%Y-%m-%d').date()
            
            # Only include future fixtures
            if event_date < today:
                continue
            
            game = {
                'event_id': 0,  # Will be auto-generated
                'date_event': event_date,
                'home_team': fixture["home"],
                'away_team': fixture["away"],
                'home_score': None,
                'away_score': None,
                'league_id': 4446,  # URC
                'league_name': "United Rugby Championship"
            }
            
            games.append(game)
            
        except Exception as e:
            logger.warning(f"Error parsing manual fixture {fixture}: {e}")
            continue
    
    logger.info(f"Generated {len(games)} manual URC fixtures")
    return games

def update_database_with_games(conn: sqlite3.Connection, games: List[Dict[str, Any]], snapshot_runtime: Optional[SnapshotRuntime] = None) -> int:
    """Update database with fetched games."""
    ensure_highlightly_match_id_column(conn)
    cursor = conn.cursor()
    updated_count = 0
    
    for game in games:
        try:
            hl_match_id = game.get("highlightly_match_id") or (
                game.get("event_id") if int(game.get("event_id") or 0) >= 1_000_000 else None
            )
            if hl_match_id is not None:
                try:
                    hl_match_id = int(hl_match_id)
                except (TypeError, ValueError):
                    hl_match_id = None

            # Get team IDs
            home_team_id = get_team_id(conn, game['home_team'], game['league_id'])
            away_team_id = get_team_id(conn, game['away_team'], game['league_id'])
            
            if not home_team_id or not away_team_id:
                continue
            
            # BULLETPROOF: Check by league, DATE (no time), and teams
            cursor.execute("""
                SELECT id, home_score, away_score, date_event, highlightly_match_id
                FROM event 
                WHERE league_id = ?
                AND home_team_id = ? 
                AND away_team_id = ? 
                AND DATE(date_event) = DATE(?)
            """, (game['league_id'], home_team_id, away_team_id, game['date_event']))
            
            existing = cursor.fetchone()
            
            if existing:
                event_id, existing_home_score, existing_away_score, existing_date, existing_hl_id = existing
                
                # Only update if we have NEW score data (game completed)
                if (game['home_score'] is not None and game['away_score'] is not None and
                    existing_home_score is None):  # Only update if previously had no score
                    
                    cursor.execute("""
                        UPDATE event 
                        SET home_score = ?, away_score = ?, season = COALESCE(?, season),
                            timestamp = COALESCE(?, timestamp), status = COALESCE(?, status),
                            highlightly_match_id = COALESCE(?, highlightly_match_id)
                        WHERE id = ?
                    """, (
                        game['home_score'], game['away_score'], game.get('season'),
                        game.get('timestamp'), game.get('status'), hl_match_id, event_id,
                    ))
                    
                    updated_count += 1
                    logger.info(f"Score added: {game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']}")
                elif hl_match_id and not existing_hl_id:
                    cursor.execute(
                        "UPDATE event SET highlightly_match_id = ? WHERE id = ?",
                        (hl_match_id, event_id),
                    )
                    updated_count += 1
                    logger.debug(
                        "Linked Highlightly match id %s -> event %s",
                        hl_match_id,
                        event_id,
                    )
                else:
                    # Game already exists - skip silently (prevent duplicates)
                    logger.debug(f"Skipped existing: {game['home_team']} vs {game['away_team']} on {game['date_event']}")
                if snapshot_runtime:
                    snapshot_runtime.process_event(conn, int(event_id), game)
            else:
                # DOUBLE-CHECK before inserting (extra safety)
                cursor.execute("""
                    SELECT COUNT(*) FROM event
                    WHERE league_id = ?
                    AND home_team_id = ?
                    AND away_team_id = ?
                    AND DATE(date_event) = DATE(?)
                """, (game['league_id'], home_team_id, away_team_id, game['date_event']))
                
                if cursor.fetchone()[0] > 0:
                    logger.debug(f"Double-check prevented duplicate: {game['home_team']} vs {game['away_team']}")
                    continue
                
                # Safe to insert
                cursor.execute("""
                    INSERT INTO event (
                        home_team_id, away_team_id, date_event, home_score, away_score,
                        league_id, season, timestamp, status, highlightly_match_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    home_team_id,
                    away_team_id,
                    game['date_event'],
                    game['home_score'],
                    game['away_score'],
                    game['league_id'],
                    game.get('season'),
                    game.get('timestamp'),
                    game.get('status'),
                    hl_match_id,
                ))
                event_id = cursor.lastrowid
                
                updated_count += 1
                logger.info(f"Added: {game['home_team']} vs {game['away_team']} ({game['date_event']})")
                if snapshot_runtime and event_id:
                    snapshot_runtime.process_event(conn, int(event_id), game)
                
        except Exception as e:
            logger.error(f"Error updating game {game.get('home_team', 'unknown')} vs {game.get('away_team', 'unknown')}: {e}")
    
    conn.commit()
    return updated_count

def main():
    """Main function to update all leagues from Highlightly."""
    parser = argparse.ArgumentParser(description='Auto-update rugby games from Highlightly')
    parser.add_argument('--db', default='data.sqlite', help='Database file path')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--include-history', action='store_true', help='Fetch all available Highlightly seasons (slower)')
    parser.add_argument('--api-key', default=None, help='Highlightly API key (or HIGHLIGHTLY_API_KEY env var)')
    parser.add_argument('--days-ahead', type=int, default=180, help='Only keep fixtures up to N days ahead (default: 180)')
    parser.add_argument('--days-back', type=int, default=14, help='Also keep fixtures up to N days back (default: 14)')
    parser.add_argument('--sleep', type=float, default=0.35, help='Delay between Highlightly API calls in seconds')
    parser.add_argument('--disable-event-snapshots', action='store_true', help='Disable event-driven pre-kickoff snapshots/finalization')
    parser.add_argument('--snapshot-before-minutes', type=int, default=20, help='Snapshot when kickoff is within this many minutes (default: 20)')
    parser.add_argument('--snapshot-after-minutes', type=int, default=5, help='Allow late snapshot this many minutes after kickoff (default: 5)')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("🚀 Starting automated game update from Highlightly")
    try:
        api_key = parse_api_key(args.api_key)
    except ValueError as exc:
        logger.error(str(exc))
        return

    api = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=False)
    probe = api.get_leagues(limit=1)
    if not probe.get("data"):
        logger.error("Highlightly auth failed. Check HIGHLIGHTLY_API_KEY in rugby-ai-predictor/.env")
        return
    
    # Connect to database
    conn = sqlite3.connect(args.db)
    ensure_highlightly_match_id_column(conn)
    snapshot_runtime = SnapshotRuntime(
        db_path=args.db,
        enabled=not args.disable_event_snapshots,
        before_kickoff_minutes=args.snapshot_before_minutes,
        after_kickoff_minutes=args.snapshot_after_minutes,
    )
    
    total_updated = 0
    request_counter = [0]
    all_leagues = list(LEAGUE_MAPPINGS.keys())
    
    logger.info(f"🔄 Fetching games for ALL {len(all_leagues)} leagues from Highlightly")
    
    for league_id in all_leagues:
        league_info = LEAGUE_MAPPINGS[league_id]
        league_name = league_info['name']
        highlightly_id = league_info['highlightly_id']
        
        logger.info(f"🔄 Fetching games for {league_name} (Highlightly ID: {highlightly_id})")
        
        try:
            games = fetch_games_from_highlightly(
                api,
                league_id,
                league_name,
                highlightly_id,
                include_history=args.include_history,
                days_ahead=args.days_ahead,
                days_back=args.days_back,
                sleep_s=max(0.0, args.sleep),
                request_counter=request_counter,
            )
            
            if games:
                updated = update_database_with_games(conn, games, snapshot_runtime=snapshot_runtime)
                total_updated += updated
                logger.info(f"✅ {league_name}: Updated {updated} games")
                
                if league_id == 4446:
                    logger.info(f"🔍 {league_name}: Checking for additional manual fixtures...")
                    missing_added = detect_and_add_missing_games(conn, league_id, league_name, snapshot_runtime=snapshot_runtime)
                    if missing_added > 0:
                        total_updated += missing_added
                        logger.info(f"🔧 {league_name}: Auto-added {missing_added} missing upcoming games from manual fixtures")
            else:
                logger.warning(f"⚠️ {league_name}: No games found from Highlightly")
                missing_added = detect_and_add_missing_games(conn, league_id, league_name, snapshot_runtime=snapshot_runtime)
                if missing_added > 0:
                    total_updated += missing_added
                    logger.info(f"🔧 {league_name}: Auto-added {missing_added} missing upcoming games from manual fixtures")
                    
        except Exception as e:
            logger.error(f"❌ Error updating {league_name}: {e}")
    
    conn.close()
    
    logger.info(f"🎉 Update complete! Total games updated: {total_updated} (Highlightly API calls: {request_counter[0]})")
    if snapshot_runtime and snapshot_runtime.enabled:
        s = snapshot_runtime.stats
        logger.info(
            "📸 Event-driven snapshots: created=%s finalized=%s skipped_outside_window=%s skipped_existing=%s errors=%s",
            s["created"], s["finalized"], s["skipped_outside_window"], s["skipped_existing"], s["errors"]
        )
    
    if total_updated > 0:
        retrain_flag_file = "retrain_needed.flag"
        try:
            with open(retrain_flag_file, 'w') as f:
                json.dump({
                    "leagues_to_retrain": list(LEAGUE_MAPPINGS.keys()),
                    "games_updated": total_updated,
                    "timestamp": datetime.now().isoformat(),
                    "reason": "new_games_fetched",
                    "trigger": "comprehensive_data_update",
                    "description": f"Found {total_updated} new/updated games from Highlightly - retraining all models to capture latest data"
                }, f, indent=2)
            logger.info(f"🔄 Created retraining flag file: {retrain_flag_file}")
            logger.info("🤖 Models will be retrained with new game data")
        except Exception as e:
            logger.error(f"Failed to create retraining flag file: {e}")
    else:
        logger.info("✅ No new games found - database is up to date")

if __name__ == "__main__":
    main()
