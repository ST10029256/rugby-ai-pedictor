"""SportRadar Rugby Union API client for league standings."""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

from prediction.standings_compute import (
    STANDINGS_CACHE_VERSION,
    _enrich_standings_row,
    normalize_highlightly_standings,
    standings_cache_doc_id,
    standings_table_usable,
)

logger = logging.getLogger(__name__)

BASE_URL = os.getenv(
    "SPORTRADAR_RUGBY_BASE_URL",
    "https://api.sportradar.com/rugby-union/trial/v3/en",
)
REQUEST_DELAY_S = 1.2
MAX_RETRIES = 4

# Local SportsDB league id -> SportRadar competition id
SPORTRADAR_COMPETITION_BY_LOCAL_ID: Dict[int, str] = {
    4986: "sr:competition:789",   # Rugby Championship
    4446: "sr:competition:419",   # United Rugby Championship
    5069: "sr:competition:796",   # Currie Cup
    4574: "sr:competition:421",   # Rugby World Cup
    4551: "sr:competition:422",   # Super Rugby
    4430: "sr:competition:420",   # French Top 14
    4414: "sr:competition:424",   # English Premiership
    4714: "sr:competition:423",   # Six Nations
    5479: "sr:competition:876",   # International Friendlies (no table)
    5480: "sr:competition:51392",  # Nations Championship
}

# Leagues with no meaningful league table in the app
NO_STANDINGS_LOCAL_IDS = {5479}

# Force a specific calendar/start year (SportRadar season label matching)
FORCE_SEASON_YEAR_BY_LOCAL_ID: Dict[int, List[int]] = {
    4574: [2023, 2019],  # RWC — not 2027 placeholder
    5069: [2025, 2026, 2024],  # Currie Cup — prefer 2025 over empty 2026
    4714: [2026, 2025, 2024],  # Six Nations — Feb/Mar tournament labelled by edition year
}

CROSS_YEAR_LOCAL_IDS = {4446, 4414, 4430}

# Fallback when seasons.json is rate-limited or unavailable (from SR audit, Jul 2026).
FALLBACK_SEASON_IDS_BY_LOCAL: Dict[int, List[str]] = {
    4986: ["sr:season:131539"],
    4446: ["sr:season:132050"],
    5069: ["sr:season:131487"],
    4574: ["sr:season:72847"],
    4551: ["sr:season:137092"],
    4430: ["sr:season:132054"],
    4414: ["sr:season:132098"],
    4714: ["sr:season:129277"],
    5479: ["sr:season:137502"],
    5480: ["sr:season:141456"],
}

_seasons_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_SEASONS_CACHE_TTL_S = 86400


def _load_env() -> None:
    if load_dotenv is None:
        return
    from pathlib import Path

    here = Path(__file__).resolve()
    functions_root = here.parents[1]
    repo_root = functions_root.parent
    for p in (
        repo_root / ".env",
        functions_root / ".env",
        functions_root / ".env.local",
    ):
        if p.exists():
            load_dotenv(dotenv_path=p, override=p.name == ".env.local")


_load_env()


def get_api_key() -> str:
    return (
        os.getenv("SPORTRADAR_API_KEY")
        or os.getenv("SPORTRADAR_RUGBY_API_KEY")
        or ""
    ).strip()


def competition_for_local_id(local_league_id: int) -> Optional[str]:
    return SPORTRADAR_COMPETITION_BY_LOCAL_ID.get(int(local_league_id))


def candidate_season_years(
    local_league_id: int,
    *,
    requested_season: Any = None,
    now: Optional[datetime] = None,
) -> List[int]:
    """Ordered calendar/start years to try for a local league id."""
    lid = int(local_league_id)
    forced = FORCE_SEASON_YEAR_BY_LOCAL_ID.get(lid)
    if forced and requested_season is None:
        return list(forced)

    now = now or datetime.utcnow()
    year = now.year
    month = now.month

    if forced:
        out = list(forced)
    elif lid in CROSS_YEAR_LOCAL_IDS:
        # Aug-Jun competitions: Jan-Jul belong to the season that started previous calendar year.
        primary = year - 1 if month <= 7 else year
        out = [primary, primary - 1, primary + 1, year, year - 1]
    else:
        out = [year, year - 1, year + 1, year - 2]

    seen: set[int] = set()
    deduped: List[int] = []
    for y in out:
        if y not in seen:
            seen.add(y)
            deduped.append(y)

    if requested_season is not None:
        try:
            req = int(requested_season)
            merged = [req]
            for y in deduped:
                if y not in merged:
                    merged.append(y)
            return merged
        except (TypeError, ValueError):
            pass

    return deduped


