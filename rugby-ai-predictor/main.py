"""
Firebase Cloud Functions for Rugby AI Predictor
Handles callable functions for predictions, matches, and data
"""

from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
import os
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, TYPE_CHECKING

# Import Firestore Timestamp for type checking
try:
    from google.cloud.firestore_v1 import Timestamp as FirestoreTimestamp  # type: ignore
except ImportError:
    FirestoreTimestamp = None


def _sqlite_has_table(db_path: str, table_name: str) -> bool:
    """Return True if SQLite DB exists and contains `table_name`."""
    try:
        if not db_path or not os.path.exists(db_path):
            return False
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                (table_name,),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except Exception:
        return None


def _get_live_model_version() -> str:
    """
    Stable model-version identifier used for historical snapshot rows.
    Override via LIVE_MODEL_VERSION if needed.
    """
    explicit = str(os.getenv("LIVE_MODEL_VERSION", "")).strip()
    if explicit:
        return explicit
    return f"{LIVE_MODEL_FAMILY}:{LIVE_MODEL_CHANNEL}"


def _ensure_prediction_snapshot_table(conn: Any) -> None:
    """
    Create persistent prediction snapshot table if it does not exist.
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            league_id INTEGER,
            model_version TEXT NOT NULL,
            snapshot_type TEXT NOT NULL, -- historical_backfill | pre_kickoff_live
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
            prediction_correct INTEGER, -- 1=true,0=false,NULL=unknown
            score_error REAL,
            source_note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_id, model_version, snapshot_type)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_match ON prediction_snapshot(match_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_league ON prediction_snapshot(league_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_snapshot_model ON prediction_snapshot(model_version, snapshot_type)"
    )
    conn.commit()


def _upsert_prediction_snapshot_row(
    conn: Any,
    *,
    match_id: int,
    league_id: Optional[int],
    model_version: str,
    snapshot_type: str,
    predicted_at: str,
    kickoff_at: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
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
    source_note: Optional[str] = None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO prediction_snapshot (
            match_id, league_id, model_version, snapshot_type, predicted_at, kickoff_at,
            home_team, away_team, predicted_winner, predicted_home_score, predicted_away_score,
            confidence, home_win_prob, away_win_prob, actual_home_score, actual_away_score,
            actual_winner, prediction_correct, score_error, source_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
            int(match_id),
            league_id,
            model_version,
            snapshot_type,
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
            source_note,
        ),
    )
def _parse_firestore_date(date_event: Any) -> Optional[datetime]:
    """Best-effort conversion of Firestore date field to a `datetime`."""
    try:
        if date_event is None:
            return None
        # Firestore Timestamp-like object
        if hasattr(date_event, "to_datetime"):
            return date_event.to_datetime()
        if isinstance(date_event, datetime):
            return date_event
        if isinstance(date_event, str):
            raw = date_event.strip()
            if not raw:
                return None
            # Handle trailing Z and plain date strings
            raw = raw.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(raw)
            except Exception:
                # Try date-only (YYYY-MM-DD)
                try:
                    return datetime.fromisoformat(raw + "T00:00:00")
                except Exception:
                    return None
        return None
    except Exception:
        return None


def _build_firestore_news_feed(
    league_id: Any,
    limit: int = 50,
    days_ahead: int = 7,
    days_back: int = 7,
) -> Dict[str, Any]:
    """
    Firestore-based fallback for the News tab.

    Returns:
      {
        "news": [<news item dict>],
        "debug": {...}
      }
    """
    import logging
    logger = logging.getLogger(__name__)

    # Use a local timezone for "today" semantics (matches stay visible on game day)
    from datetime import timezone
    import os as _os
    try:
        from zoneinfo import ZoneInfo  # py3.9+
    except Exception:
        ZoneInfo = None

    tz_name = _os.getenv("LOCAL_TIMEZONE", "Africa/Johannesburg")
    local_tz = ZoneInfo(tz_name) if ZoneInfo else timezone.utc
    now_utc = datetime.now(timezone.utc)
    today_local = now_utc.astimezone(local_tz).date()
    cutoff_future = now_utc + timedelta(days=days_ahead)
    cutoff_past = now_utc - timedelta(days=days_back)

    league_id_int = _coerce_int(league_id)
    # In league-specific mode, be more forgiving so the News tab doesn't go empty.
    if league_id_int is not None:
        days_ahead = max(days_ahead, 30)
        days_back = max(days_back, 30)
        cutoff_future = now_utc + timedelta(days=days_ahead)
        cutoff_past = now_utc - timedelta(days=days_back)

    db = get_firestore_client()
    matches_ref = db.collection("matches")
    if league_id_int is not None:
        matches_ref = matches_ref.where("league_id", "==", league_id_int)

    # Keep this query simple to avoid index issues; filter by date in Python.
    matches_ref = matches_ref.limit(1000)

    total_checked = 0
    upcoming_matches: list[dict] = []
    recent_matches: list[dict] = []
    team_ids: set[int] = set()
    # Build form + head-to-head from scored matches so previews aren't all 50%.
    # Wider historical window for form because some leagues have gaps.
    form_days = 180 if league_id_int is not None else 60
    form_cutoff_past = now_utc - timedelta(days=form_days)
    team_form_raw: dict[int, list[tuple[datetime, int, int]]] = {}
    # key: (min_team_id, max_team_id) -> list[(dt, home_score, away_score, home_team_id)]
    h2h_raw: dict[tuple[int, int], list[tuple[datetime, int, int, int]]] = {}

    for doc in matches_ref.stream():
        total_checked += 1
        m = doc.to_dict() or {}

        # Safety: enforce league match in code too
        if league_id_int is not None:
            if _coerce_int(m.get("league_id")) != league_id_int:
                continue

        dt = _parse_firestore_date(m.get("date_event"))
        if not dt:
            continue

        # Normalize to aware UTC for comparisons
        if dt.tzinfo is None:
            dt_utc = dt.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt.astimezone(timezone.utc)

        home_id = _coerce_int(m.get("home_team_id"))
        away_id = _coerce_int(m.get("away_team_id"))
        if home_id:
            team_ids.add(home_id)
        if away_id:
            team_ids.add(away_id)

        # Capture scored matches for recent form / head-to-head.
        hs = m.get("home_score")
        aws = m.get("away_score")
        try:
            hs_i = int(hs) if hs is not None else None
            aws_i = int(aws) if aws is not None else None
        except Exception:
            hs_i = None
            aws_i = None

        if (
            home_id
            and away_id
            and hs_i is not None
            and aws_i is not None
            and form_cutoff_past <= dt_utc < now_utc
        ):
            # Team form (normalize into team_score/opponent_score)
            team_form_raw.setdefault(home_id, []).append((dt_utc, hs_i, aws_i))
            team_form_raw.setdefault(away_id, []).append((dt_utc, aws_i, hs_i))

            # Head-to-head store original orientation
            a, b = (home_id, away_id) if home_id < away_id else (away_id, home_id)
            h2h_raw.setdefault((a, b), []).append((dt_utc, hs_i, aws_i, home_id))

        # Upcoming logic: keep anything from "today" onwards in local timezone
        dt_local_date = dt_utc.astimezone(local_tz).date()
        is_upcoming_window = (dt_local_date >= today_local) and (dt_utc <= cutoff_future)
        is_recent_window = (cutoff_past <= dt_utc < now_utc)

        doc_id = doc.id
        match_id_val: Any = _coerce_int(doc_id) if str(doc_id).isdigit() else doc_id
        m_norm = {
            "doc_id": doc_id,
            "match_id": match_id_val,
            "league_id": league_id_int if league_id_int is not None else _coerce_int(m.get("league_id")),
            "date_dt_utc": dt_utc,
            "date_event": dt_utc.isoformat(),
            "home_team_id": home_id,
            "away_team_id": away_id,
            "home_score": m.get("home_score"),
            "away_score": m.get("away_score"),
            "venue": m.get("venue") or m.get("strVenue") or None,
        }

        if is_upcoming_window:
            upcoming_matches.append(m_norm)
        elif is_recent_window and m.get("home_score") is not None and m.get("away_score") is not None:
            recent_matches.append(m_norm)

    # Finalize forms (latest 5)
    team_form: dict[int, list[tuple[int, int]]] = {}
    for tid, rows in team_form_raw.items():
        rows_sorted = sorted(rows, key=lambda x: x[0], reverse=True)
        team_form[tid] = [(r[1], r[2]) for r in rows_sorted[:5]]

    # Finalize head-to-head (latest 5)
    h2h: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for key, rows in h2h_raw.items():
        rows_sorted = sorted(rows, key=lambda x: x[0], reverse=True)
        h2h[key] = [(r[1], r[2], r[3]) for r in rows_sorted[:5]]

    # Batch lookup team names
    team_names: dict[int, str] = {}
    if team_ids:
        try:
            teams_ref = db.collection("teams")
            team_ids_list = list(team_ids)
            for i in range(0, len(team_ids_list), 10):
                batch = team_ids_list[i : i + 10]
                for tdoc in teams_ref.where("id", "in", batch).stream():
                    t = tdoc.to_dict() or {}
                    tid = _coerce_int(t.get("id"))
                    if tid is not None:
                        team_names[tid] = t.get("name") or f"Team {tid}"
        except Exception as e:
            logger.warning(f"Firestore team name lookup failed (fallback to IDs): {e}")

    # Sort and build news items
    upcoming_matches.sort(key=lambda x: x["date_dt_utc"])
    recent_matches.sort(key=lambda x: x["date_dt_utc"], reverse=True)

    news: list[dict] = []

    # Prefer upcoming previews; if none, show recent recaps
    if upcoming_matches:
        for m in upcoming_matches[: max(0, min(limit, 100))]:
            home_name = team_names.get(m["home_team_id"] or -1, f"Team {m['home_team_id']}" if m["home_team_id"] else "Home")
            away_name = team_names.get(m["away_team_id"] or -1, f"Team {m['away_team_id']}" if m["away_team_id"] else "Away")
            home_id = m["home_team_id"]
            away_id = m["away_team_id"]

            home_form = team_form.get(home_id, []) if home_id else []
            away_form = team_form.get(away_id, []) if away_id else []

            def _win_rate(form: list[tuple[int, int]]) -> float:
                if not form:
                    return 0.0
                return sum(1 for s, o in form if s > o) / len(form)

            def _avg_scored(form: list[tuple[int, int]]) -> float:
                if not form:
                    return 0.0
                return sum(s for s, _ in form) / len(form)

            home_wr = _win_rate(home_form)
            away_wr = _win_rate(away_form)
            home_avg = _avg_scored(home_form)
            away_avg = _avg_scored(away_form)

            # Simple strength model (same spirit as NewsService fallback)
            def _strength(wr: float, avg_pts: float, has_form: bool) -> float:
                if not has_form:
                    return 0.5
                return (wr * 0.6) + (min(avg_pts / 50.0, 1.0) * 0.4)

            home_strength = _strength(home_wr, home_avg, bool(home_form))
            away_strength = _strength(away_wr, away_avg, bool(away_form))
            total_strength = home_strength + away_strength
            home_prob = (home_strength / total_strength) if total_strength > 0 else 0.5
            home_prob = max(0.01, min(0.99, float(home_prob)))

            favored = home_name if home_prob >= 0.5 else away_name
            confidence = max(home_prob, 1.0 - home_prob)
            if confidence >= 0.62:
                title = f"{favored} favored ({confidence*100:.0f}%)"
            elif confidence >= 0.56:
                title = f"{favored} slight edge ({confidence*100:.0f}%)"
            else:
                title = f"{home_name} vs {away_name}: tight contest expected"

            # Head-to-head
            head_to_head: list[tuple[int, int, int]] = []
            if home_id and away_id:
                a, b = (home_id, away_id) if home_id < away_id else (away_id, home_id)
                head_to_head = h2h.get((a, b), [])

            # Build more "newsly" content
            content_parts: list[str] = []
            content_parts.append(f"{home_name} host {away_name}.")
            if home_form:
                content_parts.append(f"{home_name} last {len(home_form)}: {home_wr*100:.0f}% wins, {home_avg:.1f} pts/game.")
            if away_form:
                content_parts.append(f"{away_name} last {len(away_form)}: {away_wr*100:.0f}% wins, {away_avg:.1f} pts/game.")
            if head_to_head:
                # Count wins for the listed home_team_id orientation
                home_h2h_wins = 0
                for hs_i, as_i, h_id in head_to_head:
                    # If match stored with home_team_id==home_id, hs_i is home team's points
                    if h_id == home_id:
                        if hs_i > as_i:
                            home_h2h_wins += 1
                    else:
                        # Our home team was away in that meeting
                        if as_i > hs_i:
                            home_h2h_wins += 1
                content_parts.append(f"Head-to-head: {home_name} won {home_h2h_wins}/{len(head_to_head)} recent meetings.")
            content_parts.append(f"Model edge: {home_prob*100:.0f}% {home_name} win chance.")

            content = " ".join(content_parts)

            clickable_stats = [
                {
                    "label": f"Win Probability (Home): {home_prob*100:.1f}%",
                    "explanation": "Estimated from recent win rate and points scored (Firestore fallback model).",
                }
            ]
            if home_form:
                clickable_stats.append(
                    {
                        "label": f"{home_name} form: {home_wr*100:.0f}% wins",
                        "explanation": f"Last {len(home_form)} scored games in this league window.",
                    }
                )
            if away_form:
                clickable_stats.append(
                    {
                        "label": f"{away_name} form: {away_wr*100:.0f}% wins",
                        "explanation": f"Last {len(away_form)} scored games in this league window.",
                    }
                )
            news.append(
                {
                    "id": f"fs_preview_{m['match_id']}",
                    "type": "match_preview",
                    "title": title,
                    "content": content,
                    "timestamp": m["date_event"],
                    "league_id": m["league_id"],
                    "match_id": m["match_id"],
                    "impact_score": 0.0,
                    "related_stats": {
                        "home_team": home_name,
                        "away_team": away_name,
                        "home_team_id": home_id,
                        "away_team_id": away_id,
                        "venue": m.get("venue"),
                        "date_event": m["date_event"],
                        "win_probability": home_prob,
                        "home_form": home_form,
                        "away_form": away_form,
                        "head_to_head": head_to_head,
                    },
                    "clickable_stats": clickable_stats,
                }
            )
    else:
        for m in recent_matches[: max(0, min(limit, 100))]:
            home_name = team_names.get(m["home_team_id"] or -1, f"Team {m['home_team_id']}" if m["home_team_id"] else "Home")
            away_name = team_names.get(m["away_team_id"] or -1, f"Team {m['away_team_id']}" if m["away_team_id"] else "Away")
            hs = m.get("home_score")
            aw = m.get("away_score")
            try:
                hs_i = int(hs)
                aw_i = int(aw)
            except Exception:
                hs_i = hs
                aw_i = aw
            title = f"{home_name} {hs_i}-{aw_i} {away_name}"
            content = f"Recent result: {home_name} {hs_i} - {aw_i} {away_name}."
            news.append(
                {
                    "id": f"fs_recap_{m['match_id']}",
                    "type": "match_recap",
                    "title": title,
                    "content": content,
                    "timestamp": m["date_event"],
                    "league_id": m["league_id"],
                    "match_id": m["match_id"],
                    "related_stats": {
                        "home_team": home_name,
                        "away_team": away_name,
                        "home_score": hs_i,
                        "away_score": aw_i,
                        "home_team_id": m["home_team_id"],
                        "away_team_id": m["away_team_id"],
                        "date_event": m["date_event"],
                    },
                }
            )

    # Newest first for UI
    news.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {
        "news": news[:limit],
        "debug": {
            "data_source": "firestore",
            "league_id": league_id,
            "league_id_int": league_id_int,
            "total_checked": total_checked,
            "upcoming_found": len(upcoming_matches),
            "recent_found": len(recent_matches),
            "returned": min(len(news), limit),
            "timezone": tz_name,
        },
    }

if TYPE_CHECKING:
    from prediction.hybrid_predictor import MultiLeaguePredictor
    from prediction.enhanced_predictor import EnhancedRugbyPredictor

# For cost control, set max instances
set_global_options(max_instances=10)

# Initialize Firebase Admin (lazy initialization)
_app_initialized = False

def get_firestore_client():
    """Lazy initialization of Firestore client"""
    global _app_initialized
    if not _app_initialized:
        try:
            initialize_app()
        except ValueError:
            # Already initialized, ignore
            pass
        _app_initialized = True
    return firestore.client()

# Import prediction modules (lazy - only when needed)
def _get_league_mappings():
    """Lazy import of league mappings"""
    try:
        from prediction.config import LEAGUE_MAPPINGS
        return LEAGUE_MAPPINGS
    except ImportError:
        return {}

# Initialize predictors (lazy loading - will be imported when needed)
_predictor = None
_enhanced_predictor = None
LIVE_MODEL_FAMILY = os.getenv("LIVE_MODEL_FAMILY", "v4")
LIVE_MODEL_CHANNEL = os.getenv("LIVE_MODEL_CHANNEL", "prod_100")


def get_predictor():
    """Get or create MultiLeaguePredictor instance (lazy import)

    NOTE:
    -----
    The current `MultiLeaguePredictor` implementation still expects a SQLite
    database with an `event` table (used by `build_feature_table`), so using a
    special value like ``db_path='firestore'`` will cause SQLite to create an
    empty file with no tables, leading to:

        pandas.errors.DatabaseError: no such table: event

    To avoid this, we point `db_path` at a real SQLite file that contains the
    `event` table. In Cloud Functions, make sure a copy of `data.sqlite`
    lives alongside this `main.py` (i.e. in the `rugby-ai-predictor/` folder),
    or set the `DB_PATH` environment variable to an absolute path.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    global _predictor
    if _predictor is None:
        try:
            from prediction.hybrid_predictor import MultiLeaguePredictor as MLP

            # Resolve database path – prefer explicit env var, otherwise local file
            db_path = os.getenv("DB_PATH")
            if not db_path:
                # Default to a bundled SQLite file in the same directory as this module
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            logger.info(f"Initializing MultiLeaguePredictor with db_path={db_path!r}")

            # Models will be loaded from Cloud Storage
            storage_bucket = os.getenv("MODEL_STORAGE_BUCKET", "rugby-ai-61fd0.firebasestorage.app")
            logger.info(f"Using storage bucket: {storage_bucket}")
            sportdevs_api_key = os.getenv("SPORTDEVS_API_KEY", "")
            
            # Pass all parameters explicitly to match the signature
            try:
                _predictor = MLP(
                    db_path=db_path,
                    sportdevs_api_key=sportdevs_api_key,
                    artifacts_dir="artifacts",
                    storage_bucket=storage_bucket,
                )
                logger.info("MultiLeaguePredictor initialized successfully")
            except TypeError as e:
                # Fallback: try without storage_bucket (for older versions)
                logger.warning(f"Failed with storage_bucket, trying without: {e}")
                _predictor = MLP(
                    db_path=db_path,
                    sportdevs_api_key=sportdevs_api_key,
                    artifacts_dir="artifacts",
                )
                logger.info("MultiLeaguePredictor initialized without storage_bucket")
        except ImportError as e:
            raise ImportError(f"Could not import MultiLeaguePredictor: {e}")
        except Exception as e:
            raise Exception(f"Could not initialize MultiLeaguePredictor: {e}")
    return _predictor


def get_enhanced_predictor():
    """Get or create EnhancedRugbyPredictor instance (lazy import)"""
    global _enhanced_predictor
    if _enhanced_predictor is None:
        try:
            from prediction.enhanced_predictor import EnhancedRugbyPredictor as ERP
            api_key = os.getenv('HIGHLIGHTLY_API_KEY', '9c27c5f8-9437-4d42-8cc9-5179d3290a5b')
            if api_key:
                # Reuse the same DB path strategy as `get_predictor`
                db_path = os.getenv("DB_PATH")
                if not db_path:
                    db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                _enhanced_predictor = ERP(db_path, api_key)
        except (ImportError, Exception):
            pass  # Enhanced predictor is optional
    return _enhanced_predictor


def get_news_service(predictor=None, db_path: Optional[str] = None):
    """Get or create NewsService instance with API clients"""
    import logging
    logger = logging.getLogger(__name__)
    
    from prediction.news_service import NewsService
    from prediction.sportdevs_client import SportDevsClient
    from prediction.sportsdb_client import TheSportsDBClient
    from prediction.config import load_config
    
    db_path = db_path or os.getenv("DB_PATH")
    if not db_path:
        # Try multiple possible paths
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same directory as main.py
            os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent directory
            os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root directory
            "/tmp/data.sqlite",  # Firebase Functions temp directory
        ]
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                db_path = abs_path
                logger.info(f"Found database at: {abs_path}")
                break
        else:
            # Default to same directory as main.py
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            logger.warning(f"Database not found in any expected location, using default: {db_path}")
    else:
        db_path = os.path.abspath(db_path)
    
    logger.info(f"NewsService using database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")
    
    # Initialize API clients (optional - will work without them)
    sportdevs_client = None
    sportsdb_client = None
    
    try:
        # SportDevs client (optional)
        sportdevs_key = os.getenv("SPORTDEVS_API_KEY", "")
        if sportdevs_key:
            sportdevs_client = SportDevsClient(api_key=sportdevs_key)
    except Exception as e:
        logger.warning(f"Could not initialize SportDevs client: {e}")
    
    try:
        # TheSportsDB client (for logos)
        config = load_config()
        sportsdb_client = TheSportsDBClient(
            base_url=config.base_url,
            api_key=config.api_key,
            rate_limit_rpm=config.rate_limit_rpm
        )
    except Exception as e:
        logger.warning(f"Could not initialize TheSportsDB client: {e}")
    
    # Initialize social media fetcher (optional)
    social_media_fetcher = None
    try:
        from prediction.social_media_fetcher import SocialMediaFetcher
        social_media_fetcher = SocialMediaFetcher()
    except Exception as e:
        logger.warning(f"Could not initialize SocialMediaFetcher: {e}")
    
    return NewsService(
        db_path=db_path,
        predictor=predictor,
        sportdevs_client=sportdevs_client,
        sportsdb_client=sportsdb_client,
        social_media_fetcher=social_media_fetcher
    )


