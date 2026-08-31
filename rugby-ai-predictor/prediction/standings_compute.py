"""Compute league standings from match results in the local SQLite database.

The Highlightly /standings feed is unreliable for rugby (stale, mislabeled by
season, missing recent seasons, and sometimes returned in an outdated grouped
format). The match/results feed, however, is accurate - so we derive the table
ourselves from completed matches.

Scoring uses the standard rugby union system that can be derived from final
scores only:

    Win  = 4 points
    Draw = 2 points
    Loss = 0 points
    Losing bonus = +1 when losing by 7 or fewer points

The try-scoring bonus (+1 for 4+ tries) cannot be computed because try counts
are not stored, so totals may be slightly lower than official tables. This is
called out via the ``note`` field on the response.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

# Canonical keys for duplicate provider team names in the same competition.
# Values are the preferred display label once aliases are merged.
STANDINGS_TEAM_CANONICAL: Dict[str, str] = {
    "newcastle red bulls": "newcastle falcons",
    "newcastle": "newcastle falcons",
}

STANDINGS_TEAM_DISPLAY: Dict[str, str] = {
    "newcastle falcons": "Newcastle Falcons",
}


def _normalize_team_key(name: Any) -> str:
    raw = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    return STANDINGS_TEAM_CANONICAL.get(raw, raw)


def _preferred_team_label(canonical_key: str, raw_name: str) -> str:
    if canonical_key in STANDINGS_TEAM_DISPLAY:
        return STANDINGS_TEAM_DISPLAY[canonical_key]
    cleaned = str(raw_name or "").strip()
    if cleaned:
        return cleaned
    return canonical_key.title()


def _dedupe_fixtures(matches: List[tuple]) -> List[tuple]:
    """Drop duplicate rows caused by provider alias drift (same date/scores/teams)."""
    seen = set()
    deduped: List[tuple] = []
    for row in matches:
        date_event, home_id, away_id, home_score, away_score, home_name, away_name = row
        home_key = _normalize_team_key(home_name)
        away_key = _normalize_team_key(away_name)
        if away_key < home_key:
            home_key, away_key = away_key, home_key
        key = (str(date_event)[:10], home_key, away_key, home_score, away_score)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _estimate_try_bonus_points(points_scored: int) -> int:
    """Heuristic try bonus when try counts are unavailable.

    Official rugby awards +1 for scoring 4+ tries. Without try counts we
    approximate with a points threshold. 24 (~4 converted tries / mix of
    tries+kicks) over-awards less than the old 20-point cutoff.
    """
    try:
        scored = int(points_scored)
    except (TypeError, ValueError):
        return 0
    return 1 if scored >= 24 else 0

# Competitions that are knockout tournaments or have multiple pools / no league
# table - a single computed table would be meaningless, so we skip them.
SKIP_COMPUTE_LEAGUE_IDS = {
    4574,  # Rugby World Cup (pools + knockout)
    5479,  # International Friendlies (no table)
    5480,  # Nations Championship (no standings)
}


def resolve_standings_db_path() -> str:
    """Resolve the SQLite path the way the history endpoint does."""
    env_path = os.getenv("DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # rugby-ai-predictor/
    candidate = os.path.join(pkg_parent, "data.sqlite")
    if os.path.exists(candidate):
        return candidate
    return os.path.join(pkg_parent, "..", "data.sqlite")


def _parse_date(value: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except Exception:
        return None


def _season_start_year(season_str: Any) -> Optional[int]:
    match = re.match(r"(\d{4})", str(season_str or ""))
    return int(match.group(1)) if match else None


def _pick_latest_season(conn: sqlite3.Connection, league_id: int) -> Optional[str]:
    rows = conn.execute(
        """
        SELECT season, MAX(date_event) AS mx
        FROM event
        WHERE league_id = ?
          AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND season IS NOT NULL AND season != ''
        GROUP BY season
        """,
        (league_id,),
    ).fetchall()
    if not rows:
        return None
    rows = [r for r in rows if r[1]]
    if not rows:
        return None
    rows.sort(key=lambda r: str(r[1]), reverse=True)
    return rows[0][0]


def _resolve_season(conn: sqlite3.Connection, league_id: int, season: Any) -> Optional[str]:
    if season is None or str(season).strip() == "":
        return _pick_latest_season(conn, league_id)

    available = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT season FROM event WHERE league_id = ? AND season IS NOT NULL AND season != ''",
            (league_id,),
        ).fetchall()
    ]
    target = str(season).strip()
    if target in available:
        return target
    target_year = _season_start_year(target)
    if target_year is not None:
        for a in available:
            if _season_start_year(a) == target_year:
                return a
    return _pick_latest_season(conn, league_id)


def _exclude_trailing_playoffs(matches: List[tuple], gap_days: int = 4) -> List[tuple]:
    """Drop trailing knockout rounds so the table reflects the league (regular) season.

    Matchdays are date clusters. Full league rounds include most teams; trailing
    semi-finals / finals are small partial rounds and are removed.
    """
    groups: List[List[tuple]] = []
    current: List[tuple] = []
    last: Optional[datetime] = None
    for m in matches:
        d = _parse_date(m[0])
        if d is None:
            current.append(m)
            continue
        if last is None or (d - last).days <= gap_days:
            current.append(m)
        else:
            groups.append(current)
            current = [m]
        last = d
    if current:
        groups.append(current)

    if len(groups) < 2:
        return [m for g in groups for m in g]

    sizes = sorted(len(g) for g in groups)
    median = sizes[len(sizes) // 2]
    min_full_round = max(2, int(round(median * 0.6)))

    end = len(groups)
    while end > 0 and len(groups[end - 1]) < min_full_round:
        end -= 1
    kept = groups[:end] if end > 0 else groups
    return [m for g in kept for m in g]


def _enrich_standings_row(row: Dict[str, Any]) -> None:
    """Fill bonus/PD aliases on a single standings row in-place."""
    try:
        wins = int(row.get("wins") or 0)
        draws = int(row.get("draws") or 0)
        points = int(row.get("points") or 0)
    except (TypeError, ValueError):
        wins = draws = points = 0

    sp = row.get("scoredPoints") if row.get("scoredPoints") is not None else row.get("pointsFor")
    rp = row.get("receivedPoints") if row.get("receivedPoints") is not None else row.get("pointsAgainst")
    if sp is not None and rp is not None:
        try:
            diff = int(sp) - int(rp)
            row.setdefault("pointsDifference", diff)
            row.setdefault("pointsDiff", diff)
        except (TypeError, ValueError):
            pass

    if row.get("bonusPoints") is None and row.get("bonus_points") is None:
        base = wins * 4 + draws * 2
        row["bonusPoints"] = max(0, points - base)

    loses = row.get("loses") if row.get("loses") is not None else row.get("losses")
    if loses is not None:
        row.setdefault("loses", loses)
        row.setdefault("losses", loses)

    played = row.get("gamesPlayed") if row.get("gamesPlayed") is not None else row.get("played")
    if played is not None:
        row.setdefault("gamesPlayed", played)
        row.setdefault("played", played)


STANDINGS_CACHE_VERSION = 4

# Competitions with no meaningful league table in the app.
NO_STANDINGS_LOCAL_IDS = {5479}

# Aug–Jun competitions: season start-year flips in August.
CROSS_YEAR_LOCAL_IDS = {4446, 4414, 4430}

# Cache sources we still trust after SportRadar removal.
ALLOWED_STANDINGS_CACHE_SOURCES = {"highlightly", "match_results"}


def candidate_season_years(
    local_league_id: int,
    *,
    requested_season: Any = None,
    now: Optional[datetime] = None,
) -> List[int]:
    """Latest season year first; if that table is empty, try the previous year only."""
    lid = int(local_league_id)
    now = now or datetime.utcnow()
    year = now.year
    month = now.month

    if lid in CROSS_YEAR_LOCAL_IDS:
        primary = year - 1 if month <= 7 else year
    else:
        primary = year

    if requested_season is not None:
        try:
            primary = int(requested_season)
        except (TypeError, ValueError):
            pass

    return [primary, primary - 1]


def is_computed_standings(standings: Any) -> bool:
    """True for tables derived from our match DB (not Highlightly)."""
    if not isinstance(standings, dict):
        return False
    return bool(
        standings.get("_computed")
        or standings.get("_source") == "match_results"
        or standings.get("note")
    )


def standings_table_usable(standings: Any) -> bool:
    """True when a provider returned a non-empty table we can show."""
    if not isinstance(standings, dict):
        return False
    if standings.get("_rate_limited") or standings.get("_error"):
        return False
    groups = standings.get("groups")
    if not isinstance(groups, list) or not groups:
        return False
    for group in groups:
        if not isinstance(group, dict):
            continue
        for key in ("standings", "teams"):
            rows = group.get(key)
            if isinstance(rows, list) and len(rows) > 0:
                return True
    return False


def highlightly_standings_usable(standings: Any) -> bool:
    """True when Highlightly returned a non-empty live table (not DB-computed)."""
    if is_computed_standings(standings):
        return False
    return standings_table_usable(standings)


def standings_cache_doc_id(sportsdb_league_id: int, season: int) -> str:
    """Unified Firestore cache key keyed by local/SportsDB league id."""
    return f"ldb::{int(sportsdb_league_id)}::season::{int(season)}"


def count_standings_logos(standings: Any) -> tuple[int, int]:
    """Return (teams_with_logo, total_teams)."""
    if not isinstance(standings, dict):
        return 0, 0
    groups = standings.get("groups")
    if not isinstance(groups, list):
        return 0, 0
    total = 0
    with_logo = 0
    for group in groups:
        if not isinstance(group, dict):
            continue
        for list_key in ("standings", "teams"):
            rows = group.get(list_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                total += 1
                team_obj = row.get("team") if isinstance(row.get("team"), dict) else {}
                logo = (
                    (team_obj or {}).get("logo")
                    or (team_obj or {}).get("badge")
                    or row.get("logo")
                    or row.get("badge")
                )
                if logo:
                    with_logo += 1
    return with_logo, total


def load_standings_cache_document(
    cache_collection: Any,
    local_league_id: int,
    year: int,
    *,
    fresh_only: bool = False,
) -> Optional[tuple[Dict[str, Any], int, bool, str]]:
    """
    Load cached standings for one season year from Firestore.
    Returns (standings, season_year, is_fresh, source) or None.
    Ignores legacy SportRadar cache docs.
    """
    if cache_collection is None:
        return None

    now = datetime.utcnow()
    try:
        snap = cache_collection.document(
            standings_cache_doc_id(int(local_league_id), int(year))
        ).get()
        data = snap.to_dict() if getattr(snap, "exists", False) else None
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    source = str(data.get("source") or "").strip().lower()
    if source not in ALLOWED_STANDINGS_CACHE_SOURCES:
        return None
    try:
        cache_ver = int(data.get("cache_version") or 0)
    except (TypeError, ValueError):
        cache_ver = 0
    if cache_ver < STANDINGS_CACHE_VERSION:
        return None

    cached_standings = data.get("standings")
    if not isinstance(cached_standings, dict) or not standings_table_usable(cached_standings):
        return None

    is_fresh = False
    expires_at = data.get("expires_at")
    if isinstance(expires_at, str):
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            is_fresh = now <= exp_dt.replace(tzinfo=None)
        except Exception:
            is_fresh = False

    if fresh_only and not is_fresh:
        return None
    return cached_standings, int(year), is_fresh, source


def fetch_highlightly_standings_for_year(
    *,
    highlightly_league_id: Optional[int],
    season_year: int,
    league_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch + normalize Highlightly standings for one season, or None if unusable."""
    if highlightly_league_id is None:
        return None
    key = (api_key or os.getenv("HIGHLIGHTLY_API_KEY") or os.getenv("RAPIDAPI_KEY") or "").strip()
    if not key:
        return None
    try:
        from prediction.highlightly_client import HighlightlyRugbyAPI

        api = HighlightlyRugbyAPI(api_key=key, use_rapidapi=False)
        raw = api.get_standings(int(highlightly_league_id), int(season_year))
    except Exception:
        return None
    if not highlightly_standings_usable(raw):
        return None
    normalized = normalize_highlightly_standings(raw)
    if not isinstance(normalized, dict):
        return None
    league = normalized.get("league") if isinstance(normalized.get("league"), dict) else {}
    if not isinstance(normalized.get("league"), dict):
        normalized["league"] = {}
        league = normalized["league"]
    league.setdefault("name", league_name)
    league["season"] = int(season_year)
    normalized["_source"] = "highlightly"
    normalized.pop("_computed", None)
    if not highlightly_standings_usable(normalized):
        return None
    return normalized