def _parse_season_start_year(season: Dict[str, Any]) -> Optional[int]:
    """Extract a numeric start year from a SportRadar season object."""
    for key in ("year", "name"):
        raw = str(season.get(key) or "").strip()
        if not raw:
            continue
        m = re.search(r"(20\d{2})", raw)
        if m:
            return int(m.group(1))
        m2 = re.match(r"(\d{2})/(\d{2})", raw)
        if m2:
            return 2000 + int(m2.group(1))
    start = str(season.get("start_date") or "")[:4]
    if start.isdigit():
        return int(start)
    return None


def _season_matches_year(season: Dict[str, Any], target_year: int) -> bool:
    start = _parse_season_start_year(season)
    if start == target_year:
        return True
    label = str(season.get("year") or season.get("name") or "")
    yy = target_year % 100
    nyy = (target_year + 1) % 100
    return f"{yy:02d}/{nyy:02d}" in label or f"{target_year}/{target_year + 1}" in label


class SportRadarRugbyClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = (api_key or get_api_key()).strip()
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {"accept": "application/json", "x-api-key": self.api_key}
            )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.configured:
            return None
        url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
        merged = dict(params or {})
        if "live" not in merged and path.endswith("standings.json"):
            merged["live"] = "false"

        for attempt in range(MAX_RETRIES):
            try:
                if attempt:
                    time.sleep(REQUEST_DELAY_S * (attempt + 1))
                else:
                    time.sleep(REQUEST_DELAY_S)
                resp = self.session.get(url, params=merged, timeout=25)
                if resp.status_code == 429:
                    retry_after = 5 * (attempt + 1)
                    try:
                        retry_after = max(retry_after, int(resp.headers.get("Retry-After", retry_after)))
                    except (TypeError, ValueError):
                        pass
                    logger.warning(
                        "SportRadar rate limited on %s (attempt %s, sleep %ss)",
                        path,
                        attempt + 1,
                        retry_after,
                    )
                    time.sleep(min(retry_after, 45))
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else None
            except requests.RequestException as exc:
                logger.warning("SportRadar request failed %s: %s", path, exc)
                if attempt + 1 >= MAX_RETRIES:
                    return None
        return None

    def list_seasons(self, competition_id: str) -> List[Dict[str, Any]]:
        cache_key = competition_id
        cached = _seasons_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _SEASONS_CACHE_TTL_S:
            return cached[1]

        enc = quote(competition_id, safe="")
        data = self._get(f"competitions/{enc}/seasons.json")
        seasons = data.get("seasons") if isinstance(data, dict) else None
        if not isinstance(seasons, list):
            seasons = []
        _seasons_cache[cache_key] = (time.time(), seasons)
        return seasons

    def resolve_season_id(
        self,
        competition_id: str,
        target_year: int,
        *,
        local_league_id: Optional[int] = None,
    ) -> Optional[str]:
        seasons = self.list_seasons(competition_id)
        matches = [s for s in seasons if isinstance(s, dict) and _season_matches_year(s, target_year)]
        if matches:
            matches.sort(key=lambda s: str(s.get("start_date") or ""), reverse=True)
            sid = matches[0].get("id")
            if sid:
                return str(sid)

        if local_league_id is not None:
            for sid in FALLBACK_SEASON_IDS_BY_LOCAL.get(int(local_league_id), []):
                if sid:
                    return str(sid)
        return None

    def resolve_season_ids_for_year(
        self,
        competition_id: str,
        target_year: int,
        *,
        local_league_id: Optional[int] = None,
    ) -> List[str]:
        """Ordered unique season ids to try for summaries (fallbacks first, then API)."""
        out: List[str] = []
        seen: set[str] = set()

        def add(sid: Optional[str]) -> None:
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)

        # Known season ids first — avoids seasons.json when rate-limited.
        if local_league_id is not None:
            for sid in FALLBACK_SEASON_IDS_BY_LOCAL.get(int(local_league_id), []):
                add(str(sid) if sid else None)

        if not out:
            seasons = self.list_seasons(competition_id)
            api_matches = [s for s in seasons if isinstance(s, dict) and _season_matches_year(s, target_year)]
            api_matches.sort(key=lambda s: str(s.get("start_date") or ""), reverse=True)
            for season in api_matches:
                add(str(season.get("id") or "") or None)

        return out

    def fetch_standings_raw(self, season_id: str) -> Optional[Dict[str, Any]]:
        enc = quote(season_id, safe="")
        return self._get(f"seasons/{enc}/standings.json")

    def fetch_season_summaries_raw(
        self,
        season_id: str,
        *,
        start: int = 0,
        limit: int = 200,
    ) -> Optional[Dict[str, Any]]:
        enc = quote(season_id, safe="")
        return self._get(
            f"seasons/{enc}/summaries.json",
            params={"start": int(start), "limit": int(limit)},
        )

    def fetch_event_lineups_raw(self, sport_event_id: str) -> Optional[Dict[str, Any]]:
        enc = quote(str(sport_event_id), safe="")
        return self._get(f"sport_events/{enc}/lineups.json", params={"live": "false"})

    def fetch_competitor_profile_raw(self, competitor_id: str) -> Optional[Dict[str, Any]]:
        enc = quote(str(competitor_id), safe="")
        return self._get(f"competitors/{enc}/profile.json")


