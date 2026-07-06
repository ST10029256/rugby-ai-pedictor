"""
Firebase Cloud Functions for Rugby AI Predictor
Handles callable functions for predictions, matches, and data
"""

from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
from collections import Counter
import hashlib
from html import unescape
import logging
import os
import json
import re
import requests
import secrets
import string
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, TYPE_CHECKING

# Import Firestore Timestamp for type checking
try:
    from google.cloud.firestore_v1 import Timestamp as FirestoreTimestamp  # type: ignore
except ImportError:
    FirestoreTimestamp = None


_TRANSLATABLE_NEWS_TYPES = {"social_media", "external_news"}
_TRANSLATION_CACHE: Dict[str, Dict[str, str]] = {}
_TRANSLATION_CLIENT = None
_TRANSLATION_CLIENT_READY = False
_EMOJI_JOINER_CHARS = {"\u200d", "\ufe0f", "\ufe0e", "\u20e3"}


def _get_translation_client():
    """Lazily create a Google Translate client when the dependency is available."""
    global _TRANSLATION_CLIENT, _TRANSLATION_CLIENT_READY
    if _TRANSLATION_CLIENT_READY:
        return _TRANSLATION_CLIENT

    _TRANSLATION_CLIENT_READY = True
    try:
        from google.cloud import translate_v2 as translate

        _TRANSLATION_CLIENT = translate.Client()
    except Exception as exc:
        logging.getLogger(__name__).warning("News translation unavailable: %s", exc)
        _TRANSLATION_CLIENT = None
    return _TRANSLATION_CLIENT


