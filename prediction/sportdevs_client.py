"""
SportDevs API Client
Fetches odds, statistics, standings, and other data to enhance predictions
"""

import requests
import time
from typing import Dict, List, Optional, Any
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class SportDevsClient:
    """Client for SportDevs Rugby API
    
    Supports both direct SportDevs API and RapidAPI formats.
    Set use_rapidapi=True if your API key is from RapidAPI.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://rugby.sportdevs.com", use_rapidapi: bool = False, rapidapi_host: str = "sportdevs.p.rapidapi.com"):
        self.base_url = base_url
        self.api_key = api_key
        self.use_rapidapi = use_rapidapi
        
        if use_rapidapi:
            # RapidAPI format
            self.headers = {
                "Accept": "application/json",
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": rapidapi_host
            }
        else:
            # Standard SportDevs format
            self.headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-API-Key": api_key
            }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make API request with error handling and rate limiting"""
        url = f"{self.base_url}/{endpoint}"
        try:
            # Add small delay to prevent rate limiting
            time.sleep(0.1)
            response = self.session.get(url, params=params, timeout=15)
            
            # Check for subscription issues (RapidAPI)
            if response.status_code == 403:
                try:
                    error_data = response.json()
                    if "not subscribed" in str(error_data.get("message", "")).lower():
                        logger.error(f"Not subscribed to API on RapidAPI. Please subscribe to SportDevs Rugby API on RapidAPI.")
                        return None
                except:
                    pass
            
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
    
    def get_match_odds(self, match_id: int) -> Optional[Dict]:
        """Get betting odds for a specific match"""
        # For now, return None to avoid rate limiting
        # In production, would implement proper match-specific odds lookup
        return None
    
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
    
    def get_match_lineups(self, match_id: int) -> Optional[Dict]:
        """Get team lineups for a specific match"""
        lineups_data = self._make_request("matches-lineups", params={"match_id": match_id})
        if lineups_data:
            return lineups_data
        return None
    
    def get_team_news(self, team_id: int, limit: int = 50) -> List[Dict]:
        """Get news/media content for a specific team"""
        params = {"team_id": team_id, "limit": limit}
        news_data = self._make_request("media-teams", params=params)
        if news_data and isinstance(news_data, list):
            return news_data
        return []
    
    def get_league_news(self, league_id: Optional[int] = None, limit: int = 50) -> List[Dict]:
        """Get news for a specific league or all leagues"""
        params: Dict[str, Any] = {"limit": limit}
        if league_id:
            params["league_id"] = league_id
        news_data = self._make_request("media-leagues", params=params)
        if news_data and isinstance(news_data, list):
            return news_data
        return []
    
    def get_all_news(self, limit: int = 100) -> List[Dict]:
        """Get all available rugby news"""
        params = {"limit": limit}
        news_data = self._make_request("media", params=params)
        if news_data and isinstance(news_data, list):
            return news_data
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
        if 'home' in bookmaker and bookmaker['home'] > 0:
            home_odds_list.append(bookmaker['home'])
        if 'draw' in bookmaker and bookmaker['draw'] > 0:
            draw_odds_list.append(bookmaker['draw'])
        if 'away' in bookmaker and bookmaker['away'] > 0:
            away_odds_list.append(bookmaker['away'])
    
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