def _normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    comp = raw.get("competitor") if isinstance(raw.get("competitor"), dict) else {}
    name = comp.get("name") or raw.get("name") or ""
    played = raw.get("played")
    wins = raw.get("win")
    draws = raw.get("draw")
    losses = raw.get("loss")
    points_for = raw.get("points_for")
    points_against = raw.get("points_against")
    points_diff = raw.get("points_diff")
    if points_diff is None and points_for is not None and points_against is not None:
        try:
            points_diff = int(points_for) - int(points_against)
        except (TypeError, ValueError):
            points_diff = None

    row: Dict[str, Any] = {
        "position": raw.get("rank"),
        "rank": raw.get("rank"),
        "points": raw.get("points"),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "loses": losses,
        "played": played,
        "gamesPlayed": played,
        "pointsFor": points_for,
        "pointsAgainst": points_against,
        "scoredPoints": points_for,
        "receivedPoints": points_against,
        "pointsDifference": points_diff,
        "pointsDiff": points_diff,
        "team": {
            "id": comp.get("id"),
            "name": name,
            "country": comp.get("country"),
            "country_code": comp.get("country_code"),
        },
        "name": name,
    }
    _enrich_standings_row(row)
    return row


def normalize_sportradar_standings(
    raw: Dict[str, Any],
    *,
    league_name: Optional[str],
    display_season: int,
    competition_id: str,
) -> Dict[str, Any]:
    """Convert SportRadar standings payload to the app's groups/standings shape."""
    groups_out: List[Dict[str, Any]] = []
    standings_blocks = raw.get("standings")
    if not isinstance(standings_blocks, list):
        standings_blocks = []

    for block in standings_blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "total").lower()
        if block_type not in ("total", ""):
            continue
        for group in block.get("groups") or []:
            if not isinstance(group, dict):
                continue
            rows_in = group.get("standings")
            if not isinstance(rows_in, list) or not rows_in:
                continue
            rows = [_normalize_row(r) for r in rows_in if isinstance(r, dict)]
            rows.sort(
                key=lambda r: (
                    int(r.get("position") or 999),
                    -int(r.get("points") or 0),
                    -int(r.get("pointsDifference") or 0),
                )
            )
            for idx, row in enumerate(rows):
                row["position"] = idx + 1
            group_name = group.get("name") or group.get("group_name")
            stage = group.get("stage") if isinstance(group.get("stage"), dict) else {}
            if not group_name and stage:
                group_name = stage.get("name")
            groups_out.append(
                {
                    "name": group_name or "Overall",
                    "standings": rows,
                }
            )

    payload: Dict[str, Any] = {
        "league": {
            "name": league_name or raw.get("season", {}).get("name") if isinstance(raw.get("season"), dict) else league_name,
            "season": display_season,
            "competition_id": competition_id,
        },
        "groups": groups_out,
        "_source": "sportradar",
    }
    return normalize_highlightly_standings(payload)