def normalize_highlightly_standings(standings: Dict[str, Any]) -> Dict[str, Any]:
    """Merge alias teams and fill derived fields on a Highlightly standings payload."""
    if not isinstance(standings, dict):
        return standings

    groups = standings.get("groups")
    if not isinstance(groups, list):
        return standings

    for group in groups:
        if not isinstance(group, dict):
            continue
        for list_key in ("standings", "teams"):
            rows = group.get(list_key)
            if not isinstance(rows, list) or not rows:
                continue

            merged: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                team_obj = row.get("team") if isinstance(row.get("team"), dict) else {}
                raw_name = team_obj.get("name") or row.get("name") or ""
                key = _normalize_team_key(raw_name)
                display = _preferred_team_label(key, raw_name)
                if team_obj:
                    team_obj["name"] = display
                row["name"] = display
                _enrich_standings_row(row)

                if key not in merged:
                    merged[key] = row
                elif int(row.get("gamesPlayed") or row.get("played") or 0) >= int(
                    merged[key].get("gamesPlayed") or merged[key].get("played") or 0
                ):
                    merged[key] = row

            ordered = sorted(
                merged.values(),
                key=lambda r: (
                    int(r.get("position") or 999),
                    -int(r.get("points") or 0),
                    -int(r.get("pointsDifference") or r.get("pointsDiff") or 0),
                ),
            )
            for idx, row in enumerate(ordered):
                row["position"] = idx + 1
            group[list_key] = ordered

    source = standings.get("_source") or "highlightly"
    standings["_source"] = source
    standings.pop("_computed", None)
    standings.pop("note", None)
    return standings


