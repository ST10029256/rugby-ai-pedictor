"""
SportDevs API Client
Fetches odds, statistics, standings, and other data to enhance predictions
"""

import requests
import time
from typing import Dict, List, Optional, Any
from functools import lru_cache
import logging
import os
import re
from pathlib import Path
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

logger = logging.getLogger(__name__)


def _load_local_env_files() -> None:
    """Allow a single local key source for scripts + functions."""
    if load_dotenv is None:
        return
    here = Path(__file__).resolve()
    functions_root = here.parents[1]  # rugby-ai-predictor/
    repo_root = functions_root.parent
    for p in (repo_root / ".env", functions_root / ".env"):
        if p.exists():
            load_dotenv(dotenv_path=p, override=False)


_load_local_env_files()

# Local app league_id -> API-Sports league id
APISPORTS_LEAGUE_BY_LOCAL_ID: Dict[int, int] = {
    4986: 85,   # Rugby Championship
    4446: 76,   # United Rugby Championship
    5069: 37,   # Currie Cup
    4574: 69,   # Rugby World Cup
    4551: 71,   # Super Rugby
    4430: 16,   # Top 14
    4414: 13,   # Premiership Rugby
    4714: 51,   # Six Nations
    5479: 84,   # Friendlies
}

# Leagues where API season key follows start-year format (e.g. 2025-2026 => season 2025).
YEAR_SPAN_LOCAL_LEAGUE_IDS = {4414, 4430, 4446}
TEAM_NAME_ALIAS_BY_NORMALIZED: Dict[str, str] = {
    "newsouthwaleswaratahs": "waratahs",
    "wellingtonhurricanes": "hurricanes",
    "hurricanessuperrugby": "hurricanes",
    "otagohighlanders": "highlanders",
    "highlanderssuperrugby": "highlanders",
    "actbrumbies": "brumbies",
    "queenslandreds": "reds",
    "bluessuperrugby": "blues",
    "crusaderssuperrugby": "crusaders",
    "chiefssuperrugby": "chiefs",
}