def sportradar_standings_usable(standings: Any, *, local_league_id: Optional[int] = None) -> bool:
    if not standings_table_usable(standings):
        return False
    if not isinstance(standings, dict):
        return False
    if standings.get("_source") not in (None, "sportradar"):
        return False

    max_played = 0
    for group in standings.get("groups") or []:
        if not isinstance(group, dict):
            continue
        for row in group.get("standings") or group.get("teams") or []:
            if not isinstance(row, dict):
                continue
            try:
                max_played = max(max_played, int(row.get("played") or row.get("gamesPlayed") or 0))
            except (TypeError, ValueError):
                pass

    if local_league_id == 5480 and max_played == 0:
        return False
    if local_league_id == 5479:
        return False
    return max_played > 0 or local_league_id == 4574


def try_fetch_sportradar_standings(
    *,
    local_league_id: int,
    league_name: Optional[str],
    requested_season: Any = None,
    cache_collection: Any = None,
    force_refresh: bool = False,
) -> Optional[Tuple[Dict[str, Any], int, bool]]:
    """
    Fetch standings from SportRadar for a local league id.
    Returns (standings_dict, successful_season_year, cache_hit) or None.
    """
    lid = int(local_league_id)
    if lid in NO_STANDINGS_LOCAL_IDS:
        return None

    competition_id = competition_for_local_id(lid)
    if not competition_id:
        return None

    client = SportRadarRugbyClient()
    if not client.configured:
        logger.info("SportRadar API key not configured; skipping SR standings")
        return None

    years = candidate_season_years(lid, requested_season=requested_season)
    logger.info("SportRadar: trying seasons %s for local league %s", years, lid)

    for year in years:
        cache_hit = False
        if cache_collection is not None and not force_refresh:
            try:
                cache_doc_id = standings_cache_doc_id(lid, year)
                cached = cache_collection.document(cache_doc_id).get()
                cached_data = cached.to_dict() if getattr(cached, "exists", False) else None
                if isinstance(cached_data, dict):
                    expires_at = cached_data.get("expires_at")
                    is_fresh = False
                    if isinstance(expires_at, str):
                        try:
                            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                            is_fresh = datetime.utcnow() <= exp_dt.replace(tzinfo=None)
                        except Exception:
                            is_fresh = False
                    cached_standings = cached_data.get("standings")
                    if (
                        is_fresh
                        and cached_data.get("source") == "sportradar"
                        and isinstance(cached_standings, dict)
                        and sportradar_standings_usable(cached_standings, local_league_id=lid)
                    ):
                        logger.info("SportRadar standings cache HIT ldb=%s season=%s", lid, year)
                        return cached_standings, year, True
            except Exception as cache_err:
                logger.warning("SportRadar cache read failed: %s", cache_err)

        season_id = client.resolve_season_id(competition_id, year, local_league_id=lid)
        if not season_id:
            logger.info("SportRadar: no season id for competition=%s year=%s", competition_id, year)
            continue

        raw = client.fetch_standings_raw(season_id)
        if not raw:
            continue

        normalized = normalize_sportradar_standings(
            raw,
            league_name=league_name,
            display_season=year,
            competition_id=competition_id,
        )
        if not sportradar_standings_usable(normalized, local_league_id=lid):
            logger.info("SportRadar standings empty/unusable for year=%s league=%s", year, lid)
            continue

        logger.info(
            "SportRadar standings OK league=%s year=%s teams=%s",
            lid,
            year,
            sum(len(g.get("standings") or []) for g in normalized.get("groups") or []),
        )
        return normalized, year, cache_hit

    return None