def compute_standings_from_db(
    db_path: str,
    our_league_id: int,
    season: Any = None,
    *,
    win_points: int = 4,
    draw_points: int = 2,
    loss_points: int = 0,
    losing_bonus_margin: int = 7,
) -> Optional[Dict[str, Any]]:
    """Return a Highlightly-shaped standings dict computed from results, or None."""
    if int(our_league_id) in SKIP_COMPUTE_LEAGUE_IDS:
        return None
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    try:
        season_str = _resolve_season(conn, our_league_id, season)
        if not season_str:
            return None

        league_row = conn.execute(
            "SELECT name FROM league WHERE id = ?", (our_league_id,)
        ).fetchone()
        league_name = league_row[0] if league_row else None

        matches = conn.execute(
            """
            SELECT e.date_event, e.home_team_id, e.away_team_id,
                   e.home_score, e.away_score, th.name, ta.name
            FROM event e
            JOIN team th ON th.id = e.home_team_id
            JOIN team ta ON ta.id = e.away_team_id
            WHERE e.league_id = ? AND e.season = ?
              AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
            ORDER BY e.date_event ASC, e.id ASC
            """,
            (our_league_id, season_str),
        ).fetchall()
        if not matches:
            return None

        matches = _dedupe_fixtures(matches)
        matches = _exclude_trailing_playoffs(matches)
        if not matches:
            return None

        stats: Dict[str, Dict[str, Any]] = {}

        def team(canonical_key: str, raw_name: str, team_id: int) -> Dict[str, Any]:
            if canonical_key not in stats:
                stats[canonical_key] = {
                    "id": team_id,
                    "name": _preferred_team_label(canonical_key, raw_name),
                    "pl": 0,
                    "w": 0,
                    "d": 0,
                    "l": 0,
                    "pf": 0,
                    "pa": 0,
                    "pts": 0,
                    "bp": 0,
                }
            else:
                stats[canonical_key]["name"] = _preferred_team_label(
                    canonical_key, stats[canonical_key]["name"]
                )
            return stats[canonical_key]

        for _date, hid, aid, hs, as_, hname, aname in matches:
            try:
                hs_i, as_i = int(hs), int(as_)
            except (TypeError, ValueError):
                continue
            home_key = _normalize_team_key(hname)
            away_key = _normalize_team_key(aname)
            home = team(home_key, hname, hid)
            away = team(away_key, aname, aid)
            home["pl"] += 1
            away["pl"] += 1
            home["pf"] += hs_i
            home["pa"] += as_i
            away["pf"] += as_i
            away["pa"] += hs_i

            for side, scored in ((home, hs_i), (away, as_i)):
                try_bonus = _estimate_try_bonus_points(scored)
                if try_bonus:
                    side["pts"] += try_bonus
                    side["bp"] += try_bonus

            if hs_i > as_i:
                home["w"] += 1
                away["l"] += 1
                home["pts"] += win_points
                away["pts"] += loss_points
                if hs_i - as_i <= losing_bonus_margin:
                    away["pts"] += 1
                    away["bp"] += 1
            elif as_i > hs_i:
                away["w"] += 1
                home["l"] += 1
                away["pts"] += win_points
                home["pts"] += loss_points
                if as_i - hs_i <= losing_bonus_margin:
                    home["pts"] += 1
                    home["bp"] += 1
            else:
                home["d"] += 1
                away["d"] += 1
                home["pts"] += draw_points
                away["pts"] += draw_points

        if not stats:
            return None

        rows = sorted(
            stats.values(),
            key=lambda r: (-r["pts"], -(r["pf"] - r["pa"]), -r["pf"], -r["w"], r["name"]),
        )

        standings_list: List[Dict[str, Any]] = []
        try:
            from prediction.team_display_names import display_team_name_for_league
        except Exception:  # pragma: no cover
            display_team_name_for_league = None  # type: ignore

        for idx, r in enumerate(rows):
            diff = r["pf"] - r["pa"]
            display_name = r["name"]
            if display_team_name_for_league is not None:
                try:
                    display_name = display_team_name_for_league(r["name"], our_league_id)
                except Exception:
                    display_name = r["name"]
            standings_list.append(
                {
                    "position": idx + 1,
                    "team": {"id": r["id"], "name": display_name},
                    "points": r["pts"],
                    "gamesPlayed": r["pl"],
                    "played": r["pl"],
                    "wins": r["w"],
                    "draws": r["d"],
                    "loses": r["l"],
                    "losses": r["l"],
                    "scoredPoints": r["pf"],
                    "pointsFor": r["pf"],
                    "receivedPoints": r["pa"],
                    "pointsAgainst": r["pa"],
                    "pointsDifference": diff,
                    "pointsDiff": diff,
                    "bonusPoints": r["bp"],
                }
            )

        start_year = _season_start_year(season_str)
        return {
            "league": {
                "id": our_league_id,
                "name": league_name,
                "season": start_year if start_year is not None else season_str,
                "season_label": season_str,
            },
            "groups": [{"name": None, "standings": standings_list}],
            "_computed": True,
            "_source": "match_results",
            "note": (
                "Computed from regular-season match results (win 4 / draw 2 / "
                "losing bonus for margin \u22647). Try-scoring bonus is estimated "
                "(~4+ tries \u2248 24+ points) because try counts are not in the "
                "data source — table may differ slightly from the official one."
            ),
        }
    finally:
        conn.close()