class SportDevsClient:
    """Client for SportDevs Rugby API"""
    
    def __init__(self, api_key: str, base_url: str = "https://rugby.sportdevs.com"):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.apisports_base_url = os.getenv("APISPORTS_RUGBY_BASE_URL", "https://v1.rugby.api-sports.io")
        self.apisports_api_key = (
            os.getenv("APISPORTS_RUGBY_KEY")
            or os.getenv("APISPORTS_API_KEY")
            or ""
        ).strip()
        self.apisports_session = requests.Session()
        self._apisports_game_cache: Dict[int, Dict[str, Any]] = {}
        if self.apisports_api_key:
            self.apisports_session.headers.update({
                "x-apisports-key": self.apisports_api_key,
                "Accept": "application/json",
            })
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make API request with error handling and rate limiting"""
        url = f"{self.base_url}/{endpoint}"
        try:
            # Add small delay to prevent rate limiting
            time.sleep(0.1)
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if "429" in str(e):
                logger.warning(f"Rate limited for {endpoint}, waiting...")
                time.sleep(1)  # Wait longer on rate limit
                return None
            else:
                logger.warning(f"API request failed for {endpoint}: {e}")
                return None

    def _make_apisports_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make API-Sports Rugby request for live odds."""
        if not self.apisports_api_key:
            return None
        url = f"{self.apisports_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            time.sleep(0.1)
            response = self.apisports_session.get(url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                errors = payload.get("errors")
                if errors:
                    # Different plans/filters can return validation-like errors.
                    logger.debug("API-Sports odds request returned errors for %s %s: %s", endpoint, params, errors)
            return payload
        except requests.exceptions.RequestException as e:
            logger.debug("API-Sports request failed for %s params=%s: %s", endpoint, params, e)
            return None
    
    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _normalize_team_name(name: Optional[str]) -> str:
        txt = str(name or "").strip().lower()
        if not txt:
            return ""
        # Strip common suffixes/prefixes seen across feeds.
        txt = re.sub(r"\bsuper rugby\b", " ", txt)
        txt = re.sub(r"\brugby\b", " ", txt)
        txt = re.sub(r"\bunited rugby championship\b", " ", txt)
        # Keep comparisons tolerant of punctuation/spacing differences.
        normalized = re.sub(r"[^a-z0-9]+", "", txt)
        return TEAM_NAME_ALIAS_BY_NORMALIZED.get(normalized, normalized)

    def _team_names_match(self, left: str, right: str) -> bool:
        l = self._normalize_team_name(left)
        r = self._normalize_team_name(right)
        if not l or not r:
            return False
        if l == r:
            return True
        # Handle provider/app naming variants (e.g. "queenslandreds" vs "reds").
        return l in r or r in l

    @staticmethod
    def _season_from_match_date(match_date: Optional[str], league_id: Optional[int] = None) -> Optional[int]:
        if not match_date:
            return None
        raw = str(match_date).strip()
        if len(raw) < 10:
            return None
        try:
            year = int(raw[:4])
            month = int(raw[5:7])
            lid = int(league_id) if league_id is not None else None
            if lid in YEAR_SPAN_LOCAL_LEAGUE_IDS:
                # Typical rugby club season crosses years (Aug->Jun).
                return year if month >= 8 else (year - 1)
            return year
        except Exception:
            return None

    def _resolve_apisports_game_id(
        self,
        league_id: int,
        season: int,
        match_date: Optional[str],
        home_team: Optional[str],
        away_team: Optional[str],
    ) -> Optional[int]:
        params: Dict[str, Any] = {"league": int(league_id), "season": int(season)}
        if match_date:
            params["date"] = str(match_date)[:10]
        payload = self._make_apisports_request("games", params=params)
        if not isinstance(payload, dict):
            return None
        rows = payload.get("response")
        if not isinstance(rows, list) or not rows:
            return None

        home_norm = self._normalize_team_name(home_team)
        away_norm = self._normalize_team_name(away_team)
        if not home_norm or not away_norm:
            return None

        for row in rows:
            if not isinstance(row, dict):
                continue
            teams = row.get("teams") or {}
            h = self._normalize_team_name((teams.get("home") or {}).get("name"))
            a = self._normalize_team_name((teams.get("away") or {}).get("name"))
            game_id = self._safe_int(row.get("id"))
            if game_id is None:
                continue
            if (self._team_names_match(h, home_norm) and self._team_names_match(a, away_norm)) or (
                self._team_names_match(h, away_norm) and self._team_names_match(a, home_norm)
            ):
                return game_id
        return None

    def _get_apisports_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        gid = self._safe_int(game_id)
        if gid is None:
            return None
        if gid in self._apisports_game_cache:
            return self._apisports_game_cache[gid]
        payload = self._make_apisports_request("games", params={"id": int(gid)})
        if not isinstance(payload, dict):
            return None
        rows = payload.get("response")
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0] if isinstance(rows[0], dict) else None
        if not isinstance(row, dict):
            return None
        self._apisports_game_cache[gid] = row
        return row

    def get_match_odds(
        self,
        match_id: Optional[int] = None,
        league_id: Optional[int] = None,
        match_date: Optional[str] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get betting odds for a specific match"""
        resolved_match_id = self._safe_int(match_id)

        # 1) Prefer API-Sports Rugby odds (real bookmakers).
        # Docs: odds endpoint supports `game`, `league`, `season`, `bookmaker`, `bet`.
        if resolved_match_id is not None:
            payload = self._make_apisports_request("odds", params={"game": int(resolved_match_id)})
            parsed = self._extract_apisports_match_odds(
                payload,
                game_id=resolved_match_id,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
            )
            if parsed:
                return parsed

        # 1b) Resolve API-Sports game id by league/date/teams when local id doesn't match provider id.
        season = self._season_from_match_date(match_date, league_id=league_id)
        if league_id is not None and season is not None:
            api_league_id = APISPORTS_LEAGUE_BY_LOCAL_ID.get(int(league_id), int(league_id))
            resolved_game_id = self._resolve_apisports_game_id(
                league_id=int(api_league_id),
                season=int(season),
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
            )
            if resolved_game_id is not None:
                payload = self._make_apisports_request("odds", params={"game": int(resolved_game_id)})
                parsed = self._extract_apisports_match_odds(
                    payload,
                    game_id=resolved_game_id,
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_date,
                )
                if parsed:
                    return parsed

            # 1c) Fallback to league+season odds and match by team names (best-effort).
            payload = self._make_apisports_request(
                "odds",
                params={"league": int(api_league_id), "season": int(season)},
            )
            parsed = self._extract_apisports_match_odds(
                payload,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
            )
            if parsed:
                return parsed

        # 2) Fallback to legacy SportDevs if available (best-effort).
        odds_data = self._make_request("odds/full-time-results")
        if isinstance(odds_data, list):
            for row in odds_data:
                if resolved_match_id is not None and row.get("match_id") == resolved_match_id:
                    return row
        return None

    def _extract_apisports_match_odds(
        self,
        payload: Optional[Dict[str, Any]],
        game_id: Optional[int] = None,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        match_date: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize API-Sports Rugby odds payload into the existing `extract_odds_features` schema.
        """
        if not payload or not isinstance(payload, dict):
            return None
        resp = payload.get("response")
        if not isinstance(resp, list) or not resp:
            return None

        entry: Optional[Dict[str, Any]] = None
        if game_id is not None:
            for item in resp:
                if not isinstance(item, dict):
                    continue
                row_game_id = self._safe_int((item.get("game") or {}).get("id"))
                if row_game_id is not None and int(row_game_id) == int(game_id):
                    entry = item
                    break

        if entry is None and home_team and away_team:
            home_norm = self._normalize_team_name(home_team)
            away_norm = self._normalize_team_name(away_team)
            target_date = str(match_date or "")[:10]
            for item in resp:
                if not isinstance(item, dict):
                    continue
                teams = (item.get("game") or {}).get("teams") or {}
                h = self._normalize_team_name((teams.get("home") or {}).get("name"))
                a = self._normalize_team_name((teams.get("away") or {}).get("name"))
                game_meta = item.get("game") or {}
                game_date = str(game_meta.get("date") or "")[:10]
                row_game_id = self._safe_int(game_meta.get("id"))

                if (not h or not a) and row_game_id is not None:
                    resolved_game = self._get_apisports_game(int(row_game_id))
                    if resolved_game:
                        rteams = resolved_game.get("teams") or {}
                        h = self._normalize_team_name((rteams.get("home") or {}).get("name"))
                        a = self._normalize_team_name((rteams.get("away") or {}).get("name"))
                        if not game_date:
                            game_date = str(resolved_game.get("date") or "")[:10]

                if (h == home_norm and a == away_norm) or (h == away_norm and a == home_norm):
                    if target_date and game_date and target_date != game_date:
                        continue
                    entry = item
                    break

                if (
                    self._team_names_match(h, home_norm)
                    and self._team_names_match(a, away_norm)
                ) or (
                    self._team_names_match(h, away_norm)
                    and self._team_names_match(a, home_norm)
                ):
                    if target_date and game_date and target_date != game_date:
                        continue
                    entry = item
                    break

        # Keep compatibility with previous behavior only for broad calls
        # where no explicit game/team filters were provided.
        if (
            entry is None
            and game_id is None
            and not (home_team and away_team)
            and isinstance(resp[0], dict)
        ):
            entry = resp[0]
        if not isinstance(entry, dict):
            return None

        bookmakers = entry.get("bookmakers")
        if not isinstance(bookmakers, list) or not bookmakers:
            return None

        rows: List[Dict[str, Any]] = []
        for bk in bookmakers:
            if not isinstance(bk, dict):
                continue
            bk_name = str(bk.get("name") or bk.get("key") or "Unknown")
            bets = bk.get("bets")
            if not isinstance(bets, list):
                continue

            match_bet = None
            for bet in bets:
                if not isinstance(bet, dict):
                    continue
                bet_name = str(bet.get("name") or "").lower()
                # Common market names for winner lines.
                if any(x in bet_name for x in ["match winner", "winner", "1x2", "full time"]):
                    match_bet = bet
                    break
            if match_bet is None and bets:
                match_bet = bets[0] if isinstance(bets[0], dict) else None
            if not isinstance(match_bet, dict):
                continue

            values = match_bet.get("values")
            if not isinstance(values, list):
                continue

            home = draw = away = None
            for v in values:
                if not isinstance(v, dict):
                    continue
                label = str(v.get("value", "")).strip().lower()
                odd_raw = v.get("odd")
                try:
                    odd = float(odd_raw)
                except (TypeError, ValueError):
                    continue
                if odd <= 0:
                    continue
                if label in {"1", "home"}:
                    home = odd
                elif label in {"x", "draw"}:
                    draw = odd
                elif label in {"2", "away"}:
                    away = odd

            if home is None and away is None:
                continue

            rows.append({
                "bookmaker": bk_name,
                "home": home,
                "draw": draw,
                "away": away,
            })

        if not rows:
            return None

        return {
            "source": "api_sports",
            "periods": [
                {
                    "period_type": "Match Winner",
                    "odds": rows,
                }
            ],
        }
    
    def get_all_odds(self) -> List[Dict]:
        """Get all available odds data"""
        odds_data = self._make_request("odds/full-time-results")
        if odds_data and isinstance(odds_data, list):
            return odds_data
        return []
    
    @lru_cache(maxsize=500)
    def get_match_statistics(self, match_id: int) -> Optional[Dict]:
        """Get detailed statistics for a specific match"""
        stats_data = self._make_request("matches-statistics")
        if stats_data and isinstance(stats_data, list):
            # Find stats for this match
            for match_stats in stats_data:
                if match_stats.get('match_id') == match_id:
                    return match_stats
        return None
    
    def get_all_match_statistics(self) -> List[Dict]:
        """Get all available match statistics"""
        stats_data = self._make_request("matches-statistics")
        if stats_data and isinstance(stats_data, list):
            return stats_data
        return []
    
    def get_matches_by_date(self, date: Optional[str] = None) -> List[Dict]:
        """Get matches by date (format: YYYY-MM-DD)"""
        params = {"date": date} if date else None
        matches_data = self._make_request("matches-by-date", params=params)
        if matches_data and isinstance(matches_data, list):
            return matches_data
        return []
    
    def get_all_matches(self) -> List[Dict]:
        """Get all available matches"""
        matches_data = self._make_request("matches")
        if matches_data and isinstance(matches_data, list):
            return matches_data
        return []
    
    def get_match_weather(self, match_id: Optional[int] = None) -> Optional[Any]:
        """Get weather data for matches"""
        weather_data = self._make_request("matches-weather")
        if weather_data and isinstance(weather_data, list):
            if match_id:
                for w in weather_data:
                    if w.get('match_id') == match_id:
                        return w
            return weather_data  # Returns list if no match_id specified
        return None
    
    @lru_cache(maxsize=200)
    def get_standings(self, league_id: Optional[int] = None) -> List[Dict]:
        """Get league standings"""
        params = {"league_id": league_id} if league_id else None
        standings_data = self._make_request("standings", params=params)
        if standings_data and isinstance(standings_data, list):
            return standings_data
        return []
    
    @lru_cache(maxsize=100)
    def get_team_players(self, team_id: int) -> List[Dict]:
        """Get players for a specific team"""
        players_data = self._make_request("players-by-team", params={"team_id": team_id})
        if players_data and isinstance(players_data, list):
            return players_data
        return []
    
    def get_leagues(self) -> List[Dict]:
        """Get all available leagues"""
        leagues_data = self._make_request("leagues")
        if leagues_data and isinstance(leagues_data, list):
            return leagues_data
        return []
    
    def get_coaches(self) -> List[Dict]:
        """Get all coaches"""
        coaches_data = self._make_request("coaches")
        if coaches_data and isinstance(coaches_data, list):
            return coaches_data
        return []
    
    def get_referees(self) -> List[Dict]:
        """Get all referees"""
        refs_data = self._make_request("referees")
        if refs_data and isinstance(refs_data, list):
            return refs_data
        return []

def extract_odds_features(odds_data: Optional[Dict]) -> Dict[str, float]:
    """Extract useful features from odds data"""
    if not odds_data or 'periods' not in odds_data:
        return {
            'avg_home_odds': 0.0,
            'avg_draw_odds': 0.0,
            'avg_away_odds': 0.0,
            'home_win_probability': 0.5,
            'draw_probability': 0.0,
            'away_win_probability': 0.5,
            'odds_confidence': 0.0
        }
    
    # Get full-time odds (not half-time)
    full_time_odds = None
    for period in odds_data['periods']:
        if period.get('period_type') in ['Full Time', 'FT', 'ALL', 'Match']:
            full_time_odds = period.get('odds', [])
            break
    
    # If no full-time, try first period or any period
    if not full_time_odds and odds_data['periods']:
        full_time_odds = odds_data['periods'][0].get('odds', [])
    
    if not full_time_odds:
        return {
            'avg_home_odds': 0.0,
            'avg_draw_odds': 0.0,
            'avg_away_odds': 0.0,
            'home_win_probability': 0.5,
            'draw_probability': 0.0,
            'away_win_probability': 0.5,
            'odds_confidence': 0.0
        }
    
    # Calculate average odds across all bookmakers
    home_odds_list = []
    draw_odds_list = []
    away_odds_list = []
    
    for bookmaker in full_time_odds:
        try:
            h = float(bookmaker.get('home')) if bookmaker.get('home') is not None else None
            d = float(bookmaker.get('draw')) if bookmaker.get('draw') is not None else None
            a = float(bookmaker.get('away')) if bookmaker.get('away') is not None else None
        except (TypeError, ValueError):
            h = d = a = None
        if h is not None and h > 0:
            home_odds_list.append(h)
        if d is not None and d > 0:
            draw_odds_list.append(d)
        if a is not None and a > 0:
            away_odds_list.append(a)
    
    # Calculate averages
    avg_home_odds = sum(home_odds_list) / len(home_odds_list) if home_odds_list else 2.0
    avg_draw_odds = sum(draw_odds_list) / len(draw_odds_list) if draw_odds_list else 10.0
    avg_away_odds = sum(away_odds_list) / len(away_odds_list) if away_odds_list else 2.0
    
    # Convert odds to implied probabilities (more useful for ML)
    # Probability = 1 / odds, then normalize
    home_prob_raw = 1 / avg_home_odds if avg_home_odds > 0 else 0.33
    draw_prob_raw = 1 / avg_draw_odds if avg_draw_odds > 0 else 0.33
    away_prob_raw = 1 / avg_away_odds if avg_away_odds > 0 else 0.33
    
    total_prob = home_prob_raw + draw_prob_raw + away_prob_raw
    
    home_prob = home_prob_raw / total_prob if total_prob > 0 else 0.33
    draw_prob = draw_prob_raw / total_prob if total_prob > 0 else 0.33
    away_prob = away_prob_raw / total_prob if total_prob > 0 else 0.33
    
    # Confidence measure (how much do bookmakers agree?)
    if len(home_odds_list) > 1:
        import numpy as np
        home_std = np.std(home_odds_list)
        away_std = np.std(away_odds_list)
        # Lower std = higher agreement = higher confidence
        odds_confidence = 1.0 / (1.0 + home_std + away_std)
    else:
        odds_confidence = 0.5
    
    return {
        'avg_home_odds': float(avg_home_odds),
        'avg_draw_odds': float(avg_draw_odds),
        'avg_away_odds': float(avg_away_odds),
        'home_win_probability': float(home_prob),
        'draw_probability': float(draw_prob),
        'away_win_probability': float(away_prob),
        'odds_confidence': float(odds_confidence),
        'bookmaker_count': len(home_odds_list)
    }

def extract_match_stats_features(stats_data: Optional[Dict]) -> Dict[str, float]:
    """Extract useful features from match statistics"""
    if not stats_data or 'statistics' not in stats_data:
        return {
            'home_possession_pct': 50.0,
            'away_possession_pct': 50.0,
            'possession_advantage': 0.0,
            'home_conversions': 0.0,
            'away_conversions': 0.0,
            'home_tries': 0.0,
            'away_tries': 0.0
        }
    
    stats = stats_data['statistics']
    features = {
        'home_possession_pct': 50.0,
        'away_possession_pct': 50.0,
        'home_conversions': 0.0,
        'away_conversions': 0.0,
        'home_tries': 0.0,
        'away_tries': 0.0
    }
    
    for stat in stats:
        stat_type = stat.get('type', '')
        period = stat.get('period', '')
        
        # Get full match stats (ALL period)
        if period == 'ALL':
            if 'possession' in stat_type.lower():
                home_val = stat.get('home_team', '50%')
                away_val = stat.get('away_team', '50%')
                features['home_possession_pct'] = float(home_val.rstrip('%'))
                features['away_possession_pct'] = float(away_val.rstrip('%'))
            
            if 'conversion' in stat_type.lower():
                features['home_conversions'] = float(stat.get('home_team', 0))
                features['away_conversions'] = float(stat.get('away_team', 0))
            
            if 'tries' in stat_type.lower() or 'try' in stat_type.lower():
                features['home_tries'] = float(stat.get('home_team', 0))
                features['away_tries'] = float(stat.get('away_team', 0))
    
    features['possession_advantage'] = features['home_possession_pct'] - features['away_possession_pct']
    
    return features

def extract_standings_features(standings_data: List[Dict], team_id: int, league_id: int) -> Dict[str, float]:
    """Extract team standings features"""
    default = {
        'team_league_position': 8.0,  # Mid-table default
        'team_points': 0.0,
        'team_win_rate': 0.5,
        'team_goal_diff': 0.0,
        'team_form_score': 0.5
    }
    
    if not standings_data:
        return default
    
    # Find standings for this league
    for standing in standings_data:
        if standing.get('league_id') == league_id:
            competitors = standing.get('competitors', [])
            
            # Find this team
            for team in competitors:
                if team.get('team_id') == team_id:
                    matches = team.get('matches', 1)
                    wins = team.get('wins', 0)
                    
                    return {
                        'team_league_position': float(team.get('position', 8)),
                        'team_points': float(team.get('points', 0)),
                        'team_win_rate': wins / matches if matches > 0 else 0.5,
                        'team_goal_diff': float(team.get('scores_for', 0) - team.get('scores_against', 0)),
                        'team_form_score': (wins / matches if matches > 0 else 0.5)
                    }
    
    return default

def extract_weather_features(weather_data: Optional[Dict]) -> Dict[str, float]:
    """Extract weather features"""
    default = {
        'temperature': 15.0,  # Celsius, neutral
        'wind_speed': 10.0,   # km/h, neutral
        'rainfall': 0.0,      # mm
        'weather_impact_score': 0.5  # 0-1, 0.5 = neutral
    }
    
    if not weather_data:
        return default
    
    temp = float(weather_data.get('temperature', 15.0))
    wind = float(weather_data.get('wind_speed', 10.0))
    rain = float(weather_data.get('rainfall', 0.0))
    
    # Calculate weather impact (extreme = harder to play)
    temp_impact = abs(temp - 15) / 30.0  # Deviation from ideal
    wind_impact = min(wind / 40.0, 1.0)   # High wind = harder
    rain_impact = min(rain / 10.0, 1.0)   # Rain = harder
    
    weather_impact = (temp_impact + wind_impact + rain_impact) / 3.0
    
    return {
        'temperature': temp,
        'wind_speed': wind,
        'rainfall': rain,
        'weather_impact_score': weather_impact
    }
