import requests
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class HighlightlyRugbyAPI:
    """Highlightly Rugby API client for enhanced rugby data"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://rugby.highlightly.net"
        self.headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": "rugby-highlights-api.p.rapidapi.com"
        }
    
    def get_leagues(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get all available rugby leagues"""
        try:
            response = requests.get(
                f"{self.base_url}/leagues",
                headers=self.headers,
                params={"limit": limit, "offset": offset}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching leagues: {e}")
            return {"data": [], "pagination": {}}
    
    def get_matches(self, 
                   league_id: Optional[int] = None,
                   league_name: Optional[str] = None,
                   date: Optional[str] = None,
                   season: Optional[int] = None,
                   limit: int = 100,
                   offset: int = 0) -> Dict[str, Any]:
        """Get rugby matches with various filters"""
        try:
            params: Dict[str, Any] = {"limit": limit, "offset": offset}
            if league_id:
                params["leagueId"] = int(league_id)
            if league_name:
                params["leagueName"] = str(league_name)
            if date:
                params["date"] = str(date)
            if season:
                params["season"] = int(season)
                
            response = requests.get(
                f"{self.base_url}/matches",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching matches: {e}")
            return {"data": [], "pagination": {}}
    
    def get_match_details(self, match_id: int) -> Dict[str, Any]:
        """Get detailed match information including lineups, predictions, etc."""
        try:
            response = requests.get(
                f"{self.base_url}/matches/{match_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching match details for {match_id}: {e}")
            return {}
    
    def get_odds(self, 
                 match_id: Optional[int] = None,
                 league_id: Optional[int] = None,
                 bookmaker_id: Optional[int] = None,
                 odds_type: str = "prematch",
                 limit: int = 5) -> Dict[str, Any]:
        """Get match odds (disabled; manual odds entry used instead)."""
        try:
            # Odds API disabled: return empty structure so callers don't fetch from network
            logger.info("Odds API disabled: using manual odds input")
            return {"data": [], "pagination": {}}
        except Exception:
            return {"data": [], "pagination": {}}
    
    def get_team_stats(self, team_id: int, from_date: str) -> Dict[str, Any]:
        """Get team statistics"""
        try:
            response = requests.get(
                f"{self.base_url}/teams/statistics/{team_id}",
                headers=self.headers,
                params={"fromDate": from_date}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching team stats for {team_id}: {e}")
            return {}
    
    def get_head_to_head(self, team_id_one: int, team_id_two: int) -> List[Dict[str, Any]]:
        """Get head-to-head match history between two teams"""
        try:
            response = requests.get(
                f"{self.base_url}/head-2-head",
                headers=self.headers,
                params={"teamIdOne": team_id_one, "teamIdTwo": team_id_two}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching head-to-head: {e}")
            return []
    
    def get_last_five_games(self, team_id: int) -> List[Dict[str, Any]]:
        """Get last five finished games for a team"""
        try:
            response = requests.get(
                f"{self.base_url}/last-five-games",
                headers=self.headers,
                params={"teamId": team_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching last five games for {team_id}: {e}")
            return []
    
    def get_highlights(self, 
                      match_id: Optional[int] = None,
                      league_id: Optional[int] = None,
                      date: Optional[str] = None,
                      limit: int = 40) -> Dict[str, Any]:
        """Get match highlights"""
        try:
            params: Dict[str, Any] = {"limit": limit}
            if match_id:
                params["matchId"] = int(match_id)
            if league_id:
                params["leagueId"] = int(league_id)
            if date:
                params["date"] = str(date)
                
            response = requests.get(
                f"{self.base_url}/highlights",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching highlights: {e}")
            return {"data": [], "pagination": {}}
    
    def get_standings(self, league_id: int, season: int) -> Dict[str, Any]:
        """Get league standings"""
        try:
            response = requests.get(
                f"{self.base_url}/standings",
                headers=self.headers,
                params={"leagueId": league_id, "season": season}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching standings: {e}")
            return {"groups": [], "league": {}}

def test_highlightly_api():
    """Test the Highlightly API integration"""
    api_key = os.getenv('HIGHLIGHTLY_API_KEY')
    if not api_key:
        print("Please set HIGHLIGHTLY_API_KEY environment variable")
        return
    
    api = HighlightlyRugbyAPI(api_key)
    
    print("=== Testing Highlightly Rugby API ===")
    
    # Test leagues
    print("\n1. Testing leagues...")
    leagues = api.get_leagues(limit=10)
    print(f"Found {len(leagues.get('data', []))} leagues")
    
    # Test matches
    print("\n2. Testing matches...")
    matches = api.get_matches(limit=5)
    print(f"Found {len(matches.get('data', []))} matches")
    
    # Test odds (if available)
    print("\n3. Testing odds...")
    odds = api.get_odds(limit=3)
    print(f"Found {len(odds.get('data', []))} odds entries")
    
    print("\n✅ API integration test completed!")

if __name__ == "__main__":
    test_highlightly_api()