@https_fn.on_call(timeout_sec=300, memory=512)  # 5 minute timeout, 512MB memory
def predict_match(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get match prediction
    
    Request data:
    {
        "home_team": "South Africa",
        "away_team": "New Zealand",
        "league_id": 4986,
        "match_date": "2025-11-22",
        "enhanced": false
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== predict_match called ===")
        data = req.data or {}
        logger.info(f"Request data: {data}")
        
        home_team = data.get('home_team')
        away_team = data.get('away_team')
        league_id = data.get('league_id')
        match_date = data.get('match_date')
        enhanced = data.get('enhanced', False)
        
        logger.info(f"Parameters: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}, enhanced={enhanced}")
        
        # Type checking and validation
        if not all([home_team, away_team, league_id, match_date]):
            logger.error(f"Missing required fields: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}")
            return {'error': 'Missing required fields'}
        
        # Ensure types are correct
        if not isinstance(home_team, str) or not isinstance(away_team, str) or not isinstance(match_date, str):
            logger.error(f"Invalid field types: home_team type={type(home_team)}, away_team type={type(away_team)}, match_date type={type(match_date)}")
            return {'error': 'Invalid field types'}
        
        # Convert league_id to int (we know it's not None from the check above)
        if league_id is None:
            logger.error("league_id is None")
            return {'error': 'Invalid league_id'}
        
        try:
            league_id_int = int(league_id)
            logger.info(f"Converted league_id to int: {league_id_int}")
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert league_id to int: {e}")
            return {'error': 'Invalid league_id'}
        
        if enhanced:
            logger.info("Using enhanced predictor...")
            try:
                predictor = get_enhanced_predictor()
                if predictor:
                    logger.info("Enhanced predictor obtained, calling get_enhanced_prediction...")
                    prediction = predictor.get_enhanced_prediction(
                        str(home_team), str(away_team), league_id_int, str(match_date)
                    )
                    logger.info(f"Enhanced prediction received: {prediction}")
                else:
                    logger.error("Enhanced predictor not available")
                    return {'error': 'Enhanced predictor not available'}
            except FileNotFoundError as fnf:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Model not found for enhanced predictor: {fnf}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Model not found for league {league_id_int}. Please ensure models are uploaded to Cloud Storage.'}
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Enhanced prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Enhanced prediction failed: {str(e)}'}
        else:
            try:
                logger.info("Using standard predictor...")
                predictor = get_predictor()
                logger.info("Predictor obtained, calling predict_match...")
                raw_match_id = data.get('event_id') or data.get('match_id') or data.get('id')
                match_id = None
                try:
                    if raw_match_id is not None and str(raw_match_id).strip() != "":
                        match_id = int(raw_match_id)
                except (TypeError, ValueError):
                    match_id = None
                prediction = predictor.predict_match(
                    str(home_team), str(away_team), league_id_int, str(match_date), match_id=match_id
                )
                logger.info(f"Prediction received: {prediction}")
            except FileNotFoundError as fnf:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Model file not found: {fnf}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Model not found for league {league_id_int}. Please ensure models are uploaded to Cloud Storage. Details: {str(fnf)}'}
            except ImportError as import_err:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Import error: {import_err}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Failed to import required modules: {str(import_err)}'}
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Prediction failed: {str(e)}'}
        
        # Save prediction to Firestore if we have event_id or can find it
        try:
            event_id = data.get('event_id') or prediction.get('event_id') or prediction.get('match_id')
            
            # If no event_id provided, try to find it from database
            if not event_id:
                try:
                    import sqlite3
                    db_path = os.getenv("DB_PATH")
                    if not db_path:
                        db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                    
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Try to find event_id by matching teams and date
                        query = """
                        SELECT e.id FROM event e
                        LEFT JOIN team ht ON e.home_team_id = ht.id
                        LEFT JOIN team at ON e.away_team_id = at.id
                        WHERE e.league_id = ? 
                          AND (ht.name = ? OR ht.name LIKE ? OR ? LIKE '%' || ht.name || '%')
                          AND (at.name = ? OR at.name LIKE ? OR ? LIKE '%' || at.name || '%')
                          AND e.date_event LIKE ?
                        ORDER BY e.date_event DESC
                        LIMIT 1
                        """
                        
                        date_pattern = f"{match_date}%"
                        cursor.execute(query, (
                            league_id_int,
                            home_team, f"%{home_team}%", home_team,
                            away_team, f"%{away_team}%", away_team,
                            date_pattern
                        ))
                        result = cursor.fetchone()
                        if result:
                            event_id = result[0]
                        conn.close()
                except Exception as db_error:
                    logger.debug(f"Could not find event_id from database: {db_error}")
            
            # Save to Firestore if we have event_id and prediction data
            if event_id and prediction and not prediction.get('error'):
                try:
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    
                    # Extract predicted winner - always verify against scores for consistency
                    home_score = prediction.get('predicted_home_score', 0)
                    away_score = prediction.get('predicted_away_score', 0)
                    
                    # Determine winner from scores (most reliable source)
                    if home_score > away_score:
                        score_based_winner = home_team
                    elif away_score > home_score:
                        score_based_winner = away_team
                    else:
                        score_based_winner = 'Draw'
                    
                    # Get predicted_winner from prediction, but always verify against scores
                    predicted_winner = prediction.get('winner') or prediction.get('predicted_winner')
                    
                    # Convert 'Home'/'Away' to team names if needed
                    if predicted_winner == 'Home':
                        predicted_winner = home_team
                    elif predicted_winner == 'Away':
                        predicted_winner = away_team
                    elif predicted_winner == 'Draw':
                        predicted_winner = 'Draw'
                    
                    # Safety check: if predicted_winner doesn't match scores, use score-based winner
                    if predicted_winner:
                        if (predicted_winner == home_team and home_score <= away_score) or \
                           (predicted_winner == away_team and away_score <= home_score) or \
                           (predicted_winner == 'Draw' and home_score != away_score):
                            # Mismatch detected - use score-based winner
                            predicted_winner = score_based_winner
                    else:
                        # No predicted_winner provided, use score-based
                        predicted_winner = score_based_winner
                    
                    # Prepare prediction data to save
                    prediction_data = {
                        'event_id': int(event_id),
                        'league_id': league_id_int,
                        'home_team': home_team,
                        'away_team': away_team,
                        'match_date': match_date,
                        'predicted_winner': predicted_winner,
                        'winner': predicted_winner,  # Also save as 'winner' for compatibility
                        'predicted_home_score': prediction.get('predicted_home_score'),
                        'predicted_away_score': prediction.get('predicted_away_score'),
                        'home_win_prob': prediction.get('home_win_prob'),
                        'confidence': prediction.get('confidence'),
                        'prediction_type': prediction.get('prediction_type', 'AI Only'),
                        'model_type': prediction.get('model_type', LIVE_MODEL_FAMILY),
                        'model_family': prediction.get('model_family', LIVE_MODEL_FAMILY),
                        'model_channel': prediction.get('model_channel', LIVE_MODEL_CHANNEL),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    }
                    
                    # Add any additional prediction fields
                    if 'ai_probability' in prediction:
                        prediction_data['ai_probability'] = prediction.get('ai_probability')
                    if 'hybrid_probability' in prediction:
                        prediction_data['hybrid_probability'] = prediction.get('hybrid_probability')
                    if 'confidence_boost' in prediction:
                        prediction_data['confidence_boost'] = prediction.get('confidence_boost')
                    
                    prediction_ref.set(prediction_data, merge=True)
                    logger.info(f"✅ Saved prediction to Firestore for event_id: {event_id}")
                except Exception as firestore_error:
                    logger.warning(f"Could not save prediction to Firestore: {firestore_error}")
        except Exception as save_error:
            logger.warning(f"Error saving prediction: {save_error}")
        
        prediction.setdefault('model_type', LIVE_MODEL_FAMILY)
        prediction.setdefault('model_family', LIVE_MODEL_FAMILY)
        prediction.setdefault('model_channel', LIVE_MODEL_CHANNEL)
        logger.info("=== predict_match completed successfully ===")
        return prediction
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== predict_match exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return {'error': str(e), 'traceback': error_trace}


@https_fn.on_request(timeout_sec=120, memory=1024)
def predict_match_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for match prediction with explicit CORS support
    Supports both GET and POST requests
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Handle CORS preflight
    if req.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        logger.info("=== predict_match_http called ===")
        
        # Get data from request
        if req.method == 'POST':
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:  # GET
            data = dict(req.args)
        
        logger.info(f"Request data: {data}")
        
        home_team = data.get('home_team')
        away_team = data.get('away_team')
        league_id = data.get('league_id')
        match_date = data.get('match_date')
        enhanced = data.get('enhanced', False)
        
        logger.info(f"Parameters: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}, enhanced={enhanced}")
        
        # Type checking and validation
        if not all([home_team, away_team, league_id, match_date]):
            logger.error(f"Missing required fields: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}")
            response_data = {'error': 'Missing required fields'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Ensure types are correct
        if not isinstance(home_team, str) or not isinstance(away_team, str) or not isinstance(match_date, str):
            logger.error(f"Invalid field types: home_team type={type(home_team)}, away_team type={type(away_team)}, match_date type={type(match_date)}")
            response_data = {'error': 'Invalid field types'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Convert league_id to int
        try:
            league_id_int = int(league_id) if league_id is not None else 0
            if league_id_int == 0:
                raise ValueError("league_id cannot be 0 or None")
            logger.info(f"Converted league_id to int: {league_id_int}")
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert league_id to int: {e}")
            response_data = {'error': 'Invalid league_id'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Get prediction
        if enhanced:
            logger.info("Using enhanced predictor...")
            predictor = get_enhanced_predictor()
            if predictor:
                logger.info("Enhanced predictor obtained, calling get_enhanced_prediction...")
                prediction = predictor.get_enhanced_prediction(
                    str(home_team), str(away_team), league_id_int, str(match_date)
                )
                logger.info(f"Enhanced prediction received: {prediction}")
            else:
                logger.error("Enhanced predictor not available")
                response_data = {'error': 'Enhanced predictor not available'}
                headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
                return https_fn.Response(json.dumps(response_data), status=503, headers=headers)
        else:
            try:
                logger.info("Using standard predictor...")
                predictor = get_predictor()
                logger.info("Predictor obtained, calling predict_match...")
                raw_match_id = data.get('event_id') or data.get('match_id') or data.get('id')
                match_id = None
                try:
                    if raw_match_id is not None and str(raw_match_id).strip() != "":
                        match_id = int(raw_match_id)
                except (TypeError, ValueError):
                    match_id = None
                prediction = predictor.predict_match(
                    str(home_team), str(away_team), league_id_int, str(match_date), match_id=match_id
                )
                logger.info(f"Prediction received: {prediction}")
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                response_data = {'error': f'Prediction failed: {str(e)}', 'traceback': error_trace}
                headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
                return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        # Save prediction to Firestore (same logic as predict_match)
        try:
            event_id = data.get('event_id') or prediction.get('event_id') or prediction.get('match_id')
            
            # If no event_id provided, try to find it from database
            if not event_id:
                try:
                    import sqlite3
                    db_path = os.getenv("DB_PATH")
                    if not db_path:
                        db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                    
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Try to find event_id by matching teams and date
                        query = """
                        SELECT e.id FROM event e
                        LEFT JOIN team ht ON e.home_team_id = ht.id
                        LEFT JOIN team at ON e.away_team_id = at.id
                        WHERE e.league_id = ? 
                          AND (ht.name = ? OR ht.name LIKE ? OR ? LIKE '%' || ht.name || '%')
                          AND (at.name = ? OR at.name LIKE ? OR ? LIKE '%' || at.name || '%')
                          AND e.date_event LIKE ?
                        ORDER BY e.date_event DESC
                        LIMIT 1
                        """
                        
                        date_pattern = f"{match_date}%"
                        cursor.execute(query, (
                            league_id_int,
                            home_team, f"%{home_team}%", home_team,
                            away_team, f"%{away_team}%", away_team,
                            date_pattern
                        ))
                        result = cursor.fetchone()
                        if result:
                            event_id = result[0]
                        conn.close()
                except Exception as db_error:
                    logger.debug(f"Could not find event_id from database: {db_error}")
            
            # Save to Firestore if we have event_id and prediction data
            if event_id and prediction and not prediction.get('error'):
                try:
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    
                    # Extract predicted winner - always verify against scores for consistency
                    home_score = prediction.get('predicted_home_score', 0)
                    away_score = prediction.get('predicted_away_score', 0)
                    
                    # Determine winner from scores (most reliable source)
                    if home_score > away_score:
                        score_based_winner = home_team
                    elif away_score > home_score:
                        score_based_winner = away_team
                    else:
                        score_based_winner = 'Draw'
                    
                    # Get predicted_winner from prediction, but always verify against scores
                    predicted_winner = prediction.get('winner') or prediction.get('predicted_winner')
                    
                    # Convert 'Home'/'Away' to team names if needed
                    if predicted_winner == 'Home':
                        predicted_winner = home_team
                    elif predicted_winner == 'Away':
                        predicted_winner = away_team
                    elif predicted_winner == 'Draw':
                        predicted_winner = 'Draw'
                    
                    # Safety check: if predicted_winner doesn't match scores, use score-based winner
                    if predicted_winner:
                        if (predicted_winner == home_team and home_score <= away_score) or \
                           (predicted_winner == away_team and away_score <= home_score) or \
                           (predicted_winner == 'Draw' and home_score != away_score):
                            # Mismatch detected - use score-based winner
                            predicted_winner = score_based_winner
                    else:
                        # No predicted_winner provided, use score-based
                        predicted_winner = score_based_winner
                    
                    # Prepare prediction data to save
                    prediction_data = {
                        'event_id': int(event_id),
                        'league_id': league_id_int,
                        'home_team': home_team,
                        'away_team': away_team,
                        'match_date': match_date,
                        'predicted_winner': predicted_winner,
                        'winner': predicted_winner,  # Also save as 'winner' for compatibility
                        'predicted_home_score': prediction.get('predicted_home_score'),
                        'predicted_away_score': prediction.get('predicted_away_score'),
                        'home_win_prob': prediction.get('home_win_prob'),
                        'confidence': prediction.get('confidence'),
                        'prediction_type': prediction.get('prediction_type', 'AI Only'),
                        'model_type': prediction.get('model_type', LIVE_MODEL_FAMILY),
                        'model_family': prediction.get('model_family', LIVE_MODEL_FAMILY),
                        'model_channel': prediction.get('model_channel', LIVE_MODEL_CHANNEL),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    }
                    
                    # Add any additional prediction fields
                    if 'ai_probability' in prediction:
                        prediction_data['ai_probability'] = prediction.get('ai_probability')
                    if 'hybrid_probability' in prediction:
                        prediction_data['hybrid_probability'] = prediction.get('hybrid_probability')
                    if 'confidence_boost' in prediction:
                        prediction_data['confidence_boost'] = prediction.get('confidence_boost')
                    
                    prediction_ref.set(prediction_data, merge=True)
                    logger.info(f"✅ Saved prediction to Firestore for event_id: {event_id}")
                except Exception as firestore_error:
                    logger.warning(f"Could not save prediction to Firestore: {firestore_error}")
        except Exception as save_error:
            logger.warning(f"Error saving prediction: {save_error}")
        
        prediction.setdefault('model_type', LIVE_MODEL_FAMILY)
        prediction.setdefault('model_family', LIVE_MODEL_FAMILY)
        prediction.setdefault('model_channel', LIVE_MODEL_CHANNEL)
        logger.info("=== predict_match_http completed successfully ===")
        headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
        return https_fn.Response(json.dumps(prediction), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== predict_match_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {'error': str(e), 'traceback': error_trace}
        headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)


@https_fn.on_call()
def get_upcoming_matches(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get upcoming matches for a league
    
    Request data:
    {
        "league_id": 4986,  # optional
        "limit": 50  # optional, default 50
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== get_upcoming_matches called ===")
        data = req.data or {}
        league_id = data.get('league_id')
        limit = data.get('limit', 50)
        
        logger.info(f"Request data: {data}")
        logger.info(f"League ID: {league_id}, Limit: {limit}")
        
        # Query Firestore for upcoming matches
        try:
            logger.info("Getting Firestore client...")
            db = get_firestore_client()
            matches_ref = db.collection('matches')
            
            logger.info(f"Querying matches collection for league_id={league_id}")
            # CRITICAL FIX: Increased limit significantly to capture all upcoming matches
            # Without ordering by date, upcoming matches may be mixed with completed ones
            # A limit of 200 was too low - many leagues have 400+ total matches
            if league_id:
                matches_ref = matches_ref.where('league_id', '==', int(league_id))
                logger.info(f"Applied league_id filter: {int(league_id)}")
            
            # Increased limit to 1000 to ensure we capture all upcoming matches
            # Even if a league has 400 completed matches, we'll still get the 66 upcoming ones
            matches_ref = matches_ref.limit(1000)  # Increased from 200 to capture all upcoming matches
            logger.info("Using limit=1000 to ensure all upcoming matches are captured")
            
            logger.info("Starting to stream matches from Firestore...")
            
            matches = []
            # Use UTC-aware datetime for comparison with Firestore Timestamps,
            # but evaluate "today" in a local timezone so matches don't disappear during game day.
            from datetime import timezone
            import os
            try:
                from zoneinfo import ZoneInfo  # py3.9+
            except Exception:
                ZoneInfo = None

            tz_name = os.getenv("LOCAL_TIMEZONE", "Africa/Johannesburg")
            local_tz = ZoneInfo(tz_name) if ZoneInfo else timezone.utc

            now_utc = datetime.now(timezone.utc)
            now_local = now_utc.astimezone(local_tz)
            today_local = now_local.date()
            total_checked = 0
            with_scores = 0
            past_dates = 0
            no_date = 0
            date_parse_failures = 0
            sample_dates = []  # Store first few date formats we see
            
            # Collect all team IDs first for batch lookup
            team_ids_to_lookup = set()
            matches_without_teams = []
            
            for doc in matches_ref.stream():
                total_checked += 1
                match_data = doc.to_dict()
                
                if total_checked % 50 == 0:
                    logger.debug(f"Processed {total_checked} matches so far...")
                
                # Double-check league_id matches (safety check)
                match_league_id = match_data.get('league_id')
                if league_id and match_league_id != int(league_id):
                    logger.debug(f"Skipping match {doc.id}: league_id mismatch ({match_league_id} != {int(league_id)})")
                    continue  # Skip matches from other leagues
                
                # Check if date is today or in the future (LOCAL TIMEZONE).
                # IMPORTANT: Do NOT hide matches just because they already have scores on game day
                # (users want to see live scores and final scores until midnight).
                date_event = match_data.get('date_event')
                if date_event:
                    # Handle both datetime and string dates
                    match_date = None
                    is_date_only = False
                    try:
                        # Check for Firestore Timestamp first (most common)
                        # Firestore Timestamp has both timestamp() and to_datetime() methods
                        if hasattr(date_event, 'timestamp') and callable(getattr(date_event, 'to_datetime', None)):
                            # Firestore Timestamp object - convert to datetime
                            try:
                                match_date = date_event.to_datetime()
                                # Ensure timezone-aware (Firestore returns UTC)
                                if match_date.tzinfo is None:
                                    match_date = match_date.replace(tzinfo=timezone.utc)
                            except AttributeError:
                                # Fallback: use timestamp() method
                                match_date = datetime.fromtimestamp(date_event.timestamp(), tz=timezone.utc)
                        elif isinstance(date_event, datetime):
                            match_date = date_event
                            # Ensure timezone-aware
                            if match_date.tzinfo is None:
                                match_date = match_date.replace(tzinfo=timezone.utc)
                        elif isinstance(date_event, str):
                            # Try parsing ISO format or common date formats
                            if 'T' in date_event:
                                match_date = datetime.fromisoformat(date_event.replace('Z', '+00:00'))
                                if match_date.tzinfo is None:
                                    match_date = match_date.replace(tzinfo=timezone.utc)
                            else:
                                # Date-only string (YYYY-MM-DD) - treat as "all-day" for upcoming filtering
                                is_date_only = True
                                # Interpret date-only as local date at midnight so it stays visible all day locally.
                                match_date = datetime.strptime(date_event, '%Y-%m-%d')
                                match_date = match_date.replace(tzinfo=local_tz)
                        else:
                            # Try to convert unknown type
                            raise ValueError(f"Unknown date type: {type(date_event)}")
                    except Exception as parse_error:
                        # If parsing fails, skip this match
                        date_parse_failures += 1
                        # Store sample of failed dates for debugging
                        if len(sample_dates) < 3:
                            sample_dates.append({
                                'date_event': str(date_event),
                                'type': type(date_event).__name__,
                                'error': str(parse_error),
                                'has_timestamp_attr': hasattr(date_event, 'timestamp'),
                                'has_to_datetime': hasattr(date_event, 'to_datetime') if hasattr(date_event, 'timestamp') else False
                            })
                        continue
                    
                    # Include matches that are on/after *today* (local timezone).
                    # This keeps game-day matches visible all day, including live/final scores,
                    # and they will only disappear after local midnight.
                    if match_date:
                        should_include = False
                        try:
                            if is_date_only:
                                match_local_date = match_date.date()
                            else:
                                match_local_date = match_date.astimezone(local_tz).date()
                            should_include = match_local_date >= today_local
                        except Exception:
                            # Fallback: if timezone conversion fails, use UTC date
                            should_include = match_date.date() >= now_utc.date()

                        if should_include:
                            # Track how many included matches already have scores (live/final today)
                            if match_data.get('home_score') is not None or match_data.get('away_score') is not None:
                                with_scores += 1
                            match_data['id'] = doc.id
                            # Convert date to string for JSON serialization
                            if hasattr(date_event, 'timestamp'):
                                match_data['date_event'] = match_date.isoformat()
                            elif isinstance(date_event, datetime):
                                match_data['date_event'] = match_date.isoformat()
                            elif isinstance(date_event, str) and is_date_only:
                                match_data['date_event'] = match_date.date().isoformat()
                            
                            # Collect team IDs for batch lookup
                            home_team_id = match_data.get('home_team_id')
                            away_team_id = match_data.get('away_team_id')
                            
                            logger.debug(f"Match {doc.id}: future match on {match_date.isoformat()}, home_id={home_team_id}, away_id={away_team_id}")
                            
                            if home_team_id:
                                team_ids_to_lookup.add(home_team_id)
                            if away_team_id:
                                team_ids_to_lookup.add(away_team_id)
                            
                            matches_without_teams.append(match_data)
                        else:
                            past_dates += 1
                            # Compare against UTC "now" for logging only
                            days_ago = (now_utc - match_date.astimezone(timezone.utc)).days if match_date.tzinfo else (now_utc.replace(tzinfo=None) - match_date).days
                            logger.debug(f"Skipping match {doc.id}: past date ({days_ago} days ago, {match_date.isoformat()})")
                    else:
                        no_date += 1
                        # Include matches with no date (might be TBD)
                        match_data['id'] = doc.id
                        
                        # Collect team IDs for batch lookup
                        home_team_id = match_data.get('home_team_id')
                        away_team_id = match_data.get('away_team_id')
                        
                        if home_team_id:
                            team_ids_to_lookup.add(home_team_id)
                        if away_team_id:
                            team_ids_to_lookup.add(away_team_id)
                        
                        matches_without_teams.append(match_data)
            
            # Batch lookup team names (optimized - fetch all teams at once)
            team_names = {}
            if team_ids_to_lookup:
                logger.info(f"Looking up {len(team_ids_to_lookup)} unique team IDs...")
                try:
                    # Fetch all teams in batches (Firestore has a limit of 10 items per 'in' query)
                    teams_ref = db.collection('teams')
                    team_ids_list = list(team_ids_to_lookup)
                    
                    logger.info(f"Processing {len(team_ids_list)} team IDs in batches of 10...")
                    # Process in batches of 10 (Firestore 'in' query limit)
                    for i in range(0, len(team_ids_list), 10):
                        batch_ids = team_ids_list[i:i+10]
                        logger.debug(f"Fetching team batch {i//10 + 1}: {batch_ids}")
                        team_docs = teams_ref.where('id', 'in', batch_ids).stream()
                        batch_count = 0
                        for team_doc in team_docs:
                            team_data = team_doc.to_dict()
                            team_id = team_data.get('id')
                            if team_id:
                                team_names[team_id] = team_data.get('name', f'Team {team_id}')
                                batch_count += 1
                        logger.debug(f"Found {batch_count} teams in batch {i//10 + 1}")
                    
                    logger.info(f"Successfully looked up {len(team_names)} team names")
                except Exception as e:
                    logger.warning(f"Batch lookup failed: {e}, falling back to individual queries")
                    # If batch lookup fails, fallback to individual queries
                    teams_ref = db.collection('teams')
                    for team_id in team_ids_to_lookup:
                        try:
                            team_docs = teams_ref.where('id', '==', team_id).limit(1).stream()
                            for team_doc in team_docs:
                                team_data = team_doc.to_dict()
                                team_names[team_id] = team_data.get('name', f'Team {team_id}')
                                break
                        except Exception as e2:
                            logger.warning(f"Failed to lookup team {team_id}: {e2}")
                            pass
            else:
                logger.warning("No team IDs to lookup!")
            
            # Add team names to matches and filter out women's teams
            women_indicators = [' w rugby', ' women', ' womens', ' w ', ' women\'s', ' w\'s']
            logger.info(f"Processing {len(matches_without_teams)} matches, filtering women's teams...")
            
            women_filtered = 0
            for match_data in matches_without_teams:
                home_team_id = match_data.get('home_team_id')
                away_team_id = match_data.get('away_team_id')
                
                home_team_name = team_names.get(home_team_id, f'Team {home_team_id}' if home_team_id else 'Unknown')
                away_team_name = team_names.get(away_team_id, f'Team {away_team_id}' if away_team_id else 'Unknown')
                
                # Filter out women's matches
                home_lower = home_team_name.lower()
                away_lower = away_team_name.lower()
                is_women_home = any(indicator in home_lower for indicator in women_indicators)
                is_women_away = any(indicator in away_lower for indicator in women_indicators)
                
                if is_women_home or is_women_away:
                    women_filtered += 1
                    logger.debug(f"Filtered out women's match: {home_team_name} vs {away_team_name}")
                    continue  # Skip women's matches
                
                match_data['home_team'] = home_team_name
                match_data['away_team'] = away_team_name
                
                matches.append(match_data)
            
            logger.info(f"Filtered out {women_filtered} women's matches, {len(matches)} matches remaining")
            
            # Sort by date and limit (in Python, no index needed)
            def get_sort_key(match):
                date_val = match.get('date_event', '')
                if isinstance(date_val, str):
                    try:
                        return datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                    except:
                        return datetime.min
                elif hasattr(date_val, 'timestamp'):
                    return date_val.to_datetime()
                elif isinstance(date_val, datetime):
                    return date_val
                return datetime.min
            
            logger.info(f"Sorting {len(matches)} matches by date...")
            matches.sort(key=get_sort_key)
            matches = matches[:limit]
            logger.info(f"Returning {len(matches)} matches (limited to {limit})")
            
            # Include debug info
            debug_info = {
                'total_checked': total_checked,
                'with_scores': with_scores,
                'past_dates': past_dates,
                'no_date': no_date,
                'date_parse_failures': date_parse_failures,
                'matches_found': len(matches),
                'team_lookup_count': len(team_ids_to_lookup),
                'team_names_found': len(team_names),
                'women_filtered': women_filtered,
                'sample_dates': sample_dates[:3]  # First 3 samples
            }
            
            logger.info(f"=== get_upcoming_matches completed ===")
            logger.info(f"Debug info: {debug_info}")
            
            return {
                'matches': matches,
                'debug': debug_info
            }
        except Exception as firestore_error:
            # If Firestore query fails, return empty list with error details
            import traceback
            error_details = traceback.format_exc()
            return {'matches': [], 'warning': f'Firestore query failed: {str(firestore_error)}', 'error_details': error_details}
        
    except Exception as e:
        return {'error': str(e), 'matches': []}


@https_fn.on_call()
def get_live_matches(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get live matches
    
    Request data:
    {
        "league_id": 4986  # optional
    }
    """
    try:
        data = req.data
        league_id = data.get('league_id')
        
        enhanced_predictor = get_enhanced_predictor()
        if enhanced_predictor:
            matches = enhanced_predictor.get_live_matches(league_id)
            return {'matches': matches}
        else:
            return {'matches': []}
            
    except Exception as e:
        return {'error': str(e)}


@https_fn.on_request()
def get_live_matches_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for live matches with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    try:
        logger.info("=== get_live_matches_http called ===")

        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)

        league_id = data.get("league_id")
        logger.info(f"Request data: {data}, league_id={league_id}")

        enhanced_predictor = get_enhanced_predictor()
        if enhanced_predictor:
            matches = enhanced_predictor.get_live_matches(league_id)
            response_data = {"matches": matches}
            status = 200
        else:
            logger.warning("Enhanced predictor not available, returning empty matches list")
            response_data = {"matches": []}
            status = 200

        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_live_matches_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=status, headers=headers)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== get_live_matches_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {"error": str(e), "traceback": error_trace}
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)

@https_fn.on_call()
def get_leagues(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get available leagues with match counts
    """
    import sqlite3
    try:
        league_mappings = _get_league_mappings()
        
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")
        
        # Get upcoming match counts for each league
        upcoming_counts = {}
        recent_counts = {}
        
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Count upcoming matches (next 7 days)
            cursor.execute("""
                SELECT e.league_id, COUNT(*) as match_count
                FROM event e
                WHERE date(e.date_event) >= date('now')
                AND date(e.date_event) <= date('now', '+7 days')
                AND e.home_team_id IS NOT NULL
                AND e.away_team_id IS NOT NULL
                GROUP BY e.league_id
            """)
            
            for row in cursor.fetchall():
                league_id, count = row
                upcoming_counts[league_id] = count
            
            # Count recent completed matches (last 7 days)
            cursor.execute("""
                SELECT e.league_id, COUNT(*) as match_count
                FROM event e
                WHERE date(e.date_event) >= date('now', '-7 days')
                AND date(e.date_event) < date('now')
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.home_team_id IS NOT NULL
                AND e.away_team_id IS NOT NULL
                GROUP BY e.league_id
            """)
            
            for row in cursor.fetchall():
                league_id, count = row
                recent_counts[league_id] = count
            
            conn.close()
        
        leagues = []
        for league_id, name in league_mappings.items():
            upcoming = upcoming_counts.get(league_id, 0)
            recent = recent_counts.get(league_id, 0)
            has_news = upcoming > 0 or recent > 0
            
            leagues.append({
                'id': league_id,
                'name': name,
                'upcoming_matches': upcoming,
                'recent_matches': recent,
                'has_news': has_news,
                'total_news': upcoming + recent
            })
        
        return {'leagues': leagues}
        
    except Exception as e:
        print(f"Error in get_leagues: {e}")
        # Fallback to basic league list without counts
        try:
            league_mappings = _get_league_mappings()
            leagues = [
                {'id': league_id, 'name': name, 'upcoming_matches': 0, 'recent_matches': 0, 'has_news': False, 'total_news': 0}
                for league_id, name in league_mappings.items()
            ]
            return {'leagues': leagues}
        except:
            return {'error': str(e)}


def _calculate_last_10_games_accuracy(league_id: int) -> int:
    """
    Helper function to calculate the accuracy of the last 10 completed games for a league.
    Returns the number of correct predictions out of 10.
    This is NOT a Cloud Function - it's a helper function called internally.
    """
    import sqlite3
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
        
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at {db_path}, cannot calculate last 10 games accuracy")
            return 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get last 10 completed games with scores for this league
        query = """
        SELECT e.id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, 
               ht.name as home_team_name, at.name as away_team_name,
               e.date_event, e.timestamp
        FROM event e
        LEFT JOIN team ht ON e.home_team_id = ht.id
        LEFT JOIN team at ON e.away_team_id = at.id
        WHERE e.league_id = ? 
          AND e.home_score IS NOT NULL 
          AND e.away_score IS NOT NULL
          AND e.status != 'Postponed'
        ORDER BY e.date_event DESC, e.timestamp DESC
        LIMIT 10
        """
        
        cursor.execute(query, (league_id,))
        games = cursor.fetchall()
        conn.close()
        
        if len(games) < 10:
            logger.info(f"Only {len(games)} completed games found for league {league_id}")
            # Return 0 if we don't have 10 games yet
            return 0
        
        # Get predictor to make predictions for these games
        try:
            predictor = get_predictor()
            correct_predictions = 0
            
            for game in games:
                event_id, home_team_id, away_team_id, home_score, away_score, \
                home_team_name, away_team_name, date_event, timestamp = game
                
                # Determine actual winner
                if home_score > away_score:
                    actual_winner = 'Home'
                elif away_score > home_score:
                    actual_winner = 'Away'
                else:
                    actual_winner = 'Draw'
                
                # Make prediction (we need to predict as if the game hasn't happened yet)
                # For accuracy, we'd need to have stored predictions made before the game
                # For now, we'll use the model to predict based on pre-game data
                # This is a simplified approach - ideally predictions should be stored
                try:
                    # Try to get stored prediction from Firestore if available
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    prediction_doc = prediction_ref.get()
                    
                    if prediction_doc.exists:
                        pred_data = prediction_doc.to_dict()
                        predicted_winner = pred_data.get('predicted_winner') or pred_data.get('winner', '')
                        
                        # Normalize winner format
                        if predicted_winner == home_team_name or predicted_winner == 'Home':
                            predicted_winner = 'Home'
                        elif predicted_winner == away_team_name or predicted_winner == 'Away':
                            predicted_winner = 'Away'
                        elif predicted_winner == 'Draw':
                            predicted_winner = 'Draw'
                        else:
                            # Try to predict using the model
                            continue
                        
                        if predicted_winner == actual_winner:
                            correct_predictions += 1
                    else:
                        # No stored prediction, skip this game
                        continue
                except Exception as pred_error:
                    logger.debug(f"Error getting prediction for game {event_id}: {pred_error}")
                    continue
            
            logger.info(f"Last 10 games accuracy for league {league_id}: {correct_predictions}/10")
            return correct_predictions
            
        except Exception as pred_error:
            logger.warning(f"Error calculating predictions: {pred_error}")
            return 0
            
    except Exception as e:
        logger.warning(f"Error calculating last 10 games accuracy: {e}")
        return 0


@https_fn.on_call(timeout_sec=300, memory=512)
def get_league_metrics(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get league-specific metrics (accuracy, training games, etc.)
    
    Request data:
    {
        "league_id": 4414  # required
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== get_league_metrics called (V4-first) ===")
        data = req.data or {}
        league_id = data.get('league_id')
        
        if not league_id:
            logger.error("league_id is required")
            return {'error': 'league_id is required'}
        
        league_id_str = str(league_id)
        logger.info(f"Fetching metrics for league_id: {league_id_str}")
        
        # Calculate last 10 games accuracy
        last_10_accuracy = _calculate_last_10_games_accuracy(league_id)
        
        # PRIMARY: Try to load from Firestore (fastest and most reliable)
        try:
            db = get_firestore_client()
            
            # Try individual league metrics document first (fastest)
            logger.info(f"Trying league_metrics/{league_id_str}...")
            # Force fresh read (no cache) by using get() with transaction-like behavior
            league_metric_ref = db.collection('league_metrics').document(league_id_str)
            league_metric_doc = league_metric_ref.get()
            logger.info(f"Document read - exists: {league_metric_doc.exists}, path: {league_metric_ref.path}")
            
            if league_metric_doc.exists:
                league_metric = league_metric_doc.to_dict()
                model_type = league_metric.get('model_type', 'unknown')
                accuracy = league_metric.get('accuracy', 0.0)
                logger.info(f"Found league metrics in Firestore: model_type={model_type}, accuracy={accuracy}%, training_games={league_metric.get('training_games', 0)}")
                logger.info(f"Full league_metric data: {league_metric}")
                
                # Force XGBoost if we detect old stacking data (safety check)
                if model_type == 'stacking' and 'last_updated' in league_metric:
                    last_updated = league_metric.get('last_updated', '')
                    if '2025-12-09' in last_updated:  # Old optimized timestamp
                        logger.warning(f"WARNING: Detected old stacking data, trying to reload from XGBoost registry...")
                        # Fall through to try XGBoost registry
                    else:
                        # Get margin from performance data if available in league_metrics
                        performance = league_metric.get('performance', {})
                        overall_mae = performance.get('overall_mae', 0.0) if performance else 0.0
                        
                        # If no performance data in league_metrics, try to get from model_registry
                        if overall_mae == 0.0:
                            try:
                                registry_ref = db.collection('model_registry').document('xgboost')
                                registry_doc = registry_ref.get()
                                if registry_doc.exists:
                                    registry = registry_doc.to_dict()
                                    league_data = registry.get('leagues', {}).get(league_id_str)
                                    if league_data:
                                        perf = league_data.get('performance', {})
                                        overall_mae = perf.get('overall_mae', 0.0)
                            except Exception as e:
                                logger.debug(f"Could not get margin from model_registry: {e}")
                        
                        return {
                            'league_id': league_id,
                            'accuracy': accuracy,
                            'training_games': league_metric.get('training_games', 0),
                            'ai_rating': league_metric.get('ai_rating', 'N/A'),
                            'overall_mae': round(overall_mae, 2) if overall_mae > 0 else 0.0,
                            'trained_at': league_metric.get('trained_at'),
                            'model_type': model_type,
                            'model_family': league_metric.get('model_family', model_type or LIVE_MODEL_FAMILY),
                            'model_channel': league_metric.get('model_channel', LIVE_MODEL_CHANNEL),
                        }
                else:
                    # Get margin from performance data if available in league_metrics
                    performance = league_metric.get('performance', {})
                    overall_mae = performance.get('overall_mae', 0.0) if performance else 0.0
                    
                    # If no performance data in league_metrics, try to get from model_registry
                    if overall_mae == 0.0:
                        try:
                            registry_ref = db.collection('model_registry').document('xgboost')
                            registry_doc = registry_ref.get()
                            if registry_doc.exists:
                                registry = registry_doc.to_dict()
                                league_data = registry.get('leagues', {}).get(league_id_str)
                                if league_data:
                                    perf = league_data.get('performance', {})
                                    overall_mae = perf.get('overall_mae', 0.0)
                        except Exception as e:
                            logger.debug(f"Could not get margin from model_registry: {e}")
                    
                    return {
                        'league_id': league_id,
                        'accuracy': accuracy,
                        'training_games': league_metric.get('training_games', 0),
                        'ai_rating': league_metric.get('ai_rating', 'N/A'),
                        'overall_mae': round(overall_mae, 2) if overall_mae > 0 else 0.0,
                        'trained_at': league_metric.get('trained_at'),
                        'model_type': model_type,
                        'model_family': league_metric.get('model_family', model_type or LIVE_MODEL_FAMILY),
                        'model_channel': league_metric.get('model_channel', LIVE_MODEL_CHANNEL),
                    }
            
            # Fallback registry lookup (V4 first, then legacy docs).
            for registry_doc_name in ['v4', 'xgboost', 'optimized']:
                logger.info(f"Trying model_registry/{registry_doc_name}...")
                registry_ref = db.collection('model_registry').document(registry_doc_name)
                registry_doc = registry_ref.get()
                if not registry_doc.exists:
                    continue
            
                registry = registry_doc.to_dict()
                league_data = registry.get('leagues', {}).get(league_id_str)
                
                if league_data:
                    performance = league_data.get('performance', {})
                    accuracy = performance.get('winner_accuracy', 0.0) * 100
                    training_games = league_data.get('training_games', 0)
                    
                    # Calculate AI rating based on accuracy
                    if accuracy >= 80:
                        ai_rating = '9/10'
                    elif accuracy >= 75:
                        ai_rating = '8/10'
                    elif accuracy >= 70:
                        ai_rating = '7/10'
                    elif accuracy >= 65:
                        ai_rating = '6/10'
                    elif accuracy >= 60:
                        ai_rating = '5/10'
                    else:
                        ai_rating = '4/10'
                    
                    # Get margin from performance data
                    overall_mae = performance.get('overall_mae', 0.0)
                    
                    logger.info(
                        f"Found league data in registry/{registry_doc_name}: accuracy={accuracy}, "
                        f"games={training_games}, margin={overall_mae}"
                    )
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'overall_mae': round(overall_mae, 2),
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', registry_doc_name),
                        'model_family': league_data.get('model_family', league_data.get('model_type', registry_doc_name)),
                        'model_channel': league_data.get('model_channel', LIVE_MODEL_CHANNEL),
                    }
        except Exception as firestore_error:
            logger.warning(f"Error loading from Firestore: {firestore_error}")
        
        # FALLBACK: Try to load from Cloud Storage (XGBoost first, then optimized)
        try:
            from firebase_admin import storage
            bucket = storage.bucket()
            
            # Try XGBoost registry first
            blob = bucket.blob('model_registry.json')
            if not blob.exists():
                blob = bucket.blob('artifacts/model_registry.json')
            
            if blob.exists():
                logger.info("Trying Cloud Storage (XGBoost registry)...")
                registry_json = blob.download_as_text()
                registry = json.loads(registry_json)
                model_type_preference = 'xgboost'
            else:
                # Fallback to optimized registry
                blob = bucket.blob('model_registry_optimized.json')
                if not blob.exists():
                    blob = bucket.blob('artifacts_optimized/model_registry_optimized.json')
                if blob.exists():
                    logger.info("Trying Cloud Storage (Optimized registry)...")
                    registry_json = blob.download_as_text()
                    registry = json.loads(registry_json)
                    model_type_preference = 'stacking'
                else:
                    raise FileNotFoundError("No registry found in Cloud Storage")
            
            if blob.exists():
                
                league_data = registry.get('leagues', {}).get(league_id_str)
                
                if league_data:
                    performance = league_data.get('performance', {})
                    accuracy = performance.get('winner_accuracy', 0.0) * 100
                    training_games = league_data.get('training_games', 0)
                    
                    # Calculate AI rating based on accuracy
                    if accuracy >= 80:
                        ai_rating = '9/10'
                    elif accuracy >= 75:
                        ai_rating = '8/10'
                    elif accuracy >= 70:
                        ai_rating = '7/10'
                    elif accuracy >= 65:
                        ai_rating = '6/10'
                    elif accuracy >= 60:
                        ai_rating = '5/10'
                    else:
                        ai_rating = '4/10'
                    
                    # Get margin from performance data
                    overall_mae = performance.get('overall_mae', 0.0)
                    
                    logger.info(f"Found league data in Cloud Storage: accuracy={accuracy}, games={training_games}, margin={overall_mae}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'overall_mae': round(overall_mae, 2),
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', model_type_preference if 'model_type_preference' in locals() else 'unknown'),
                        'model_family': league_data.get('model_family', league_data.get('model_type', LIVE_MODEL_FAMILY)),
                        'model_channel': league_data.get('model_channel', LIVE_MODEL_CHANNEL),
                    }
        except Exception as storage_error:
            logger.warning(f"Error loading from storage: {storage_error}")
        
        # FALLBACK: Try to load from local file (for development or if included in deployment)
        # Try XGBoost registry first, then optimized
        possible_paths = [
            os.path.join(os.path.dirname(__file__), 'artifacts', 'model_registry.json'),
            os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'model_registry.json'),
            os.path.join(os.getcwd(), 'artifacts', 'model_registry.json'),
            '/tmp/artifacts/model_registry.json',
            os.path.join(os.path.dirname(__file__), 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.path.dirname(__file__), '..', 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.getcwd(), 'artifacts_optimized', 'model_registry_optimized.json'),
            '/tmp/artifacts_optimized/model_registry_optimized.json',
        ]
        
        for registry_path in possible_paths:
            try:
                if os.path.exists(registry_path):
                    logger.info(f"Trying local file: {registry_path}")
                    with open(registry_path, 'r') as f:
                        registry = json.load(f)
                        league_data = registry.get('leagues', {}).get(league_id_str)
                        
                        if league_data:
                            performance = league_data.get('performance', {})
                            accuracy = performance.get('winner_accuracy', 0.0) * 100
                            training_games = league_data.get('training_games', 0)
                            
                            # Calculate AI rating
                            if accuracy >= 80:
                                ai_rating = '9/10'
                            elif accuracy >= 75:
                                ai_rating = '8/10'
                            elif accuracy >= 70:
                                ai_rating = '7/10'
                            elif accuracy >= 65:
                                ai_rating = '6/10'
                            elif accuracy >= 60:
                                ai_rating = '5/10'
                            else:
                                ai_rating = '4/10'
                            
                            # Determine model type from path
                            model_type = league_data.get('model_type', 'unknown')
                            if 'artifacts_optimized' in registry_path or 'optimized' in registry_path.lower():
                                model_type = league_data.get('model_type', 'stacking')
                            elif 'artifacts' in registry_path and 'optimized' not in registry_path:
                                model_type = league_data.get('model_type', 'xgboost')
                            
                            # Get margin from performance data
                            overall_mae = performance.get('overall_mae', 0.0)
                            
                            logger.info(f"✅ Found league data in local file: accuracy={accuracy:.1f}%, games={training_games}, margin={overall_mae:.2f}, type={model_type}")
                            return {
                                'league_id': league_id,
                                'accuracy': round(accuracy, 1),
                                'training_games': training_games,
                                'ai_rating': ai_rating,
                                'overall_mae': round(overall_mae, 2),
                                'trained_at': league_data.get('trained_at'),
                                'model_type': model_type,
                                'model_family': league_data.get('model_family', model_type or LIVE_MODEL_FAMILY),
                                'model_channel': league_data.get('model_channel', LIVE_MODEL_CHANNEL),
                            }
            except Exception as file_error:
                logger.debug(f"Error loading from {registry_path}: {file_error}")
                continue
        
        # Default fallback if no data found
        logger.warning(f"⚠️ No metrics found for league_id {league_id_str} in any source. Returning defaults.")
        logger.warning(
            "   To fix this, run: python scripts/publish_v4_metrics_to_firestore.py "
            "--report artifacts/maz_maxed_v4_metrics_latest.json"
        )
        return {
            'league_id': league_id,
            'accuracy': 0.0,
            'training_games': 0,
            'ai_rating': 'N/A',
            'overall_mae': 0.0,
            'trained_at': None,
            'model_type': 'unknown',
            'model_family': LIVE_MODEL_FAMILY,
            'model_channel': LIVE_MODEL_CHANNEL,
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_league_metrics: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return {'error': str(e)}


@https_fn.on_call()
def verify_license_key(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Verify a license key and return authentication status.
    
    Request: { 'license_key': 'XXXX-XXXX-XXXX-XXXX' }
    Response: { 'valid': bool, 'expires_at': timestamp, 'subscription_type': str }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = get_firestore_client()
        license_key = req.data.get('license_key', '').strip().upper()
        
        # Normalize: remove dashes and spaces for comparison
        # Frontend sends keys without dashes, but Firestore stores with dashes
        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        logger.info(f"Verifying license key: {license_key[:8]}... (normalized: {license_key_normalized[:8]}...)")
        
        if not license_key_normalized:
            return {'valid': False, 'error': 'License key is required'}
        
        # Query Firestore - need to check both formats (with and without dashes)
        subscriptions_ref = db.collection('subscriptions')
        
        # Try exact match first (in case key is stored without dashes)
        query = subscriptions_ref.where('license_key', '==', license_key).limit(1)
        docs = list(query.stream())
        
        # If not found, try with dashes formatted (XXXX-XXXX-XXXX-XXXX)
        if not docs and len(license_key_normalized) == 16:
            formatted_key = f"{license_key_normalized[0:4]}-{license_key_normalized[4:8]}-{license_key_normalized[8:12]}-{license_key_normalized[12:16]}"
            query = subscriptions_ref.where('license_key', '==', formatted_key).limit(1)
            docs = list(query.stream())
            if docs:
                logger.info(f"Found key with formatted dashes: {formatted_key}")
        
        # If still not found, try normalized (no dashes)
        if not docs:
            query = subscriptions_ref.where('license_key', '==', license_key_normalized).limit(1)
            docs = list(query.stream())
            if docs:
                logger.info(f"Found key without dashes: {license_key_normalized}")
        
        logger.info(f"Found {len(docs)} documents matching license key")
        
        if not docs:
            # Try to list all keys for debugging (remove in production)
            all_docs = list(subscriptions_ref.limit(5).stream())
            logger.warning(f"Invalid license key attempted: {license_key} (normalized: {license_key_normalized})")
            sample_keys = [doc.to_dict().get('license_key', 'N/A')[:12] + '...' for doc in all_docs]
            logger.info(f"Sample keys in database: {sample_keys}")
            return {'valid': False, 'error': 'Invalid license key'}
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        
        # Check if subscription is active
        now = datetime.utcnow()
        expires_at = subscription.get('expires_at')
        
        if expires_at:
            # Handle Firestore Timestamp
            if hasattr(expires_at, 'timestamp'):
                expires_datetime = datetime.utcfromtimestamp(expires_at.timestamp())
            elif isinstance(expires_at, datetime):
                expires_datetime = expires_at
            else:
                expires_datetime = datetime.utcnow() + timedelta(days=30)  # Default fallback
            
            if expires_datetime < now:
                logger.warning(f"Expired license key: {license_key[:8]}...")
                return {'valid': False, 'error': 'License key has expired'}
        
        # Check if already used (optional - for single-use keys)
        if subscription.get('used', False) and not subscription.get('reusable', True):
            logger.warning(f"Already used license key: {license_key[:8]}...")
            return {'valid': False, 'error': 'License key has already been used'}
        
        # Mark as used if not reusable
        if not subscription.get('reusable', True):
            subscriptions_ref.document(subscription_id).update({'used': True, 'used_at': firestore.SERVER_TIMESTAMP})
        
        # Update last_used timestamp
        subscriptions_ref.document(subscription_id).update({'last_used': firestore.SERVER_TIMESTAMP})
        
        logger.info(f"Valid license key verified: {license_key[:8]}...")
        
        return {
            'valid': True,
            'expires_at': expires_at.timestamp() if hasattr(expires_at, 'timestamp') else None,
            'subscription_type': subscription.get('subscription_type', 'premium'),
            'email': subscription.get('email', ''),
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error verifying license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'valid': False, 'error': 'Server error verifying license key'}


@https_fn.on_request()
def verify_license_key_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for license key verification with explicit CORS support.
    This is used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)
        
        license_key = data.get('license_key', '').strip().upper()
        
        # Normalize: remove dashes and spaces for comparison
        # Frontend sends keys without dashes, but Firestore stores with dashes
        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        if not license_key_normalized:
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'License key is required'}),
                status=400,
                headers=headers
            )
        
        # Use the same verification logic as the callable function
        db = get_firestore_client()
        subscriptions_ref = db.collection('subscriptions')
        
        # Try exact match first (in case key is stored without dashes)
        query = subscriptions_ref.where('license_key', '==', license_key).limit(1)
        docs = list(query.stream())
        
        # If not found, try with dashes formatted (XXXX-XXXX-XXXX-XXXX)
        if not docs and len(license_key_normalized) == 16:
            formatted_key = f"{license_key_normalized[0:4]}-{license_key_normalized[4:8]}-{license_key_normalized[8:12]}-{license_key_normalized[12:16]}"
            query = subscriptions_ref.where('license_key', '==', formatted_key).limit(1)
            docs = list(query.stream())
        
        # If still not found, try normalized (no dashes)
        if not docs:
            query = subscriptions_ref.where('license_key', '==', license_key_normalized).limit(1)
            docs = list(query.stream())
        
        if not docs:
            logger.warning(f"Invalid license key attempted: {license_key[:8]}... (normalized: {license_key_normalized[:8]}...)")
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'Invalid license key'}),
                status=200,
                headers=headers
            )
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        
        # Check if subscription is active
        now = datetime.utcnow()
        expires_at = subscription.get('expires_at')
        
        if expires_at:
            # Handle Firestore Timestamp
            if hasattr(expires_at, 'timestamp'):
                expires_datetime = datetime.utcfromtimestamp(expires_at.timestamp())
            elif isinstance(expires_at, datetime):
                expires_datetime = expires_at
            else:
                expires_datetime = datetime.utcnow() + timedelta(days=30)
            
            if expires_datetime < now:
                logger.warning(f"Expired license key: {license_key[:8]}...")
                headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                return https_fn.Response(
                    json.dumps({'valid': False, 'error': 'License key has expired'}),
                    status=200,
                    headers=headers
                )
        
        # Check if already used (optional - for single-use keys)
        if subscription.get('used', False) and not subscription.get('reusable', True):
            logger.warning(f"Already used license key: {license_key[:8]}...")
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'License key has already been used'}),
                status=200,
                headers=headers
            )
        
        # Mark as used if not reusable
        if not subscription.get('reusable', True):
            subscriptions_ref.document(subscription_id).update({'used': True, 'used_at': firestore.SERVER_TIMESTAMP})
        
        # Update last_used timestamp
        subscriptions_ref.document(subscription_id).update({'last_used': firestore.SERVER_TIMESTAMP})
        
        logger.info(f"Valid license key verified: {license_key[:8]}...")
        
        response_data = {
            'valid': True,
            'expires_at': expires_at.timestamp() if hasattr(expires_at, 'timestamp') else None,
            'subscription_type': subscription.get('subscription_type', 'premium'),
            'email': subscription.get('email', ''),
        }
        
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        return https_fn.Response(
            json.dumps(response_data),
            status=200,
            headers=headers
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Error verifying license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        return https_fn.Response(
            json.dumps({'valid': False, 'error': 'Server error verifying license key'}),
            status=500,
            headers=headers
        )


@https_fn.on_call()
def generate_license_key(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Generate a new license key for a subscription purchase.
    This would typically be called by a payment webhook (Stripe, PayPal, etc.)
    
    Request: { 
        'email': 'user@example.com',
        'subscription_type': 'monthly' | 'yearly',
        'duration_days': 30 (optional, defaults based on subscription_type)
    }
    Response: { 'license_key': 'XXXX-XXXX-XXXX-XXXX', 'expires_at': timestamp }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Optional: Add admin authentication check here
        # For now, we'll allow it but you should secure this endpoint
        
        db = get_firestore_client()
        email = req.data.get('email', '').strip().lower()
        subscription_type = req.data.get('subscription_type', 'monthly')
        duration_days = req.data.get('duration_days')
        
        if not email:
            return {'error': 'Email is required'}
        
        # Set duration based on subscription type
        if not duration_days:
            if subscription_type == 'yearly':
                duration_days = 365
            elif subscription_type == 'monthly':
                duration_days = 30
            else:
                duration_days = 30  # Default
        
        # Generate a secure license key (format: XXXX-XXXX-XXXX-XXXX)
        alphabet = string.ascii_uppercase + string.digits
        key_parts = []
        for _ in range(4):
            part = ''.join(secrets.choice(alphabet) for _ in range(4))
            key_parts.append(part)
        license_key = '-'.join(key_parts)
        
        # Calculate expiration date
        expires_at = datetime.utcnow() + timedelta(days=duration_days)
        
        # Store in Firestore
        subscription_data = {
            'license_key': license_key,
            'email': email,
            'subscription_type': subscription_type,
            'created_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at,
            'used': False,
            'reusable': True,  # Allow multiple logins with same key
            'active': True,
        }
        
        doc_ref = db.collection('subscriptions').add(subscription_data)
        subscription_id = doc_ref[1].id
        
        logger.info(f"Generated license key for {email}: {license_key[:8]}...")
        
        # TODO: Send email with license key using Gmail API or email service
        # This would typically use:
        # - Gmail API (requires OAuth setup)
        # - SendGrid, Mailgun, or similar service
        # - Firebase Extensions for email
        
        return {
            'license_key': license_key,
            'expires_at': expires_at.timestamp(),
            'subscription_id': subscription_id,
            'email': email,
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'error': f'Error generating license key: {str(e)}'}


@https_fn.on_call(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def generate_license_key_with_email(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Generate a license key, save to Firestore, and send email.
    This is called after payment is processed.
    
    Request: {
        'email': 'user@example.com',
        'name': 'John Doe',
        'subscription_type': 'monthly' | '6months' | 'yearly',
        'duration_days': 30 (optional),
        'amount': 29 (optional, for records)
    }
    Response: {
        'license_key': 'XXXX-XXXX-XXXX-XXXX',
        'expires_at': timestamp,
        'subscription_id': '...',
        'email_sent': bool
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = get_firestore_client()
        email = req.data.get('email', '').strip().lower()
        name = req.data.get('name', '').strip()
        subscription_type = req.data.get('subscription_type', 'monthly')
        duration_days = req.data.get('duration_days')
        amount = req.data.get('amount', 0)
        
        if not email:
            return {'error': 'Email is required'}
        
        # Map subscription types to duration
        if not duration_days:
            if subscription_type == 'yearly':
                duration_days = 365
            elif subscription_type == '6months':
                duration_days = 180
            elif subscription_type == 'monthly':
                duration_days = 30
            else:
                duration_days = 30
        
        # Generate license key
        alphabet = string.ascii_uppercase + string.digits
        key_parts = []
        for _ in range(4):
            part = ''.join(secrets.choice(alphabet) for _ in range(4))
            key_parts.append(part)
        license_key = '-'.join(key_parts)
        
        # Calculate expiration date
        expires_at = datetime.utcnow() + timedelta(days=duration_days)
        
        # Store in Firestore
        subscription_data = {
            'license_key': license_key,
            'email': email,
            'name': name,
            'subscription_type': subscription_type,
            'duration_days': duration_days,
            'amount': amount,
            'created_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at,
            'used': False,
            'reusable': True,
            'active': True,
            'payment_completed': True,
            'payment_date': firestore.SERVER_TIMESTAMP,
        }
        
        doc_ref = db.collection('subscriptions').add(subscription_data)
        subscription_id = doc_ref[1].id
        
        logger.info(f"Generated license key for {email}: {license_key[:8]}... (Duration: {duration_days} days)")
        
        # Send email with license key
        email_sent = False
        email_error_message = None
        try:
            email_result = send_license_key_email(email, name, license_key, subscription_type, duration_days, expires_at)
            if isinstance(email_result, dict):
                email_sent = email_result.get('success', False)
                email_error_message = email_result.get('error', None)
            else:
                email_sent = bool(email_result)
            
            if email_sent:
                logger.info(f"Email sent successfully to {email}")
            else:
                logger.warning(f"Email sending failed for {email}, but license key was created")
                if email_error_message:
                    logger.warning(f"Email error: {email_error_message}")
        except Exception as email_error:
            logger.error(f"Error sending email: {str(email_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            email_error_message = str(email_error)
            # Don't fail the whole operation if email fails
        
        response = {
            'license_key': license_key,
            'expires_at': expires_at.timestamp(),
            'subscription_id': subscription_id,
            'email': email,
            'email_sent': email_sent,
            'duration_days': duration_days,
            'subscription_type': subscription_type,
        }
        
        if email_error_message:
            response['email_error'] = email_error_message
        
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating license key with email: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'error': f'Error processing subscription: {str(e)}'}


def send_license_key_email(email: str, name: str, license_key: str, subscription_type: str, duration_days: int, expires_at: datetime) -> bool:
    """
    Send license key email to user.
    Returns True if email was sent successfully, False otherwise.
    
    You can implement this using:
    - SendGrid (recommended)
    - Gmail API
    - Mailgun
    - AWS SES
    - Firebase Extensions (Email Trigger)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Option 1: Using SendGrid (recommended for production)
        # Uncomment and configure if you have SendGrid API key
        # Example implementation:
        # import sendgrid
        # from sendgrid.helpers.mail import Mail, Email, To, Content
        # 
        # sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
        # from_email = Email("noreply@rugbyai.com")  # Your verified sender
        # to_email = To(email)
        # 
        # # Format expiration date
        # expires_str = expires_at.strftime('%B %d, %Y')
        # duration_str = f"{duration_days} days" if duration_days < 365 else f"{duration_days // 365} year(s)"
        # 
        # subject = "Your Rugby AI Predictor License Key"
        # html_content = f"""
        # <html>
        # <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        #     <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        #         <h2 style="color: #22c55e;">Thank you for your subscription!</h2>
        #         <p>Hi {name},</p>
        #         <p>Your subscription to Rugby AI Predictor has been activated!</p>
        #         <div style="background: #f8fafc; border: 2px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
        #             <p style="margin: 0; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;">Your License Key</p>
        #             <p style="margin: 10px 0; font-size: 24px; font-weight: 700; color: #22c55e; letter-spacing: 3px; font-family: monospace;">{license_key}</p>
        #         </div>
        #         <p><strong>Subscription Details:</strong></p>
        #         <ul>
        #             <li>Plan: {subscription_type.title()}</li>
        #             <li>Duration: {duration_str}</li>
        #             <li>Expires: {expires_str}</li>
        #         </ul>
        #         <p>To activate your account:</p>
        #         <ol>
        #             <li>Go to the Rugby AI Predictor login page</li>
        #             <li>Enter your license key: <strong>{license_key}</strong></li>
        #             <li>Start accessing premium predictions!</li>
        #         </ol>
        #         <p style="margin-top: 30px; color: #64748b; font-size: 14px;">
        #             If you have any questions, please contact our support team.
        #         </p>
        #         <p style="margin-top: 20px;">
        #             Best regards,<br>
        #             Rugby AI Predictor Team
        #         </p>
        #     </div>
        # </body>
        # </html>
        # """
        # content = Content("text/html", html_content)
        # message = Mail(from_email, to_email, subject, content)
        # response = sg.send(message)
        # return response.status_code == 202
        
        # Option 2: Using Gmail API (requires OAuth setup)
        # See LICENSE_KEY_SETUP.md for Gmail API implementation
        
        # Option 3: Using Gmail SMTP (easiest to set up)
        # 
        # SETUP INSTRUCTIONS:
        # 1. Get Gmail App Password: https://myaccount.google.com/apppasswords
        # 2. Set as Firebase Functions secrets:
        #    firebase functions:secrets:set GMAIL_USER
        #    firebase functions:secrets:set GMAIL_APP_PASSWORD
        # 3. Deploy: firebase deploy --only functions:generate_license_key_with_email
        #
        # Try to get secrets from multiple sources:
        # 1. Environment variables (Firebase Functions v2 injects them automatically)
        # 2. Legacy Firebase Functions config
        # 3. Secret Manager API as fallback
        
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # Try legacy config method (works with older firebase-functions versions)
        # Legacy config is available via FIREBASE_CONFIG environment variable (JSON)
        if not gmail_user or not gmail_password:
            try:
                # Legacy config is stored in FIREBASE_CONFIG as JSON
                firebase_config_str = os.getenv('FIREBASE_CONFIG')
                if firebase_config_str:
                    import json
                    firebase_config = json.loads(firebase_config_str)
                    # Config structure: {"gmail": {"user": "...", "app_password": "..."}}
                    if 'gmail' in firebase_config:
                        gmail_config = firebase_config['gmail']
                        if not gmail_user and 'user' in gmail_config:
                            gmail_user = gmail_config['user']
                        if not gmail_password and 'app_password' in gmail_config:
                            gmail_password = gmail_config['app_password']
                        if gmail_user or gmail_password:
                            logger.info("✅ Retrieved Gmail credentials from legacy config (FIREBASE_CONFIG)")
            except Exception as config_err:
                logger.debug(f"Legacy config (FIREBASE_CONFIG) not available: {config_err}")
            
            # Also try accessing via functions.config() if available
            if not gmail_user or not gmail_password:
                try:
                    # Try the functions.config() method directly
                    from firebase_functions import config as functions_config
                    if hasattr(functions_config, 'gmail'):
                        if not gmail_user:
                            gmail_user = getattr(functions_config.gmail, 'user', None)
                        if not gmail_password:
                            gmail_password = getattr(functions_config.gmail, 'app_password', None)
                        if gmail_user or gmail_password:
                            logger.info("✅ Retrieved Gmail credentials from functions.config()")
                except (ImportError, AttributeError) as e:
                    logger.debug(f"functions.config() not available: {e}")
            
            # Also try direct environment variable access (legacy config might set these directly)
            if not gmail_user:
                gmail_user = os.getenv('GMAIL_USER') or os.getenv('gmail_user')
            if not gmail_password:
                gmail_password = os.getenv('GMAIL_APP_PASSWORD') or os.getenv('gmail_app_password') or os.getenv('gmail.app_password')
        
        # If not found in env vars, try Secret Manager API directly
        if not gmail_user or not gmail_password:
            logger.info("Secrets not found in environment variables, trying Secret Manager API...")
            try:
                from google.cloud import secretmanager
                # Get project ID - try multiple sources
                project_id = (
                    os.getenv('GCP_PROJECT') or 
                    os.getenv('GOOGLE_CLOUD_PROJECT') or 
                    os.getenv('GCLOUD_PROJECT') or
                    'rugby-ai-61fd0'
                )
                logger.info(f"Using project ID: {project_id}")
                
                # Initialize client
                try:
                    client = secretmanager.SecretManagerServiceClient()
                    logger.info("Secret Manager client initialized")
                except Exception as client_err:
                    logger.error(f"Failed to initialize Secret Manager client: {client_err}")
                    raise
                
                if not gmail_user:
                    try:
                        # Try with project number first (Firebase uses project number for secrets)
                        # Firebase secrets are stored as: projects/PROJECT_NUMBER/secrets/SECRET_NAME
                        # But we can also try with project ID
                        secret_name = f"projects/{project_id}/secrets/GMAIL_USER/versions/latest"
                        logger.info(f"Attempting to access secret: {secret_name}")
                        response = client.access_secret_version(request={"name": secret_name})
                        gmail_user = response.payload.data.decode("UTF-8").strip()
                        logger.info("✅ Retrieved GMAIL_USER from Secret Manager")
                    except Exception as e:
                        # Try with project number (645506509698)
                        try:
                            secret_name = f"projects/645506509698/secrets/GMAIL_USER/versions/latest"
                            logger.info(f"Trying with project number: {secret_name}")
                            response = client.access_secret_version(request={"name": secret_name})
                            gmail_user = response.payload.data.decode("UTF-8").strip()
                            logger.info("✅ Retrieved GMAIL_USER from Secret Manager (using project number)")
                        except Exception as e2:
                            logger.error(f"❌ Could not retrieve GMAIL_USER from Secret Manager")
                            logger.error(f"Error with project ID: {str(e)}")
                            logger.error(f"Error with project number: {str(e2)}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")
                
                if not gmail_password:
                    try:
                        secret_name = f"projects/{project_id}/secrets/GMAIL_APP_PASSWORD/versions/latest"
                        logger.info(f"Attempting to access secret: {secret_name}")
                        response = client.access_secret_version(request={"name": secret_name})
                        gmail_password = response.payload.data.decode("UTF-8").strip()
                        logger.info("✅ Retrieved GMAIL_APP_PASSWORD from Secret Manager")
                    except Exception as e:
                        # Try with project number
                        try:
                            secret_name = f"projects/645506509698/secrets/GMAIL_APP_PASSWORD/versions/latest"
                            logger.info(f"Trying with project number: {secret_name}")
                            response = client.access_secret_version(request={"name": secret_name})
                            gmail_password = response.payload.data.decode("UTF-8").strip()
                            logger.info("✅ Retrieved GMAIL_APP_PASSWORD from Secret Manager (using project number)")
                        except Exception as e2:
                            logger.error(f"❌ Could not retrieve GMAIL_APP_PASSWORD from Secret Manager")
                            logger.error(f"Error with project ID: {str(e)}")
                            logger.error(f"Error with project number: {str(e2)}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")
            except ImportError as import_err:
                logger.error(f"❌ google-cloud-secret-manager not available: {import_err}")
                logger.error("Install it with: pip install google-cloud-secret-manager")
            except Exception as e:
                logger.error(f"❌ Error accessing Secret Manager: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Debug logging
        logger.info(f"Checking for Gmail credentials...")
        logger.info(f"GMAIL_USER exists: {gmail_user is not None}")
        logger.info(f"GMAIL_APP_PASSWORD exists: {gmail_password is not None}")
        if gmail_user:
            logger.info(f"GMAIL_USER value: {gmail_user[:3]}...{gmail_user[-3:] if len(gmail_user) > 6 else '***'}")
        if not gmail_user or not gmail_password:
            logger.warning("Gmail credentials not found in environment variables or Secret Manager!")
            logger.warning("Available env vars starting with GMAIL: " + str([k for k in os.environ.keys() if 'GMAIL' in k.upper()]))
            logger.warning("All env vars: " + str(list(os.environ.keys())[:20]))  # First 20 for debugging
        
        if gmail_user and gmail_password:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                # Format expiration date
                expires_str = expires_at.strftime('%B %d, %Y')
                duration_str = f"{duration_days} days" if duration_days < 365 else f"{duration_days // 365} year(s)"
                
                # Create email
                msg = MIMEMultipart('alternative')
                msg['Subject'] = "Your Rugby AI Predictor License Key"
                # Send from your Gmail address with a friendly name
                msg['From'] = f"Rugby AI Predictor <{gmail_user}>"
                msg['To'] = email
                msg['Reply-To'] = gmail_user  # Replies go back to your email
                
                # HTML email body
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #22c55e;">Thank you for your subscription!</h2>
                        <p>Hi {name},</p>
                        <p>Your subscription to Rugby AI Predictor has been activated!</p>
                        
                        <div style="background: #f8fafc; border: 2px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;">Your License Key</p>
                            <p style="margin: 10px 0; font-size: 24px; font-weight: 700; color: #22c55e; letter-spacing: 3px; font-family: monospace;">{license_key}</p>
                        </div>
                        
                        <p><strong>Subscription Details:</strong></p>
                        <ul>
                            <li>Plan: {subscription_type.title()}</li>
                            <li>Duration: {duration_str}</li>
                            <li>Expires: {expires_str}</li>
                        </ul>
                        
                        <p>To activate your account:</p>
                        <ol>
                            <li>Go to the Rugby AI Predictor login page</li>
                            <li>Enter your license key: <strong>{license_key}</strong></li>
                            <li>Start accessing premium predictions!</li>
                        </ol>
                        
                        <p style="margin-top: 30px; color: #64748b; font-size: 14px;">
                            If you have any questions, please contact our support team.
                        </p>
                        
                        <p style="margin-top: 20px;">
                            Best regards,<br>
                            Rugby AI Predictor Team
                        </p>
                    </div>
                </body>
                </html>
                """
                
                # Plain text version
                text_body = f"""
Thank you for your subscription!

Hi {name},

Your subscription to Rugby AI Predictor has been activated!

Your License Key: {license_key}

Subscription Details:
- Plan: {subscription_type.title()}
- Duration: {duration_str}
- Expires: {expires_str}

To activate your account:
1. Go to the Rugby AI Predictor login page
2. Enter your license key: {license_key}
3. Start accessing premium predictions!

If you have any questions, please contact our support team.

Best regards,
Rugby AI Predictor Team
                """
                
                part1 = MIMEText(text_body, 'plain')
                part2 = MIMEText(html_body, 'html')
                
                msg.attach(part1)
                msg.attach(part2)
                
                # Send email via Gmail SMTP
                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(gmail_user, gmail_password)
                    server.send_message(msg)
                
                logger.info(f"Email sent successfully to {email}")
                return {'success': True}
                
            except Exception as smtp_error:
                import traceback
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"SMTP email sending failed: {str(smtp_error)}")
                logger.error(f"SMTP error type: {type(smtp_error).__name__}")
                logger.error(f"SMTP error details: {error_details}")
                # Return error details
                return {
                    'success': False,
                    'error': f"SMTP error: {str(smtp_error)}"
                }
        
        # Option 4: For testing - log the email content (if no email service configured)
        logger.warning("=" * 60)
        logger.warning("EMAIL NOT SENT - No email service configured")
        logger.warning("=" * 60)
        logger.warning(f"To: {email}")
        logger.warning(f"Subject: Your Rugby AI Predictor License Key")
        logger.warning(f"License Key: {license_key}")
        logger.warning(f"Subscription: {subscription_type} ({duration_days} days)")
        logger.warning(f"Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.warning("=" * 60)
        logger.warning("To enable email sending, set GMAIL_USER and GMAIL_APP_PASSWORD environment variables")
        logger.warning("Or configure SendGrid, Mailgun, or another email service")
        logger.warning("=" * 60)
        
        # Return detailed error information
        return {
            'success': False,
            'error': 'No email service configured. Set GMAIL_USER and GMAIL_APP_PASSWORD secrets.'
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error in send_license_key_email: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': f"Email function error: {str(e)}"
        }


@https_fn.on_call(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def test_email_config(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Test function to check if email credentials are accessible.
    Returns status of Gmail configuration.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Try all methods to get credentials
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        methods_tried = []
        methods_tried.append(f"Environment variables: GMAIL_USER={gmail_user is not None}, GMAIL_APP_PASSWORD={gmail_password is not None}")
        
        # Try legacy config via FIREBASE_CONFIG environment variable
        try:
            firebase_config_str = os.getenv('FIREBASE_CONFIG')
            if firebase_config_str:
                import json
                firebase_config = json.loads(firebase_config_str)
                if 'gmail' in firebase_config:
                    gmail_config = firebase_config['gmail']
                    if not gmail_user and 'user' in gmail_config:
                        gmail_user = gmail_config['user']
                    if not gmail_password and 'app_password' in gmail_config:
                        gmail_password = gmail_config['app_password']
                    methods_tried.append("Legacy config (FIREBASE_CONFIG): Gmail config found")
                else:
                    methods_tried.append(f"Legacy config (FIREBASE_CONFIG): Available but no gmail key. Keys: {list(firebase_config.keys())}")
            else:
                methods_tried.append("Legacy config (FIREBASE_CONFIG): Not set")
        except Exception as e:
            methods_tried.append(f"Legacy config (FIREBASE_CONFIG) error: {str(e)}")
        
        # Try functions.config() method
        try:
            from firebase_functions import config as functions_config
            if hasattr(functions_config, 'gmail'):
                methods_tried.append("functions.config(): Available")
                if not gmail_user:
                    gmail_user = getattr(functions_config.gmail, 'user', None)
                if not gmail_password:
                    gmail_password = getattr(functions_config.gmail, 'app_password', None)
            else:
                methods_tried.append("functions.config(): Available but no gmail attribute")
        except (ImportError, AttributeError) as e:
            methods_tried.append(f"functions.config(): Not available - {str(e)}")
        
        # Try Secret Manager
        if not gmail_user or not gmail_password:
            try:
                from google.cloud import secretmanager
                client = secretmanager.SecretManagerServiceClient()
                project_id = 'rugby-ai-61fd0'
                
                if not gmail_user:
                    try:
                        name = f"projects/645506509698/secrets/GMAIL_USER/versions/latest"
                        response = client.access_secret_version(request={"name": name})
                        gmail_user = response.payload.data.decode("UTF-8").strip()
                        methods_tried.append("Secret Manager: GMAIL_USER retrieved")
                    except Exception as e:
                        methods_tried.append(f"Secret Manager GMAIL_USER error: {str(e)}")
                
                if not gmail_password:
                    try:
                        name = f"projects/645506509698/secrets/GMAIL_APP_PASSWORD/versions/latest"
                        response = client.access_secret_version(request={"name": name})
                        gmail_password = response.payload.data.decode("UTF-8").strip()
                        methods_tried.append("Secret Manager: GMAIL_APP_PASSWORD retrieved")
                    except Exception as e:
                        methods_tried.append(f"Secret Manager GMAIL_APP_PASSWORD error: {str(e)}")
            except ImportError:
                methods_tried.append("Secret Manager: Package not installed")
            except Exception as e:
                methods_tried.append(f"Secret Manager error: {str(e)}")
        
        result = {
            'gmail_user_found': gmail_user is not None,
            'gmail_password_found': gmail_password is not None,
            'both_found': gmail_user is not None and gmail_password is not None,
            'methods_tried': methods_tried,
            'gmail_user_preview': gmail_user[:3] + '...' + gmail_user[-3:] if gmail_user and len(gmail_user) > 6 else 'Not found',
        }
        
        if gmail_user and gmail_password:
            result['status'] = '✅ Credentials found! Email should work.'
        else:
            result['status'] = '❌ Credentials not found. Check permissions or use legacy config.'
            result['recommendation'] = 'Try: firebase functions:config:set gmail.user="..." gmail.app_password="..."'
        
        return result
        
    except Exception as e:
        import traceback
        logger.error(f"Error in test_email_config: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'error': f'Test failed: {str(e)}',
            'both_found': False
        }


@https_fn.on_call(timeout_sec=60, memory=512, secrets=["TWITTER_BEARER_TOKEN"])
def get_news_feed(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Get personalized news feed
    
    Request data:
    {
        "user_id": "optional_user_id",
        "followed_teams": [123, 456],
        "followed_leagues": [4446, 4986],
        "limit": 50
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        user_id = data.get('user_id')
        followed_teams = data.get('followed_teams', [])
        followed_leagues = data.get('followed_leagues', [])
        league_id = data.get('league_id')  # NEW: Primary league filter
        limit = data.get('limit', 50)
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data.sqlite"))
        db_path = os.path.abspath(db_path) if db_path else db_path
        logger.info(f"Using database path: {db_path}")
        logger.info(f"Database exists: {os.path.exists(db_path)}")

        # If SQLite is missing/unhealthy, fall back to Firestore so News still works.
        sqlite_ok = bool(db_path) and os.path.exists(db_path) and _sqlite_has_table(db_path, "event")
        if not sqlite_ok:
            fs = _build_firestore_news_feed(league_id=league_id, limit=int(limit) if limit is not None else 50)
            return {
                'success': True,
                'news': fs.get('news', []),
                'count': len(fs.get('news', [])),
                'debug': fs.get('debug', {}),
                'warning': 'SQLite not available; used Firestore fallback for news.'
            }

        # Ensure all downstream components use the same DB path
        os.environ["DB_PATH"] = db_path
        predictor = get_predictor()
        news_service = get_news_service(predictor=predictor, db_path=db_path)
        
        logger.info(f"Getting news feed: user_id={user_id}, league_id={league_id}, followed_teams={followed_teams}, followed_leagues={followed_leagues}, limit={limit}")
        
        # Get news feed - LEAGUE-SPECIFIC if league_id provided
        news_items = news_service.get_news_feed(
            user_id=user_id,
            followed_teams=followed_teams,
            followed_leagues=followed_leagues,
            league_id=league_id,  # NEW: Filter by specific league
            limit=limit
        )
        
        logger.info(f"Generated {len(news_items)} news items")
        
        # Convert to dict format
        news_data = [item.to_dict() for item in news_items]
        
        return {
            'success': True,
            'news': news_data,
            'count': len(news_data),
            'debug': {
                'data_source': 'sqlite',
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'sqlite_has_event_table': _sqlite_has_table(db_path, "event") if db_path else False,
            }
        }
    except Exception as e:
        logger.error(f"Error in get_news_feed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'success': False
        }


@https_fn.on_call(timeout_sec=60, memory=512)
def get_trending_topics(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Get trending rugby topics
    
    Request data:
    {
        "limit": 10
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        limit = data.get('limit', 10)
        league_id = data.get('league_id')  # NEW: League-specific trending topics

        # Prefer SQLite-backed trending; fall back to Firestore when SQLite isn't available.
        db_path = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data.sqlite"))
        db_path = os.path.abspath(db_path) if db_path else db_path
        sqlite_ok = bool(db_path) and os.path.exists(db_path) and _sqlite_has_table(db_path, "event")
        if not sqlite_ok:
            # Minimal Firestore fallback: reuse news feed debug and provide empty topics rather than failing.
            fs = _build_firestore_news_feed(league_id=league_id, limit=0)
            return {
                'success': True,
                'topics': [],
                'count': 0,
                'debug': fs.get('debug', {}),
                'warning': 'SQLite not available; trending topics unavailable (Firestore fallback active).'
            }

        os.environ["DB_PATH"] = db_path
        news_service = get_news_service(db_path=db_path)
        topics = news_service.get_trending_topics(limit=limit, league_id=league_id)  # NEW: Pass league_id
        
        return {
            'success': True,
            'topics': topics,
            'count': len(topics),
            'debug': {
                'data_source': 'sqlite',
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'sqlite_has_event_table': _sqlite_has_table(db_path, "event") if db_path else False,
            }
        }
    except Exception as e:
        logger.error(f"Error in get_trending_topics: {e}")
        return {
            'error': str(e),
            'success': False
        }


@https_fn.on_request(timeout_sec=300, memory=512, secrets=["TWITTER_BEARER_TOKEN"])
def get_news_feed_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for news feed with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        logger.info("="*80)
        logger.info("=== get_news_feed_http CALLED ===")
        logger.info("="*80)
        logger.info(f"📥 Request method: {req.method}")
        logger.info(f"📥 Request URL: {req.url if hasattr(req, 'url') else 'N/A'}")
        
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
                logger.info(f"📥 Parsed POST data: {data}")
            except Exception as parse_error:
                logger.error(f"📥 Error parsing POST data: {parse_error}")
                data = {}
        else:
            data = dict(req.args)
            logger.info(f"📥 GET args data: {data}")
        
        user_id = data.get('user_id')
        followed_teams = data.get('followed_teams', [])
        followed_leagues = data.get('followed_leagues', [])
        league_id = data.get('league_id')  # NEW: Primary league filter
        limit = data.get('limit', 50)
        
        logger.info("="*80)
        logger.info("=== REQUEST PARAMETERS ===")
        logger.info("="*80)
        logger.info(f"📥 user_id: {user_id}")
        logger.info(f"📥 followed_teams: {followed_teams}")
        logger.info(f"📥 followed_leagues: {followed_leagues}")
        logger.info(f"📥 league_id: {league_id} (type: {type(league_id).__name__})")
        logger.info(f"📥 limit: {limit}")
        logger.info("="*80)
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH")
        if not db_path:
            # Try multiple possible paths for Firebase Functions
            # In Firebase Functions, the working directory is the function's directory (rugby-ai-predictor/)
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same dir as main.py
                os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent dir (root)
                os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root of repo
                "/tmp/data.sqlite",  # Fallback for Firebase Functions
            ]
            logger.info(f"Searching for database in {len(possible_paths)} possible locations...")
            for path in possible_paths:
                abs_path = os.path.abspath(path)
                exists = os.path.exists(abs_path)
                logger.info(f"  Checking: {abs_path} - {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
                if exists:
                    db_path = abs_path
                    logger.info(f"✅ Found database at: {db_path}")
                    break
            else:
                # Default to same directory as main.py
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                logger.warning(f"⚠️ Database not found in any expected location, using default: {db_path}")
        
        logger.info(f"Final database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")

        # If SQLite is missing/unhealthy, serve Firestore-based news so the UI isn't empty.
        sqlite_ok = bool(db_path) and os.path.exists(db_path) and _sqlite_has_table(db_path, "event")
        if not sqlite_ok:
            fs = _build_firestore_news_feed(league_id=league_id, limit=int(limit) if limit is not None else 50)
            response_data = {
                'success': True,
                'news': fs.get('news', []),
                'count': len(fs.get('news', [])),
                'debug': {
                    **fs.get('debug', {}),
                    'db_path': db_path,
                    'db_exists': os.path.exists(db_path) if db_path else False,
                    'sqlite_has_event_table': False,
                },
                'warning': 'SQLite not available; used Firestore fallback for news.'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        # Ensure all downstream components use the same DB path
        os.environ["DB_PATH"] = db_path

        predictor = None
        try:
            if db_path and os.path.exists(db_path):
                predictor = get_predictor()
        except Exception as pred_error:
            logger.warning(f"Could not initialize predictor: {pred_error}")
            predictor = None
        
        try:
            news_service = get_news_service(predictor=predictor, db_path=db_path)
            
            # Test database connection
            try:
                import sqlite3
                test_conn = sqlite3.connect(db_path)
                test_cursor = test_conn.cursor()
                test_cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = ?", (league_id,))
                match_count = test_cursor.fetchone()[0]
                test_cursor.execute("SELECT COUNT(*) FROM event WHERE date_event >= date('now') AND date_event <= date('now', '+7 days') AND league_id = ?", (league_id,))
                upcoming_count = test_cursor.fetchone()[0]
                test_conn.close()
                logger.info(f"Database test: {match_count} total matches, {upcoming_count} upcoming matches for league {league_id}")
            except Exception as db_test_error:
                logger.warning(f"Database test failed: {db_test_error}")
        except Exception as ns_error:
            logger.error(f"Could not initialize news service: {ns_error}")
            import traceback
            logger.error(traceback.format_exc())
            # Return empty news instead of failing
            response_data = {
                'success': True,
                'news': [],
                'count': 0,
                'error': f'News service initialization failed: {str(ns_error)}'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        # Get news feed - LEAGUE-SPECIFIC if league_id provided
        try:
            logger.info(f"Calling get_news_feed with league_id={league_id}, limit={limit}")
            logger.info(f"  user_id={user_id}, followed_teams={followed_teams}, followed_leagues={followed_leagues}")
            
            # Test database query directly before calling news service
            league_id_int = _coerce_int(league_id)
            sqlite_league_total = None
            sqlite_upcoming_7d = None
            sqlite_recent_30d = None
            sqlite_min_date_event = None
            sqlite_max_date_event = None
            used_firestore_fallback = False
            firestore_fallback_reason = None
            try:
                import sqlite3
                test_conn = sqlite3.connect(db_path)
                test_cursor = test_conn.cursor()
                
                if league_id_int is not None:
                    test_cursor.execute(
                        "SELECT COUNT(*) FROM event WHERE league_id = ?",
                        (league_id_int,),
                    )
                    sqlite_league_total = int(test_cursor.fetchone()[0] or 0)
                    test_cursor.execute(
                        "SELECT MIN(date_event), MAX(date_event) FROM event WHERE league_id = ?",
                        (league_id_int,),
                    )
                    row = test_cursor.fetchone()
                    if row:
                        sqlite_min_date_event, sqlite_max_date_event = row[0], row[1]

                # Check upcoming matches for this league
                test_cursor.execute("""
                    SELECT COUNT(*) FROM event 
                    WHERE league_id = ? 
                    AND date(date_event) >= date('now') 
                    AND date(date_event) <= date('now', '+7 days')
                    AND home_team_id IS NOT NULL 
                    AND away_team_id IS NOT NULL
                """, (league_id_int if league_id_int is not None else league_id,))
                sqlite_upcoming_7d = int(test_cursor.fetchone()[0] or 0)
                logger.info(f"  Direct DB query: {sqlite_upcoming_7d} upcoming matches (7d) for league {league_id}")
                
                # Check recent matches
                test_cursor.execute("""
                    SELECT COUNT(*) FROM event 
                    WHERE league_id = ? 
                    AND date(date_event) >= date('now', '-30 days')
                    AND date(date_event) < date('now')
                    AND home_score IS NOT NULL 
                    AND away_score IS NOT NULL
                    AND home_team_id IS NOT NULL 
                    AND away_team_id IS NOT NULL
                """, (league_id_int if league_id_int is not None else league_id,))
                sqlite_recent_30d = int(test_cursor.fetchone()[0] or 0)
                logger.info(f"  Direct DB query: {sqlite_recent_30d} recent matches (30d) for league {league_id}")
                
                test_conn.close()
            except Exception as db_test_error:
                logger.warning(f"  Database test query failed: {db_test_error}")
            
            # If SQLite DB is present but has no usable data for this league, fall back to Firestore
            # (this commonly happens when the bundled SQLite doesn't include a league, or date parsing fails).
            if league_id_int is not None:
                if sqlite_league_total == 0:
                    used_firestore_fallback = True
                    firestore_fallback_reason = "sqlite_no_matches_for_league"
                elif (sqlite_upcoming_7d == 0) and (sqlite_recent_30d == 0):
                    used_firestore_fallback = True
                    firestore_fallback_reason = "sqlite_no_upcoming_or_recent_for_league_or_date_parse_issue"

            if used_firestore_fallback:
                fs = _build_firestore_news_feed(
                    league_id=league_id_int,
                    limit=int(limit) if limit is not None else 50,
                )
                news_data = fs.get("news", []) or []
                news_items = []  # for downstream debug calculations
                logger.warning(
                    f"Using Firestore fallback for news (league_id={league_id_int}, reason={firestore_fallback_reason}). "
                    f"Returned {len(news_data)} items."
                )
            else:
                news_items = news_service.get_news_feed(
                    user_id=user_id,
                    followed_teams=followed_teams,
                    followed_leagues=followed_leagues,
                    league_id=league_id,  # NEW: Filter by specific league
                    limit=limit
                )
                logger.info(f"get_news_feed returned {len(news_items)} items")
                
                if len(news_items) == 0:
                    logger.warning("="*80)
                    logger.warning(f"⚠️⚠️⚠️ NO NEWS ITEMS RETURNED FOR LEAGUE {league_id}! ⚠️⚠️⚠️")
                    logger.warning("="*80)
                    logger.warning(f"  This might indicate:")
                    logger.warning(f"  1. No upcoming matches in the next 7 days for this league")
                    logger.warning(f"  2. Date filtering issue (check date('now') vs actual dates)")
                    logger.warning(f"  3. Database doesn't have matches for this league")
                    logger.warning(f"  4. News service queries are failing silently")
                    logger.warning("="*80)
                
                # Convert to dict format
                logger.info(f"Converting {len(news_items)} news items to dict format...")
                news_data = []
                for i, item in enumerate(news_items):
                    try:
                        item_dict = item.to_dict()
                        news_data.append(item_dict)
                        if i < 3:  # Log first 3 items
                            logger.info(f"  Item {i+1}: type={item_dict.get('type')}, league_id={item_dict.get('league_id')}, title={item_dict.get('title', '')[:50]}")
                    except Exception as convert_error:
                        logger.error(f"  Error converting item {i+1} to dict: {convert_error}")
                
                logger.info(f"✅ Converted {len(news_data)} items to dict format")
                
                # Log first few items for debugging
                if len(news_data) > 0:
                    logger.info(f"📰 Sample news items (first 3):")
                    for i, item in enumerate(news_data[:3], 1):
                        logger.info(f"  {i}. [{item.get('type')}] {item.get('title', '')[:50]}... (league_id: {item.get('league_id')})")
                else:
                    logger.warning("📰 No news items to display!")
        except Exception as feed_error:
            logger.error(f"Error getting news feed: {feed_error}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            news_data = []
        
        # Calculate what news_service returned
        news_service_count = len(news_items) if 'news_items' in locals() else 0
        
        response_data = {
            'success': True,
            'news': news_data,
            'count': len(news_data),
            'debug': {
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'sqlite_has_event_table': _sqlite_has_table(db_path, "event") if db_path else False,
                'data_source': 'firestore' if 'used_firestore_fallback' in locals() and used_firestore_fallback else 'sqlite',
                'league_id': league_id,
                'predictor_available': predictor is not None,
                'request_league_id': league_id,
                'request_limit': limit,
                'news_items_count': len(news_data),
                'news_service_returned': news_service_count,
                'sqlite_league_total': sqlite_league_total if 'sqlite_league_total' in locals() else None,
                'sqlite_upcoming_7d': sqlite_upcoming_7d if 'sqlite_upcoming_7d' in locals() else None,
                'sqlite_recent_30d': sqlite_recent_30d if 'sqlite_recent_30d' in locals() else None,
                'sqlite_min_date_event': sqlite_min_date_event if 'sqlite_min_date_event' in locals() else None,
                'sqlite_max_date_event': sqlite_max_date_event if 'sqlite_max_date_event' in locals() else None,
                'firestore_fallback_reason': firestore_fallback_reason if 'firestore_fallback_reason' in locals() else None,
            }
        }
        
        logger.info("="*80)
        logger.info("=== get_news_feed_http RESPONSE ===")
        logger.info("="*80)
        logger.info(f"✅ Success: {response_data['success']}")
        logger.info(f"📊 News count: {response_data['count']}")
        logger.info(f"🔍 Debug info:")
        for key, value in response_data['debug'].items():
            logger.info(f"   {key}: {value}")
        logger.info("="*80)
        
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_news_feed_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_news_feed_http: {e}")
        logger.error(f"Traceback: {error_trace}")
        # Return empty news array instead of error to prevent UI issues
        response_data = {
            'success': True,
            'news': [],
            'count': 0,
            'error': str(e)  # Include error for debugging but don't fail
        }
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)


@https_fn.on_request(timeout_sec=300, memory=512)
def proxy_video_http(req: https_fn.Request) -> https_fn.Response:
    """
    Proxy X/Twitter-hosted MP4 files so browser playback works in-app.
    `video.twimg.com` often rejects direct cross-site hotlink requests with 403.
    """
    import logging
    import requests
    from urllib.parse import urlparse

    logger = logging.getLogger(__name__)

    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Range",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type",
        "Access-Control-Max-Age": "3600",
    }

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204, headers=cors_headers)

    if req.method != "GET":
        return https_fn.Response(
            json.dumps({"success": False, "error": "Method not allowed"}),
            status=405,
            headers={**cors_headers, "Content-Type": "application/json"},
        )

    target_url = (req.args.get("url") or "").strip()
    if not target_url:
        return https_fn.Response(
            json.dumps({"success": False, "error": "Missing required query param: url"}),
            status=400,
            headers={**cors_headers, "Content-Type": "application/json"},
        )

    try:
        parsed = urlparse(target_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Invalid URL scheme")
        # Keep strict to avoid SSRF and only allow known X/Twitter media hosts.
        allowed_hosts = {"video.twimg.com", "pbs.twimg.com", "ton.twimg.com"}
        if host not in allowed_hosts:
            raise ValueError(f"Host not allowed: {host}")
    except Exception as url_error:
        return https_fn.Response(
            json.dumps({"success": False, "error": f"Invalid media URL: {url_error}"}),
            status=400,
            headers={**cors_headers, "Content-Type": "application/json"},
        )

    try:
        upstream_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "video/*,*/*;q=0.8",
            "Referer": "https://x.com/",
            "Origin": "https://x.com",
        }
        range_header = req.headers.get("Range")
        if range_header:
            upstream_headers["Range"] = range_header

        upstream = requests.get(
            target_url,
            headers=upstream_headers,
            timeout=(8, 30),
            stream=True,
            allow_redirects=True,
        )

        response_headers = {
            **cors_headers,
            "Content-Type": upstream.headers.get("Content-Type", "video/mp4"),
            "Cache-Control": "public, max-age=3600",
        }
        for header_name in ("Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
            header_value = upstream.headers.get(header_name)
            if header_value:
                response_headers[header_name] = header_value

        return https_fn.Response(
            upstream.content,
            status=upstream.status_code,
            headers=response_headers,
        )
    except Exception as proxy_error:
        logger.error(f"proxy_video_http error: {proxy_error}")
        return https_fn.Response(
            json.dumps({"success": False, "error": "Media proxy request failed"}),
            status=502,
            headers={**cors_headers, "Content-Type": "application/json"},
        )


@https_fn.on_request(timeout_sec=300, memory=512)
def get_trending_topics_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for trending topics with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        logger.info("=== get_trending_topics_http called ===")
        
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)
        
        limit = data.get('limit', 10)
        league_id = data.get('league_id')  # NEW: League-specific trending topics
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH")
        if not db_path:
            # Try multiple possible paths for Firebase Functions
            # In Firebase Functions, the working directory is the function's directory (rugby-ai-predictor/)
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same dir as main.py
                os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent dir (root)
                os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root of repo
                "/tmp/data.sqlite",  # Fallback for Firebase Functions
            ]
            logger.info(f"Searching for database in {len(possible_paths)} possible locations...")
            for path in possible_paths:
                abs_path = os.path.abspath(path)
                exists = os.path.exists(abs_path)
                logger.info(f"  Checking: {abs_path} - {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
                if exists:
                    db_path = abs_path
                    logger.info(f"✅ Found database at: {db_path}")
                    break
            else:
                # Default to same directory as main.py
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                logger.warning(f"⚠️ Database not found in any expected location, using default: {db_path}")
        
        logger.info(f"Final database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")

        sqlite_ok = bool(db_path) and os.path.exists(db_path) and _sqlite_has_table(db_path, "event")
        if not sqlite_ok:
            response_data = {
                'success': True,
                'topics': [],
                'count': 0,
                'debug': {
                    'data_source': 'firestore',
                    'db_path': db_path,
                    'db_exists': os.path.exists(db_path) if db_path else False,
                    'sqlite_has_event_table': False,
                    'league_id': league_id,
                },
                'warning': 'SQLite not available; trending topics unavailable (Firestore fallback active).'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        os.environ["DB_PATH"] = db_path

        predictor = None
        try:
            if db_path and os.path.exists(db_path):
                predictor = get_predictor()
        except Exception as pred_error:
            logger.warning(f"Could not initialize predictor: {pred_error}")
            predictor = None
        
        try:
            news_service = get_news_service(predictor=predictor, db_path=db_path)
        except Exception as ns_error:
            logger.error(f"Could not initialize news service: {ns_error}")
            # Return empty topics instead of failing
            response_data = {
                'success': True,
                'topics': [],
                'count': 0,
                'error': f'News service initialization failed: {str(ns_error)}'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        try:
            logger.info(f"Calling get_trending_topics with league_id={league_id}, limit={limit}")
            topics = news_service.get_trending_topics(limit=limit, league_id=league_id)  # NEW: Pass league_id
            logger.info(f"get_trending_topics returned {len(topics)} topics")
        except Exception as topics_error:
            logger.error(f"Error getting trending topics: {topics_error}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            topics = []
        
        response_data = {
            'success': True,
            'topics': topics,
            'count': len(topics),
            'debug': {
                'data_source': 'sqlite',
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'sqlite_has_event_table': _sqlite_has_table(db_path, "event") if db_path else False,
                'league_id': league_id
            }
        }
        
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_trending_topics_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_trending_topics_http: {e}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {
            'error': str(e),
            'success': False
        }
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)


@https_fn.on_request(timeout_sec=60, memory=512)
def get_league_standings_http(req: https_fn.Request) -> https_fn.Response:
    """
    Get league standings from Highlightly API
    
    Request body:
    {
        "league_id": 73119  # Highlightly league ID
    }
    """
    import logging
    import json
    from datetime import datetime, timedelta
    logger = logging.getLogger(__name__)
    
    logger.info("="*80)
    logger.info("=== get_league_standings_http CALLED ===")
    logger.info("="*80)
    logger.info(f"Request method: {req.method}")
    logger.info(f"Request headers: {dict(req.headers)}")
    
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }
    
    try:
        # Parse request data
        if req.method == 'OPTIONS':
            logger.info("OPTIONS request - returning CORS preflight")
            return https_fn.Response('', status=204, headers=headers)
        
        logger.info("Parsing request JSON...")
        data = req.get_json(silent=True) or {}
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        
        highlightly_league_id = data.get('league_id')
        sportsdb_league_id = data.get('sportsdb_league_id')
        client_league_name = data.get('league_name')
        license_key = data.get('license_key')
        force_refresh = bool(data.get('force_refresh', False))
        cache_ttl_seconds_raw = data.get('cache_ttl_seconds')
        logger.info(f"Extracted league_id: {highlightly_league_id} (type: {type(highlightly_league_id)})")
        logger.info(f"Optional sportsdb_league_id: {sportsdb_league_id} (type: {type(sportsdb_league_id)})")
        if client_league_name:
            logger.info(f"Optional league_name: {client_league_name}")
        if license_key:
            logger.info("Optional license_key provided (used for client caching).")

        # Standings cache TTL (server-side). Clamp to keep Firestore load reasonable.
        try:
            cache_ttl_seconds = int(cache_ttl_seconds_raw) if cache_ttl_seconds_raw is not None else 21600  # 6h
        except Exception:
            cache_ttl_seconds = 21600
        cache_ttl_seconds = max(900, min(cache_ttl_seconds, 86400))  # 15 min .. 24h
        
        if not highlightly_league_id:
            logger.error("❌ Missing league_id in request")
            response_data = {
                'success': False,
                'error': 'league_id is required',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        logger.info(f"📊 Fetching standings for Highlightly league ID: {highlightly_league_id}")
        
        # Initialize Highlightly client
        logger.info("Importing HighlightlyRugbyAPI...")
        from prediction.highlightly_client import HighlightlyRugbyAPI
        import os
        
        logger.info("Checking for API keys...")
        # Prefer RapidAPI key, then try Highlightly key, then fallback
        # Use RapidAPI by default since it has better rate limits
        use_rapidapi = True  # Use RapidAPI by default for better reliability
        api_key = os.getenv('RAPIDAPI_KEY') or os.getenv('HIGHLIGHTLY_API_KEY') or '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
        
        if api_key:
            api_type = "RapidAPI" if use_rapidapi else "Highlightly Direct"
            logger.info(f"✅ API key found ({api_type}): {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''} (length: {len(api_key)})")
        else:
            logger.error("❌ No API key found in environment variables")
            logger.error("   RAPIDAPI_KEY: " + str(os.getenv('RAPIDAPI_KEY')))
            logger.error("   HIGHLIGHTLY_API_KEY: " + str(os.getenv('HIGHLIGHTLY_API_KEY')))
            response_data = {
                'success': False,
                'error': 'RAPIDAPI_KEY or HIGHLIGHTLY_API_KEY not configured',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        logger.info(f"Initializing HighlightlyRugbyAPI client (use_rapidapi={use_rapidapi})...")
        try:
            client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
            logger.info(f"✅ HighlightlyRugbyAPI client initialized successfully (using {'RapidAPI' if use_rapidapi else 'Highlightly Direct'})")
        except Exception as client_error:
            logger.error(f"❌ Failed to initialize Highlightly client: {client_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            response_data = {
                'success': False,
                'error': f'Failed to initialize API client: {str(client_error)}',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        # Season handling:
        # Many rugby competitions span two calendar years (e.g. 2025/26) but the API expects
        # the *start year* (e.g. 2025). If we only try the current calendar year we will 404
        # for URC / Premiership / Top14 etc early in the year.
        requested_season = data.get("season")
        now_utc = datetime.utcnow()
        current_year = now_utc.year
        current_month = now_utc.month

        # Highlightly league IDs that typically span Aug/Sept -> May/Jun and are keyed by start-year.
        CROSS_YEAR_STANDINGS_LEAGUES = {
            65460,  # United Rugby Championship
            11847,  # English Premiership Rugby
            14400,  # French Top 14
        }

        # Rugby World Cup (59503) is held every 4 years - 2023, 2019, 2015, 2011, etc.
        RUGBY_WORLD_CUP_LEAGUE_ID = 59503

        def _dedupe_keep_order(items):
            seen = set()
            out = []
            for x in items:
                if x in seen:
                    continue
                seen.add(x)
                out.append(x)
            return out

        def _candidate_standings_seasons(league_id: int) -> list:
            # If the caller explicitly requests a season, honor it first.
            if requested_season is not None:
                try:
                    return [int(requested_season)]
                except (TypeError, ValueError):
                    logger.warning(f"Invalid requested season {requested_season}; falling back to auto season detection")

            # Rugby World Cup: held every 4 years. Try recent tournament years first.
            if league_id == RUGBY_WORLD_CUP_LEAGUE_ID:
                return [2023, 2019, 2015, 2011, 2007]

            # Cross-year leagues (URC, Premiership, Top 14): Jan-Jun belong to previous season start-year.
            if league_id in CROSS_YEAR_STANDINGS_LEAGUES:
                primary = current_year - 1 if current_month <= 6 else current_year
                return _dedupe_keep_order([primary, primary - 1, primary + 1, current_year, current_year - 1])

            # Default for most comps: try current year first, then nearby.
            return _dedupe_keep_order([current_year, current_year - 1, current_year + 1, current_year - 2])

        # Compute seasons to try (ordered)
        try:
            league_id_int = int(highlightly_league_id)
        except Exception:
            league_id_int = highlightly_league_id

        seasons_to_try = _candidate_standings_seasons(league_id_int) if isinstance(league_id_int, int) else [current_year, current_year - 1]
        logger.info(f"📅 Now (UTC): {now_utc.isoformat()} | year={current_year}, month={current_month}")
        logger.info(f"🔍 Will try seasons (in order): {seasons_to_try}")
        
        standings = None
        successful_season = None
        last_error = None
        cache_hit = False
        stale_cache_payload = None  # last known cached payload (even if expired)

        # Firestore cache for standings (prevents Highlightly rate-limits)
        fs_cache = None
        cache_collection = None
        try:
            fs_cache = get_firestore_client()
            cache_collection = fs_cache.collection("standings_cache_v1")
        except Exception as cache_init_err:
            logger.warning(f"Standings cache init failed (continuing without cache): {cache_init_err}")
            fs_cache = None
            cache_collection = None
        
        for year in seasons_to_try:
            logger.info(f"\n--- Trying season {year} ---")
            try:
                # Cache check BEFORE hitting Highlightly API.
                if cache_collection is not None and not force_refresh and isinstance(league_id_int, int):
                    try:
                        cache_doc_id = f"hl::{int(highlightly_league_id)}::season::{int(year)}"
                        cache_ref = cache_collection.document(cache_doc_id)
                        cached = cache_ref.get()
                        cached_data = cached.to_dict() if getattr(cached, "exists", False) else None
                        if isinstance(cached_data, dict) and isinstance(cached_data.get("standings"), dict):
                            expires_at = cached_data.get("expires_at")
                            is_fresh = False
                            try:
                                if isinstance(expires_at, str):
                                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                                    is_fresh = datetime.utcnow() <= exp_dt.replace(tzinfo=None)
                            except Exception:
                                is_fresh = False

                            if is_fresh:
                                standings = cached_data.get("standings")
                                successful_season = int(year)
                                cache_hit = True
                                logger.info(f"✅ Standings cache HIT for league={highlightly_league_id}, season={year}")
                                break
                            else:
                                # Keep last stale cache as fallback if we get rate-limited.
                                stale_cache_payload = cached_data.get("standings") or stale_cache_payload
                                logger.info(f"🕰️ Standings cache STALE for league={highlightly_league_id}, season={year} (will revalidate)")
                    except Exception as cache_read_err:
                        logger.warning(f"Standings cache read failed (continuing): {cache_read_err}")

                logger.info(f"Calling client.get_standings(league_id={highlightly_league_id}, season={year})...")
                standings = client.get_standings(league_id=highlightly_league_id, season=year)
                logger.info(f"✅ API call completed for season {year}")
                logger.info(f"Response type: {type(standings)}")
                
                # Check if we got rate limited (429) - API might return empty structure
                if isinstance(standings, dict):
                    # Check for explicit rate limit flag
                    if standings.get('_rate_limited'):
                        logger.error(f"   ❌ Rate limited (429) - API quota exceeded")
                        last_error = Exception("Rate limited (429) - API quota exceeded")
                        # Don't try other seasons if rate limited
                        break
                    
                    groups = standings.get('groups', [])
                    league_info = standings.get('league', {})
                    
                    logger.info(f"   Groups count: {len(groups)}")
                    logger.info(f"   League info: {league_info}")
                    
                    # Check if response is empty
                    if len(groups) == 0 and (not league_info or not league_info.get('name')):
                        logger.warning(f"⚠️ Empty response for season {year}")
                        logger.warning(f"   Full response structure: {json.dumps(standings, indent=2, default=str)}")
                        
                        # If we have an error flag, it's definitely an error
                        if standings.get('_error'):
                            logger.error(f"   ❌ API Error: {standings.get('_error')}")
                            last_error = Exception(standings.get('_error'))
                            continue
                        
                        # If rate limited flag is set, handle it
                        if standings.get('_rate_limited'):
                            logger.error(f"   ❌ Rate limited (429) - API quota exceeded")
                            last_error = Exception("Rate limited (429) - API quota exceeded")
                            break
                        
                        # Otherwise, no data for this season
                        logger.warning(f"   No standings data for season {year} - might not exist yet")
                        last_error = Exception(f"No standings data for season {year}")
                        continue
                
                if standings:
                    logger.info(f"Response keys: {list(standings.keys()) if isinstance(standings, dict) else 'N/A'}")
                    
                    if isinstance(standings, dict):
                        if standings.get('groups') or standings.get('league'):
                            groups = standings.get('groups', [])
                            logger.info(f"Found {len(groups)} groups in response")
                            
                            if groups and len(groups) > 0:
                                logger.info(f"Analyzing groups for teams/standings...")
                                for idx, group in enumerate(groups):
                                    logger.info(f"  Group {idx + 1}: keys = {list(group.keys()) if isinstance(group, dict) else 'N/A'}")
                                    if isinstance(group, dict):
                                        standings_list = group.get('standings', [])
                                        teams_list = group.get('teams', [])
                                        logger.info(f"    standings: {len(standings_list)} items")
                                        logger.info(f"    teams: {len(teams_list)} items")
                                
                                # Check if groups have teams/standings
                                has_teams = any(
                                    (g.get('standings') and len(g.get('standings', [])) > 0) or
                                    (g.get('teams') and len(g.get('teams', [])) > 0)
                                    for g in groups
                                )
                                logger.info(f"Has teams: {has_teams}")
                                
                                if has_teams:
                                    total_teams = sum(
                                        len(g.get('standings', [])) + len(g.get('teams', []))
                                        for g in groups if isinstance(g, dict)
                                    )
                                    logger.info(f"✅ Found standings for league {highlightly_league_id} (season {year})")
                                    logger.info(f"   Total teams across all groups: {total_teams}")
                                    successful_season = year
                                    break
                                else:
                                    logger.warning(f"⚠️ Groups found but no teams/standings data in season {year}")
                            else:
                                logger.warning(f"⚠️ Empty groups array for season {year}")
                        else:
                            logger.warning(f"⚠️ Response has no 'groups' or 'league' keys for season {year}")
                    else:
                        logger.warning(f"⚠️ Response is not a dict for season {year}")
                else:
                    logger.warning(f"⚠️ Empty response for season {year}")
                    
            except Exception as year_error:
                error_msg = str(year_error)
                last_error = year_error
                logger.error(f"❌ Season {year} failed with error: {year_error}")
                logger.error(f"   Error type: {type(year_error).__name__}")
                
                if '404' in error_msg:
                    logger.info(f"   404 Not Found - standings don't exist for season {year}")
                elif '429' in error_msg:
                    logger.warning(f"   429 Too Many Requests - rate limited")
                else:
                    import traceback
                    logger.error(f"   Full traceback: {traceback.format_exc()}")
                continue
        
        logger.info("\n" + "="*80)
        logger.info("=== FINAL RESULT ===")
        logger.info("="*80)
        
        if standings and successful_season:
            logger.info(f"✅ SUCCESS: Found standings for season {successful_season}")
            logger.info(f"   League ID: {highlightly_league_id}")
            logger.info(f"   Season: {successful_season}")
            
            # Log standings summary
            if isinstance(standings, dict):
                groups = standings.get('groups', [])
                league_info = standings.get('league', {})
                logger.info(f"   Groups: {len(groups)}")
                logger.info(f"   League info: {league_info.get('name', 'N/A')} - {league_info.get('season', 'N/A')}")
                
                total_teams = 0
                for group in groups:
                    if isinstance(group, dict):
                        teams_count = len(group.get('standings', [])) + len(group.get('teams', []))
                        total_teams += teams_count
                logger.info(f"   Total teams: {total_teams}")

                # Enrich standings with team logos (luxury UI) using TheSportsDB:
                # Frontend passes `sportsdb_league_id` (TheSportsDB league id like 4446 for URC).
                # We fetch all teams once and map badges to the standings teams by name.
                try:
                    sportsdb_id_int = int(sportsdb_league_id) if sportsdb_league_id is not None else None
                except Exception:
                    sportsdb_id_int = None

                if sportsdb_id_int:
                    try:
                        import re
                        from prediction.config import load_config
                        from prediction.sportsdb_client import TheSportsDBClient

                        def _norm_team_name(s: str) -> str:
                            s2 = (s or "").strip().lower()
                            s2 = re.sub(r"[^a-z0-9]+", " ", s2)
                            s2 = re.sub(r"\s+", " ", s2).strip()
                            return s2

                        def _name_variants(name: str) -> list:
                            """Generate variants for fuzzy matching (e.g. 'Glasgow Warriors RFC' -> ['glasgow warriors rfc','glasgow warriors','glasgow'])."""
                            n = _norm_team_name(name)
                            if not n:
                                return []
                            out = [n]
                            for suffix in (" rugby", " rfc", " rugby club", " rugby union"):
                                if n.endswith(suffix):
                                    shortened = n[: -len(suffix)].strip()
                                    if shortened:
                                        out.append(shortened)
                            words = n.split()
                            if len(words) > 1:
                                out.append(words[0])
                            if len(words) >= 2:
                                out.append(" ".join(words[:2]))
                            return list(dict.fromkeys(out))

                        def _find_logo(standings_name: str, logos_by_norm: dict) -> Optional[str]:
                            """Try exact, overrides, then fuzzy match to resolve logo."""
                            from prediction.config import STANDINGS_TEAM_OVERRIDES
                            sn = _norm_team_name(standings_name)
                            if not sn:
                                return None
                            variants = _name_variants(standings_name)
                            for v in variants:
                                if v in logos_by_norm:
                                    return logos_by_norm[v]
                            overrides = STANDINGS_TEAM_OVERRIDES.get(sn) or []
                            for alt in overrides:
                                if alt in logos_by_norm:
                                    return logos_by_norm[alt]
                                for v in _name_variants(alt):
                                    if v in logos_by_norm:
                                        return logos_by_norm[v]
                            if len(sn) < 3:
                                return None
                            best_url = None
                            best_len = 0
                            for key, url in logos_by_norm.items():
                                if len(key) < 3:
                                    continue
                                if sn == key or sn in key or key in sn:
                                    ln = min(len(sn), len(key))
                                    if ln > best_len:
                                        best_len = ln
                                        best_url = url
                            return best_url

                        # Cache in Firestore to avoid calling TheSportsDB on every request
                        logos_by_norm: Dict[str, str] = {}
                        cache_used = False
                        try:
                            fs = get_firestore_client()
                            cache_doc_id = f"league::{sportsdb_id_int}::v3"
                            cache_ref = fs.collection("team_logo_cache").document(cache_doc_id)
                            cached = cache_ref.get()
                            cached_data = cached.to_dict() if getattr(cached, "exists", False) else None
                            if isinstance(cached_data, dict):
                                cached_logos = cached_data.get("logos_by_norm")
                                fetched_at = cached_data.get("fetched_at")
                                # TTL: 7 days
                                is_fresh = False
                                try:
                                    if isinstance(fetched_at, str):
                                        fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                                        is_fresh = (datetime.utcnow() - fetched_dt).days < 7
                                except Exception:
                                    is_fresh = False
                                if isinstance(cached_logos, dict) and cached_logos and is_fresh:
                                    logos_by_norm = {str(k): str(v) for k, v in cached_logos.items() if k and v}
                                    cache_used = True
                                    logger.info(f"✅ Using cached team logos for sportsdb_league_id={sportsdb_id_int} ({len(logos_by_norm)} logos)")
                        except Exception as cache_err:
                            logger.warning(f"Team logo cache read failed (continuing without cache): {cache_err}")
                            fs = None
                            cache_ref = None

                        if not logos_by_norm:
                            cfg = load_config()
                            sportsdb = TheSportsDBClient(
                                base_url=cfg.base_url,
                                api_key=cfg.api_key,
                                rate_limit_rpm=cfg.rate_limit_rpm,
                            )
                            teams_api = sportsdb.get_teams(sportsdb_id_int) or []
                            if not teams_api and client_league_name:
                                found = sportsdb.find_rugby_league(client_league_name)
                                if found:
                                    tsdb_id = found.get("idLeague")
                                    if tsdb_id:
                                        teams_api = sportsdb.get_teams(tsdb_id) or []
                                        logger.info(f"Resolved TheSportsDB league via find_rugby_league: id={tsdb_id}")
                            for t in teams_api:
                                try:
                                    name = t.get("strTeam") or ""
                                    alt = t.get("strAlternate") or ""
                                    badge = t.get("strTeamBadge") or t.get("strTeamLogo") or t.get("strTeamJersey") or ""
                                    if not badge:
                                        continue
                                    for v in _name_variants(name) if name else []:
                                        logos_by_norm[v] = badge
                                    if alt:
                                        for part in str(alt).split(","):
                                            part = part.strip()
                                            if part:
                                                for v in _name_variants(part):
                                                    logos_by_norm[v] = badge
                                except Exception:
                                    continue
                            logger.info(f"Fetched {len(teams_api)} teams from TheSportsDB for league {sportsdb_id_int}; mapped logos={len(logos_by_norm)}")

                            # Write cache
                            try:
                                if cache_ref is not None:
                                    cache_ref.set(
                                        {
                                            "sportsdb_league_id": sportsdb_id_int,
                                            "league_name": client_league_name,
                                            "logos_by_norm": logos_by_norm,
                                            "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                                            "source": "thesportsdb_lookup_all_teams",
                                        },
                                        merge=True,
                                    )
                            except Exception as cache_write_err:
                                logger.warning(f"Team logo cache write failed: {cache_write_err}")

                        # Merge logos into standings structure (mutate in-place)
                        if logos_by_norm:
                            applied = 0
                            missed_names = []
                            for g in groups:
                                if not isinstance(g, dict):
                                    continue
                                for list_key in ("standings", "teams"):
                                    rows = g.get(list_key)
                                    if not isinstance(rows, list):
                                        continue
                                    for row in rows:
                                        if not isinstance(row, dict):
                                            continue
                                        team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                                        name = None
                                        if team_obj:
                                            name = team_obj.get("name") or team_obj.get("team_name") or team_obj.get("strTeam")
                                        if not name:
                                            name = row.get("name") or row.get("team_name") or row.get("strTeam")
                                        if not name:
                                            continue
                                        logo = _find_logo(str(name), logos_by_norm)
                                        if not logo and not cache_used:
                                            missed_names.append(str(name))
                                        if logo:
                                            if team_obj is not None:
                                                team_obj.setdefault("logo", logo)
                                                team_obj.setdefault("badge", logo)
                                            row.setdefault("logo", logo)
                                            applied += 1
                            if missed_names and not cache_used:
                                cfg = load_config()
                                sportsdb = TheSportsDBClient(base_url=cfg.base_url, api_key=cfg.api_key, rate_limit_rpm=cfg.rate_limit_rpm)
                                for nm in missed_names[:8]:
                                    try:
                                        searched = sportsdb.search_teams(nm)
                                        for t in searched[:3]:
                                            badge = t.get("strTeamBadge") or t.get("strTeamLogo") or ""
                                            if not badge:
                                                continue
                                            ts_name = t.get("strTeam") or ""
                                            if _norm_team_name(nm) in _norm_team_name(ts_name) or _norm_team_name(ts_name) in _norm_team_name(nm):
                                                for g in groups:
                                                    if not isinstance(g, dict):
                                                        continue
                                                    for rows in (g.get("standings") or [], g.get("teams") or []):
                                                        for row in rows:
                                                            if not isinstance(row, dict):
                                                                continue
                                                            team_obj = row.get("team") if isinstance(row.get("team"), dict) else None
                                                            rn = (team_obj or {}).get("name") or (team_obj or {}).get("team_name") or row.get("name") or row.get("team_name") or ""
                                                            if rn and _norm_team_name(rn) == _norm_team_name(nm):
                                                                if team_obj is not None:
                                                                    team_obj.setdefault("logo", badge)
                                                                    team_obj.setdefault("badge", badge)
                                                                row.setdefault("logo", badge)
                                                                applied += 1
                                                                break
                                                break
                                    except Exception:
                                        continue
                            logger.info(f"✅ Applied {applied} team logos into standings payload (cache_used={cache_used})")
                        else:
                            logger.warning(f"No logos mapped for sportsdb_league_id={sportsdb_id_int}; standings will render initials")

                    except Exception as logo_err:
                        logger.warning(f"Standings logo enrichment failed (continuing without logos): {logo_err}")

                # Write standings cache (after enrichment) so future requests skip Highlightly.
                if cache_collection is not None and not cache_hit and not force_refresh and isinstance(successful_season, int):
                    try:
                        cache_doc_id = f"hl::{int(highlightly_league_id)}::season::{int(successful_season)}"
                        cache_ref = cache_collection.document(cache_doc_id)
                        expires_dt = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=cache_ttl_seconds)
                        cache_ref.set(
                            {
                                "highlightly_league_id": int(highlightly_league_id),
                                "sportsdb_league_id": int(sportsdb_league_id) if str(sportsdb_league_id).isdigit() else sportsdb_league_id,
                                "league_name": client_league_name,
                                "season": int(successful_season),
                                "standings": standings,
                                "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                                "expires_at": expires_dt.isoformat() + "Z",
                                "source": "highlightly",
                            },
                            merge=True,
                        )
                        logger.info(f"✅ Wrote standings cache doc {cache_doc_id} (ttl={cache_ttl_seconds}s)")
                    except Exception as cache_write_err:
                        logger.warning(f"Standings cache write failed: {cache_write_err}")
            
            response_data = {
                'success': True,
                'standings': standings,
                'season': successful_season,
                'league_id': highlightly_league_id,
                'cache_hit': cache_hit,
            }
            logger.info(f"✅ Returning success response (status 200)")
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        else:
            logger.warning(f"⚠️ NO STANDINGS FOUND")
            logger.warning(f"   League ID: {highlightly_league_id}")
            logger.warning(f"   Tried seasons: {seasons_to_try}")
            
            # Check if rate limited
            error_msg = None
            is_rate_limited = False
            if last_error:
                error_str = str(last_error)
                if '429' in error_str or 'Rate limited' in error_str or 'quota exceeded' in error_str.lower():
                    is_rate_limited = True
            
            if is_rate_limited:
                error_msg = f'API rate limit exceeded. Please try again in a few minutes. (League ID: {highlightly_league_id})'
                logger.error(f"   ❌ RATE LIMITED - API quota exceeded")
                # If we have stale cache, return it rather than erroring.
                if isinstance(stale_cache_payload, dict):
                    logger.warning("Returning STALE cached standings due to rate limit.")
                    response_data = {
                        'success': True,
                        'standings': stale_cache_payload,
                        'season': None,
                        'league_id': highlightly_league_id,
                        'cache_hit': True,
                        'cache_stale': True,
                        'warning': error_msg,
                    }
                    return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
            elif highlightly_league_id == RUGBY_WORLD_CUP_LEAGUE_ID:
                error_msg = (
                    'Rugby World Cup is a tournament held every 4 years (e.g. 2023, 2019, 2015). '
                    'Standings data may not be available for this competition from the current data source.'
                )
            else:
                error_msg = f'No standings data available for league {highlightly_league_id} (tried seasons {seasons_to_try})'
                if last_error:
                    logger.warning(f"   Last error: {last_error}")
                    error_msg += f'. Last error: {str(last_error)}'
            
            response_data = {
                'success': False,
                'error': error_msg,
                'standings': None,
                'rate_limited': is_rate_limited,
                'debug': {
                    'tried_seasons': seasons_to_try,
                    'last_error': str(last_error) if last_error else None,
                    'league_id': highlightly_league_id
                }
            }
            logger.info(f"⚠️ Returning error response (status 200)")
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
            
    except Exception as e:
        logger.error("="*80)
        logger.error("❌ EXCEPTION IN get_league_standings_http")
        logger.error("="*80)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_trace}")
        logger.error("="*80)
        
        response_data = {
            'success': False,
            'error': f'Server error: {str(e)}',
            'standings': None,
            'debug': {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': error_trace
            }
        }
        logger.error(f"❌ Returning error response (status 500)")
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
    
    finally:
        logger.info("="*80)
        logger.info("=== get_league_standings_http COMPLETED ===")
        logger.info("="*80)



@https_fn.on_request(timeout_sec=120, memory=1024)
def capture_upcoming_prediction_snapshots_http(req: https_fn.Request) -> https_fn.Response:
    """
    Capture immutable pre-kickoff prediction snapshots for upcoming fixtures.
    Run this on a schedule (e.g. every 15 minutes) to build true forward history.
    """
    import logging
    import sqlite3
    from datetime import datetime, timezone, timedelta

    logger = logging.getLogger(__name__)
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    if req.method == "OPTIONS":
        preflight_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=preflight_headers)

    try:
        data = req.get_json(silent=True) or {}
        hours_ahead = int(data.get("hours_ahead", 36))
        # "Just before kickoff" window (defaults to 0-20 minutes before kickoff).
        min_minutes_before_kickoff = int(data.get("min_minutes_before_kickoff", 0))
        max_minutes_before_kickoff = int(data.get("max_minutes_before_kickoff", 20))
        limit = int(data.get("limit", 400))
        league_id_filter = data.get("league_id")
        dry_run = bool(data.get("dry_run", False))
        model_version = str(data.get("model_version") or _get_live_model_version())

        hours_ahead = max(1, min(hours_ahead, 168))
        min_minutes_before_kickoff = max(0, min(min_minutes_before_kickoff, 240))
        max_minutes_before_kickoff = max(min_minutes_before_kickoff, min(max_minutes_before_kickoff, 360))
        limit = max(1, min(limit, 2000))

        db_path = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "data.sqlite")
        db_path = os.path.abspath(db_path)
        if not os.path.exists(db_path):
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Database file not found at {db_path}"}),
                status=404,
                headers=response_headers,
            )

        from prediction.db import connect
        conn = connect(db_path)
        cursor = conn.cursor()
        _ensure_prediction_snapshot_table(conn)

        now_utc = datetime.now(timezone.utc)
        cutoff_utc = now_utc + timedelta(hours=hours_ahead)
        query = """
            SELECT
                e.id,
                e.league_id,
                e.date_event,
                e.timestamp,
                t1.name as home_team_name,
                t2.name as away_team_name
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE e.home_team_id IS NOT NULL
              AND e.away_team_id IS NOT NULL
              AND (e.home_score IS NULL OR e.away_score IS NULL)
        """
        params: list[Any] = []
        if league_id_filter is not None:
            query += " AND e.league_id = ?"
            params.append(int(league_id_filter))
        query += " ORDER BY COALESCE(e.timestamp, e.date_event) ASC LIMIT ?"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        predictor = get_predictor()
        scanned = 0
        within_window = 0
        created_or_updated = 0
        skipped_existing = 0
        failed = 0
        finalized_completed = 0
        failures: list[dict] = []

        for row in rows:
            scanned += 1
            match_id, league_id_val, date_event, kickoff_ts, home_team_name, away_team_name = row
            if not home_team_name or not away_team_name:
                continue

            kickoff_raw = kickoff_ts or date_event
            if not kickoff_raw:
                continue
            try:
                kickoff_norm = str(kickoff_raw).replace("Z", "+00:00")
                kickoff_dt = datetime.fromisoformat(kickoff_norm)
                if kickoff_dt.tzinfo is None:
                    kickoff_dt = kickoff_dt.replace(tzinfo=timezone.utc)
                else:
                    kickoff_dt = kickoff_dt.astimezone(timezone.utc)
            except Exception:
                # Date-only fallback.
                try:
                    kickoff_dt = datetime.fromisoformat(str(date_event)[:10]).replace(tzinfo=timezone.utc)
                except Exception:
                    continue

            if kickoff_dt < now_utc or kickoff_dt > cutoff_utc:
                continue
            minutes_to_kickoff = (kickoff_dt - now_utc).total_seconds() / 60.0
            in_snapshot_window = (
                minutes_to_kickoff >= float(min_minutes_before_kickoff)
                and minutes_to_kickoff <= float(max_minutes_before_kickoff)
            )
            if not in_snapshot_window:
                continue
            within_window += 1

            cursor.execute(
                """
                SELECT 1
                FROM prediction_snapshot
                WHERE match_id = ?
                  AND model_version = ?
                  AND snapshot_type = 'pre_kickoff_live'
                LIMIT 1
                """,
                (int(match_id), model_version),
            )
            if cursor.fetchone() is not None:
                skipped_existing += 1
                continue

            try:
                pred = predictor.predict_match(
                    home_team=home_team_name,
                    away_team=away_team_name,
                    league_id=int(league_id_val),
                    match_date=str(date_event),
                    match_id=int(match_id),
                )
                if not dry_run:
                    _upsert_prediction_snapshot_row(
                        conn,
                        match_id=int(match_id),
                        league_id=int(league_id_val) if league_id_val is not None else None,
                        model_version=model_version,
                        snapshot_type="pre_kickoff_live",
                        predicted_at=now_utc.isoformat(),
                        kickoff_at=kickoff_dt.isoformat(),
                        home_team=home_team_name,
                        away_team=away_team_name,
                        predicted_winner=pred.get("predicted_winner"),
                        predicted_home_score=float(pred.get("predicted_home_score")) if pred.get("predicted_home_score") is not None else None,
                        predicted_away_score=float(pred.get("predicted_away_score")) if pred.get("predicted_away_score") is not None else None,
                        confidence=float(pred.get("confidence")) if pred.get("confidence") is not None else None,
                        home_win_prob=float(pred.get("home_win_prob")) if pred.get("home_win_prob") is not None else None,
                        away_win_prob=float(pred.get("away_win_prob")) if pred.get("away_win_prob") is not None else None,
                        actual_home_score=None,
                        actual_away_score=None,
                        actual_winner=None,
                        prediction_correct=None,
                        score_error=None,
                        source_note="auto_upcoming_window",
                    )
                created_or_updated += 1
            except Exception as e:
                failed += 1
                failures.append({"match_id": int(match_id), "error": str(e)})

        if not dry_run:
            # Finalize completed matches: store actuals + correctness for existing pre-kickoff snapshots.
            cursor.execute(
                """
                SELECT
                    s.match_id,
                    s.model_version,
                    s.predicted_home_score,
                    s.predicted_away_score,
                    s.predicted_winner,
                    e.home_score,
                    e.away_score
                FROM prediction_snapshot s
                JOIN event e ON e.id = s.match_id
                WHERE s.snapshot_type = 'pre_kickoff_live'
                  AND s.actual_home_score IS NULL
                  AND s.actual_away_score IS NULL
                  AND e.home_score IS NOT NULL
                  AND e.away_score IS NOT NULL
                """
            )
            completed_rows = cursor.fetchall()
            for (
                match_id_val,
                model_version_val,
                pred_home,
                pred_away,
                pred_winner,
                actual_home,
                actual_away,
            ) in completed_rows:
                if actual_home > actual_away:
                    actual_winner = "Home"
                elif actual_away > actual_home:
                    actual_winner = "Away"
                else:
                    actual_winner = "Draw"

                prediction_correct = None
                if pred_winner in {"Home", "Away", "Draw"}:
                    prediction_correct = 1 if pred_winner == actual_winner else 0

                score_error = None
                if pred_home is not None and pred_away is not None:
                    try:
                        score_error = abs(float(pred_home) - float(actual_home)) + abs(float(pred_away) - float(actual_away))
                    except Exception:
                        score_error = None

                cursor.execute(
                    """
                    UPDATE prediction_snapshot
                    SET actual_home_score = ?,
                        actual_away_score = ?,
                        actual_winner = ?,
                        prediction_correct = ?,
                        score_error = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE match_id = ?
                      AND model_version = ?
                      AND snapshot_type = 'pre_kickoff_live'
                    """,
                    (
                        int(actual_home),
                        int(actual_away),
                        actual_winner,
                        prediction_correct,
                        score_error,
                        int(match_id_val),
                        str(model_version_val),
                    ),
                )
                finalized_completed += 1

            conn.commit()
        conn.close()

        response_data = {
            "success": True,
            "dry_run": dry_run,
            "model_version": model_version,
            "hours_ahead": hours_ahead,
            "min_minutes_before_kickoff": min_minutes_before_kickoff,
            "max_minutes_before_kickoff": max_minutes_before_kickoff,
            "limit": limit,
            "scanned": scanned,
            "within_window": within_window,
            "created_or_updated": created_or_updated,
            "skipped_existing": skipped_existing,
            "finalized_completed": finalized_completed,
            "failed": failed,
            "failures": failures[:30],
        }
        return https_fn.Response(json.dumps(response_data), status=200, headers=response_headers)
    except Exception as e:
        logger.error(f"capture_upcoming_prediction_snapshots_http error: {e}")
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            headers=response_headers,
        )


@https_fn.on_request(timeout_sec=120, memory=1024)
def apisports_rugby_webhook_http(req: https_fn.Request) -> https_fn.Response:
    """
    Webhook endpoint for match lifecycle automation:
    - On match started/live: create pre-kickoff/live snapshot if missing
    - On match finished: finalize actual vs AI fields in snapshot history
    """
    import logging
    from datetime import datetime, timezone

    logger = logging.getLogger(__name__)
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    if req.method == "OPTIONS":
        preflight_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Webhook-Secret",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=preflight_headers)

    try:
        # Optional shared-secret guard (recommended in production).
        expected_secret = str(os.getenv("APISPORTS_WEBHOOK_SECRET", "")).strip()
        received_secret = (
            req.headers.get("X-Webhook-Secret")
            or req.headers.get("x-webhook-secret")
            or req.args.get("secret")
            or ""
        )
        if expected_secret and received_secret != expected_secret:
            return https_fn.Response(
                json.dumps({"success": False, "error": "Unauthorized webhook request"}),
                status=401,
                headers=response_headers,
            )

        payload = req.get_json(silent=True)
        if payload is None:
            return https_fn.Response(
                json.dumps({"success": True, "received": 0, "processed": 0, "note": "No JSON body"}),
                status=200,
                headers=response_headers,
            )

        # Support common webhook shapes: dict, list, {"data":[...]}.
        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                events = payload.get("data") or []
            elif isinstance(payload.get("events"), list):
                events = payload.get("events") or []
            else:
                events = [payload]
        else:
            events = []

        db_path = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "data.sqlite")
        db_path = os.path.abspath(db_path)
        if not os.path.exists(db_path):
            return https_fn.Response(
                json.dumps({"success": False, "error": f"Database file not found at {db_path}"}),
                status=404,
                headers=response_headers,
            )

        from prediction.db import connect
        conn = connect(db_path)
        cur = conn.cursor()
        _ensure_prediction_snapshot_table(conn)

        predictor = get_predictor()
        model_version = _get_live_model_version()

        started_statuses = {
            "LIVE", "IN PLAY", "1H", "2H", "3Q", "4Q", "HT", "ET", "P", "AET", "BREAK",
            "1ST HALF", "2ND HALF",
        }
        finished_statuses = {
            "FT", "FULL TIME", "FINISHED", "AFTER EXTRA TIME", "AET", "PEN", "PENALTIES",
        }

        processed = 0
        snapshots_created = 0
        snapshots_finalized = 0
        errors = 0
        error_samples: list[dict] = []

        def _to_int(v: Any) -> Optional[int]:
            try:
                if v is None:
                    return None
                return int(v)
            except Exception:
                return None

        def _first_match_id(obj: dict) -> Optional[int]:
            candidates = [
                obj.get("id"),
                obj.get("event_id"),
                (obj.get("game") or {}).get("id") if isinstance(obj.get("game"), dict) else None,
                (obj.get("fixture") or {}).get("id") if isinstance(obj.get("fixture"), dict) else None,
                (obj.get("match") or {}).get("id") if isinstance(obj.get("match"), dict) else None,
            ]
            for c in candidates:
                val = _to_int(c)
                if val is not None:
                    return val
            return None

        def _extract_status_text(obj: dict) -> str:
            status_obj = obj.get("status")
            parts = []
            if isinstance(status_obj, dict):
                parts.append(str(status_obj.get("short") or ""))
                parts.append(str(status_obj.get("long") or ""))
            else:
                parts.append(str(status_obj or ""))
            game_obj = obj.get("game") if isinstance(obj.get("game"), dict) else {}
            if isinstance(game_obj, dict):
                game_status = game_obj.get("status")
                if isinstance(game_status, dict):
                    parts.append(str(game_status.get("short") or ""))
                    parts.append(str(game_status.get("long") or ""))
                else:
                    parts.append(str(game_status or ""))
            return " ".join(p for p in parts if p).strip().upper()

        def _extract_scores(obj: dict) -> tuple[Optional[int], Optional[int]]:
            # Prefer explicit top-level score structure.
            score_obj = obj.get("scores")
            if isinstance(score_obj, dict):
                hs = _to_int(score_obj.get("home"))
                aws = _to_int(score_obj.get("away"))
                if hs is not None and aws is not None:
                    return hs, aws
                h_struct = score_obj.get("home")
                a_struct = score_obj.get("away")
                if isinstance(h_struct, dict) and isinstance(a_struct, dict):
                    hs = _to_int(h_struct.get("total") or h_struct.get("points") or h_struct.get("score"))
                    aws = _to_int(a_struct.get("total") or a_struct.get("points") or a_struct.get("score"))
                    if hs is not None and aws is not None:
                        return hs, aws
            # Fallback common keys.
            hs = _to_int(obj.get("home_score"))
            aws = _to_int(obj.get("away_score"))
            return hs, aws

        def _extract_kickoff_iso(obj: dict) -> Optional[str]:
            for v in [
                obj.get("date"),
                obj.get("date_event"),
                obj.get("timestamp"),
                (obj.get("game") or {}).get("date") if isinstance(obj.get("game"), dict) else None,
            ]:
                if not v:
                    continue
                try:
                    raw = str(v).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(raw)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    return dt.isoformat()
                except Exception:
                    continue
            return None

        for item in events:
            if not isinstance(item, dict):
                continue
            try:
                match_id = _first_match_id(item)
                if match_id is None:
                    continue

                status_text = _extract_status_text(item)
                home_score, away_score = _extract_scores(item)
                kickoff_iso = _extract_kickoff_iso(item)

                # Load current DB row details used by predictor/snapshot.
                cur.execute(
                    """
                    SELECT
                        e.id, e.league_id, e.date_event, e.timestamp, e.home_score, e.away_score,
                        t1.name as home_team_name, t2.name as away_team_name
                    FROM event e
                    LEFT JOIN team t1 ON e.home_team_id = t1.id
                    LEFT JOIN team t2 ON e.away_team_id = t2.id
                    WHERE e.id = ?
                    LIMIT 1
                    """,
                    (int(match_id),),
                )
                row = cur.fetchone()
                if not row:
                    # Unknown match in local DB; skip safely.
                    continue

                event_id, league_id_val, db_date_event, db_timestamp, db_home_score, db_away_score, home_team_name, away_team_name = row

                # Update event score/status quickly from webhook payload.
                if status_text:
                    cur.execute("UPDATE event SET status = COALESCE(?, status) WHERE id = ?", (status_text, int(event_id)))
                if kickoff_iso:
                    cur.execute(
                        "UPDATE event SET timestamp = COALESCE(?, timestamp), date_event = COALESCE(date_event, substr(?, 1, 10)) WHERE id = ?",
                        (kickoff_iso, kickoff_iso, int(event_id)),
                    )
                if home_score is not None and away_score is not None:
                    cur.execute(
                        "UPDATE event SET home_score = ?, away_score = ? WHERE id = ?",
                        (int(home_score), int(away_score), int(event_id)),
                    )
                    db_home_score, db_away_score = int(home_score), int(away_score)

                # Refresh values from payload/DB for processing.
                match_date_for_pred = str(db_date_event or (kickoff_iso[:10] if kickoff_iso else ""))

                is_started = any(token in status_text for token in started_statuses)
                is_finished = any(token in status_text for token in finished_statuses) or (
                    db_home_score is not None and db_away_score is not None
                )

                if is_started and not is_finished:
                    # Create snapshot once at start/live if missing.
                    cur.execute(
                        """
                        SELECT 1 FROM prediction_snapshot
                        WHERE match_id = ? AND model_version = ? AND snapshot_type = 'pre_kickoff_live'
                        LIMIT 1
                        """,
                        (int(event_id), model_version),
                    )
                    if cur.fetchone() is None and home_team_name and away_team_name and league_id_val is not None and match_date_for_pred:
                        pred = predictor.predict_match(
                            home_team=str(home_team_name),
                            away_team=str(away_team_name),
                            league_id=int(league_id_val),
                            match_date=str(match_date_for_pred),
                            match_id=None,  # AI-only snapshot
                        )
                        _upsert_prediction_snapshot_row(
                            conn,
                            match_id=int(event_id),
                            league_id=int(league_id_val),
                            model_version=model_version,
                            snapshot_type="pre_kickoff_live",
                            predicted_at=datetime.now(timezone.utc).isoformat(),
                            kickoff_at=kickoff_iso or (str(db_timestamp) if db_timestamp else None),
                            home_team=str(home_team_name),
                            away_team=str(away_team_name),
                            predicted_winner=pred.get("predicted_winner"),
                            predicted_home_score=float(pred.get("predicted_home_score")) if pred.get("predicted_home_score") is not None else None,
                            predicted_away_score=float(pred.get("predicted_away_score")) if pred.get("predicted_away_score") is not None else None,
                            confidence=float(pred.get("confidence")) if pred.get("confidence") is not None else None,
                            home_win_prob=float(pred.get("home_win_prob")) if pred.get("home_win_prob") is not None else None,
                            away_win_prob=float(pred.get("away_win_prob")) if pred.get("away_win_prob") is not None else None,
                            actual_home_score=None,
                            actual_away_score=None,
                            actual_winner=None,
                            prediction_correct=None,
                            score_error=None,
                            source_note="webhook_match_started",
                        )
                        snapshots_created += 1

                if is_finished and db_home_score is not None and db_away_score is not None:
                    # Finalize snapshot with actual outcomes.
                    if db_home_score > db_away_score:
                        actual_winner = "Home"
                    elif db_away_score > db_home_score:
                        actual_winner = "Away"
                    else:
                        actual_winner = "Draw"

                    cur.execute(
                        """
                        SELECT predicted_home_score, predicted_away_score, predicted_winner
                        FROM prediction_snapshot
                        WHERE match_id = ? AND model_version = ? AND snapshot_type = 'pre_kickoff_live'
                        LIMIT 1
                        """,
                        (int(event_id), model_version),
                    )
                    srow = cur.fetchone()
                    if srow:
                        pred_home, pred_away, pred_winner = srow
                        prediction_correct = None
                        if pred_winner in {"Home", "Away", "Draw"}:
                            prediction_correct = 1 if pred_winner == actual_winner else 0
                        score_error = None
                        if pred_home is not None and pred_away is not None:
                            score_error = abs(float(pred_home) - float(db_home_score)) + abs(float(pred_away) - float(db_away_score))
                        cur.execute(
                            """
                            UPDATE prediction_snapshot
                            SET actual_home_score = ?,
                                actual_away_score = ?,
                                actual_winner = ?,
                                prediction_correct = ?,
                                score_error = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE match_id = ? AND model_version = ? AND snapshot_type = 'pre_kickoff_live'
                            """,
                            (
                                int(db_home_score),
                                int(db_away_score),
                                actual_winner,
                                prediction_correct,
                                score_error,
                                int(event_id),
                                model_version,
                            ),
                        )
                        snapshots_finalized += 1

                processed += 1
            except Exception as item_error:
                errors += 1
                if len(error_samples) < 20:
                    error_samples.append({"error": str(item_error), "raw": str(item)[:300]})

        conn.commit()
        conn.close()

        return https_fn.Response(
            json.dumps(
                {
                    "success": True,
                    "received": len(events),
                    "processed": processed,
                    "snapshots_created": snapshots_created,
                    "snapshots_finalized": snapshots_finalized,
                    "errors": errors,
                    "error_samples": error_samples,
                }
            ),
            status=200,
            headers=response_headers,
        )
    except Exception as e:
        logger.error(f"apisports_rugby_webhook_http error: {e}")
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            headers=response_headers,
        )


@https_fn.on_request(timeout_sec=120, memory=1024)
def get_historical_predictions_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for historical predictions with explicit CORS support.
    Returns historical matches organized by year and week with AI predictions vs actual results.
    
    Request body:
    {
        "league_id": 4986,  # optional, filter by league
        "year": "2026",     # optional, fetch a single calendar year (recommended)
        "limit": 100        # optional, limit number of matches
    }
    """
    import logging
    import sys
    import os
    from datetime import datetime
    from time import perf_counter
    from collections import defaultdict
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    logger.info("="*80)
    logger.info("=== get_historical_predictions_http CALLED ===")
    logger.info("="*80)
    request_started_at = perf_counter()
    
    # Handle CORS preflight (match pattern used by other HTTP functions)
    if req.method == "OPTIONS":
        logger.info("OPTIONS request - returning CORS preflight")
        preflight_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=preflight_headers)
    
    # Define response headers with CORS for all responses
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }
    
    try:
        # Parse request data
        data = req.get_json(silent=True) or {}
        league_id = data.get('league_id')
        year = data.get('year')
        limit = data.get('limit')
        offset = data.get('offset', 0)
        try:
            limit = int(limit) if limit is not None else 500
        except Exception:
            limit = 500
        try:
            offset = int(offset) if offset is not None else 0
        except Exception:
            offset = 0
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        
        logger.info(f"Request data: league_id={league_id}, year={year}, limit={limit}, offset={offset}")
        
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            # If not found, try parent directory
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")
        
        logger.info(f"Using database path: {db_path}")
        
        if not os.path.exists(db_path):
            logger.error(f"Database file not found at {db_path}")
            response_data = {
                'error': f'Database file not found at {db_path}',
                'matches_by_year_week': {},
                'statistics': {},
            }
            return https_fn.Response(json.dumps(response_data), status=404, headers=response_headers)
        
        # Inline function to get historical matches with predictions
        def get_week_number(date_str: str) -> int:
            """Get ISO week number from date string (YYYY-MM-DD)"""
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                return date_obj.isocalendar()[1]
            except:
                return 0

        def get_year_week_key(date_str: str) -> str:
            """Get year-week key for grouping (e.g., '2024-W01')"""
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                year, week, _ = date_obj.isocalendar()
                return f"{year}-W{week:02d}"
            except:
                return "Unknown"
        
        # Import needed modules
        from prediction.db import connect
        predictor = get_predictor()
        
        # Connect to database
        conn = connect(db_path)
        cursor = conn.cursor()
        _ensure_prediction_snapshot_table(conn)
        
        # If year is not provided, pick a sensible default year and return all available years
        # so the UI can switch years without loading everything at once.
        available_years = []
        selected_year = None
        year_summary = {}
        try:
            t0_years = perf_counter()
            year_query = """
            SELECT DISTINCT substr(e.date_event, 1, 4) AS yr
            FROM event e
            WHERE e.date_event IS NOT NULL
            """
            year_params = []
            if league_id:
                year_query += " AND e.league_id = ?"
                year_params.append(league_id)
            year_query += " ORDER BY yr DESC"
            cursor.execute(year_query, year_params)
            available_years = [r[0] for r in cursor.fetchall() if r and r[0]]
            logger.info(f"[hist] available_years query completed in {(perf_counter() - t0_years) * 1000:.1f} ms (count={len(available_years)})")
        except Exception as e:
            logger.warning(f"Could not compute available years: {e}")
            available_years = []

        # Build a lightweight year summary (total matches vs completed matches).
        # This helps the UI explain why a year exists (scheduled games) but has 0 completed.
        try:
            t0_summary = perf_counter()
            sum_sql = """
                SELECT
                    substr(e.date_event, 1, 4) AS yr,
                    COUNT(1) AS total,
                    SUM(CASE WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL AND date(e.date_event) <= date('now') THEN 1 ELSE 0 END) AS completed
                FROM event e
                WHERE e.date_event IS NOT NULL
            """
            sum_params = []
            if league_id:
                sum_sql += " AND e.league_id = ?"
                sum_params.append(league_id)
            sum_sql += " GROUP BY yr ORDER BY yr DESC"
            cursor.execute(sum_sql, sum_params)
            for r in cursor.fetchall() or []:
                try:
                    yr = r[0]
                    if not yr:
                        continue
                    year_summary[str(yr)] = {
                        "total": int(r[1] or 0),
                        "completed": int(r[2] or 0),
                    }
                except Exception:
                    continue
            logger.info(f"[hist] year_summary query completed in {(perf_counter() - t0_summary) * 1000:.1f} ms (years={len(year_summary)})")
        except Exception as e:
            logger.warning(f"Could not compute year summary: {e}")
            year_summary = {}

        # Prefer current calendar year when available (but keep Rugby World Cup on tournament years).
        now_utc = datetime.utcnow()
        current_year = str(now_utc.year)
        if year is None:
            if str(league_id) == "4574":
                for y in ["2023", "2019", "2015", "2011", "2007"]:
                    if y in available_years:
                        selected_year = y
                        break
                if selected_year is None:
                    selected_year = available_years[0] if available_years else None
            else:
                selected_year = current_year if current_year in available_years else (available_years[0] if available_years else None)
        else:
            selected_year = str(year)

        # Fast path: serve immutable snapshot predictions if available.
        model_version = _get_live_model_version()
        snapshot_where = [
            "e.home_score IS NOT NULL",
            "e.away_score IS NOT NULL",
            "e.date_event IS NOT NULL",
            "date(e.date_event) <= date('now')",
            "s.model_version = ?",
        ]
        snapshot_params: list[Any] = [model_version]
        if league_id:
            snapshot_where.append("e.league_id = ?")
            snapshot_params.append(league_id)
        if selected_year:
            try:
                yr = int(str(selected_year).strip()[:4])
                prev_yr = str(yr - 1)
                snapshot_where.append("(substr(e.date_event, 1, 4) = ? OR substr(e.date_event, 1, 4) = ?)")
                snapshot_params.extend([str(yr), prev_yr])
            except (ValueError, TypeError):
                snapshot_where.append("substr(e.date_event, 1, 4) = ?")
                snapshot_params.append(str(selected_year))

        snapshot_filter_sql = " AND ".join(snapshot_where)
        snapshot_count_sql = f"""
            SELECT COUNT(1)
            FROM prediction_snapshot s
            JOIN event e ON e.id = s.match_id
            WHERE {snapshot_filter_sql}
        """
        cursor.execute(snapshot_count_sql, snapshot_params)
        snapshot_total_rows = int((cursor.fetchone() or [0])[0] or 0)
        logger.info(
            f"[hist] snapshot rows available={snapshot_total_rows} "
            f"(model_version={model_version}, year={selected_year}, league_id={league_id})"
        )

        if snapshot_total_rows > 0:
            snapshot_data_sql = f"""
                SELECT
                    e.id,
                    e.league_id,
                    l.name as league_name,
                    e.date_event,
                    e.timestamp,
                    e.home_team_id,
                    e.away_team_id,
                    e.home_score,
                    e.away_score,
                    t1.name as home_team_name,
                    t2.name as away_team_name,
                    e.season,
                    e.round,
                    e.venue,
                    e.status,
                    s.predicted_winner,
                    s.predicted_home_score,
                    s.predicted_away_score,
                    s.confidence,
                    s.home_win_prob,
                    s.away_win_prob,
                    s.prediction_correct,
                    s.score_error,
                    s.predicted_at,
                    s.snapshot_type
                FROM prediction_snapshot s
                JOIN event e ON e.id = s.match_id
                LEFT JOIN league l ON e.league_id = l.id
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE {snapshot_filter_sql}
                ORDER BY e.date_event ASC, e.league_id
                LIMIT ? OFFSET ?
            """
            cursor.execute(snapshot_data_sql, [*snapshot_params, limit, offset])
            snapshot_rows = cursor.fetchall()

            matches_by_year_week = defaultdict(lambda: defaultdict(list))
            all_matches = []
            correct_predictions = 0
            total_predictions = 0
            score_errors: list[float] = []

            for row in snapshot_rows:
                (
                    match_id,
                    league_id_val,
                    league_name,
                    date_event,
                    kickoff_ts,
                    home_team_id,
                    away_team_id,
                    home_score,
                    away_score,
                    home_team_name,
                    away_team_name,
                    season,
                    round_num,
                    venue,
                    status,
                    predicted_winner,
                    predicted_home_score,
                    predicted_away_score,
                    prediction_confidence,
                    home_win_prob,
                    away_win_prob,
                    prediction_correct_raw,
                    prediction_error,
                    _predicted_at,
                    _snapshot_type,
                ) = row

                if not home_team_name or not away_team_name or not date_event:
                    continue

                if home_score > away_score:
                    actual_winner = "Home"
                    actual_winner_team = home_team_name
                elif away_score > home_score:
                    actual_winner = "Away"
                    actual_winner_team = away_team_name
                else:
                    actual_winner = "Draw"
                    actual_winner_team = None

                prediction_correct = None
                if prediction_correct_raw is not None:
                    prediction_correct = bool(int(prediction_correct_raw))
                elif predicted_winner and predicted_winner != "Error":
                    prediction_correct = (predicted_winner == actual_winner)

                if prediction_correct is not None:
                    total_predictions += 1
                    if prediction_correct:
                        correct_predictions += 1
                if prediction_error is not None:
                    try:
                        score_errors.append(float(prediction_error))
                    except Exception:
                        pass

                year = date_event[:4] if date_event else "Unknown"
                try:
                    round_key = str(int(round_num)) if round_num is not None else get_year_week_key(date_event)
                except Exception:
                    round_key = get_year_week_key(date_event)
                week = get_week_number(date_event)

                def _has_meaningful_time(v: Any) -> bool:
                    try:
                        s = str(v or "")
                    except Exception:
                        return False
                    if "T" not in s:
                        return False
                    return ("T00:00" not in s)

                kickoff_at = kickoff_ts if (kickoff_ts and _has_meaningful_time(kickoff_ts)) else None
                status_norm = str(status or "").upper()
                went_to_extra_time = ("AET" in status_norm) or ("EXTRA" in status_norm) or ("ET" in status_norm and "SET" not in status_norm)

                match_data = {
                    "match_id": match_id,
                    "league_id": league_id_val,
                    "league_name": league_name or f"League {league_id_val}",
                    "date": date_event,
                    "kickoff_at": kickoff_at,
                    "went_to_extra_time": went_to_extra_time,
                    "year": year,
                    "week": week,
                    "year_week": round_key,
                    "season": season,
                    "round": round_num,
                    "venue": venue,
                    "status": status,
                    "home_team": home_team_name,
                    "away_team": away_team_name,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "actual_home_score": home_score,
                    "actual_away_score": away_score,
                    "actual_winner": actual_winner,
                    "actual_winner_team": actual_winner_team,
                    "predicted_home_score": predicted_home_score,
                    "predicted_away_score": predicted_away_score,
                    "predicted_winner": predicted_winner,
                    "prediction_confidence": prediction_confidence,
                    "prediction_error": prediction_error,
                    "prediction_correct": prediction_correct,
                    "score_difference": abs(home_score - away_score) if home_score is not None and away_score is not None else None,
                    "predicted_score_difference": abs(predicted_home_score - predicted_away_score) if predicted_home_score is not None and predicted_away_score is not None else None,
                    "home_win_prob": home_win_prob,
                    "away_win_prob": away_win_prob,
                }

                matches_by_year_week[year][round_key].append(match_data)
                all_matches.append(match_data)

            accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
            avg_score_error = (sum(score_errors) / len(score_errors)) if score_errors else None

            result = {
                "available_years": available_years,
                "selected_year": selected_year,
                "year_summary": year_summary,
                "matches_by_year_week": {
                    year_key: {week_key: matches for week_key, matches in weeks.items()}
                    for year_key, weeks in matches_by_year_week.items()
                },
                "all_matches": all_matches,
                "statistics": {
                    "total_matches": len(all_matches),
                    "total_predictions": total_predictions,
                    "correct_predictions": correct_predictions,
                    "accuracy_percentage": round(accuracy, 2),
                    "average_score_error": round(avg_score_error, 2) if avg_score_error is not None else None,
                },
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total_rows": snapshot_total_rows,
                    "returned_rows": len(snapshot_rows),
                    "has_more": (offset + len(snapshot_rows)) < snapshot_total_rows,
                    "next_offset": (offset + len(snapshot_rows)) if (offset + len(snapshot_rows)) < snapshot_total_rows else None,
                },
                "by_league": {},
                "debug": {
                    "data_source": "prediction_snapshot",
                    "model_version": model_version,
                },
            }

            leagues_dict = defaultdict(list)
            for match in all_matches:
                leagues_dict[match["league_id"]].append(match)
            for league_id_val, league_matches in leagues_dict.items():
                league_correct = sum(1 for m in league_matches if m.get("prediction_correct") is True)
                league_total = sum(1 for m in league_matches if m.get("prediction_correct") is not None)
                league_accuracy = (league_correct / league_total * 100) if league_total > 0 else 0
                league_losses = max(0, league_total - league_correct)
                league_errors = [float(m.get("prediction_error")) for m in league_matches if m.get("prediction_error") is not None]
                league_mae = (sum(league_errors) / len(league_errors)) if league_errors else None
                result["by_league"][league_id_val] = {
                    "league_name": league_matches[0]["league_name"] if league_matches else f"League {league_id_val}",
                    "total_matches": len(league_matches),
                    "total_predictions": league_total,
                    "correct_predictions": league_correct,
                    "incorrect_predictions": league_losses,
                    "accuracy_percentage": round(league_accuracy, 2),
                    "average_score_error": round(league_mae, 2) if league_mae is not None else None,
                }

            conn.close()
            logger.info("[hist] served from prediction_snapshot table")
            return https_fn.Response(json.dumps(result), status=200, headers=response_headers)

        # Query for completed matches with scores
        base_query = """
        SELECT 
            e.id,
            e.league_id,
            l.name as league_name,
            e.date_event,
            e.timestamp,
            e.home_team_id,
            e.away_team_id,
            e.home_score,
            e.away_score,
            t1.name as home_team_name,
            t2.name as away_team_name,
            e.season,
            e.round,
            e.venue,
            e.status
        FROM event e
        LEFT JOIN league l ON e.league_id = l.id
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.home_score IS NOT NULL 
        AND e.away_score IS NOT NULL
        AND e.date_event IS NOT NULL
        AND date(e.date_event) <= date('now')
        """

        params = []
        if league_id:
            base_query += " AND e.league_id = ?"
            params.append(league_id)

        if selected_year:
            try:
                yr = int(str(selected_year).strip()[:4])
                prev_yr = str(yr - 1)
                base_query += " AND (substr(e.date_event, 1, 4) = ? OR substr(e.date_event, 1, 4) = ?)"
                params.extend([str(yr), prev_yr])
            except (ValueError, TypeError):
                base_query += " AND substr(e.date_event, 1, 4) = ?"
                params.append(str(selected_year))

        count_query = f"SELECT COUNT(1) FROM ({base_query}) q"
        t0_count = perf_counter()
        cursor.execute(count_query, params)
        total_rows = int((cursor.fetchone() or [0])[0] or 0)
        logger.info(f"[hist] count query completed in {(perf_counter() - t0_count) * 1000:.1f} ms (rows={total_rows}, limit={limit}, offset={offset})")

        query = base_query + " ORDER BY e.date_event ASC, e.league_id LIMIT ? OFFSET ?"
        query_params = [*params, limit, offset]
        t0_data = perf_counter()
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        logger.info(f"[hist] data query completed in {(perf_counter() - t0_data) * 1000:.1f} ms (returned={len(results)})")
        
        # Compute league round for matches missing round (season-based: Week 1 = first week of season)
        def _compute_league_rounds(rows):
            """Group matches into rounds by matchday (within 10 days = same round). Week 1 = first week of season."""
            from datetime import datetime
            round_assignments = {}
            prev_date = None
            current_round = 0
            day_threshold = 4
            season_gap_days = 90
            for r in rows:
                mid, _, _, date_event = r[0], r[1], r[2], r[3]
                if not date_event:
                    continue
                try:
                    dt = datetime.strptime(date_event[:10], '%Y-%m-%d')
                except Exception:
                    continue
                key = (mid, date_event[:10] if date_event else '')
                if prev_date is None:
                    current_round = 1
                elif (dt - prev_date).days > season_gap_days:
                    current_round = 1
                elif (dt - prev_date).days > day_threshold:
                    current_round += 1
                round_assignments[key] = current_round
                prev_date = dt
            return round_assignments
        
        league_rounds = _compute_league_rounds(results) if results else {}
        
        # Organize matches by year and round (not ISO week)
        matches_by_year_week = defaultdict(lambda: defaultdict(list))
        all_matches = []
        
        correct_predictions = 0
        total_predictions = 0
        score_errors = []
        
        logger.info(f"Processing {len(results)} completed matches...")
        
        t0_process = perf_counter()
        for row in results:
            match_id, league_id_val, league_name, date_event, kickoff_ts, home_team_id, away_team_id, \
            home_score, away_score, home_team_name, away_team_name, season, round_num, \
            venue, status = row
            
            # Skip if missing critical data
            if not home_team_name or not away_team_name or not date_event:
                continue
            
            # Determine actual winner
            if home_score > away_score:
                actual_winner = 'Home'
                actual_winner_team = home_team_name
            elif away_score > home_score:
                actual_winner = 'Away'
                actual_winner_team = away_team_name
            else:
                actual_winner = 'Draw'
                actual_winner_team = None
            
            # Generate prediction for this match
            predicted_winner = None
            predicted_home_score = None
            predicted_away_score = None
            prediction_confidence = None
            prediction_error = None
            
            if predictor:
                try:
                    pred = predictor.predict_match(
                        home_team=home_team_name,
                        away_team=away_team_name,
                        league_id=league_id_val,
                        match_date=date_event,
                        match_id=match_id,
                    )
                    
                    predicted_home_score = pred.get('predicted_home_score', 0)
                    predicted_away_score = pred.get('predicted_away_score', 0)
                    prediction_confidence = pred.get('confidence', 0.5)
                    predicted_winner = pred.get('predicted_winner', 'Unknown')
                    
                    home_error = abs(predicted_home_score - home_score)
                    away_error = abs(predicted_away_score - away_score)
                    prediction_error = home_error + away_error
                    if not selected_year or date_event[:4] == selected_year:
                        if predicted_winner == actual_winner:
                            correct_predictions += 1
                        total_predictions += 1
                        score_errors.append(prediction_error)
                    
                except Exception as e:
                    logger.warning(f"Could not generate prediction for {home_team_name} vs {away_team_name} on {date_event}: {e}")
                    predicted_winner = 'Error'
            
            year = date_event[:4] if date_event else "Unknown"
            # Prefer API round when valid (1-30); else use computed league round
            key = (match_id, date_event[:10] if date_event else '')
            try:
                api_r = int(str(round_num or '').strip()) if round_num is not None else None
                use_api = api_r is not None and 1 <= api_r <= 30
            except (ValueError, TypeError):
                use_api = False
            effective_round = round_num if use_api else league_rounds.get(key)
            if effective_round is None:
                effective_round = league_rounds.get(key)
            # Group key: round-based (e.g. "1", "2") for display
            round_key = str(effective_round) if effective_round is not None else get_year_week_key(date_event)
            year_week_key = round_key
            week = get_week_number(date_event)

            # Prefer full timestamp (kickoff) when available. If we only have midnight UTC,
            # treat as unknown kickoff time to avoid showing a fixed local time (e.g. 02:00).
            def _has_meaningful_time(v: Any) -> bool:
                try:
                    s = str(v or "")
                except Exception:
                    return False
                if "T" not in s:
                    return False
                # matches "...T00:00..." (with optional seconds/ms and timezone)
                return ("T00:00" not in s)

            kickoff_at = kickoff_ts if (kickoff_ts and _has_meaningful_time(kickoff_ts)) else None
            status_norm = str(status or "").upper()
            went_to_extra_time = ("AET" in status_norm) or ("EXTRA" in status_norm) or ("ET" in status_norm and "SET" not in status_norm)
            
            match_data = {
                'match_id': match_id,
                'league_id': league_id_val,
                'league_name': league_name or f"League {league_id_val}",
                'date': date_event,
                'kickoff_at': kickoff_at,
                'went_to_extra_time': went_to_extra_time,
                'year': year,
                'week': week,
                'year_week': year_week_key,
                'season': season,
                'round': effective_round,
                'venue': venue,
                'status': status,
                'home_team': home_team_name,
                'away_team': away_team_name,
                'home_team_id': home_team_id,
                'away_team_id': away_team_id,
                'actual_home_score': home_score,
                'actual_away_score': away_score,
                'actual_winner': actual_winner,
                'actual_winner_team': actual_winner_team,
                'predicted_home_score': predicted_home_score,
                'predicted_away_score': predicted_away_score,
                'predicted_winner': predicted_winner,
                'prediction_confidence': prediction_confidence,
                'prediction_error': prediction_error,
                'prediction_correct': predicted_winner == actual_winner if predicted_winner and predicted_winner != 'Error' else None,
                'score_difference': abs(home_score - away_score) if home_score and away_score else None,
                'predicted_score_difference': abs(predicted_home_score - predicted_away_score) if predicted_home_score is not None and predicted_away_score is not None else None,
            }
            
            matches_by_year_week[year][year_week_key].append(match_data)
            if not selected_year or year == selected_year:
                all_matches.append(match_data)
        logger.info(f"[hist] prediction/mapping loop completed in {(perf_counter() - t0_process) * 1000:.1f} ms")
        
        conn.close()
        
        # Calculate accuracy statistics
        accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
        avg_score_error = sum(score_errors) / len(score_errors) if score_errors else None
        
        # Convert defaultdict to regular dict for JSON serialization
        result = {
            'available_years': available_years,
            'selected_year': selected_year,
            'year_summary': year_summary,
            'matches_by_year_week': {
                year: {
                    week_key: matches
                    for week_key, matches in weeks.items()
                }
                for year, weeks in matches_by_year_week.items()
            },
            'all_matches': all_matches,
            'statistics': {
                'total_matches': len(all_matches),
                'total_predictions': total_predictions,
                'correct_predictions': correct_predictions,
                'accuracy_percentage': round(accuracy, 2),
                'average_score_error': round(avg_score_error, 2) if avg_score_error else None,
            },
            'pagination': {
                'limit': limit,
                'offset': offset,
                'total_rows': total_rows,
                'returned_rows': len(results),
                'has_more': (offset + len(results)) < total_rows,
                'next_offset': (offset + len(results)) if (offset + len(results)) < total_rows else None,
            },
            'by_league': {}
        }
        
        # Group by league for easier filtering
        leagues_dict = defaultdict(list)
        for match in all_matches:
            leagues_dict[match['league_id']].append(match)
        
        for league_id_val, league_matches in leagues_dict.items():
            league_correct = sum(1 for m in league_matches if m.get('prediction_correct') is True)
            league_total = sum(1 for m in league_matches if m.get('prediction_correct') is not None)
            league_accuracy = (league_correct / league_total * 100) if league_total > 0 else 0
            league_losses = max(0, league_total - league_correct)
            league_errors = [float(m.get('prediction_error')) for m in league_matches if m.get('prediction_error') is not None]
            league_mae = (sum(league_errors) / len(league_errors)) if league_errors else None
            
            result['by_league'][league_id_val] = {
                'league_name': league_matches[0]['league_name'] if league_matches else f"League {league_id_val}",
                'total_matches': len(league_matches),
                'total_predictions': league_total,
                'correct_predictions': league_correct,
                'incorrect_predictions': league_losses,
                'accuracy_percentage': round(league_accuracy, 2),
                'average_score_error': round(league_mae, 2) if league_mae is not None else None,
            }
        
        logger.info(f"Retrieved {result['statistics']['total_matches']} matches")
        logger.info(f"Generated {result['statistics']['total_predictions']} predictions")
        logger.info(f"Accuracy: {result['statistics'].get('accuracy_percentage', 0):.2f}%")
        logger.info(f"[hist] total endpoint time {(perf_counter() - request_started_at) * 1000:.1f} ms")
        
        # Convert any datetime objects to strings for JSON serialization
        def convert_for_json(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_for_json(item) for item in obj]
            elif isinstance(obj, (defaultdict, set)):
                return convert_for_json(dict(obj) if isinstance(obj, defaultdict) else list(obj))
            else:
                return obj
        
        result = convert_for_json(result)
        
        logger.info("=== get_historical_predictions_http completed successfully ===")
        return https_fn.Response(json.dumps(result), status=200, headers=response_headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== get_historical_predictions_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {
            "error": str(e),
            "traceback": error_trace,
            "matches_by_year_week": {},
            "statistics": {},
        }
        # Always include CORS headers even on error
        return https_fn.Response(json.dumps(response_data), status=500, headers=response_headers)


@https_fn.on_request(timeout_sec=540, memory=2048)
def get_historical_backtest_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for TRUE historical evaluation via walk-forward backtest (unseen).

    For each week in the selected year, trains a fresh model using only matches
    strictly BEFORE that week, then predicts matches in that week.

    Request body:
    {
        "league_id": 4414,      # required
        "year": "2026",         # optional (calendar year). If omitted, uses most recent year with completed matches.
        "days_back": 3650,      # optional, how far back training history can go (default ~10y)
        "min_train_games": 30,  # optional
        "refresh": false        # optional, bypass Firestore cache
    }
    """
    import logging
    import os
    import json
    import sqlite3
    from datetime import datetime, timedelta
    from collections import defaultdict

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    try:
        data = req.get_json(silent=True) or {}
        league_id_raw = data.get("league_id")
        if league_id_raw is None:
            return https_fn.Response(
                json.dumps({"error": "league_id is required"}),
                status=400,
                headers=headers,
            )
        league_id = int(league_id_raw)

        year = data.get("year")
        refresh = bool(data.get("refresh", False))
        min_train_games = int(data.get("min_train_games", 30))
        days_back = int(data.get("days_back", 3650))

        # DB path (same logic as other endpoints)
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")

        if not os.path.exists(db_path):
            return https_fn.Response(
                json.dumps({"error": f"Database file not found at {db_path}"}),
                status=404,
                headers=headers,
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Determine available years (include scheduled games too) and selected year.
        year_sql = """
            SELECT DISTINCT substr(e.date_event, 1, 4) AS yr
            FROM event e
            WHERE e.date_event IS NOT NULL
              AND e.league_id = ?
            ORDER BY yr DESC
        """
        cur.execute(year_sql, (league_id,))
        available_years = [r["yr"] for r in cur.fetchall() if r and r["yr"]]

        # Year summary (total vs completed). Helps UI explain missing “completed” years.
        year_summary = {}
        try:
            cur.execute(
                """
                SELECT
                  substr(e.date_event, 1, 4) AS yr,
                  COUNT(1) AS total,
                  SUM(CASE WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL AND date(e.date_event) <= date('now') THEN 1 ELSE 0 END) AS completed
                FROM event e
                WHERE e.league_id = ?
                  AND e.date_event IS NOT NULL
                GROUP BY yr
                ORDER BY yr DESC
                """,
                (league_id,),
            )
            for r in cur.fetchall() or []:
                yr = r["yr"] if isinstance(r, sqlite3.Row) else r[0]
                total = r["total"] if isinstance(r, sqlite3.Row) else r[1]
                completed = r["completed"] if isinstance(r, sqlite3.Row) else r[2]
                if yr:
                    year_summary[str(yr)] = {"total": int(total or 0), "completed": int(completed or 0)}
        except Exception as e:
            logger.warning(f"Could not compute year summary: {e}")
            year_summary = {}

        now_utc = datetime.utcnow()
        current_year = str(now_utc.year)

        if year is not None:
            selected_year = str(year)
        else:
            # Rugby World Cup: prefer tournament years.
            if league_id == 4574:
                selected_year = None
                for y in ["2023", "2019", "2015", "2011", "2007"]:
                    if y in available_years:
                        selected_year = y
                        break
                if not selected_year:
                    selected_year = available_years[0] if available_years else None
            else:
                selected_year = current_year if current_year in available_years else (available_years[0] if available_years else None)

        if not selected_year:
            conn.close()
            return https_fn.Response(
                json.dumps(
                    {
                        "available_years": available_years,
                        "selected_year": None,
                        "year_summary": year_summary,
                        "matches_by_year_week": {},
                        "statistics": {},
                        "error": "No matches found for this league",
                    }
                ),
                status=200,
                headers=headers,
            )

        # If there are no completed matches for this league/year yet, return an empty payload (still 200)
        # so the UI can show the year and a friendly message.
        cur.execute(
            """
            SELECT COUNT(1) AS cnt
            FROM event e
            WHERE e.league_id = ?
              AND e.date_event IS NOT NULL
              AND e.home_score IS NOT NULL
              AND e.away_score IS NOT NULL
              AND date(e.date_event) <= date('now')
              AND substr(e.date_event, 1, 4) = ?
            """,
            (league_id, selected_year),
        )
        row_cnt = cur.fetchone()
        completed_cnt = int(row_cnt["cnt"]) if row_cnt and row_cnt["cnt"] is not None else 0
        if completed_cnt == 0:
            conn.close()
            return https_fn.Response(
                json.dumps(
                    {
                        "available_years": available_years,
                        "selected_year": selected_year,
                        "year_summary": year_summary,
                        "matches_by_year_week": {},
                        "statistics": {},
                        "error": f"No completed matches found for {selected_year} yet",
                    }
                ),
                status=200,
                headers=headers,
            )

        # Cache in Firestore (avoid recompute)
        # Invalidate cache when it has no matches but DB now has completed games (e.g. 2026 games added after initial cache)
        try:
            fs = get_firestore_client()
            cache_id = f"walk_forward_v4::{league_id}::{selected_year}"
            cache_ref = fs.collection("backtests").document(cache_id)
            if not refresh:
                cached = cache_ref.get()
                if getattr(cached, "exists", False):
                    cached_data = cached.to_dict() or {}
                    payload = cached_data.get("data")
                    if isinstance(payload, dict) and payload.get("selected_year") == selected_year:
                        mbyw = payload.get("matches_by_year_week") or {}
                        year_matches = mbyw.get(selected_year) if isinstance(mbyw, dict) else {}
                        total_cached = sum(len(v) if isinstance(v, list) else 0 for v in (year_matches or {}).values()) if isinstance(year_matches, dict) else 0
                        has_cached_matches = total_cached > 0 and not payload.get("error")
                        if has_cached_matches:
                            conn.close()
                            return https_fn.Response(json.dumps(payload), status=200, headers=headers)
                        # Cache has no matches for this year - re-check DB; if we now have completed games, bypass cache
                        if completed_cnt > 0:
                            logger.info(f"Backtest cache invalidated for {selected_year}: cache empty but DB has {completed_cnt} completed matches")
        except Exception as cache_err:
            logger.warning(f"Backtest cache read failed (continuing without cache): {cache_err}")
            fs = None
            cache_ref = None

        # Load team/league names for display
        cur.execute("SELECT id, name FROM team")
        team_name = {int(r["id"]): r["name"] for r in cur.fetchall() if r and r["id"] is not None}
        cur.execute("SELECT id, name FROM league WHERE id = ?", (league_id,))
        row = cur.fetchone()
        league_name = row["name"] if row and row["name"] else f"League {league_id}"

        # Build feature table (chronological, pre-match features).
        # IMPORTANT: build features on a SMALL in-memory DB for this league only.
        # The full DB can be large and may cause slowdowns or memory issues in Cloud Functions.
        from prediction.features import build_feature_table, FeatureConfig
        import pandas as pd
        import xgboost as xgb

        today_iso = datetime.utcnow().date().isoformat()
        min_date_iso = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()

        # Pull only completed matches for this league within the training window
        cur.execute(
            """
            SELECT
              e.id AS id,
              e.league_id AS league_id,
              e.season AS season,
              e.date_event AS date_event,
              e.timestamp AS timestamp,
              e.home_team_id AS home_team_id,
              e.away_team_id AS away_team_id,
              e.home_score AS home_score,
              e.away_score AS away_score
            FROM event e
            WHERE e.league_id = ?
              AND e.home_team_id IS NOT NULL
              AND e.away_team_id IS NOT NULL
              AND e.date_event IS NOT NULL
              AND e.home_score IS NOT NULL
              AND e.away_score IS NOT NULL
              AND date(e.date_event) >= date(?)
              AND date(e.date_event) <= date(?)
            ORDER BY date(e.date_event) ASC, e.timestamp ASC, e.id ASC
            """,
            (league_id, min_date_iso, today_iso),
        )
        event_rows = cur.fetchall()

        # Create in-memory DB with only the columns build_feature_table needs
        mem = sqlite3.connect(":memory:")
        mem.execute(
            """
            CREATE TABLE event (
              id INTEGER PRIMARY KEY,
              league_id INTEGER,
              season TEXT,
              date_event TEXT,
              timestamp INTEGER,
              home_team_id INTEGER,
              away_team_id INTEGER,
              home_score INTEGER,
              away_score INTEGER
            )
            """
        )
        if event_rows:
            mem.executemany(
                """
                INSERT INTO event (id, league_id, season, date_event, timestamp, home_team_id, away_team_id, home_score, away_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        int(r["id"]),
                        int(r["league_id"]),
                        r["season"],
                        r["date_event"],
                        r["timestamp"],
                        int(r["home_team_id"]),
                        int(r["away_team_id"]),
                        int(r["home_score"]),
                        int(r["away_score"]),
                    )
                    for r in event_rows
                ],
            )
        mem.commit()

        config = FeatureConfig(
            elo_priors=None,
            elo_k=24.0,
            neutral_mode=(league_id == 4574 or league_id == 4714),
        )
        df = build_feature_table(mem, config)
        mem.close()

        # Completed matches only, already filtered by query; sort just in case
        df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
        df.sort_values(["date_event", "event_id"], inplace=True)

        # Calendar year filter for the evaluation set
        try:
            target_year_int = int(selected_year)
        except Exception:
            target_year_int = None
        if target_year_int is not None:
            df_eval = df[df["date_event"].dt.year == target_year_int].copy()
        else:
            df_eval = df.copy()

        if df_eval.empty:
            conn.close()
            payload = {
                "available_years": available_years,
                "selected_year": selected_year,
                "matches_by_year_week": {},
                "statistics": {},
                "by_league": {},
                "warning": "No completed matches found for selected year",
            }
            return https_fn.Response(json.dumps(payload), status=200, headers=headers)

        # Feature columns (match training script behavior)
        exclude_cols = {
            "event_id",
            "league_id",
            "season",
            "date_event",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
            "home_win",
        }
        feature_cols = [c for c in df.columns if c not in exclude_cols]
        feature_cols = [c for c in feature_cols if not df[c].isna().all()]

        # Week keys for eval matches
        def year_week_key(ts: pd.Timestamp) -> str:
            iso = ts.isocalendar()
            return f"{int(iso.year)}-W{int(iso.week):02d}"

        df_eval["year_week"] = df_eval["date_event"].apply(year_week_key)
        df_eval["year"] = df_eval["date_event"].dt.strftime("%Y")
        df_eval["week"] = df_eval["date_event"].dt.isocalendar().week.astype(int)

        # Order weeks chronologically (based on first match date in week)
        week_first_date = (
            df_eval.groupby("year_week")["date_event"].min().sort_values()
        )
        week_keys = list(week_first_date.index)

        matches_by_year_week = defaultdict(lambda: defaultdict(list))

        total_predictions = 0
        correct_predictions = 0
        draws_excluded = 0
        score_errors: list[float] = []
        weeks_evaluated = 0
        weeks_skipped = 0

        # Model hyperparams (same defaults as training)
        def train_models(train_df):
            X_train = train_df[feature_cols].fillna(0).values
            y_winner = (train_df["home_score"] > train_df["away_score"]).astype(int).values
            y_home = train_df["home_score"].values
            y_away = train_df["away_score"].values

            clf = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
            )
            clf.fit(X_train, y_winner)

            reg_home = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="mae",
            )
            reg_home.fit(X_train, y_home)

            reg_away = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="mae",
            )
            reg_away.fit(X_train, y_away)

            return clf, reg_home, reg_away

        for wk in week_keys:
            wk_start = week_first_date.loc[wk]

            # Train on all matches strictly before this week
            train_df = df[df["date_event"] < wk_start].copy()
            if len(train_df) < min_train_games:
                weeks_skipped += 1
                continue

            week_df = df_eval[df_eval["year_week"] == wk].copy()
            if week_df.empty:
                continue

            clf, reg_home, reg_away = train_models(train_df)
            weeks_evaluated += 1

            X_test = week_df[feature_cols].fillna(0).values
            home_win_prob = clf.predict_proba(X_test)[:, 1]
            pred_home = reg_home.predict(X_test)
            pred_away = reg_away.predict(X_test)

            for i, row in enumerate(week_df.itertuples(index=False)):
                # row access via attributes: event_id, league_id, season, date_event, home_team_id, away_team_id, home_score, away_score, home_win, ...
                event_id = int(getattr(row, "event_id"))
                date_event = getattr(row, "date_event")
                home_team_id = int(getattr(row, "home_team_id"))
                away_team_id = int(getattr(row, "away_team_id"))
                home_score = int(getattr(row, "home_score"))
                away_score = int(getattr(row, "away_score"))

                if home_score > away_score:
                    actual_winner = "Home"
                    actual_winner_team = team_name.get(home_team_id)
                elif away_score > home_score:
                    actual_winner = "Away"
                    actual_winner_team = team_name.get(away_team_id)
                else:
                    actual_winner = "Draw"
                    actual_winner_team = None

                p = float(home_win_prob[i])
                predicted_home_score = float(max(0.0, pred_home[i]))
                predicted_away_score = float(max(0.0, pred_away[i]))
                # Winner must match predicted scores - avoid classifier/regression mismatch (e.g. scores say Lions, classifier says Sharks)
                # Allow AI to predict Draw when scores are equal
                if predicted_home_score > predicted_away_score:
                    predicted_winner = "Home"
                elif predicted_away_score > predicted_home_score:
                    predicted_winner = "Away"
                else:
                    predicted_winner = "Draw"

                prediction_correct = predicted_winner == actual_winner
                total_predictions += 1
                if prediction_correct:
                    correct_predictions += 1
                if actual_winner == "Draw":
                    draws_excluded += 1

                err = abs(predicted_home_score - home_score) + abs(predicted_away_score - away_score)
                score_errors.append(float(err))

                match_year = str(getattr(row, "year"))
                match_week = int(getattr(row, "week"))
                match_year_week = str(getattr(row, "year_week"))

                matches_by_year_week[match_year][match_year_week].append(
                    {
                        "match_id": event_id,
                        "league_id": league_id,
                        "league_name": league_name,
                        "date": date_event.strftime("%Y-%m-%d") if hasattr(date_event, "strftime") else str(date_event),
                        "year": match_year,
                        "week": match_week,
                        "year_week": match_year_week,
                        "home_team": team_name.get(home_team_id, f"Team {home_team_id}"),
                        "away_team": team_name.get(away_team_id, f"Team {away_team_id}"),
                        "home_team_id": home_team_id,
                        "away_team_id": away_team_id,
                        "actual_home_score": home_score,
                        "actual_away_score": away_score,
                        "actual_winner": actual_winner,
                        "actual_winner_team": actual_winner_team,
                        "predicted_home_score": predicted_home_score,
                        "predicted_away_score": predicted_away_score,
                        "predicted_winner": predicted_winner,
                        "prediction_confidence": float(max(p, 1.0 - p)),
                        "prediction_error": float(err),
                        "prediction_correct": prediction_correct,
                        "evaluation_mode": "walk_forward_backtest",
                        "train_games_used": int(len(train_df)),
                    }
                )

        # Include previous year's matches for round continuity (season 2025–May 2026: Dec R8 -> Jan R9)
        try:
            prev_year = str(int(selected_year) - 1) if selected_year else None
            if prev_year:
                cur.execute(
                    """
                    SELECT e.id, e.date_event, e.home_team_id, e.away_team_id, e.home_score, e.away_score
                    FROM event e
                    WHERE e.league_id = ?
                      AND e.home_team_id IS NOT NULL
                      AND e.away_team_id IS NOT NULL
                      AND e.date_event IS NOT NULL
                      AND e.home_score IS NOT NULL
                      AND e.away_score IS NOT NULL
                      AND date(e.date_event) <= date('now')
                      AND substr(e.date_event, 1, 4) = ?
                    ORDER BY date(e.date_event) ASC
                    """,
                    (league_id, prev_year),
                )
                for r in cur.fetchall() or []:
                    eid = int(r["id"])
                    dt_str = r["date_event"] or ""
                    dt = pd.to_datetime(dt_str) if dt_str else None
                    if dt is None:
                        continue
                    iso = dt.isocalendar()
                    yw = f"{int(iso.year)}-W{int(iso.week):02d}"
                    yr = str(iso.year)
                    matches_by_year_week[yr][yw].append({
                        "match_id": eid,
                        "date": dt_str[:10] if len(dt_str) >= 10 else dt_str,
                        "home_team": team_name.get(int(r["home_team_id"]), f"Team {r['home_team_id']}"),
                        "away_team": team_name.get(int(r["away_team_id"]), f"Team {r['away_team_id']}"),
                        "actual_home_score": int(r["home_score"]),
                        "actual_away_score": int(r["away_score"]),
                        "year": yr,
                        "year_week": yw,
                        "week": int(iso.week),
                    })
        except Exception as prev_err:
            logger.warning(f"Could not add prev year matches for round continuity: {prev_err}")

        conn.close()

        accuracy = (correct_predictions / total_predictions * 100.0) if total_predictions > 0 else 0.0
        avg_score_error = (sum(score_errors) / len(score_errors)) if score_errors else None

        payload = {
            "available_years": available_years,
            "selected_year": selected_year,
            "matches_by_year_week": {y: dict(w) for y, w in matches_by_year_week.items()},
            "statistics": {
                "total_matches": total_predictions,
                "total_predictions": total_predictions,
                "correct_predictions": correct_predictions,
                "accuracy_percentage": round(accuracy, 2),
                "average_score_error": round(avg_score_error, 2) if avg_score_error is not None else None,
                "draws_excluded": draws_excluded,
                "weeks_evaluated": weeks_evaluated,
                "weeks_skipped": weeks_skipped,
                "min_train_games": min_train_games,
                "evaluation_mode": "walk_forward_backtest",
            },
            "by_league": {
                league_id: {
                    "league_name": league_name,
                    "total_predictions": total_predictions,
                    "correct_predictions": correct_predictions,
                    "accuracy_percentage": round(accuracy, 2),
                }
            },
        }

        # Cache the result if possible
        try:
            if fs is not None and cache_ref is not None:
                try:
                    from firebase_admin import firestore as fb_firestore  # type: ignore
                    server_ts = fb_firestore.SERVER_TIMESTAMP
                except Exception:
                    server_ts = datetime.utcnow().isoformat()
                cache_ref.set(
                    {
                        "league_id": league_id,
                        "year": selected_year,
                        "mode": "walk_forward_backtest",
                        "data": payload,
                        "updated_at": server_ts,
                    },
                    merge=True,
                )
        except Exception as cache_write_err:
            logger.warning(f"Backtest cache write failed: {cache_write_err}")

        return https_fn.Response(json.dumps(payload), status=200, headers=headers)

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"Error in get_historical_backtest_http: {e}\n{err}")
        return https_fn.Response(
            json.dumps({"error": str(e), "traceback": err}),
            status=500,
            headers=headers,
        )


@https_fn.on_call(timeout_sec=60, memory=512)
def parse_social_embed(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Parse social media URL and return embed info
    
    Request data:
    {
        "url": "https://instagram.com/p/...",
        "context": "lineup",
        "related_data": {}
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        url = data.get('url')
        context = data.get('context')
        related_data = data.get('related_data', {})
        
        if not url:
            return {'error': 'URL is required', 'success': False}
        
        from prediction.social_media_service import SocialMediaService
        
        # Generate AI explanation
        ai_explanation = SocialMediaService.generate_ai_explanation(
            embed_type="social",
            context=context or "general",
            related_data=related_data
        )
        
        # Create embed object
        embed = SocialMediaService.create_embed_object(
            url=url,
            context=context,
            ai_explanation=ai_explanation
        )
        
        return {
            'success': True,
            'embed': embed
        }
    except Exception as e:
        logger.error(f"Error in parse_social_embed: {e}")
        return {
            'error': str(e),
            'success': False
        }