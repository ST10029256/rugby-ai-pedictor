"""Highlightly league mappings and fixture fetch helpers (all 10 rugby leagues)."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .highlightly_client import HighlightlyRugbyAPI

logger = logging.getLogger(__name__)

# Our internal league id -> (display name, Highlightly league id)
HIGHLIGHTLY_LEAGUE_MAPPINGS: Dict[int, Tuple[str, int]] = {
    4986: ("Rugby Championship", 73119),
    4446: ("United Rugby Championship", 65460),
    5069: ("Currie Cup", 32271),
    4574: ("Rugby World Cup", 59503),
    4551: ("Super Rugby", 61205),
    4430: ("French Top 14", 14400),
    4414: ("English Premiership Rugby", 11847),
    4714: ("Six Nations Championship", 44185),
    5479: ("Rugby Union International Friendlies", 72268),
    5480: ("Nations Championship", 124179),
}

YEAR_SPAN_LEAGUE_IDS = {4414, 4430, 4446}
WOMEN_INDICATORS = (" w rugby", " women", " womens", " w ", " women's", " w's")


def ensure_highlightly_match_id_column(conn: sqlite3.Connection) -> None:
    """Add event.highlightly_match_id if missing (idempotent)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(event)").fetchall()}
    if "highlightly_match_id" not in cols:
        conn.execute("ALTER TABLE event ADD COLUMN highlightly_match_id INTEGER")
        conn.commit()
        logger.info("Added event.highlightly_match_id column")


def lookup_highlightly_match_id(conn: sqlite3.Connection, local_event_id: int) -> Optional[int]:
    """Return stored Highlightly match id for a local SQLite event row."""
    row = conn.execute(
        "SELECT highlightly_match_id FROM event WHERE id = ? LIMIT 1",
        (int(local_event_id),),
    ).fetchone()
    if not row or row[0] is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def parse_api_key(explicit: Optional[str] = None) -> str:
    import os

    key = (
        (explicit or "").strip()
        or os.getenv("HIGHLIGHTLY_API_KEY", "").strip()
        or os.getenv("RAPIDAPI_KEY", "").strip()
    )
    if not key:
        raise ValueError(
            "Missing Highlightly key. Set HIGHLIGHTLY_API_KEY in rugby-ai-predictor/.env "
            "or pass --api-key."
        )
    return key


def is_womens_match(home: str, away: str) -> bool:
    home_l = home.lower()
    away_l = away.lower()
    return any(x in home_l for x in WOMEN_INDICATORS) or any(x in away_l for x in WOMEN_INDICATORS)


