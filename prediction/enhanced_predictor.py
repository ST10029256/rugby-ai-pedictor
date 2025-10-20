import sqlite3
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from .highlightly_client import HighlightlyRugbyAPI
from .hybrid_predictor import HybridPredictor

logger = logging.getLogger(__name__)

class EnhancedRugbyPredictor:
    """Enhanced rugby predictor combining AI models with Highlightly API data"""
    
    def __init__(self, db_path: str, highlightly_api_key: str):
        self.db_path = db_path
        self.highlightly_api = HighlightlyRugbyAPI(highlightly_api_key)
        self.hybrid_predictor = HybridPredictor(db_path)
        
        # League mapping between our system and Highlightly
        self.league_mapping = {
            4986: "Rugby Championship",  # Our ID -> Highlightly name
            4446: "United Rugby Championship",
            5069: "Currie Cup",
            4574: "Rugby World Cup",
            4551: "Super Rugby",
            4430: "French Top 14",
            4414: "English Premiership Rugby"
        }
    
    def get_enhanced_prediction(self, 
                              home_team: str, 
                              away_team: str, 
                              league_id: int,
                              match_date: str) -> Dict[str, Any]:
        """Get enhanced prediction combining AI with live data"""
        
        # Get base AI prediction
        base_prediction = self.hybrid_predictor.predict_match(
            home_team, away_team, league_id, match_date
        )
        
        # Get additional data from Highlightly API
        enhanced_data = self._get_enhanced_match_data(home_team, away_team, league_id, match_date)
        
        # Combine predictions
        enhanced_prediction = {
            **base_prediction,
            "enhanced_data": enhanced_data,
            "prediction_confidence": self._calculate_confidence(base_prediction, enhanced_data),
            "data_sources": ["AI_Model", "Highlightly_API", "Historical_Data"]
        }
        
        return enhanced_prediction
    
    def _get_enhanced_match_data(self, 
                                home_team: str, 
                                away_team: str, 
                                league_id: int,
                                match_date: str) -> Dict[str, Any]:
        """Get additional match data from Highlightly API"""
        
        enhanced_data = {
            "live_odds": {},
            "team_form": {},
            "head_to_head": [],
            "highlights": [],
            "match_details": {},
            "standings": {}
        }
        
        try:
            # Get league name for API calls
            league_name = self.league_mapping.get(league_id)
            if not league_name:
                return enhanced_data
            
            # Get matches for the date
            matches = self.highlightly_api.get_matches(
                league_name=league_name,
                date=match_date,
                limit=50
            )
            
            # Find the specific match
            target_match = self._find_match(matches.get('data', []), home_team, away_team)
            if not target_match:
                return enhanced_data
            
            match_id = target_match.get('id')
            if not match_id:
                return enhanced_data
            
            # Get detailed match information
            match_details = self.highlightly_api.get_match_details(match_id)
            enhanced_data["match_details"] = match_details
            
            # Get odds if available
            odds_data = self.highlightly_api.get_odds(match_id=match_id)
            enhanced_data["live_odds"] = self._process_odds(odds_data)
            
            # Get team statistics
            home_team_id = target_match.get('homeTeam', {}).get('id')
            away_team_id = target_match.get('awayTeam', {}).get('id')
            
            if home_team_id and away_team_id:
                # Get team form (last 5 games)
                home_form = self.highlightly_api.get_last_five_games(home_team_id)
                away_form = self.highlightly_api.get_last_five_games(away_team_id)
                
                enhanced_data["team_form"] = {
                    "home": self._process_team_form(home_form),
                    "away": self._process_team_form(away_form)
                }
                
                # Get head-to-head history
                h2h = self.highlightly_api.get_head_to_head(home_team_id, away_team_id)
                enhanced_data["head_to_head"] = self._process_h2h(h2h)
            
            # Get highlights
            highlights = self.highlightly_api.get_highlights(match_id=match_id)
            enhanced_data["highlights"] = highlights.get('data', [])
            
            # Get current standings
            current_year = datetime.now().year
            standings = self.highlightly_api.get_standings(match_id, current_year)
            enhanced_data["standings"] = standings
            
        except Exception as e:
            logger.error(f"Error getting enhanced match data: {e}")
        
        return enhanced_data
    
    def _find_match(self, matches: List[Dict], home_team: str, away_team: str) -> Optional[Dict]:
        """Find specific match in API results"""
        for match in matches:
            home_name = match.get('homeTeam', {}).get('name', '').lower()
            away_name = match.get('awayTeam', {}).get('name', '').lower()
            
            if (home_team.lower() in home_name and away_team.lower() in away_name) or \
               (away_team.lower() in home_name and home_team.lower() in away_name):
                return match
        
        return None
    
    def _process_odds(self, odds_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process odds data for easier consumption"""
        processed_odds = {}
        
        for odds_entry in odds_data.get('data', []):
            bookmaker = odds_entry.get('bookmaker', {}).get('name', 'Unknown')
            markets = odds_entry.get('markets', [])
            
            processed_odds[bookmaker] = {}
            for market in markets:
                market_name = market.get('name', 'Unknown')
                processed_odds[bookmaker][market_name] = market.get('outcomes', [])
        
        return processed_odds
    
    def _process_team_form(self, form_data: List[Dict]) -> Dict[str, Any]:
        """Process team form data"""
        if not form_data:
            return {"games": [], "win_rate": 0, "avg_score": 0}
        
        wins = 0
        total_score = 0
        games = []
        
        for game in form_data:
            home_score = game.get('homeScore', 0)
            away_score = game.get('awayScore', 0)
            is_home = game.get('homeTeam', {}).get('id') == game.get('homeTeam', {}).get('id')
            
            # Determine if team won
            if is_home and home_score > away_score:
                wins += 1
            elif not is_home and away_score > home_score:
                wins += 1
            
            team_score = home_score if is_home else away_score
            total_score += team_score
            
            games.append({
                "date": game.get('date'),
                "score": f"{home_score}-{away_score}",
                "won": (is_home and home_score > away_score) or (not is_home and away_score > home_score)
            })
        
        return {
            "games": games,
            "win_rate": wins / len(form_data) if form_data else 0,
            "avg_score": total_score / len(form_data) if form_data else 0
        }
    
    def _process_h2h(self, h2h_data: List[Dict]) -> List[Dict]:
        """Process head-to-head data"""
        processed_h2h = []
        
        for game in h2h_data:
            processed_h2h.append({
                "date": game.get('date'),
                "home_team": game.get('homeTeam', {}).get('name'),
                "away_team": game.get('awayTeam', {}).get('name'),
                "home_score": game.get('homeScore'),
                "away_score": game.get('awayScore'),
                "league": game.get('league', {}).get('name')
            })
        
        return processed_h2h
    
    def _calculate_confidence(self, base_prediction: Dict, enhanced_data: Dict) -> float:
        """Calculate prediction confidence based on available data"""
        confidence = 0.5  # Base confidence
        
        # Increase confidence based on available data
        if enhanced_data.get("live_odds"):
            confidence += 0.1
        
        if enhanced_data.get("team_form", {}).get("home", {}).get("games"):
            confidence += 0.1
        
        if enhanced_data.get("head_to_head"):
            confidence += 0.1
        
        if enhanced_data.get("match_details"):
            confidence += 0.1
        
        # Increase confidence based on AI prediction strength
        ai_confidence = base_prediction.get("confidence", 0.5)
        confidence = (confidence + ai_confidence) / 2
        
        return min(confidence, 1.0)
    
    def get_live_matches(self, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get live/upcoming matches with enhanced data"""
        try:
            league_name = self.league_mapping.get(league_id) if league_id else None
            today = datetime.now().strftime("%Y-%m-%d")
            
            matches = self.highlightly_api.get_matches(
                league_name=league_name,
                date=today,
                limit=50
            )
            
            live_matches = []
            for match in matches.get('data', []):
                match_state = match.get('state', {}).get('name', '')
                
                if match_state in ['Not started', 'First half', 'Second half', 'Half time']:
                    enhanced_match = {
                        "match_id": match.get('id'),
                        "home_team": match.get('homeTeam', {}).get('name'),
                        "away_team": match.get('awayTeam', {}).get('name'),
                        "date": match.get('date'),
                        "state": match_state,
                        "league": match.get('league', {}).get('name'),
                        "prediction": self._get_quick_prediction(match)
                    }
                    live_matches.append(enhanced_match)
            
            return live_matches
            
        except Exception as e:
            logger.error(f"Error getting live matches: {e}")
            return []
    
    def _get_quick_prediction(self, match: Dict) -> Dict[str, Any]:
        """Get quick prediction for a match"""
        try:
            home_team = match.get('homeTeam', {}).get('name', '')
            away_team = match.get('awayTeam', {}).get('name', '')
            match_date = match.get('date', '')
            
            # Try to map to our league system
            league_name = match.get('league', {}).get('name', '')
            league_id = self._map_league_name_to_id(league_name)
            
            if league_id:
                prediction = self.hybrid_predictor.predict_match(
                    home_team, away_team, league_id, match_date
                )
                return prediction
            
            return {"error": "League not supported"}
            
        except Exception as e:
            logger.error(f"Error getting quick prediction: {e}")
            return {"error": str(e)}
    
    def _map_league_name_to_id(self, league_name: str) -> Optional[int]:
        """Map Highlightly league name to our league ID"""
        reverse_mapping = {v: k for k, v in self.league_mapping.items()}
        return reverse_mapping.get(league_name)

def test_enhanced_predictor():
    """Test the enhanced predictor"""
    import os
    
    api_key = os.getenv('HIGHLIGHTLY_API_KEY')
    if not api_key:
        print("Please set HIGHLIGHTLY_API_KEY environment variable")
        return
    
    predictor = EnhancedRugbyPredictor('data.sqlite', api_key)
    
    print("=== Testing Enhanced Rugby Predictor ===")
    
    # Test live matches
    print("\n1. Testing live matches...")
    live_matches = predictor.get_live_matches()
    print(f"Found {len(live_matches)} live/upcoming matches")
    
    # Test enhanced prediction
    if live_matches:
        print("\n2. Testing enhanced prediction...")
        match = live_matches[0]
        prediction = predictor.get_enhanced_prediction(
            match['home_team'],
            match['away_team'],
            4446,  # URC
            match['date']
        )
        print(f"Enhanced prediction generated with confidence: {prediction.get('prediction_confidence', 0):.2f}")
    
    print("\n✅ Enhanced predictor test completed!")

if __name__ == "__main__":
    test_enhanced_predictor()
