import sqlite3
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from .highlightly_client import HighlightlyRugbyAPI
from .hybrid_predictor import MultiLeaguePredictor
from .highlightly_leagues import extract_scores

logger = logging.getLogger(__name__)

class EnhancedRugbyPredictor:
    """Enhanced rugby predictor combining AI models with Highlightly API data"""
    
    def __init__(self, db_path: str, highlightly_api_key: str):
        self.db_path = db_path
        self.highlightly_api = HighlightlyRugbyAPI(highlightly_api_key)
        self.hybrid_predictor = MultiLeaguePredictor(db_path)
        
        # League mapping between our system and Highlightly
        self.league_mapping = {
            4986: "Rugby Championship",  # Our ID -> Highlightly name
            4446: "United Rugby Championship",
            5069: "Currie Cup",
            4574: "Rugby World Cup",
            4551: "Super Rugby",
            4430: "French Top 14",
            4414: "English Premiership Rugby",
            4714: "Six Nations Championship",
            5479: "Rugby Union International Friendlies",
            5480: "Nations Championship",
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
        """Process odds data for easier consumption."""
        from .highlightly_odds import normalize_highlightly_odds

        normalized = normalize_highlightly_odds(odds_data)
        if normalized and normalized.get("periods"):
            processed: Dict[str, Any] = {}
            for row in normalized["periods"][0].get("odds") or []:
                bk = str(row.get("bookmaker") or "Unknown")
                outcomes = []
                if row.get("home") is not None:
                    outcomes.append({"name": "Home", "odd": row["home"]})
                if row.get("draw") is not None:
                    outcomes.append({"name": "Draw", "odd": row["draw"]})
                if row.get("away") is not None:
                    outcomes.append({"name": "Away", "odd": row["away"]})
                processed[bk] = {"Full Time Result": outcomes}
            return processed

        processed_odds: Dict[str, Any] = {}
        for odds_entry in odds_data.get("data", []):
            bookmaker = odds_entry.get("bookmaker", {}).get("name", "Unknown")
            markets = odds_entry.get("markets", [])
            processed_odds[bookmaker] = {}
            for market in markets:
                market_name = market.get("name", "Unknown")
                processed_odds[bookmaker][market_name] = market.get("outcomes", [])

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
    
    @staticmethod
    def _extract_match_state(match: Dict[str, Any]) -> str:
        state = match.get("state") or match.get("status") or ""
        if isinstance(state, dict):
            return str(
                state.get("name")
                or state.get("description")
                or state.get("short")
                or ""
            ).strip()
        return str(state or "").strip()

    @staticmethod
    def _extract_game_time(match: Dict[str, Any], state_name: str) -> Optional[str]:
        """Best-effort clock/minute from Highlightly's inconsistent rugby payloads."""
        state = match.get("state") if isinstance(match.get("state"), dict) else {}
        candidates = [
            match.get("minute"),
            match.get("clock"),
            match.get("elapsed"),
            match.get("gameTime"),
            match.get("game_time"),
            match.get("time"),
            state.get("minute") if isinstance(state, dict) else None,
            state.get("clock") if isinstance(state, dict) else None,
            state.get("elapsed") if isinstance(state, dict) else None,
            state.get("time") if isinstance(state, dict) else None,
        ]
        for raw in candidates:
            if raw is None or raw == "":
                continue
            if isinstance(raw, (int, float)):
                minute = int(raw)
                return str(minute) if minute >= 0 else None
            text = str(raw).strip()
            if not text:
                continue
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                return digits
            if "'" in text or "’" in text:
                return text.replace("’", "'").rstrip("'")
        # Rugby halves without an explicit clock still need a phase label.
        if state_name in {"First half", "Second half", "Half time"}:
            return None
        return None

    @staticmethod
    def _extract_start_time(date_raw: Any) -> Optional[str]:
        if not date_raw:
            return None
        text = str(date_raw).strip()
        # ISO-ish: 2026-09-08T19:35:00Z
        if "T" in text and len(text) >= 16:
            hhmm = text.split("T", 1)[1][:5]
            if hhmm and hhmm[0].isdigit():
                return hhmm
        return None

    def get_live_matches(self, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get live/upcoming matches with scores, clock, venue and logos."""
        try:
            try:
                league_id = int(league_id) if league_id is not None else None
            except (TypeError, ValueError):
                league_id = None
            league_name = self.league_mapping.get(league_id) if league_id else None
            hl_league_id = None
            if league_id is not None:
                try:
                    from .highlightly_leagues import HIGHLIGHTLY_LEAGUE_MAPPINGS
                    mapped = HIGHLIGHTLY_LEAGUE_MAPPINGS.get(league_id)
                    if mapped:
                        hl_league_id = int(mapped[1])
                except Exception:
                    hl_league_id = None
            try:
                from zoneinfo import ZoneInfo
                now_sast = datetime.now(ZoneInfo("Africa/Johannesburg"))
            except Exception:
                now_sast = datetime.utcnow() + timedelta(hours=2)
            day_list = [
                now_sast.strftime("%Y-%m-%d"),
                (now_sast + timedelta(days=1)).strftime("%Y-%m-%d"),
            ]

            raw_matches = []
            seen_ids = set()
            for day in day_list:
                payload = self.highlightly_api.get_matches(
                    league_id=hl_league_id,
                    league_name=None if hl_league_id else league_name,
                    date=day,
                    limit=50,
                )
                for row in payload.get("data", []) or []:
                    if not isinstance(row, dict):
                        continue
                    row_id = row.get("id")
                    if row_id is not None:
                        if row_id in seen_ids:
                            continue
                        seen_ids.add(row_id)
                    raw_matches.append(row)

            live_states = {"Not started", "First half", "Second half", "Half time"}
            live_matches = []
            for match in raw_matches:
                if not isinstance(match, dict):
                    continue
                match_state = self._extract_match_state(match) or "Not started"
                if match_state not in live_states:
                    continue

                home_team = match.get("homeTeam") or {}
                away_team = match.get("awayTeam") or {}
                league = match.get("league") or {}
                venue = match.get("venue") or {}
                round_info = match.get("round") or {}

                home_score, away_score = extract_scores(match)
                date_raw = match.get("date")
                start_time = self._extract_start_time(date_raw)
                game_time = self._extract_game_time(match, match_state)
                is_live = match_state in {"First half", "Second half", "Half time"}

                venue_name = None
                if isinstance(venue, dict):
                    venue_name = venue.get("name") or venue.get("venue")
                elif venue:
                    venue_name = str(venue)

                round_name = None
                if isinstance(round_info, dict):
                    round_name = round_info.get("name") or round_info.get("round")
                elif round_info:
                    round_name = str(round_info)

                formatted_date = None
                if date_raw:
                    formatted_date = str(date_raw).split("T", 1)[0]

                enhanced_match = {
                    "match_id": match.get("id"),
                    "home_team": home_team.get("name") if isinstance(home_team, dict) else home_team,
                    "away_team": away_team.get("name") if isinstance(away_team, dict) else away_team,
                    "home_logo": home_team.get("logo") if isinstance(home_team, dict) else None,
                    "away_logo": away_team.get("logo") if isinstance(away_team, dict) else None,
                    "home_score": home_score if home_score is not None else (0 if is_live else None),
                    "away_score": away_score if away_score is not None else (0 if is_live else None),
                    "date": date_raw,
                    "date_event": date_raw,
                    "formatted_date": formatted_date,
                    "start_time": start_time,
                    "game_time": game_time,
                    "state": match_state,
                    "is_live": is_live,
                    "league": league.get("name") if isinstance(league, dict) else league_name,
                    "venue": venue_name,
                    "round": round_name,
                    "prediction": {},
                }
                live_matches.append(enhanced_match)

            # Live boards first, then half-time, then kickoff waiting.
            rank = {"First half": 0, "Second half": 0, "Half time": 1, "Not started": 2}
            live_matches.sort(key=lambda m: (rank.get(m.get("state"), 9), str(m.get("date") or "")))
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