def _should_attempt_translation(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    alpha_chars = sum(1 for char in text if char.isalpha())
    return alpha_chars >= 3


def _is_emoji_char(char: str) -> bool:
    code = ord(char)
    return (
        0x1F1E6 <= code <= 0x1F1FF  # regional indicator flags
        or 0x1F300 <= code <= 0x1FAFF  # emoji / symbols / pictographs
        or 0x2600 <= code <= 0x27BF  # misc symbols + dingbats
        or 0x1F900 <= code <= 0x1F9FF  # supplemental symbols
        or 0x1FA70 <= code <= 0x1FAFF  # symbols and pictographs extended
        or 0x1F3FB <= code <= 0x1F3FF  # skin tone modifiers
    )


def _extract_emoji_sequences(text: str) -> list[str]:
    sequences: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        current = text[i]

        if "\U0001F1E6" <= current <= "\U0001F1FF":
            cluster = current
            if i + 1 < length and "\U0001F1E6" <= text[i + 1] <= "\U0001F1FF":
                cluster += text[i + 1]
                i += 1
            sequences.append(cluster)
            i += 1
            continue

        if not _is_emoji_char(current):
            i += 1
            continue

        cluster = current
        i += 1
        while i < length:
            nxt = text[i]
            if nxt in _EMOJI_JOINER_CHARS or _is_emoji_char(nxt):
                cluster += nxt
                i += 1
                continue
            break
        sequences.append(cluster)

    return sequences


def _restore_missing_emojis(original_text: str, translated_text: str) -> str:
    original_emojis = _extract_emoji_sequences(original_text)
    if not original_emojis:
        return translated_text

    translated_emojis = Counter(_extract_emoji_sequences(translated_text))
    missing_emojis: list[str] = []
    for emoji_seq in original_emojis:
        if translated_emojis[emoji_seq] > 0:
            translated_emojis[emoji_seq] -= 1
            continue
        missing_emojis.append(emoji_seq)

    if not missing_emojis:
        return translated_text

    suffix = "".join(missing_emojis)
    if not translated_text:
        return suffix
    if re.search(r"\s$", translated_text):
        return f"{translated_text}{suffix}"
    return f"{translated_text} {suffix}"


def _normalize_text_for_compare(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _translate_text_to_english(value: Any) -> str:
    """Translate arbitrary post text to English with a small process cache."""
    text = str(value or "").strip()
    if not _should_attempt_translation(text):
        return text

    cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cached = _TRANSLATION_CACHE.get(cache_key)
    if cached:
        return cached.get("text", text)

    client = _get_translation_client()
    if client is None:
        return text

    try:
        result = client.translate(text, target_language="en", format_="text")
        translated = unescape(str(result.get("translatedText") or text)).strip() or text
        translated = _restore_missing_emojis(text, translated)
        _TRANSLATION_CACHE[cache_key] = {"text": translated}
        return translated
    except Exception as exc:
        logging.getLogger(__name__).warning("News translation failed: %s", exc)
        return text


def _translate_news_items_to_english(news_items: Any) -> int:
    """
    Force third-party news items into English before the UI renders them.
    Returns the number of fields updated.
    """
    if not isinstance(news_items, list):
        return 0

    translated_fields = 0
    for item in news_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in _TRANSLATABLE_NEWS_TYPES:
            continue

        original_title = str(item.get("title") or "").strip()
        if original_title:
            translated_title = _translate_text_to_english(original_title)
            if translated_title != original_title:
                item["title"] = translated_title
                translated_fields += 1

        original_content = str(item.get("content") or "").strip()
        if original_content:
            translated_content = _translate_text_to_english(original_content)
            if translated_content != original_content:
                item["content"] = translated_content
                translated_fields += 1

    return translated_fields


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
            api_key = os.getenv('HIGHLIGHTLY_API_KEY', '').strip()
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


def _parse_match_id_from_request(data: Dict[str, Any]) -> Optional[int]:
    raw_match_id = data.get("event_id") or data.get("match_id") or data.get("id")
    try:
        if raw_match_id is not None and str(raw_match_id).strip() != "":
            return int(raw_match_id)
    except (TypeError, ValueError):
        pass
    return None


def _resolve_predicted_winner_for_save(
    prediction: Dict[str, Any],
    home_team: str,
    away_team: str,
) -> str:
    """Normalize winner for Firestore, using scores only when AI scores are available."""
    predicted_winner = prediction.get("winner") or prediction.get("predicted_winner")
    if predicted_winner == "Home":
        predicted_winner = home_team
    elif predicted_winner == "Away":
        predicted_winner = away_team

    home_score = prediction.get("predicted_home_score")
    away_score = prediction.get("predicted_away_score")
    show_scores = prediction.get("show_scores", True) and home_score is not None and away_score is not None
    if not show_scores:
        if predicted_winner in {home_team, away_team, "Draw"}:
            return str(predicted_winner)
        home_win_prob = float(prediction.get("home_win_prob") or prediction.get("bookmaker_home_win_prob") or 0.5)
        if home_win_prob > 0.5:
            return home_team
        if home_win_prob < 0.5:
            return away_team
        return "Draw"

    if home_score > away_score:
        score_based_winner = home_team
    elif away_score > home_score:
        score_based_winner = away_team
    else:
        score_based_winner = "Draw"

    if predicted_winner:
        if (predicted_winner == home_team and home_score <= away_score) or (
            predicted_winner == away_team and away_score <= home_score
        ) or (predicted_winner == "Draw" and home_score != away_score):
            return score_based_winner
        return str(predicted_winner)
    return score_based_winner


def _run_standard_prediction(
    predictor: Any,
    data: Dict[str, Any],
    league_id_int: int,
    home_team: str,
    away_team: str,
    match_date: str,
) -> Dict[str, Any]:
    """Use hybrid AI when a model exists; otherwise return bookmaker odds only."""
    import logging

    logger = logging.getLogger(__name__)
    odds_only = bool(data.get("odds_only", False))
    match_id = _parse_match_id_from_request(data)
    has_model = predictor.has_trained_model(league_id_int)

    if odds_only or not has_model:
        logger.info(
            "Bookmaker odds only for league %s (odds_only=%s, has_model=%s)",
            league_id_int,
            odds_only,
            has_model,
        )
        return predictor.predict_match_odds_only(
            str(home_team),
            str(away_team),
            league_id_int,
            str(match_date),
            match_id=match_id,
        )

    try:
        prediction = predictor.predict_match(
            str(home_team),
            str(away_team),
            league_id_int,
            str(match_date),
            match_id=match_id,
        )
        prediction.setdefault("model_available", True)
        prediction.setdefault("show_scores", True)
        return prediction
    except (FileNotFoundError, ValueError, RuntimeError, ImportError) as model_err:
        logger.warning(
            "Model prediction unavailable for league %s, falling back to odds only: %s",
            league_id_int,
            model_err,
        )
        return predictor.predict_match_odds_only(
            str(home_team),
            str(away_team),
            league_id_int,
            str(match_date),
            match_id=match_id,
        )


@https_fn.on_call(timeout_sec=300, memory=512, secrets=["HIGHLIGHTLY_API_KEY"])  # 5 minute timeout, 512MB memory
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
                prediction = _run_standard_prediction(
                    predictor,
                    data,
                    league_id_int,
                    str(home_team),
                    str(away_team),
                    str(match_date),
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
                    
                    predicted_winner = _resolve_predicted_winner_for_save(
                        prediction, str(home_team), str(away_team)
                    )
                    
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
                        'model_available': prediction.get('model_available', True),
                        'show_scores': prediction.get('show_scores', True),
                        'bookmaker_count': prediction.get('bookmaker_count', 0),
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


@https_fn.on_request(timeout_sec=120, memory=1024, secrets=["HIGHLIGHTLY_API_KEY"])
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
                prediction = _run_standard_prediction(
                    predictor,
                    data,
                    league_id_int,
                    str(home_team),
                    str(away_team),
                    str(match_date),
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
                    
                    predicted_winner = _resolve_predicted_winner_for_save(
                        prediction, str(home_team), str(away_team)
                    )
                    
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
                        'model_available': prediction.get('model_available', True),
                        'show_scores': prediction.get('show_scores', True),
                        'bookmaker_count': prediction.get('bookmaker_count', 0),
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


# Firestore collection + default TTL for the batched upcoming-predictions cache.
# Bookmaker odds barely move minute to minute pre-match, and inside the final
# ~20 minutes the scheduled capture job records the immutable snapshot, so a
# short TTL keeps the live home view fast without going stale.
_UPCOMING_PRED_CACHE_COLLECTION = "upcoming_prediction_cache_v1"
_UPCOMING_PRED_CACHE_TTL_SECONDS = 1800  # 30 minutes
_UPCOMING_PRED_BATCH_MAX = 40


def _batch_cache_key(event_id: Any, home_team: str, away_team: str, match_date: str) -> str:
    """Stable Firestore doc id for a fixture's cached prediction."""
    if event_id:
        return f"evt_{event_id}"
    raw = f"{home_team}|{away_team}|{match_date}".lower()
    return "k_" + re.sub(r"[^a-z0-9]+", "_", raw).strip("_")[:200]


def _load_pre_kickoff_snapshot(
    db_path: str, match_id: Any, model_version: str
) -> Optional[Dict[str, Any]]:
    """Return an immutable pre-kickoff snapshot for a fixture if one exists.

    Near kickoff the scheduled job records the exact prediction we should show,
    so the live view stays consistent with the forward-test history.
    """
    if not match_id or not os.path.exists(db_path):
        return None
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT predicted_winner, predicted_home_score, predicted_away_score,
                       confidence, home_win_prob, away_win_prob
                FROM prediction_snapshot
                WHERE match_id = ? AND model_version = ?
                  AND snapshot_type = 'pre_kickoff_live'
                LIMIT 1
                """,
                (int(match_id), model_version),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        winner, hs, as_, conf, hwp, awp = row
        return {
            "predicted_winner": winner,
            "predicted_home_score": hs,
            "predicted_away_score": as_,
            "confidence": conf,
            "home_win_prob": hwp,
            "away_win_prob": awp,
            "show_scores": hs is not None,
            "model_available": hs is not None,
            "prediction_type": "AI Snapshot (pre-kickoff)",
            "bookmaker_count": 0,
            "_source": "snapshot",
        }
    except Exception:
        return None


@https_fn.on_request(timeout_sec=300, memory=1024, secrets=["HIGHLIGHTLY_API_KEY"])
def predict_matches_batch_http(req: https_fn.Request) -> https_fn.Response:
    """Predict a whole round of fixtures in a single request.

    The live home view used to fire 2xN per-match Cloud Function calls per
    league round. This endpoint collapses that into one call: it serves cached
    predictions from Firestore (TTL) or an immutable pre-kickoff snapshot when
    available, and only computes the misses live - reusing the warm predictor
    plus the per-instance odds / team-history caches. Computed results are
    written back to the Firestore cache so other users and instances reuse them.

    Request JSON:
        {
          "league_id": 4446,
          "matches": [{"event_id": 1, "home_team": "...", "away_team": "...",
                        "match_date": "2026-06-22"}, ...],
          "model_version": "<optional>"
        }

    Response JSON:
        {"predictions": [<raw prediction dict + event_id/home_team/away_team/match_date>],
         "model_version": "...", "counts": {...}}
    """
    import logging

    logger = logging.getLogger(__name__)

    cors_headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
    if req.method == "OPTIONS":
        return https_fn.Response(
            "",
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Max-Age": "3600",
            },
        )

    try:
        data = req.get_json(silent=True) or {}
        league_id_raw = data.get("league_id")
        matches = data.get("matches") or []
        if not isinstance(matches, list) or not matches:
            return https_fn.Response(
                json.dumps({"error": "matches must be a non-empty list"}),
                status=400,
                headers=cors_headers,
            )
        try:
            league_id_int = int(league_id_raw)
            if league_id_int == 0:
                raise ValueError
        except (TypeError, ValueError):
            return https_fn.Response(
                json.dumps({"error": "Invalid league_id"}), status=400, headers=cors_headers
            )

        matches = matches[:_UPCOMING_PRED_BATCH_MAX]
        model_version = str(data.get("model_version") or _get_live_model_version())
        try:
            ttl_seconds = int(data.get("ttl_seconds", _UPCOMING_PRED_CACHE_TTL_SECONDS))
        except (TypeError, ValueError):
            ttl_seconds = _UPCOMING_PRED_CACHE_TTL_SECONDS
        ttl_seconds = max(60, min(ttl_seconds, 6 * 3600))
        force_refresh = bool(data.get("force_refresh", False))

        db_path = os.getenv("DB_PATH") or os.path.join(os.path.dirname(__file__), "data.sqlite")
        now_ms = int(time.time() * 1000)

        # Normalize the requested fixtures up front.
        normalized = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            home = str(m.get("home_team") or "").strip()
            away = str(m.get("away_team") or "").strip()
            match_date = str(m.get("match_date") or "").strip()
            event_id = m.get("event_id") or m.get("id")
            if not home or not away or not match_date:
                continue
            normalized.append(
                {
                    "event_id": event_id,
                    "home_team": home,
                    "away_team": away,
                    "match_date": match_date,
                    "cache_key": _batch_cache_key(event_id, home, away, match_date),
                }
            )

        if not normalized:
            return https_fn.Response(
                json.dumps({"error": "No valid matches provided"}), status=400, headers=cors_headers
            )

        # Firestore is optional - if it is unavailable we still compute live.
        db = None
        cache_col = None
        try:
            db = get_firestore_client()
            cache_col = db.collection(_UPCOMING_PRED_CACHE_COLLECTION)
        except Exception as fs_err:
            logger.warning(f"Batch predict: Firestore cache unavailable: {fs_err}")

        cached_by_key: Dict[str, Dict[str, Any]] = {}
        if cache_col is not None and not force_refresh:
            try:
                refs = [cache_col.document(item["cache_key"]) for item in normalized]
                for snap in db.get_all(refs):
                    if not snap.exists:
                        continue
                    doc = snap.to_dict() or {}
                    if doc.get("model_version") != model_version:
                        continue
                    cached_ms = doc.get("cached_at_ms") or 0
                    if now_ms - int(cached_ms) > ttl_seconds * 1000:
                        continue
                    pred = doc.get("prediction")
                    if isinstance(pred, dict):
                        cached_by_key[snap.id] = pred
            except Exception as read_err:
                logger.warning(f"Batch predict: cache read failed: {read_err}")

        predictor = None
        results: List[Dict[str, Any]] = []
        counts = {"cache": 0, "snapshot": 0, "computed": 0, "failed": 0}

        for item in normalized:
            key = item["cache_key"]
            home, away = item["home_team"], item["away_team"]
            match_date, event_id = item["match_date"], item["event_id"]

            pred: Optional[Dict[str, Any]] = None
            source = "computed"

            cached = cached_by_key.get(key)
            if cached is not None:
                pred = cached
                source = "cache"
                counts["cache"] += 1

            if pred is None:
                snap_pred = _load_pre_kickoff_snapshot(db_path, event_id, model_version)
                if snap_pred is not None:
                    pred = snap_pred
                    source = "snapshot"
                    counts["snapshot"] += 1

            if pred is None:
                try:
                    if predictor is None:
                        predictor = get_predictor()
                    pred = _run_standard_prediction(
                        predictor,
                        {"event_id": event_id, "match_id": event_id},
                        league_id_int,
                        home,
                        away,
                        match_date,
                    )
                    pred.setdefault("model_type", LIVE_MODEL_FAMILY)
                    pred.setdefault("model_family", LIVE_MODEL_FAMILY)
                    pred.setdefault("model_channel", LIVE_MODEL_CHANNEL)
                    counts["computed"] += 1
                    # Write back to the shared cache (best effort).
                    if cache_col is not None:
                        try:
                            cache_col.document(key).set(
                                {
                                    "event_id": event_id,
                                    "league_id": league_id_int,
                                    "model_version": model_version,
                                    "home_team": home,
                                    "away_team": away,
                                    "match_date": match_date,
                                    "prediction": pred,
                                    "cached_at": firestore.SERVER_TIMESTAMP,
                                    "cached_at_ms": now_ms,
                                }
                            )
                        except Exception as write_err:
                            logger.debug(f"Batch predict: cache write failed for {key}: {write_err}")
                except Exception as compute_err:
                    counts["failed"] += 1
                    logger.warning(
                        f"Batch predict failed for {home} vs {away}: {compute_err}"
                    )
                    pred = {"error": str(compute_err)}

            enriched = dict(pred)
            enriched["event_id"] = event_id
            enriched["home_team"] = home
            enriched["away_team"] = away
            enriched["match_date"] = match_date
            enriched.setdefault("_source", source)
            results.append(enriched)

        return https_fn.Response(
            json.dumps(
                {
                    "predictions": results,
                    "model_version": model_version,
                    "counts": counts,
                }
            ),
            status=200,
            headers=cors_headers,
        )
    except Exception as e:
        import traceback

        logger.error(f"predict_matches_batch_http error: {e}")
        return https_fn.Response(
            json.dumps({"error": str(e), "traceback": traceback.format_exc()}),
            status=500,
            headers=cors_headers,
        )


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
            
            logger.info(f"Querying matches collection for league_id={league_id}")
            from datetime import timezone, time
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
            today_start_local = datetime.combine(today_local, time.min).replace(tzinfo=local_tz)
            today_start_utc = today_start_local.astimezone(timezone.utc)

            fetch_limit = max(int(limit) * 4, 200)
            base_ref = db.collection('matches')
            if league_id:
                base_ref = base_ref.where('league_id', '==', int(league_id))
                logger.info(f"Applied league_id filter: {int(league_id)}")

            # Query upcoming fixtures directly instead of scanning the first N docs
            # (leagues with 1000+ historical matches never reached future fixtures).
            used_fallback_scan = False
            try:
                matches_ref = (
                    base_ref
                    .where('date_event', '>=', today_start_utc)
                    .order_by('date_event')
                    .limit(fetch_limit)
                )
                logger.info(
                    "Using indexed upcoming query: date_event >= %s (limit=%s)",
                    today_start_utc.isoformat(),
                    fetch_limit,
                )
            except Exception as query_error:
                used_fallback_scan = True
                logger.warning(
                    "Indexed upcoming query failed (%s); falling back to recent scan",
                    query_error,
                )
                matches_ref = base_ref.limit(1000)
            
            logger.info("Starting to stream matches from Firestore...")
            
            matches = []
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

            try:
                from prediction.kickoff_times import enrich_matches_kickoff

                enrich_matches_kickoff(matches)
            except Exception as kickoff_err:
                logger.warning(f"Kickoff enrichment failed (continuing): {kickoff_err}")
            
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
                'sample_dates': sample_dates[:3],  # First 3 samples
                'query_mode': 'fallback_scan' if used_fallback_scan else 'indexed_upcoming',
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


@https_fn.on_call(secrets=["HIGHLIGHTLY_API_KEY"])
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


@https_fn.on_request(secrets=["HIGHLIGHTLY_API_KEY"])
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
        
        # NOTE: a "last 10 games" recompute used to run here, but its result was
        # never returned to the client while it forced a model load + ~10
        # Firestore reads on every metrics view (a needless cold-start trigger).
        # The displayed accuracy comes from the walk-forward backtest stored in
        # league_metrics below, so that dead computation has been removed.
        
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


def _find_subscription_by_license_key(subscriptions_ref, license_key: str, license_key_normalized: str):
    """Look up a subscription document by license key (multiple stored formats)."""
    query = subscriptions_ref.where('license_key', '==', license_key).limit(1)
    docs = list(query.stream())
    if not docs and len(license_key_normalized) == 16:
        formatted_key = (
            f"{license_key_normalized[0:4]}-{license_key_normalized[4:8]}-"
            f"{license_key_normalized[8:12]}-{license_key_normalized[12:16]}"
        )
        query = subscriptions_ref.where('license_key', '==', formatted_key).limit(1)
        docs = list(query.stream())
    if not docs:
        query = subscriptions_ref.where('license_key', '==', license_key_normalized).limit(1)
        docs = list(query.stream())
    return docs


def _expires_datetime(expires_at):
    if not expires_at:
        return None
    if hasattr(expires_at, 'timestamp'):
        return datetime.utcfromtimestamp(expires_at.timestamp())
    if isinstance(expires_at, datetime):
        return expires_at
    return None


DEVICE_BINDING_DISCLAIMER = (
    'Your license is bound to your registered browser/device profile. '
    'If your device changes, browser changes, or system settings change significantly, '
    're-approval may be required.'
)

ERROR_DEVICE_PROFILE_REGISTERED = (
    'This license is already registered to another browser/device profile. '
    'If you changed browser, reset your device, or cleared your app data, '
    'request approval to rebind this license.'
)

ERROR_DEVICE_REBIND_PENDING = (
    'Your device profile changed and a re-registration request is pending. '
    f'{DEVICE_BINDING_DISCLAIMER} '
    'Contact support with your license key to approve access on this profile.'
)

_DEVICE_PROFILE_FIELDS = (
    'os_family', 'browser_family', 'platform_class', 'platform', 'screen_class',
    'timezone', 'language', 'hardware_concurrency_bucket', 'device_memory_bucket',
    'touch_support',
)

_DEVICE_PROFILE_WEIGHTS = {
    'os_family': 22.0,
    'browser_family': 18.0,
    'platform_class': 12.0,
    'platform': 8.0,
    'screen_class': 14.0,
    'timezone': 10.0,
    'language': 6.0,
    'hardware_concurrency_bucket': 6.0,
    'device_memory_bucket': 4.0,
}

_REBIND_TRUST_FIELDS = (
    'os_family', 'browser_family', 'platform_class', 'platform', 'screen_class',
)

_FINGERPRINT_REBIND_THRESHOLD = 88.0
_FINGERPRINT_REBIND_THRESHOLD_MOBILE = 95.0
_FINGERPRINT_PENDING_THRESHOLD = 45.0

_PENDING_FIELD_CLEAR = (
    'pending_device_id', 'pending_device_fingerprint', 'pending_device_fingerprint_profile',
    'pending_device_label', 'device_rebind_requested_at', 'pending_device_score',
    'pending_device_reason', 'pending_device_ip_hash', 'pending_device_user_agent',
    'pending_device_browser', 'pending_device_os', 'pending_device_last_seen_at',
)


def _hash_client_ip(ip: str) -> str:
    ip = (ip or '').strip()
    if not ip:
        return ''
    return hashlib.sha256(f'rugby-ai-ip::{ip}'.encode()).hexdigest()[:32]


def _extract_request_context_callable(req) -> Dict[str, str]:
    ip = ''
    ua = ''
    try:
        raw = getattr(req, 'raw_request', None)
        if raw is not None:
            headers = getattr(raw, 'headers', {}) or {}
            ip = str(headers.get('X-Forwarded-For', '') or '').split(',')[0].strip()
            if not ip:
                ip = str(getattr(raw, 'remote_addr', '') or '')
            ua = str(headers.get('User-Agent', '') or '')[:512]
    except Exception:
        pass
    return {'ip_hash': _hash_client_ip(ip), 'user_agent': ua}


def _extract_request_context_http(req: https_fn.Request) -> Dict[str, str]:
    ip = str(req.headers.get('X-Forwarded-For', '') or '').split(',')[0].strip()
    if not ip:
        ip = str(getattr(req, 'remote_addr', '') or '')
    ua = str(req.headers.get('User-Agent', '') or '')[:512]
    return {'ip_hash': _hash_client_ip(ip), 'user_agent': ua}


def _derive_screen_class(profile: dict) -> str:
    existing = (profile.get('screen_class') or '').strip().lower()
    if existing:
        return existing
    try:
        w = int(profile.get('screen_width') or 0)
        h = int(profile.get('screen_height') or 0)
    except (TypeError, ValueError):
        w, h = 0, 0
    max_dim = max(w, h)
    if max_dim <= 0:
        return 'unknown'
    if max_dim <= 768:
        return 'small'
    if max_dim <= 1024:
        return 'medium'
    if max_dim <= 1440:
        return 'large'
    if max_dim <= 1920:
        return 'xl'
    return 'xxl'


def _derive_platform_class(profile: dict) -> str:
    existing = (profile.get('platform_class') or '').strip().lower()
    if existing:
        return existing
    os_family = (profile.get('os_family') or '').lower()
    if os_family in ('ios', 'android'):
        return 'mobile'
    return 'desktop'


def _bucket_hardware_concurrency(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 'unknown'
    if n <= 0:
        return 'unknown'
    if n <= 2:
        return '1-2'
    if n <= 4:
        return '3-4'
    if n <= 8:
        return '5-8'
    return '9+'


def _bucket_device_memory(value) -> str:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 'unknown'
    if n <= 0:
        return 'unknown'
    if n <= 2:
        return '1-2'
    if n <= 4:
        return '3-4'
    if n <= 8:
        return '5-8'
    return '9+'


def _profile_from_user_agent(ua: str) -> Dict[str, str]:
    """Best-effort profile when the client profile payload is missing."""
    ua = (ua or '').strip()
    ua_lower = ua.lower()
    if 'iphone' in ua_lower or 'ipad' in ua_lower:
        os_family = 'ios'
    elif 'android' in ua_lower:
        os_family = 'android'
    elif 'win' in ua_lower:
        os_family = 'windows'
    elif 'mac' in ua_lower:
        os_family = 'macos'
    elif 'linux' in ua_lower:
        os_family = 'linux'
    else:
        os_family = ''

    if 'edg/' in ua_lower:
        browser_family = 'edge'
    elif 'chrome' in ua_lower and 'edg' not in ua_lower:
        browser_family = 'chrome'
    elif 'firefox' in ua_lower:
        browser_family = 'firefox'
    elif 'safari' in ua_lower and 'chrome' not in ua_lower:
        browser_family = 'safari'
    else:
        browser_family = ''

    if 'iphone' in ua_lower or ('android' in ua_lower and 'mobile' in ua_lower):
        platform_class = 'mobile'
    elif 'ipad' in ua_lower or 'tablet' in ua_lower:
        platform_class = 'tablet'
    elif 'android' in ua_lower:
        platform_class = 'tablet'
    else:
        platform_class = 'desktop'

    platform = 'Win32' if os_family == 'windows' else ('MacIntel' if os_family == 'macos' else '')
    return _normalize_fingerprint_profile({
        'os_family': os_family,
        'browser_family': browser_family,
        'platform_class': platform_class,
        'platform': platform,
    })


def _profile_has_core_identity(profile: dict) -> bool:
    return bool(
        (profile.get('os_family') or '').strip()
        and (profile.get('browser_family') or '').strip()
    )


def _resolve_device_profile(
    raw_profile,
    raw_profile_json: str,
    user_agent: str,
) -> Dict[str, str]:
    """Resolve profile from dict, JSON string backup, or User-Agent fallback."""
    if isinstance(raw_profile, dict) and _profile_has_core_identity(
        _normalize_fingerprint_profile(raw_profile)
    ):
        return _normalize_fingerprint_profile(raw_profile)

    if raw_profile_json:
        try:
            parsed = json.loads(raw_profile_json) if isinstance(raw_profile_json, str) else raw_profile_json
            if isinstance(parsed, dict):
                normalized = _normalize_fingerprint_profile(parsed)
                if _profile_has_core_identity(normalized):
                    return normalized
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    if user_agent:
        ua_profile = _profile_from_user_agent(user_agent)
        if _profile_has_core_identity(ua_profile):
            return ua_profile

    return _normalize_fingerprint_profile(raw_profile if isinstance(raw_profile, dict) else {})


def _compute_fingerprint_from_profile(profile: dict) -> str:
    """Mirror client SHA-256 fingerprint from normalized high-trust profile fields."""
    p = _normalize_fingerprint_profile(profile)
    parts = '|||'.join([
        p.get('os_family', ''),
        p.get('browser_family', ''),
        p.get('platform_class', ''),
        p.get('platform', ''),
        p.get('screen_class', ''),
        p.get('timezone', ''),
        p.get('language', ''),
        p.get('hardware_concurrency_bucket', ''),
        p.get('device_memory_bucket', ''),
    ])
    return hashlib.sha256(parts.encode('utf-8')).hexdigest()


def _normalize_fingerprint_profile(raw) -> Dict[str, str]:
    """Sanitize client fingerprint traits for storage and comparison."""
    if not isinstance(raw, dict):
        raw = {}
    normalized: Dict[str, str] = {}
    for field in _DEVICE_PROFILE_FIELDS:
        value = raw.get(field, '')
        normalized[field] = str(value or '').strip()[:128]

    if not normalized.get('screen_class'):
        normalized['screen_class'] = _derive_screen_class(raw)
    if not normalized.get('platform_class'):
        normalized['platform_class'] = _derive_platform_class(normalized)
    if not normalized.get('hardware_concurrency_bucket'):
        normalized['hardware_concurrency_bucket'] = _bucket_hardware_concurrency(
            raw.get('hardware_concurrency')
        )
    if not normalized.get('device_memory_bucket'):
        normalized['device_memory_bucket'] = _bucket_device_memory(
            raw.get('device_memory')
        )
    if not normalized.get('language') and raw.get('language'):
        normalized['language'] = str(raw.get('language')).split('-')[0].lower()[:16]
    return normalized


def _fingerprint_similarity(bound_profile: dict, current_profile: dict) -> float:
    """Return 0–100 similarity score between two device fingerprint profiles."""
    if not bound_profile or not current_profile:
        return 0.0
    score = 0.0
    for field, weight in _DEVICE_PROFILE_WEIGHTS.items():
        bound_val = (bound_profile.get(field) or '').strip().lower()
        current_val = (current_profile.get(field) or '').strip().lower()
        if bound_val and current_val and bound_val == current_val:
            score += weight
    return round(score, 1)


def _high_trust_fields_match(bound_profile: dict, current_profile: dict) -> tuple:
    """All critical identity fields must agree for controlled auto-rebind."""
    mismatches = []
    for field in _REBIND_TRUST_FIELDS:
        bound_val = (bound_profile.get(field) or '').strip().lower()
        current_val = (current_profile.get(field) or '').strip().lower()
        if not bound_val or not current_val or bound_val != current_val:
            mismatches.append(field)
    return (len(mismatches) == 0, mismatches)


def _storage_clear_trust_match(bound_profile: dict, current_profile: dict) -> bool:
    """
    Cache-clear rebind: core browser/device identity must match.
    screen_class may be unknown on UA-only fallback; soft fields may drift.
    """
    required = ('os_family', 'browser_family', 'platform_class', 'platform')
    for field in required:
        bound_val = (bound_profile.get(field) or '').strip().lower()
        current_val = (current_profile.get(field) or '').strip().lower()
        if not bound_val or not current_val or bound_val != current_val:
            return False
    bound_sc = (bound_profile.get('screen_class') or '').strip().lower()
    current_sc = (current_profile.get('screen_class') or '').strip().lower()
    if current_sc and current_sc not in ('', 'unknown') and bound_sc != current_sc:
        return False
    return True


def _rebind_similarity_threshold(current_profile: dict) -> float:
    platform_class = (current_profile.get('platform_class') or '').lower()
    if platform_class in ('mobile', 'tablet'):
        return _FINGERPRINT_REBIND_THRESHOLD_MOBILE
    return _FINGERPRINT_REBIND_THRESHOLD


def _controlled_rebind_eligible(
    bound_profile: dict,
    current_profile: dict,
    similarity: float,
) -> tuple:
    """Auto-rebind only when score is high AND high-trust fields all match."""
    if not bound_profile or not current_profile:
        return False, 'missing_profile'
    trust_ok, mismatches = _high_trust_fields_match(bound_profile, current_profile)
    if not trust_ok:
        return False, f"trust_mismatch:{','.join(mismatches)}"
    threshold = _rebind_similarity_threshold(current_profile)
    if similarity < threshold:
        return False, f'similarity_below_{threshold}'
    return True, 'high_trust_match'


def _clear_pending_fields(update_fields: Dict[str, Any]) -> None:
    for field in _PENDING_FIELD_CLEAR:
        update_fields[field] = firestore.DELETE_FIELD


def _classify_device_binding(
    bound_device_id: str,
    device_id: str,
    bound_fingerprint: str,
    device_fingerprint: str,
    bound_profile: dict,
    current_profile: dict,
    has_stored_bound_profile: bool,
    legacy_rebind_used: bool,
) -> tuple:
    """
    Classify login attempt.
    Returns (decision, reason, similarity).
    decision: allow | rebind | legacy_rebind | pending | block
    """
    similarity = _fingerprint_similarity(bound_profile, current_profile) if (
        bound_profile and current_profile
    ) else 0.0

    if bound_device_id and bound_device_id == device_id:
        return ('allow', 'device_id_match', similarity)

    server_fp = ''
    if _profile_has_core_identity(current_profile):
        server_fp = _compute_fingerprint_from_profile(current_profile)

    if bound_fingerprint and (
        (device_fingerprint and bound_fingerprint == device_fingerprint)
        or (server_fp and bound_fingerprint == server_fp)
    ):
        return ('rebind', 'exact_fingerprint', similarity)

    # Cache cleared: new device_id but same browser/device profile.
    if (
        bound_device_id
        and bound_device_id != device_id
        and _storage_clear_trust_match(bound_profile, current_profile)
        and _profile_has_core_identity(bound_profile)
        and _profile_has_core_identity(current_profile)
    ):
        return ('rebind', 'storage_clear_trust_match', similarity)

    trust_ok, mismatches = _high_trust_fields_match(bound_profile, current_profile)
    if (
        bound_device_id
        and bound_device_id != device_id
        and trust_ok
        and _profile_has_core_identity(bound_profile)
        and _profile_has_core_identity(current_profile)
    ):
        return ('rebind', 'storage_clear_full_trust_match', similarity)

    if not legacy_rebind_used:
        if bound_device_id and bound_fingerprint and not has_stored_bound_profile:
            return ('legacy_rebind', 'missing_stored_profile', similarity)
        if bound_device_id and not bound_fingerprint and device_fingerprint:
            return ('legacy_rebind', 'missing_stored_fingerprint', similarity)

    if bound_profile and current_profile:
        eligible, reason = _controlled_rebind_eligible(
            bound_profile, current_profile, similarity,
        )
        if eligible:
            return ('rebind', reason, similarity)
        if similarity >= _FINGERPRINT_PENDING_THRESHOLD:
            return ('pending', reason or 'profile_changed', similarity)
        return ('block', 'low_similarity', similarity)

    return ('block', 'no_profile', similarity)


def _verify_subscription_record(
    subscription: dict,
    subscription_id: str,
    subscriptions_ref,
    device_id: str,
    device_label: str,
    device_fingerprint: str,
    device_fingerprint_profile: dict,
    device_fingerprint_profile_json: str,
    request_context: dict,
    logger,
) -> Dict[str, Any]:
    """Validate subscription expiry/usage and enforce browser/device profile binding."""
    now = datetime.utcnow()
    expires_at = subscription.get('expires_at')
    expires_datetime = _expires_datetime(expires_at)

    if expires_datetime and expires_datetime < now:
        logger.warning(f"Expired license key for subscription {subscription_id}")
        return {'valid': False, 'error': 'License key has expired'}

    if subscription.get('used', False) and not subscription.get('reusable', True):
        logger.warning(f"Already used license key for subscription {subscription_id}")
        return {'valid': False, 'error': 'License key has already been used'}

    device_id = (device_id or '').strip()
    device_fingerprint = (device_fingerprint or '').strip()
    request_context = request_context or {}
    current_profile = _resolve_device_profile(
        device_fingerprint_profile,
        device_fingerprint_profile_json,
        request_context.get('user_agent', ''),
    )
    if not device_id or len(device_id) < 8:
        return {
            'valid': False,
            'error': 'Device identification required. Refresh the page and try again.',
        }
    if not device_fingerprint or len(device_fingerprint) < 16:
        return {
            'valid': False,
            'error': 'Device verification failed. Refresh the page and try again.',
        }

    bound_device_id = (subscription.get('bound_device_id') or '').strip()
    bound_fingerprint = (subscription.get('bound_device_fingerprint') or '').strip()
    bound_profile = _normalize_fingerprint_profile(
        subscription.get('bound_device_fingerprint_profile') or {}
    )
    has_stored_bound_profile = bool(subscription.get('bound_device_fingerprint_profile'))
    legacy_rebind_used = bool(subscription.get('legacy_rebind_used', False))
    request_context = request_context or {}
    update_fields: Dict[str, Any] = {
        'last_used': firestore.SERVER_TIMESTAMP,
        'last_device_seen_at': firestore.SERVER_TIMESTAMP,
    }
    device_newly_bound = False
    device_rebound = False

    # Admin approved a pending transfer — confirm pending device + fingerprint match.
    pending_device_id = (subscription.get('pending_device_id') or '').strip()
    pending_fingerprint = (subscription.get('pending_device_fingerprint') or '').strip()
    if subscription.get('device_transfer_approved') and pending_device_id == device_id:
        if pending_fingerprint and pending_fingerprint != device_fingerprint:
            logger.warning(
                f"Approved rebind fingerprint mismatch for subscription {subscription_id}"
            )
            return {
                'valid': False,
                'device_rebind_pending': True,
                'error': ERROR_DEVICE_REBIND_PENDING,
            }
        update_fields['bound_device_id'] = device_id
        update_fields['bound_device_fingerprint'] = device_fingerprint
        update_fields['bound_device_fingerprint_profile'] = current_profile
        if device_label:
            update_fields['device_label'] = str(device_label)[:200]
        update_fields['device_bound_at'] = firestore.SERVER_TIMESTAMP
        update_fields['device_rebind_pending'] = False
        update_fields['device_transfer_approved'] = False
        _clear_pending_fields(update_fields)
        device_rebound = True
        logger.info(
            f"Admin-approved device rebind completed for subscription {subscription_id}"
        )
    elif bound_device_id:
        decision, reason, similarity = _classify_device_binding(
            bound_device_id, device_id, bound_fingerprint, device_fingerprint,
            bound_profile, current_profile, has_stored_bound_profile, legacy_rebind_used,
        )
        logger.info(
            f"Device binding decision for {subscription_id}: {decision} "
            f"(similarity={similarity}, reason={reason}, "
            f"has_core={_profile_has_core_identity(current_profile)})"
        )

        if decision == 'allow':
            if device_fingerprint and device_fingerprint != bound_fingerprint:
                update_fields['bound_device_fingerprint'] = device_fingerprint
            if current_profile and current_profile != bound_profile:
                update_fields['bound_device_fingerprint_profile'] = current_profile
        elif decision in ('rebind', 'legacy_rebind'):
            update_fields['bound_device_id'] = device_id
            update_fields['bound_device_fingerprint'] = device_fingerprint
            update_fields['bound_device_fingerprint_profile'] = current_profile
            update_fields['device_rebind_pending'] = False
            update_fields['device_transfer_approved'] = False
            _clear_pending_fields(update_fields)
            if device_label:
                update_fields['device_label'] = str(device_label)[:200]
            device_rebound = True
            if decision == 'legacy_rebind':
                update_fields['legacy_rebind_used'] = True
                update_fields['legacy_rebind_at'] = firestore.SERVER_TIMESTAMP
                update_fields['legacy_rebind_reason'] = str(reason)[:200]
                logger.info(
                    f"Legacy one-time rebind for subscription {subscription_id} "
                    f"(reason={reason})"
                )
            else:
                logger.info(
                    f"Controlled rebind for subscription {subscription_id} "
                    f"(similarity={similarity}, reason={reason})"
                )
        elif decision == 'pending':
            attempt_count = int(subscription.get('device_rebind_attempt_count') or 0) + 1
            update_fields['device_rebind_pending'] = True
            update_fields['pending_device_id'] = device_id
            update_fields['pending_device_fingerprint'] = device_fingerprint
            update_fields['pending_device_fingerprint_profile'] = current_profile
            update_fields['device_rebind_requested_at'] = firestore.SERVER_TIMESTAMP
            update_fields['pending_device_last_seen_at'] = firestore.SERVER_TIMESTAMP
            update_fields['pending_device_score'] = similarity
            update_fields['pending_device_reason'] = str(reason)[:200]
            update_fields['device_rebind_attempt_count'] = attempt_count
            if request_context.get('ip_hash'):
                update_fields['pending_device_ip_hash'] = request_context['ip_hash']
            if request_context.get('user_agent'):
                update_fields['pending_device_user_agent'] = request_context['user_agent']
            update_fields['pending_device_browser'] = current_profile.get('browser_family', '')
            update_fields['pending_device_os'] = current_profile.get('os_family', '')
            if device_label:
                update_fields['pending_device_label'] = str(device_label)[:200]
            logger.warning(
                f"Device profile change pending approval for subscription {subscription_id} "
                f"(similarity={similarity}, reason={reason}, attempt={attempt_count})"
            )
            subscriptions_ref.document(subscription_id).update(update_fields)
            return {
                'valid': False,
                'device_rebind_pending': True,
                'error': ERROR_DEVICE_REBIND_PENDING,
            }
        else:
            logger.warning(
                f"Device profile blocked for subscription {subscription_id}: "
                f"bound={bound_device_id[:8]}... attempted={device_id[:8]}... "
                f"(similarity={similarity}, reason={reason})"
            )
            return {
                'valid': False,
                'error': ERROR_DEVICE_PROFILE_REGISTERED,
                'device_mismatch': True,
            }
    else:
        update_fields['bound_device_id'] = device_id
        update_fields['bound_device_fingerprint'] = device_fingerprint
        update_fields['bound_device_fingerprint_profile'] = current_profile
        update_fields['device_bound_at'] = firestore.SERVER_TIMESTAMP
        if device_label:
            update_fields['device_label'] = str(device_label)[:200]
        device_newly_bound = True
        logger.info(f"Bound subscription {subscription_id} to device {device_id[:8]}...")

    if not subscription.get('reusable', True) and not subscription.get('used', False):
        update_fields['used'] = True
        update_fields['used_at'] = firestore.SERVER_TIMESTAMP

    subscriptions_ref.document(subscription_id).update(update_fields)

    expires_ts = expires_at.timestamp() if hasattr(expires_at, 'timestamp') else None
    return {
        'valid': True,
        'expires_at': expires_ts,
        'subscription_type': subscription.get('subscription_type', 'premium'),
        'email': subscription.get('email', ''),
        'device_bound': True,
        'device_newly_bound': device_newly_bound,
        'device_rebound': device_rebound,
    }


@https_fn.on_call()
def verify_license_key(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Verify a license key and return authentication status.
    
    Request: {
        'license_key': 'XXXX-XXXX-XXXX-XXXX',
        'device_id': 'uuid-for-this-browser',
        'device_label': 'iPhone | Windows | ...' (optional)
    }
    Response: { 'valid': bool, 'expires_at': timestamp, 'subscription_type': str, ... }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = get_firestore_client()
        license_key = req.data.get('license_key', '').strip().upper()
        device_id = req.data.get('device_id', '')
        device_label = req.data.get('device_label', '')
        device_fingerprint = req.data.get('device_fingerprint', '')
        device_fingerprint_profile = req.data.get('device_fingerprint_profile', {})
        device_fingerprint_profile_json = req.data.get('device_fingerprint_profile_json', '')
        
        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        logger.info(f"Verifying license key: {license_key[:8]}... device={str(device_id)[:8]}...")
        
        if not license_key_normalized:
            return {'valid': False, 'error': 'License key is required'}
        
        subscriptions_ref = db.collection('subscriptions')
        docs = _find_subscription_by_license_key(subscriptions_ref, license_key, license_key_normalized)
        
        logger.info(f"Found {len(docs)} documents matching license key")
        
        if not docs:
            logger.warning(f"Invalid license key attempted: {license_key[:8]}...")
            return {'valid': False, 'error': 'Invalid license key'}
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        req_ctx = _extract_request_context_callable(req)
        result = _verify_subscription_record(
            subscription, subscription_id, subscriptions_ref,
            device_id, device_label, device_fingerprint, device_fingerprint_profile,
            device_fingerprint_profile_json, req_ctx, logger,
        )
        if result.get('valid'):
            logger.info(f"Valid license key verified: {license_key[:8]}...")
        return result
        
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
        device_id = data.get('device_id', '')
        device_label = data.get('device_label', '')
        device_fingerprint = data.get('device_fingerprint', '')
        device_fingerprint_profile = data.get('device_fingerprint_profile', {})
        device_fingerprint_profile_json = data.get('device_fingerprint_profile_json', '')

        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        if not license_key_normalized:
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'License key is required'}),
                status=400,
                headers=headers
            )
        
        db = get_firestore_client()
        subscriptions_ref = db.collection('subscriptions')
        docs = _find_subscription_by_license_key(subscriptions_ref, license_key, license_key_normalized)
        
        if not docs:
            logger.warning(f"Invalid license key attempted: {license_key[:8]}...")
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'Invalid license key'}),
                status=200,
                headers=headers
            )
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        req_ctx = _extract_request_context_http(req)
        result = _verify_subscription_record(
            subscription, subscription_id, subscriptions_ref,
            device_id, device_label, device_fingerprint, device_fingerprint_profile,
            device_fingerprint_profile_json, req_ctx, logger,
        )
        
        if result.get('valid'):
            logger.info(f"Valid license key verified: {license_key[:8]}...")
        
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        return https_fn.Response(
            json.dumps(result),
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


LOGIN_CODE_TTL_SECONDS = 600
LOGIN_CODE_RATE_LIMIT_SECONDS = 60
LOGIN_CODE_MAX_ATTEMPTS = 5


def _find_subscription_by_email(subscriptions_ref, email: str):
    """Return the best active subscription doc for an email address."""
    email = (email or '').strip().lower()
    if not email:
        return None, None
    docs = list(subscriptions_ref.where('email', '==', email).limit(10).stream())
    if not docs:
        return None, None

    now = datetime.utcnow()
    candidates = []
    for doc in docs:
        sub = doc.to_dict() or {}
        if sub.get('active') is False:
            continue
        if sub.get('payment_completed') is False:
            continue
        expires_dt = _expires_datetime(sub.get('expires_at'))
        if expires_dt and expires_dt < now:
            continue
        if not sub.get('license_key'):
            continue
        candidates.append((doc, sub))

    if not candidates:
        return None, None

    def _sort_key(item):
        sub = item[1]
        for field in ('payment_date', 'created_at', 'last_used'):
            val = sub.get(field)
            if hasattr(val, 'timestamp'):
                return val.timestamp()
            if isinstance(val, datetime):
                return val.timestamp()
        return 0.0

    candidates.sort(key=_sort_key, reverse=True)
    doc, sub = candidates[0]
    return doc.id, sub


def _hash_login_code(email: str, subscription_id: str, code: str) -> str:
    normalized = f'rugby-login::{email.strip().lower()}::{subscription_id}::{code.strip()}'
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _generate_login_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def send_login_code_email(email: str, code: str) -> bool:
    """Email a one-time login code. Returns True if sent."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        if not gmail_user or not gmail_password:
            logger.warning('Gmail credentials missing — cannot send login code')
            return False

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Your Rugby AI Predictor sign-in code'
        msg['From'] = f'Rugby AI Predictor <{gmail_user}>'
        msg['To'] = email
        msg['Reply-To'] = gmail_user

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;line-height:1.6;color:#333;">
          <div style="max-width:520px;margin:0 auto;padding:20px;">
            <h2 style="color:#22c55e;">Sign in to Rugby AI Predictor</h2>
            <p>Use this one-time code to sign in. It expires in 10 minutes.</p>
            <div style="background:#f8fafc;border:2px solid #22c55e;border-radius:8px;padding:20px;margin:20px 0;text-align:center;">
              <p style="margin:0;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">Login code</p>
              <p style="margin:10px 0;font-size:32px;font-weight:700;color:#22c55e;letter-spacing:8px;font-family:monospace;">{code}</p>
            </div>
            <p style="color:#64748b;font-size:14px;">If you did not request this, you can ignore this email.</p>
          </div>
        </body></html>
        """
        text_body = (
            f'Sign in to Rugby AI Predictor\n\n'
            f'Your one-time login code: {code}\n\n'
            f'This code expires in 10 minutes.\n'
        )
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        logger.error(f'Failed to send login code email: {exc}')
        return False


def _request_email_login_code(email: str, logger) -> Dict[str, Any]:
    """Generate and email a login code for an active subscription."""
    email = (email or '').strip().lower()
    if not email or '@' not in email:
        return {'success': True, 'message': 'If an account exists for this email, a sign-in code was sent.'}

    db = get_firestore_client()
    subscriptions_ref = db.collection('subscriptions')
    subscription_id, subscription = _find_subscription_by_email(subscriptions_ref, email)

    # Uniform response — do not reveal whether the email exists.
    uniform = {
        'success': True,
        'message': 'If an account exists for this email, a sign-in code was sent.',
    }
    if not subscription_id:
        logger.info(f'Login code requested for unknown email: {email[:3]}...')
        return uniform

    now = datetime.utcnow()
    sent_at = subscription.get('login_code_sent_at')
    if sent_at and hasattr(sent_at, 'timestamp'):
        elapsed = now.timestamp() - sent_at.timestamp()
        if elapsed < LOGIN_CODE_RATE_LIMIT_SECONDS:
            return uniform

    code = _generate_login_code()
    code_hash = _hash_login_code(email, subscription_id, code)
    expires_at = now + timedelta(seconds=LOGIN_CODE_TTL_SECONDS)

    subscriptions_ref.document(subscription_id).update({
        'login_code_hash': code_hash,
        'login_code_expires_at': expires_at,
        'login_code_sent_at': firestore.SERVER_TIMESTAMP,
        'login_code_attempts': 0,
    })

    if send_login_code_email(email, code):
        logger.info(f'Login code sent for subscription {subscription_id}')
    else:
        logger.warning(f'Login code email failed for subscription {subscription_id}')
    return uniform


def _verify_email_login_code(
    email: str,
    code: str,
    device_id: str,
    device_label: str,
    device_fingerprint: str,
    device_fingerprint_profile: dict,
    device_fingerprint_profile_json: str,
    request_context: dict,
    logger,
) -> Dict[str, Any]:
    """Verify email OTP and complete subscription auth with device binding."""
    email = (email or '').strip().lower()
    code = (code or '').strip()
    if not email or '@' not in email:
        return {'valid': False, 'error': 'Email is required'}
    if not code or len(code) != 6 or not code.isdigit():
        return {'valid': False, 'error': 'Enter the 6-digit code from your email'}

    db = get_firestore_client()
    subscriptions_ref = db.collection('subscriptions')
    subscription_id, subscription = _find_subscription_by_email(subscriptions_ref, email)
    if not subscription_id:
        return {'valid': False, 'error': 'Invalid email or code'}

    attempts = int(subscription.get('login_code_attempts') or 0)
    if attempts >= LOGIN_CODE_MAX_ATTEMPTS:
        return {'valid': False, 'error': 'Too many attempts. Request a new code.'}

    stored_hash = (subscription.get('login_code_hash') or '').strip()
    expires_at = subscription.get('login_code_expires_at')
    expires_dt = _expires_datetime(expires_at)
    now = datetime.utcnow()

    if not stored_hash or not expires_dt or expires_dt < now:
        return {'valid': False, 'error': 'Code expired. Request a new sign-in code.'}

    expected_hash = _hash_login_code(email, subscription_id, code)
    if stored_hash != expected_hash:
        subscriptions_ref.document(subscription_id).update({
            'login_code_attempts': attempts + 1,
        })
        return {'valid': False, 'error': 'Invalid email or code'}

    subscriptions_ref.document(subscription_id).update({
        'login_code_hash': firestore.DELETE_FIELD,
        'login_code_expires_at': firestore.DELETE_FIELD,
        'login_code_attempts': firestore.DELETE_FIELD,
    })

    result = _verify_subscription_record(
        subscription, subscription_id, subscriptions_ref,
        device_id, device_label, device_fingerprint, device_fingerprint_profile,
        device_fingerprint_profile_json, request_context, logger,
    )
    if result.get('valid'):
        license_key = (subscription.get('license_key') or '').strip()
        result['license_key'] = license_key
        logger.info(f'Email login verified for subscription {subscription_id}')
    return result


@https_fn.on_call(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def request_email_login_code(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """Send a one-time login code to the subscription email on file."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        email = req.data.get('email', '')
        return _request_email_login_code(email, logger)
    except Exception as exc:
        logger.error(f'Error requesting email login code: {exc}')
        return {'success': False, 'error': 'Could not send sign-in code. Try again later.'}


@https_fn.on_request(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def request_email_login_code_http(req: https_fn.Request) -> https_fn.Response:
    """HTTP endpoint to request an email login code."""
    import logging
    logger = logging.getLogger(__name__)
    headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
    if req.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600',
        })
    try:
        data = req.get_json(silent=True) or {} if req.method == 'POST' else dict(req.args)
        result = _request_email_login_code(data.get('email', ''), logger)
        return https_fn.Response(json.dumps(result), status=200, headers=headers)
    except Exception as exc:
        logger.error(f'Error in request_email_login_code_http: {exc}')
        return https_fn.Response(
            json.dumps({'success': False, 'error': 'Could not send sign-in code.'}),
            status=500,
            headers=headers,
        )


@https_fn.on_call()
def verify_email_login_code(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """Verify email OTP and sign in with device binding."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        req_ctx = _extract_request_context_callable(req)
        return _verify_email_login_code(
            req.data.get('email', ''),
            req.data.get('code', ''),
            req.data.get('device_id', ''),
            req.data.get('device_label', ''),
            req.data.get('device_fingerprint', ''),
            req.data.get('device_fingerprint_profile', {}),
            req.data.get('device_fingerprint_profile_json', ''),
            req_ctx,
            logger,
        )
    except Exception as exc:
        logger.error(f'Error verifying email login code: {exc}')
        return {'valid': False, 'error': 'Server error verifying sign-in code'}


@https_fn.on_request()
def verify_email_login_code_http(req: https_fn.Request) -> https_fn.Response:
    """HTTP endpoint to verify email OTP login."""
    import logging
    logger = logging.getLogger(__name__)
    if req.method == 'OPTIONS':
        return https_fn.Response('', status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600',
        })
    headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
    try:
        data = req.get_json(silent=True) or {} if req.method == 'POST' else dict(req.args)
        req_ctx = _extract_request_context_http(req)
        result = _verify_email_login_code(
            data.get('email', ''),
            data.get('code', ''),
            data.get('device_id', ''),
            data.get('device_label', ''),
            data.get('device_fingerprint', ''),
            data.get('device_fingerprint_profile', {}),
            data.get('device_fingerprint_profile_json', ''),
            req_ctx,
            logger,
        )
        return https_fn.Response(json.dumps(result), status=200, headers=headers)
    except Exception as exc:
        logger.error(f'Error in verify_email_login_code_http: {exc}')
        return https_fn.Response(
            json.dumps({'valid': False, 'error': 'Server error verifying sign-in code'}),
            status=500,
            headers=headers,
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
            news_data = fs.get('news', [])
            translated_fields = _translate_news_items_to_english(news_data)
            return {
                'success': True,
                'news': news_data,
                'count': len(news_data),
                'debug': fs.get('debug', {}),
                'translated_fields': translated_fields,
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
        translated_fields = _translate_news_items_to_english(news_data)
        
        return {
            'success': True,
            'news': news_data,
            'count': len(news_data),
            'translated_fields': translated_fields,
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
            
            # Official-account social leagues should still use the NewsService even when
            # SQLite has no nearby fixtures, because their feed can come directly from X.
            official_social_league_ids = {4414, 4430, 4446, 4551, 4574, 4714, 5479, 5480}

            # If SQLite DB is present but has no usable data for this league, fall back to Firestore
            # (this commonly happens when the bundled SQLite doesn't include a league, or date parsing fails).
            # Skip this fallback for official-social leagues so X-only feeds still load.
            if league_id_int is not None:
                if league_id_int in official_social_league_ids:
                    logger.info(
                        f"Skipping Firestore news fallback for official-social league {league_id_int}; "
                        "allowing NewsService social feed to run."
                    )
                elif sqlite_league_total == 0:
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
                translated_fields = _translate_news_items_to_english(news_data)
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
                translated_fields = _translate_news_items_to_english(news_data)
                if translated_fields:
                    logger.info("Translated %s third-party news fields to English", translated_fields)
                
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
                'translated_fields': translated_fields if 'translated_fields' in locals() else 0,
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
        if not response_headers.get("Accept-Ranges"):
            response_headers["Accept-Ranges"] = "bytes"

        # Stream chunks instead of buffering the entire MP4 in memory.
        # Browsers send Range requests for progressive playback; this makes reels start much faster.
        def _stream_body():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return https_fn.Response(
            _stream_body(),
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


@https_fn.on_request(timeout_sec=60, memory=512, secrets=["SPORTRADAR_API_KEY", "APISPORTS_RUGBY_KEY"])
def get_league_standings_http(req: https_fn.Request) -> https_fn.Response:
    """
    Get league standings from SportRadar (team logos via API-Sports).
    
    Request body:
    {
        "sportsdb_league_id": 4986,   # Required local league id
        "league_id": 73119            # Optional — league banner logo only
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
        
        if not sportsdb_league_id:
            logger.error("❌ Missing sportsdb_league_id in request")
            response_data = {
                'success': False,
                'error': 'sportsdb_league_id is required',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)

        try:
            local_league_id = int(sportsdb_league_id)
        except (TypeError, ValueError):
            logger.error("❌ Invalid sportsdb_league_id in request")
            response_data = {
                'success': False,
                'error': 'sportsdb_league_id must be a valid integer',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)

        # Optional: used only for league banner logo URL (not standings data).
        highlightly_league_id = data.get('league_id')

        logger.info(
            f"📊 Fetching SportRadar standings for local league id={local_league_id}"
            + (f" (banner logo hl id={highlightly_league_id})" if highlightly_league_id else "")
        )

        import os

        sportradar_key = (
            os.getenv("SPORTRADAR_API_KEY") or os.getenv("SPORTRADAR_RUGBY_API_KEY") or ""
        ).strip()
        apisports_key = (
            os.getenv("APISPORTS_RUGBY_KEY") or os.getenv("APISPORTS_API_KEY") or ""
        ).strip()

        if sportradar_key:
            logger.info(f"✅ SportRadar API key configured (length: {len(sportradar_key)})")
        if apisports_key:
            logger.info(f"✅ API-Sports key configured (length: {len(apisports_key)})")

        if not sportradar_key:
            logger.error("❌ SPORTRADAR_API_KEY not configured")
            response_data = {
                'success': False,
                'error': 'SPORTRADAR_API_KEY not configured',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=500, headers=headers)

        requested_season = data.get("season")

        from prediction.sportradar_client import (
            CROSS_YEAR_LOCAL_IDS,
            NO_STANDINGS_LOCAL_IDS,
            candidate_season_years,
            try_fetch_sportradar_standings,
        )
        from prediction.standings_compute import STANDINGS_CACHE_VERSION, standings_cache_doc_id

        if local_league_id in NO_STANDINGS_LOCAL_IDS:
            response_data = {
                'success': False,
                'error': 'Standings are not available for this competition.',
                'standings': None,
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)

        seasons_to_try = candidate_season_years(local_league_id, requested_season=requested_season)
        logger.info(f"🔍 SportRadar will try seasons (in order): {seasons_to_try}")

        standings = None
        successful_season = None
        cache_hit = False
        standings_source = "sportradar"
        stale_cache_payload = None

        fs_cache = None
        cache_collection = None
        try:
            fs_cache = get_firestore_client()
            cache_collection = fs_cache.collection("standings_cache_v1")
        except Exception as cache_init_err:
            logger.warning(f"Standings cache init failed (continuing without cache): {cache_init_err}")
            fs_cache = None
            cache_collection = None

        try:
            sr_result = try_fetch_sportradar_standings(
                local_league_id=local_league_id,
                league_name=client_league_name,
                requested_season=requested_season,
                cache_collection=cache_collection,
                force_refresh=force_refresh,
            )
            if sr_result:
                standings, successful_season, cache_hit = sr_result
                logger.info(
                    "✅ SportRadar standings for league %s season %s (cache_hit=%s)",
                    local_league_id,
                    successful_season,
                    cache_hit,
                )
        except Exception as sr_err:
            logger.warning(f"SportRadar standings fetch failed: {sr_err}")

        # Stale SportRadar cache fallback (never Highlightly / computed tables).
        if standings is None and cache_collection is not None and not force_refresh:
            for year in seasons_to_try:
                try:
                    cache_ref = cache_collection.document(
                        standings_cache_doc_id(local_league_id, int(year))
                    )
                    cached = cache_ref.get()
                    cached_data = cached.to_dict() if getattr(cached, "exists", False) else None
                    if not isinstance(cached_data, dict):
                        continue
                    if cached_data.get("source") != "sportradar":
                        continue
                    cached_standings = cached_data.get("standings")
                    if isinstance(cached_standings, dict) and cached_standings.get("groups"):
                        stale_cache_payload = cached_standings
                        successful_season = int(year)
                        logger.info(
                            "Using stale SportRadar cache for league %s season %s",
                            local_league_id,
                            year,
                        )
                        break
                except Exception:
                    continue
            if stale_cache_payload is not None:
                standings = stale_cache_payload
                cache_hit = True

        logger.info("\n" + "="*80)
        logger.info("=== FINAL RESULT ===")
        logger.info("="*80)
        
        if standings and successful_season:
            logger.info(f"✅ SUCCESS: Found standings for season {successful_season}")
            logger.info(f"   Local league ID: {local_league_id}")
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

                # Team crests: API-Sports /teams?search= (primary), then TheSportsDB + static map.
                try:
                    from prediction.standings_logos import enrich_standings_logos
                    from prediction.config import load_config
                    from prediction.sportsdb_client import TheSportsDBClient

                    cfg = load_config()
                    sportsdb_logo_client = TheSportsDBClient(
                        base_url=cfg.base_url,
                        api_key=cfg.api_key,
                        rate_limit_rpm=cfg.rate_limit_rpm,
                    )
                    enrich_standings_logos(
                        standings,
                        sportsdb_league_id=local_league_id,
                        highlightly_league_id=highlightly_league_id,
                        firestore_client=fs_cache,
                        sportsdb_client=sportsdb_logo_client,
                    )
                except Exception as logo_err:
                    logger.warning(
                        "Standings logo enrichment failed (continuing without logos): %s",
                        logo_err,
                    )

                # Write standings cache (after enrichment).
                if cache_collection is not None and not cache_hit and not force_refresh and isinstance(successful_season, int):
                    try:
                        cache_doc_id = standings_cache_doc_id(int(local_league_id), int(successful_season))
                        cache_ref = cache_collection.document(cache_doc_id)
                        expires_dt = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=cache_ttl_seconds)
                        cache_ref.set(
                            {
                                "sportsdb_league_id": int(local_league_id),
                                "highlightly_league_id": int(highlightly_league_id) if highlightly_league_id is not None else None,
                                "league_name": client_league_name,
                                "season": int(successful_season),
                                "standings": standings,
                                "fetched_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                                "expires_at": expires_dt.isoformat() + "Z",
                                "source": "sportradar",
                                "cache_version": STANDINGS_CACHE_VERSION,
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
                'display_season': (
                    f"{successful_season}/{str(int(successful_season) + 1)[-2:]}"
                    if isinstance(successful_season, int)
                    and local_league_id in CROSS_YEAR_LOCAL_IDS
                    else str(successful_season) if successful_season is not None else None
                ),
                'league_id': local_league_id,
                'source': 'sportradar',
                'cache_hit': cache_hit,
            }
            logger.info(f"✅ Returning success response (status 200)")
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        else:
            logger.warning("⚠️ NO STANDINGS FOUND from SportRadar")
            logger.warning(f"   Local league ID: {local_league_id}")
            logger.warning(f"   Tried seasons: {seasons_to_try}")

            error_msg = (
                f'No SportRadar standings available for league {local_league_id} '
                f'(tried seasons {seasons_to_try})'
            )
            if local_league_id == 4574:
                error_msg = (
                    'Rugby World Cup pool standings are keyed to tournament years (e.g. 2023). '
                    'Try again or check SportRadar coverage for the selected season.'
                )

            response_data = {
                'success': False,
                'error': error_msg,
                'standings': None,
                'debug': {
                    'tried_seasons': seasons_to_try,
                    'sportsdb_league_id': local_league_id,
                    'source': 'sportradar',
                }
            }
            logger.info("⚠️ Returning error response (status 200)")
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


# Legacy curated fixtures (optional metadata only — match list comes from SportRadar).
FEATURED_LINEUP_MATCHES: Dict[int, List[Dict[str, Any]]] = {}


@https_fn.on_request(timeout_sec=120, memory=512, secrets=["SPORTRADAR_API_KEY"])
def get_match_lineups_http(req: https_fn.Request) -> https_fn.Response:
    """Fetch match lineups or list lineup-capable fixtures from SportRadar."""
    import json
    import logging
    import os

    logger = logging.getLogger(__name__)
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204, headers=headers)

    try:
        data = req.get_json(silent=True) or {}
        sportsdb_league_id = data.get("sportsdb_league_id")
        sport_event_id = (data.get("sport_event_id") or data.get("event_id") or "").strip()
        list_matches = bool(data.get("list_matches"))
        requested_season = data.get("season")
        match_scope = str(data.get("match_scope") or "historic").strip().lower()
        if match_scope not in ("historic", "upcoming"):
            match_scope = "historic"

        try:
            local_league_id = int(sportsdb_league_id) if sportsdb_league_id is not None else None
        except (TypeError, ValueError):
            local_league_id = None

        sportradar_key = (
            os.getenv("SPORTRADAR_API_KEY") or os.getenv("SPORTRADAR_RUGBY_API_KEY") or ""
        ).strip()
        if not sportradar_key:
            return https_fn.Response(
                json.dumps({"success": False, "error": "SPORTRADAR_API_KEY not configured", "lineups": None}),
                status=500,
                headers=headers,
            )

        from prediction.sportradar_client import SportRadarRugbyClient
        from prediction.lineups_normalize import normalize_sportradar_lineups
        from prediction.lineups_match_list import list_league_lineup_matches

        client = SportRadarRugbyClient(api_key=sportradar_key)

        if list_matches or not sport_event_id:
            if local_league_id is None:
                return https_fn.Response(
                    json.dumps(
                        {
                            "success": False,
                            "error": "sportsdb_league_id is required to list matches",
                            "matches": [],
                        }
                    ),
                    status=400,
                    headers=headers,
                )
            listing = list_league_lineup_matches(
                client,
                local_league_id=local_league_id,
                requested_season=requested_season,
                match_scope=match_scope,
            )
            if listing.get("error") and not listing.get("matches"):
                return https_fn.Response(
                    json.dumps(
                        {
                            "success": False,
                            "error": listing.get("error"),
                            "matches": [],
                            "sportsdb_league_id": local_league_id,
                        }
                    ),
                    status=200,
                    headers=headers,
                )
            return https_fn.Response(
                json.dumps(
                    {
                        "success": True,
                        "sportsdb_league_id": local_league_id,
                        "season": listing.get("successful_season"),
                        "season_years_tried": listing.get("season_years_tried") or [],
                        "match_scope": match_scope,
                        "matches": listing.get("matches") or [],
                        "competition_id": listing.get("competition_id"),
                    }
                ),
                status=200,
                headers=headers,
            )

        featured = FEATURED_LINEUP_MATCHES.get(local_league_id or -1, [])

        raw = client.fetch_event_lineups_raw(sport_event_id)
        if not raw:
            return https_fn.Response(
                json.dumps(
                    {
                        "success": False,
                        "error": "Lineups not available for this match",
                        "sport_event_id": sport_event_id,
                        "featured_matches": featured,
                        "lineups": None,
                    }
                ),
                status=200,
                headers=headers,
            )

        payload = normalize_sportradar_lineups(raw)
        from prediction.jersey_kits import enrich_lineup_teams_with_kits

        teams_block = payload.get("teams") if isinstance(payload.get("teams"), list) else []
        enrich_lineup_teams_with_kits(client, teams_block)
        meta = next((m for m in featured if m.get("sport_event_id") == sport_event_id), None)
        if not meta:
            teams = payload.get("teams") if isinstance(payload.get("teams"), list) else []
            home_team = next((t.get("name") for t in teams if t.get("qualifier") == "home"), None)
            away_team = next((t.get("name") for t in teams if t.get("qualifier") == "away"), None)
            if not home_team and len(teams) >= 1:
                home_team = teams[0].get("name")
            if not away_team and len(teams) >= 2:
                away_team = teams[1].get("name")
            match_info = payload.get("match") if isinstance(payload.get("match"), dict) else {}
            meta = {
                "sport_event_id": sport_event_id,
                "label": f"{home_team or 'Home'} vs {away_team or 'Away'}",
                "home_team": home_team,
                "away_team": away_team,
                "start_time": match_info.get("start_time"),
                "round": match_info.get("round"),
                "venue": match_info.get("venue"),
            }
        if meta:
            payload["featured"] = meta

        return https_fn.Response(
            json.dumps(
                {
                    "success": True,
                    "sport_event_id": sport_event_id,
                    "sportsdb_league_id": local_league_id,
                    "featured_matches": featured,
                    "lineups": payload,
                }
            ),
            status=200,
            headers=headers,
        )
    except Exception as exc:
        logger.exception("get_match_lineups_http failed: %s", exc)
        return https_fn.Response(
            json.dumps({"success": False, "error": str(exc), "lineups": None}),
            status=500,
            headers=headers,
        )



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

    return https_fn.Response(
        json.dumps({
            "success": False,
            "error": "API-Sports webhook disabled. Match data is synced via Highlightly pipeline.",
        }),
        status=410,
        headers=response_headers,
    )

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
    request_id = None
    
    # Handle CORS preflight (match pattern used by other HTTP functions)
    if req.method == "OPTIONS":
        logger.info("OPTIONS request - returning CORS preflight")
        preflight_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Request-Id",
            "Access-Control-Max-Age": "3600",
            "Access-Control-Expose-Headers": "X-History-Request-Id",
        }
        return https_fn.Response("", status=204, headers=preflight_headers)
    
    # Define response headers with CORS for all responses
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
        "Access-Control-Expose-Headers": "X-History-Request-Id",
    }
    
    try:
        # Parse request data
        data = req.get_json(silent=True) or {}
        request_id = str(
            data.get("client_request_id")
            or req.headers.get("X-Client-Request-Id")
            or f"hist-{secrets.token_hex(6)}"
        )
        response_headers["X-History-Request-Id"] = request_id
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
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        
        logger.info(
            f"[hist][{request_id}] request metadata: "
            f"method={req.method}, origin={req.headers.get('Origin')}, "
            f"content_type={req.headers.get('Content-Type')}, "
            f"content_length={req.headers.get('Content-Length')}, "
            f"user_agent={req.headers.get('User-Agent')}"
        )
        logger.info(
            f"[hist][{request_id}] request payload: "
            f"league_id={league_id}, year={year}, limit={limit}, offset={offset}, "
            f"refresh={data.get('refresh')}"
        )
        
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            # If not found, try parent directory
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")
        
        db_exists = os.path.exists(db_path)
        db_size_bytes = os.path.getsize(db_path) if db_exists else None
        logger.info(
            f"[hist][{request_id}] database path resolved: "
            f"path={db_path}, exists={db_exists}, size_bytes={db_size_bytes}"
        )
        
        if not db_exists:
            logger.error(f"[hist][{request_id}] database file not found at {db_path}")
            response_data = {
                'request_id': request_id,
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
        predictor = None
        
        # Connect to database
        t0_connect = perf_counter()
        conn = connect(db_path)
        cursor = conn.cursor()
        _ensure_prediction_snapshot_table(conn)
        logger.info(
            f"[hist][{request_id}] database connected and snapshot table ensured in "
            f"{(perf_counter() - t0_connect) * 1000:.1f} ms"
        )
        
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
            logger.info(f"[hist][{request_id}] available_years query completed in {(perf_counter() - t0_years) * 1000:.1f} ms (count={len(available_years)})")
        except Exception as e:
            logger.warning(f"[hist][{request_id}] could not compute available years: {e}")
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
            logger.info(f"[hist][{request_id}] year_summary query completed in {(perf_counter() - t0_summary) * 1000:.1f} ms (years={len(year_summary)})")
        except Exception as e:
            logger.warning(f"[hist][{request_id}] could not compute year summary: {e}")
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
                # Prefer current calendar year; UI merges cross-year (Sep-Jun) windows client-side.
                if current_year in available_years:
                    selected_year = current_year
                else:
                    for yr in available_years:
                        completed = int((year_summary.get(str(yr)) or {}).get("completed", 0) or 0)
                        if completed > 0:
                            selected_year = str(yr)
                            break
                if selected_year is None:
                    selected_year = available_years[0] if available_years else None
        else:
            selected_year = str(year)

        # Unified fast path: all completed matches with optional snapshot predictions (no slow replay).
        model_version = _get_live_model_version()
        event_where = [
            "e.home_score IS NOT NULL",
            "e.away_score IS NOT NULL",
            "e.date_event IS NOT NULL",
            "date(e.date_event) <= date('now')",
        ]
        event_params: list[Any] = []
        if league_id:
            event_where.append("e.league_id = ?")
            event_params.append(league_id)
        if selected_year:
            try:
                yr = int(str(selected_year).strip()[:4])
                prev_yr = str(yr - 1)
                event_where.append("(substr(e.date_event, 1, 4) = ? OR substr(e.date_event, 1, 4) = ?)")
                event_params.extend([str(yr), prev_yr])
            except (ValueError, TypeError):
                event_where.append("substr(e.date_event, 1, 4) = ?")
                event_params.append(str(selected_year))

        event_filter_sql = " AND ".join(event_where)
        count_query = f"""
            SELECT COUNT(1)
            FROM event e
            WHERE {event_filter_sql}
        """
        t0_count = perf_counter()
        cursor.execute(count_query, event_params)
        total_rows = int((cursor.fetchone() or [0])[0] or 0)
        logger.info(
            f"[hist][{request_id}] count query completed in {(perf_counter() - t0_count) * 1000:.1f} ms "
            f"(rows={total_rows}, limit={limit}, offset={offset})"
        )

        unified_data_sql = f"""
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
            FROM event e
            LEFT JOIN league l ON e.league_id = l.id
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            LEFT JOIN prediction_snapshot s ON s.rowid = (
                SELECT s2.rowid
                FROM prediction_snapshot s2
                WHERE s2.match_id = e.id AND s2.model_version = ?
                ORDER BY CASE s2.snapshot_type WHEN 'pre_kickoff_live' THEN 0 ELSE 1 END, s2.id DESC
                LIMIT 1
            )
            WHERE {event_filter_sql}
            ORDER BY e.date_event ASC, e.league_id
            LIMIT ? OFFSET ?
        """
        t0_data = perf_counter()
        cursor.execute(unified_data_sql, [model_version, *event_params, limit, offset])
        results = cursor.fetchall()
        logger.info(
            f"[hist][{request_id}] unified data query completed in {(perf_counter() - t0_data) * 1000:.1f} ms "
            f"(returned={len(results)})"
        )

        def _compute_league_rounds(rows):
            """Group matches into rounds by matchday (within 4 days = same round)."""
            from datetime import datetime as _dt
            round_assignments = {}
            prev_date = None
            current_round = 0
            day_threshold = 4
            season_gap_days = 90
            for r in rows:
                mid, date_event = r[0], r[3]
                if not date_event:
                    continue
                try:
                    dt = _dt.strptime(date_event[:10], '%Y-%m-%d')
                except Exception:
                    continue
                key = (mid, date_event[:10])
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

        def _has_meaningful_time(v: Any) -> bool:
            try:
                s = str(v or "")
            except Exception:
                return False
            if "T" not in s:
                return False
            return ("T00:00" not in s)

        matches_by_year_week = defaultdict(lambda: defaultdict(list))
        all_matches = []
        correct_predictions = 0
        total_predictions = 0
        score_errors: list[float] = []

        logger.info(f"[hist][{request_id}] processing {len(results)} completed matches...")
        t0_process = perf_counter()
        for row in results:
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
            elif predicted_winner and predicted_winner not in {"Error", "Unknown"}:
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

            year_key = date_event[:4] if date_event else "Unknown"
            key = (match_id, date_event[:10] if date_event else '')
            try:
                api_r = int(str(round_num or '').strip()) if round_num is not None else None
                use_api = api_r is not None and 1 <= api_r <= 30
            except (ValueError, TypeError):
                use_api = False
            effective_round = round_num if use_api else league_rounds.get(key)
            try:
                round_key = str(int(effective_round)) if effective_round is not None else get_year_week_key(date_event)
            except Exception:
                round_key = get_year_week_key(date_event)
            week = get_week_number(date_event)

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
                "year": year_key,
                "week": week,
                "year_week": round_key,
                "season": season,
                "round": effective_round,
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

            matches_by_year_week[year_key][round_key].append(match_data)
            all_matches.append(match_data)

        logger.info(f"[hist][{request_id}] mapping loop completed in {(perf_counter() - t0_process) * 1000:.1f} ms")
        
        conn.close()
        
        # Calculate accuracy statistics
        accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
        avg_score_error = sum(score_errors) / len(score_errors) if score_errors else None
        
        # Convert defaultdict to regular dict for JSON serialization
        result = {
            'request_id': request_id,
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
            'by_league': {},
            'debug': {
                'data_source': 'event_with_snapshot',
                'model_version': model_version,
            },
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
        
        logger.info(f"[hist][{request_id}] retrieved {result['statistics']['total_matches']} matches")
        logger.info(f"[hist][{request_id}] generated {result['statistics']['total_predictions']} predictions")
        logger.info(f"[hist][{request_id}] accuracy {result['statistics'].get('accuracy_percentage', 0):.2f}%")
        logger.info(f"[hist][{request_id}] total endpoint time {(perf_counter() - request_started_at) * 1000:.1f} ms")
        
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
        
        logger.info(f"=== get_historical_predictions_http completed successfully [{request_id}] ===")
        return https_fn.Response(json.dumps(result), status=200, headers=response_headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== get_historical_predictions_http exception [{request_id}] ===")
        logger.error(f"[hist][{request_id}] Error: {str(e)}")
        logger.error(f"[hist][{request_id}] Traceback: {error_trace}")
        response_data = {
            "request_id": request_id,
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


@https_fn.on_request(timeout_sec=540, memory=1024)
def scan_firestore_matches_http(req: https_fn.Request) -> https_fn.Response:
    """
    Scan the Firestore matches collection for duplicate fixtures and data issues.

    Request body:
    {
        "remove_duplicates": false,
        "confirm_remove": false,
        "sample_limit": 25
    }
    """
    import logging
    import json
    import traceback

    logger = logging.getLogger(__name__)
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }

    try:
        if req.method == "OPTIONS":
            return https_fn.Response("", status=204, headers=headers)

        data = req.get_json(silent=True) or {}
        remove_duplicates = bool(data.get("remove_duplicates", False))
        confirm_remove = bool(data.get("confirm_remove", False))
        sample_limit = data.get("sample_limit", 25)

        try:
            sample_limit = int(sample_limit)
        except Exception:
            sample_limit = 25
        sample_limit = max(1, min(sample_limit, 100))

        if remove_duplicates and not confirm_remove:
            return https_fn.Response(
                json.dumps(
                    {
                        "success": False,
                        "error": "Set confirm_remove=true to delete duplicate match documents.",
                    }
                ),
                status=400,
                headers=headers,
            )

        from prediction.match_data_health import scan_firestore_matches

        db = get_firestore_client()
        result = scan_firestore_matches(
            db,
            remove_duplicates=remove_duplicates,
            sample_limit=sample_limit,
        )
        logger.info(
            "Firestore match scan complete: total=%s duplicate_docs=%s removed=%s dry_run=%s",
            result.get("total_docs"),
            result.get("duplicate_docs"),
            result.get("removed_docs"),
            result.get("dry_run"),
        )
        return https_fn.Response(json.dumps(result), status=200, headers=headers)
    except Exception as e:
        logger.error("Error in scan_firestore_matches_http: %s", e)
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"success": False, "error": str(e)}),
            status=500,
            headers=headers,
        )