def parse_match_dt(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip()
    try:
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def season_candidates(now: datetime, our_league_id: int, include_history: bool) -> List[int]:
    year = now.year
    if include_history:
        seasons = list(range(2015, year + 2))
        if our_league_id == 4574:
            seasons.extend([2023, 2027])
    elif our_league_id == 4574:
        seasons = [year + 1, year, year - 1, 2023]
    elif our_league_id == 5479:
        seasons = [year, year - 1, year - 2]
    elif our_league_id == 5480:
        seasons = [year, year + 1, year - 1]
    else:
        seasons = [year, year - 1, year - 2]

    seen: set[int] = set()
    out: List[int] = []
    for s in seasons:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def detect_best_season(
    api: HighlightlyRugbyAPI,
    highlightly_league_id: int,
    our_league_id: int,
    today: datetime,
    request_counter: Optional[List[int]] = None,
    sleep_s: float = 0.0,
) -> Tuple[Optional[int], int]:
    best_season: Optional[int] = None
    best_score = -1
    best_total = 0

    for season in season_candidates(today, our_league_id, include_history=False):
        if sleep_s > 0:
            time.sleep(sleep_s)
        resp = api.get_matches(league_id=highlightly_league_id, season=season, limit=1)
        if request_counter is not None:
            request_counter[0] += 1
        if not resp.get("data") and not (resp.get("pagination") or {}).get("totalCount"):
            continue
        total = int((resp.get("pagination") or {}).get("totalCount") or 0)
        if total <= 0:
            continue

        future_bonus = 0
        for row in resp.get("data") or []:
            dt = parse_match_dt(row.get("date"))
            if dt and dt.date() >= today.date():
                future_bonus += 1000

        score = total + future_bonus
        if score > best_score:
            best_score = score
            best_season = season
            best_total = total

    return best_season, best_total


def fetch_season_matches(
    api: HighlightlyRugbyAPI,
    highlightly_league_id: int,
    season: int,
    page_size: int = 100,
    request_counter: Optional[List[int]] = None,
    sleep_s: float = 0.0,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    total_count: Optional[int] = None
    page_size = max(1, min(page_size, 100))

    while True:
        if sleep_s > 0:
            time.sleep(sleep_s)
        resp = api.get_matches(
            league_id=highlightly_league_id,
            season=season,
            limit=page_size,
            offset=offset,
        )
        if request_counter is not None:
            request_counter[0] += 1
        batch = resp.get("data") or []
        pag = resp.get("pagination") or {}
        if total_count is None:
            total_count = int(pag.get("totalCount") or 0)
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        if total_count is not None and offset >= total_count:
            break
        if len(batch) < page_size:
            break

    return rows


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _coerce_score(value: Any) -> Optional[int]:
    """Coerce a single score value that may be int, numeric string, or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text == "" or not any(ch.isdigit() for ch in text):
        return None
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _split_pair_score(value: Any) -> Tuple[Optional[int], Optional[int]]:
    """Parse combined score strings like '24-17', '24 : 17', '24 - 17'."""
    if not isinstance(value, str):
        return None, None
    import re

    nums = re.findall(r"\d+", value)
    if len(nums) >= 2:
        return _safe_int(nums[0]), _safe_int(nums[1])
    return None, None


def extract_scores(row: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """Robustly pull final home/away scores from a Highlightly match row.

    Highlightly's rugby payloads are inconsistent: some matches expose flat
    ``homeScore``/``awayScore`` ints, others nest them under ``score``,
    ``state.score`` (often a combined ``"24 - 17"`` string), per-team ``score``
    fields, or a ``scores`` list. We were only reading the first two shapes,
    which silently dropped scores for finished matches that used the others -
    leaving them in the DB as 'Finished' with NULL scores. Try every known
    shape before giving up.
    """
    home = _coerce_score(row.get("homeScore"))
    away = _coerce_score(row.get("awayScore"))
    if home is not None and away is not None:
        return home, away

    score_obj = row.get("score")
    if isinstance(score_obj, dict):
        home = home if home is not None else _coerce_score(score_obj.get("home"))
        away = away if away is not None else _coerce_score(score_obj.get("away"))
        if home is None or away is None:
            ph, pa = _split_pair_score(score_obj.get("current") or score_obj.get("display") or score_obj.get("ft"))
            home = home if home is not None else ph
            away = away if away is not None else pa
    if home is not None and away is not None:
        return home, away

    state = row.get("state")
    if isinstance(state, dict):
        s_score = state.get("score")
        if isinstance(s_score, dict):
            home = home if home is not None else _coerce_score(s_score.get("home"))
            away = away if away is not None else _coerce_score(s_score.get("away"))
            if home is None or away is None:
                ph, pa = _split_pair_score(s_score.get("current") or s_score.get("display"))
                home = home if home is not None else ph
                away = away if away is not None else pa
        elif isinstance(s_score, str):
            ph, pa = _split_pair_score(s_score)
            home = home if home is not None else ph
            away = away if away is not None else pa
    if home is not None and away is not None:
        return home, away

    home_team = row.get("homeTeam")
    away_team = row.get("awayTeam")
    if isinstance(home_team, dict) and home is None:
        home = _coerce_score(home_team.get("score"))
    if isinstance(away_team, dict) and away is None:
        away = _coerce_score(away_team.get("score"))

    return home, away


def _season_label(season: int, our_league_id: int) -> str:
    if our_league_id in YEAR_SPAN_LEAGUE_IDS:
        return f"{season}-{season + 1}"
    return str(season)


def highlightly_row_to_game(
    row: Dict[str, Any],
    our_league_id: int,
    league_name: str,
    season: int,
) -> Optional[Dict[str, Any]]:
    home = str((row.get("homeTeam") or {}).get("name") or "").strip()
    away = str((row.get("awayTeam") or {}).get("name") or "").strip()
    if not home or not away or is_womens_match(home, away):
        return None

    dt = parse_match_dt(row.get("date"))
    if dt is None:
        return None

    home_score, away_score = extract_scores(row)

    state = row.get("state") or row.get("status") or ""
    if isinstance(state, dict):
        state = (
            state.get("description")
            or state.get("name")
            or state.get("short")
            or str(state)
        )
    status = str(state)

    return {
        "event_id": _safe_int(row.get("id"), 0) or 0,
        "highlightly_match_id": _safe_int(row.get("id")),
        "date_event": dt.date(),
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "league_id": our_league_id,
        "league_name": league_name,
        "season": _season_label(season, our_league_id),
        "timestamp": dt.isoformat(),
        "status": status,
    }


def _filter_by_date_window(
    games: List[Dict[str, Any]],
    days_ahead: int,
    days_back: int,
    league_name: str,
) -> List[Dict[str, Any]]:
    today = datetime.utcnow().date()
    min_date = today - timedelta(days=days_back)
    max_date = today + timedelta(days=days_ahead)
    in_window: List[Dict[str, Any]] = []
    past = future = 0

    for game in games:
        d = game.get("date_event")
        if not isinstance(d, date):
            continue
        if d < min_date or d > max_date:
            continue
        in_window.append(game)
        if d < today:
            past += 1
        elif d > today:
            future += 1

    logger.info(
        "Date window for %s: %s .. %s | in-window=%s (past=%s, future=%s)",
        league_name,
        min_date,
        max_date,
        len(in_window),
        past,
        future,
    )
    return in_window


def fetch_games_from_highlightly(
    api: HighlightlyRugbyAPI,
    our_league_id: int,
    league_name: str,
    highlightly_league_id: int,
    include_history: bool = False,
    days_ahead: int = 180,
    days_back: int = 14,
    page_size: int = 100,
    sleep_s: float = 0.35,
    request_counter: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Fetch fixtures for one league from Highlightly and return SQLite-ready game rows."""
    today = datetime.now(timezone.utc)
    logger.info(
        "Fetching %s from Highlightly (our=%s hl=%s history=%s)",
        league_name,
        our_league_id,
        highlightly_league_id,
        include_history,
    )

    seasons: List[int]
    if include_history:
        seasons = season_candidates(today, our_league_id, include_history=True)
    else:
        # Fetch the recent candidate seasons (current + previous), NOT just the
        # single "best" one. detect_best_season adds a large future-fixture
        # bonus, so once a season ends and the next season's schedule is
        # published it locks onto the upcoming season and stops refreshing the
        # just-finished one - leaving recently completed matches stuck with no
        # score. Pulling the recent candidates guarantees those results are
        # backfilled; the date-window filter still trims anything too old.
        seasons = season_candidates(today, our_league_id, include_history=False)[:3]
        if not seasons:
            best, _total = detect_best_season(
                api,
                highlightly_league_id,
                our_league_id,
                today,
                request_counter=request_counter,
                sleep_s=sleep_s,
            )
            if best is None:
                logger.warning("No Highlightly season with fixtures for %s", league_name)
                return []
            seasons = [best]

    games: List[Dict[str, Any]] = []
    seen: set[tuple] = set()

    for season in seasons:
        raw_rows = fetch_season_matches(
            api,
            highlightly_league_id,
            season,
            page_size=page_size,
            request_counter=request_counter,
            sleep_s=sleep_s,
        )
        logger.info("%s season=%s: fetched %s rows from Highlightly", league_name, season, len(raw_rows))
        for row in raw_rows:
            game = highlightly_row_to_game(row, our_league_id, league_name, season)
            if not game:
                continue
            key = (game["date_event"], game["home_team"], game["away_team"])
            if key in seen:
                continue
            seen.add(key)
            games.append(game)

    logger.info("Found %s unique games for %s from Highlightly", len(games), league_name)
    if include_history:
        return games
    return _filter_by_date_window(games, days_ahead, days_back, league_name)


def scan_league_summary(
    api: HighlightlyRugbyAPI,
    our_league_id: int,
    league_name: str,
    highlightly_league_id: int,
    today: datetime,
    page_size: int,
    request_counter: List[int],
    sleep_s: float,
) -> Dict[str, Any]:
    """Return scan stats (used by scan_highlightly_leagues.py)."""
    season, season_total = detect_best_season(
        api, highlightly_league_id, our_league_id, today, request_counter, sleep_s
    )
    result: Dict[str, Any] = {
        "our_league_id": our_league_id,
        "league_name": league_name,
        "highlightly_league_id": highlightly_league_id,
        "selected_season": season,
        "season_total_api": season_total,
        "matches_total": 0,
        "completed": 0,
        "upcoming": 0,
        "upcoming_matches": [],
        "sample_completed": [],
        "error": None,
    }
    if season is None:
        result["error"] = "No season with fixtures found on Highlightly"
        return result

    raw_rows = fetch_season_matches(
        api, highlightly_league_id, season, page_size, request_counter, sleep_s
    )
    normalized: List[Dict[str, Any]] = []
    for row in raw_rows:
        game = highlightly_row_to_game(row, our_league_id, league_name, season)
        if not game:
            continue
        dt = parse_match_dt(row.get("date"))
        completed = game["home_score"] is not None and game["away_score"] is not None
        upcoming = bool(dt and dt.date() >= today.date() and not completed)
        normalized.append(
            {
                "match_id": row.get("id"),
                "date": game["timestamp"],
                "date_only": game["date_event"].isoformat(),
                "home_team": game["home_team"],
                "away_team": game["away_team"],
                "home_score": game["home_score"],
                "away_score": game["away_score"],
                "completed": completed,
                "upcoming": upcoming,
                "state": game["status"],
                "league_name_api": (row.get("league") or {}).get("name"),
            }
        )

    upcoming = [m for m in normalized if m["upcoming"]]
    completed = [m for m in normalized if m["completed"]]
    upcoming.sort(key=lambda x: x["date"])
    completed.sort(key=lambda x: x["date"], reverse=True)

    result["matches_total"] = len(normalized)
    result["completed"] = len(completed)
    result["upcoming"] = len(upcoming)
    result["upcoming_matches"] = upcoming[:25]
    result["sample_completed"] = completed[:5]
    return result
