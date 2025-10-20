#!/usr/bin/env python3
"""
Expert-Level Hybrid AI Rugby Prediction App
Combines optimized AI with live SportDevs odds for maximum accuracy
"""

import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pytz

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Import Highlightly API integration
try:
    from prediction.highlightly_client import HighlightlyRugbyAPI
    HIGHLIGHTLY_AVAILABLE = True
except ImportError:
    HighlightlyRugbyAPI = None  # type: ignore
    HIGHLIGHTLY_AVAILABLE = False
    st.warning("⚠️ Highlightly API not available - enhanced features disabled")

# Try to import XGBoost FIRST to ensure it's available
XGBOOST_AVAILABLE = False
XGBOOST_VERSION = None

# Multiple import strategies for XGBoost in Streamlit
import_strategies = [
    # Strategy 1: Direct import
    lambda: __import__('xgboost'),
    # Strategy 2: Import with fromlist
    lambda: __import__('xgboost', fromlist=['']),
    # Strategy 3: Add to sys.modules first
    lambda: (sys.modules.setdefault('xgboost', __import__('xgboost')), None)[1],
    # Strategy 4: Force import with exec
    lambda: exec('import xgboost', globals()),
]

for i, strategy in enumerate(import_strategies):
    try:
        strategy()
        import xgboost  # type: ignore
        XGBOOST_AVAILABLE = True
        XGBOOST_VERSION = xgboost.__version__
        # XGBoost imported successfully
        
        # Ensure XGBoost is available in the global namespace for pickle
        globals()['xgboost'] = xgboost
        sys.modules['xgboost'] = xgboost
        
        # XGBoost imported successfully
        break
    except (ImportError, Exception) as e:
        # XGBoost import strategy failed
        continue

if not XGBOOST_AVAILABLE:
    # All XGBoost import strategies failed
    pass

# Import our expert AI components
from prediction.features import build_feature_table, FeatureConfig

# Configuration
SPORTDEVS_API_KEY = os.getenv("SPORTDEVS_API_KEY", "qwh9orOkZESulf4QBhf0IQ")  # Your API key
THESPORTSDB_API_KEY = os.getenv("THESPORTSDB_API_KEY", "123")  # TheSportsDB API key
APISPORTS_API_KEY = os.getenv("APISPORTS_API_KEY", "")  # APISports API key

# Timezone configuration for South Africa
SA_TIMEZONE = pytz.timezone('Africa/Johannesburg')

def convert_utc_to_sa_time(utc_datetime_str: str) -> tuple[str, str]:
    """Convert UTC datetime string to South African time
    Returns: (formatted_date, start_time) in SA timezone
    """
    try:
        # Parse UTC datetime
        utc_dt = datetime.fromisoformat(utc_datetime_str.replace('Z', '+00:00'))
        
        # Convert to South African timezone
        sa_dt = utc_dt.astimezone(SA_TIMEZONE)
        
        # Format for display
        formatted_date = sa_dt.strftime('%Y-%m-%d')
        start_time = sa_dt.strftime('%H:%M')
        
        return formatted_date, start_time
    except Exception:
        return 'TBD', 'TBD'
LEAGUE_CONFIGS = {
    4986: {"name": "Rugby Championship", "neutral_mode": False},
    4446: {"name": "United Rugby Championship", "neutral_mode": False},
    5069: {"name": "Currie Cup", "neutral_mode": False},
    4574: {"name": "Rugby World Cup", "neutral_mode": True},
    4551: {"name": "Super Rugby", "neutral_mode": False},
    4430: {"name": "French Top 14", "neutral_mode": False},
    4414: {"name": "English Premiership Rugby", "neutral_mode": False},
}

@st.cache_data(ttl=1800)  # Cache for 30 minutes to reduce API calls
def get_highlightly_data(home_team: str, away_team: str, league_id: int, match_date: str) -> Dict:
    """Get enhanced data from Highlightly API"""
    if not HIGHLIGHTLY_AVAILABLE:
        return {}
    
    try:
        api_key = os.getenv('HIGHLIGHTLY_API_KEY')
        if not api_key:
            # Fallback: Set the API key directly (temporary fix)
            api_key = '9c27c5f8-9437-4d42-8cc9-5179d3290a5b'
        
        if not api_key or not HighlightlyRugbyAPI:
            return {}
        
        api = HighlightlyRugbyAPI(api_key)
        
        # League mapping
        league_mapping = {
            4986: "Rugby Championship",
            4446: "United Rugby Championship", 
            5069: "Currie Cup",
            4574: "Rugby World Cup",
            4551: "Super Rugby",
            4430: "French Top 14",
            4414: "English Premiership Rugby"
        }
        
        league_name = league_mapping.get(league_id)
        if not league_name:
            return {}
        
        # Get matches for the date
        matches = api.get_matches(
            league_name=league_name,
            date=match_date,
            limit=50
        )
        
        # Find the specific match
        target_match = None
        for match in matches.get('data', []):
            home_name = match.get('homeTeam', {}).get('name', '').lower()
            away_name = match.get('awayTeam', {}).get('name', '').lower()
            
            if (home_team.lower() in home_name and away_team.lower() in away_name) or \
               (away_team.lower() in home_name and home_team.lower() in away_name):
                target_match = match
                break
        
        if not target_match:
            return {}
        
        match_id = target_match.get('id')
        if not match_id:
            return {}
        
        # Get enhanced data
        enhanced_data: Dict[str, Any] = {
            "match_details": api.get_match_details(match_id),
            "odds": api.get_odds(match_id=match_id),
            "highlights": api.get_highlights(match_id=match_id),
            "standings": _safe_get_standings(api, match_id) if match_id is not None else {}
        }
        
        # Get team data
        home_team_id = target_match.get('homeTeam', {}).get('id')
        away_team_id = target_match.get('awayTeam', {}).get('id')
        
        if home_team_id and away_team_id:
            enhanced_data["team_form"] = {
                "home": api.get_last_five_games(home_team_id),
                "away": api.get_last_five_games(away_team_id)
            }
            h2h_data = api.get_head_to_head(home_team_id, away_team_id)
            enhanced_data["head_to_head"] = h2h_data if isinstance(h2h_data, list) else []
        
        return enhanced_data
        
    except Exception as e:
        st.error(f"Error fetching Highlightly data: {e}")
        return {}

@st.cache_data(ttl=1800)  # Cache for 30 minutes to reduce API calls
def get_live_matches(league_id: Optional[int] = None) -> List[Dict]:
    """Get live/upcoming matches"""
    
    if not HIGHLIGHTLY_AVAILABLE:
        return []
    
    try:
        api_key = os.getenv('HIGHLIGHTLY_API_KEY')
        if not api_key:
            # Fallback: Set the API key directly (temporary fix)
            api_key = '9c27c5f8-9437-4d42-8cc9-5179d3290a5b'
        
        if not api_key or not HighlightlyRugbyAPI:
            return []
        
        api = HighlightlyRugbyAPI(api_key)
        
        league_mapping = {
            4986: "Rugby Championship",
            4446: "United Rugby Championship",
            5069: "Currie Cup", 
            4574: "Rugby World Cup",
            4551: "Super Rugby",
            4430: "French Top 14",
            4414: "English Premiership Rugby"
        }
        
        league_name = league_mapping.get(league_id) if league_id else None
        
        # Look for matches in the next 24 hours only (using South African time)
        from datetime import timedelta
        now_sa = datetime.now(SA_TIMEZONE)
        tomorrow_sa = now_sa + timedelta(days=1)
        
        # Get all matches without league filter (Highlightly doesn't support all leagues)
        # We'll filter by showing only matches in the next 24 hours
        matches = api.get_matches(
            league_name=None,  # Get all rugby matches
            limit=200  # Increased limit to catch all matches
        )
        
        live_matches = []
        for match in matches.get('data', []):
            match_state = match.get('state', {}).get('description', '')
            
            # Check if match is within next 24 hours
            match_date_str = match.get('date', '')
            is_within_24h = False
            match_datetime_sa = None
            
            if match_date_str:
                try:
                    # Parse match date and convert to South African timezone
                    match_datetime_utc = datetime.fromisoformat(match_date_str.replace('Z', '+00:00'))
                    match_datetime_sa = match_datetime_utc.astimezone(SA_TIMEZONE)
                    
                    # Check if match is within next 24 hours (using SA time)
                    time_diff = match_datetime_sa - now_sa
                    is_within_24h = 0 <= time_diff.total_seconds() <= 86400  # 24 hours in seconds
                except:
                    is_within_24h = False
                    match_datetime_sa = None
            
            # Include upcoming matches and live matches within 24 hours
            if match_state in ['Not started', 'First half', 'Second half', 'Half time', 'Break time'] and is_within_24h:
                # Get live scores if available
                home_score = match.get('homeScore', 0)
                away_score = match.get('awayScore', 0)
                
                # Extract start time and formatted date from date if available
                match_date = match.get('date', '')
                if match_date:
                    # Convert UTC time to South African time
                    formatted_date, start_time = convert_utc_to_sa_time(match_date)
                else:
                    start_time = 'TBD'
                    formatted_date = 'TBD'
                
                # Get game time for live matches (this would come from API in real implementation)
                game_time = None
                if match_state in ['First half', 'Second half', 'Half time']:
                    # Game time should come from the API - not simulated
                    game_time = match.get('gameTime')  # This would be the actual API field
                
                live_matches.append({
                    "match_id": match.get('id'),
                    "home_team": match.get('homeTeam', {}).get('name'),
                    "away_team": match.get('awayTeam', {}).get('name'),
                    "date": match.get('date'),
                    "formatted_date": formatted_date,
                    "start_time": start_time,
                    "game_time": game_time,
                    "state": match_state,
                    "league": match.get('league', {}).get('name'),
                    "home_score": home_score,
                    "away_score": away_score,
                    "live_score": f"{home_score} - {away_score}" if home_score > 0 or away_score > 0 else "TBD",
                    "match_datetime_sa": match_datetime_sa  # Store for sorting
                })
        
        # Remove duplicate matches (same match_id)
        seen_match_ids = set()
        unique_matches = []
        for match in live_matches:
            match_id = match.get('match_id')
            if match_id and match_id not in seen_match_ids:
                seen_match_ids.add(match_id)
                unique_matches.append(match)
        
        # Sort matches by date (earliest first - today's matches before tomorrow's)
        unique_matches.sort(key=lambda x: x.get('match_datetime_sa', datetime.now(SA_TIMEZONE)))
        
        return unique_matches
        
    except Exception as e:
        st.error(f"Error fetching live matches: {e}")
        return []

def _safe_get_standings(api, match_id):
    """Safely get standings data, handling 404 errors"""
    try:
        return api.get_standings(match_id, datetime.now().year)
    except Exception as e:
        # Silently handle 404 and other errors for standings
        return {}

def enhance_prediction_with_odds(prediction: Dict, highlightly_data: Dict) -> Dict:
    """Enhance AI prediction with odds and other data"""
    if not highlightly_data:
        return prediction
    
    enhanced = prediction.copy()
    
    # Process odds data
    odds_data = highlightly_data.get('odds', {}).get('data', [])
    if odds_data:
        enhanced['live_odds'] = {}
        for odds_entry in odds_data:
            bookmaker = odds_entry.get('bookmaker', {}).get('name', 'Unknown')
            markets = odds_entry.get('markets', [])
            
            enhanced['live_odds'][bookmaker] = {}
            for market in markets:
                market_name = market.get('name', 'Unknown')
                outcomes = market.get('outcomes', [])
                
                # Find home/away odds
                for outcome in outcomes:
                    if 'home' in outcome.get('name', '').lower():
                        enhanced['live_odds'][bookmaker]['home'] = outcome.get('odds')
                    elif 'away' in outcome.get('name', '').lower():
                        enhanced['live_odds'][bookmaker]['away'] = outcome.get('odds')
    
    # Process team form
    team_form = highlightly_data.get('team_form', {})
    if team_form:
        enhanced['team_form'] = {}
        
        for team_type, games in team_form.items():
            if games:
                wins = sum(1 for game in games if _team_won(game, team_type))
                enhanced['team_form'][team_type] = {
                    'win_rate': wins / len(games),
                    'games': games[:5]  # Last 5 games
                }
    
    # Process head-to-head
    h2h = highlightly_data.get('head_to_head', [])
    if h2h:
        enhanced['head_to_head'] = h2h[:5]  # Last 5 meetings
    
    # Process standings
    standings = highlightly_data.get('standings', {})
    if standings:
        enhanced['standings'] = standings
    
    # Calculate enhanced confidence
    confidence_factors = []
    
    # Base AI confidence
    confidence_str = prediction.get('confidence', '50%')
    confidence_value = float(confidence_str.replace('%', '')) / 100 if isinstance(confidence_str, str) else confidence_str
    confidence_factors.append(confidence_value)
    
    # Odds confidence (if odds favor our prediction)
    if enhanced.get('live_odds'):
        confidence_factors.append(0.1)  # Bonus for having odds
    
    # Team form confidence
    if enhanced.get('team_form'):
        confidence_factors.append(0.1)  # Bonus for having form data
    
    # Head-to-head confidence
    if enhanced.get('head_to_head'):
        confidence_factors.append(0.1)  # Bonus for having H2H data
    
    enhanced['enhanced_confidence'] = min(sum(confidence_factors), 1.0)
    enhanced['data_sources'] = ['AI_Model', 'Highlightly_API']
    
    return enhanced

def _team_won(game: Dict, team_type: str) -> bool:
    """Determine if team won the game"""
    home_score = game.get('homeScore', 0)
    away_score = game.get('awayScore', 0)
    
    if team_type == 'home':
        return home_score > away_score
    else:
        return away_score > home_score

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_optimized_model(league_id: int):
    """Load optimized model with caching"""
    try:
        model_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
                return model
        else:
            # Fallback to old model if optimized doesn't exist
            old_path = f'artifacts/league_{league_id}_model.pkl'
            if os.path.exists(old_path):
                with open(old_path, 'rb') as f:
                    return pickle.load(f)
        return None
    except Exception as e:
        # Re-raise all errors to be handled by safe loader
        raise e

def load_model_safely(league_id: int):
    """Load model with XGBoost fallback handling"""
    # Check if optimized model exists first
    optimized_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
    if os.path.exists(optimized_path):
        try:
            with open(optimized_path, 'rb') as f:
                model = pickle.load(f)
            # Model loaded silently
            return model
        except Exception as e:
            st.warning(f"Failed to load optimized model: {e}")
    
    # Fallback to legacy model
    try:
        model_path = f'artifacts/league_{league_id}_model.pkl'
        if os.path.exists(model_path):
            # Use the module-level XGBoost availability check
            xgboost_available = XGBOOST_AVAILABLE
            
            # Ensure XGBoost is available during pickle loading
            if XGBOOST_AVAILABLE:
                import xgboost  # type: ignore
                # Make sure xgboost is in the current namespace for pickle
                current_frame = sys._getframe()
                current_frame.f_globals['xgboost'] = xgboost
            
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            # Check if it's a legacy model with XGBoost
            if 'models' in model_data and 'gbdt_clf' in model_data['models']:
                if not xgboost_available:
                    # Create a simplified model without XGBoost - avoid accessing gbdt_clf
                    simplified_model = {
                        'league_id': model_data['league_id'],
                        'league_name': model_data['league_name'],
                        'trained_at': model_data['trained_at'],
                        'training_games': model_data['training_games'],
                        'feature_columns': model_data['feature_columns'],
                        'scaler': model_data.get('scaler'),
                        'performance': model_data.get('performance', {}),
                        'team_mappings': model_data.get('team_mappings', {}),
                        'models': {
                            'clf': model_data['models']['clf']
                        },
                        'model_type': 'simplified_legacy'
                    }
                    return simplified_model
                else:
                    # XGBoost is available, use the full model
                    return model_data
            
            return model_data
        else:
            st.error(f"Model file not found: {model_path}")
            return None
    except Exception as e:
        st.error(f"Failed to load model for league {league_id}: {e}")
        return None

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_teams():
    """Get team names with caching"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM team")
        teams = dict(cursor.fetchall())
        conn.close()
        return teams
    except:
        return {}

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_upcoming_games(league_id: int):
    """Get upcoming games for a league"""
    try:
        conn = sqlite3.connect('data.sqlite')
        config = FeatureConfig(elo_priors=None, elo_k=24.0, 
                              neutral_mode=LEAGUE_CONFIGS[league_id]["neutral_mode"])
        feature_df = build_feature_table(conn, config)
        conn.close()
        
        # Filter upcoming games
        upcoming = feature_df[
            (feature_df["league_id"] == league_id) &
            pd.isna(feature_df["home_win"])
        ].copy()
        
        # Filter to future only
        if "date_event" in upcoming.columns and len(upcoming) > 0:
            today = pd.Timestamp.today().date()
            upcoming["date_event"] = pd.to_datetime(upcoming["date_event"], errors="coerce")
            # Ensure we have a DataFrame before accessing .dt
            if isinstance(upcoming, pd.DataFrame):
                upcoming = upcoming[upcoming["date_event"].dt.date >= today]
        
        return upcoming
    except Exception as e:
        st.error(f"Error getting upcoming games: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_past_games(league_id: int):
    """Get recent past games for REAL accuracy testing (not training data)"""
    try:
        conn = sqlite3.connect('data.sqlite')
        config = FeatureConfig(elo_priors=None, elo_k=24.0, 
                              neutral_mode=LEAGUE_CONFIGS[league_id]["neutral_mode"])
        feature_df = build_feature_table(conn, config)
        conn.close()
        
        # Filter completed games
        past_games = feature_df[
            (feature_df["league_id"] == league_id) &
            feature_df["home_win"].notna() &
            (feature_df["home_score"] > 0) &
            (feature_df["away_score"] > 0)
        ].copy()
        
        # Sort by date descending
        if "date_event" in past_games.columns and len(past_games) > 0:
            past_games["date_event"] = pd.to_datetime(past_games["date_event"], errors="coerce")
            # Sort by date_event column in descending order
            if isinstance(past_games, pd.DataFrame):
                past_games = past_games.sort_values(by=["date_event"], ascending=False)
            
            # IMPORTANT: Only test on RECENT games (last 20% of data)
            # This ensures we're testing on games the AI hasn't seen during training
            total_games = len(past_games)
            test_size = max(10, int(total_games * 0.2))  # At least 10 games, or 20% of total
            past_games = past_games.head(test_size)  # Most recent games
        
        return past_games
    except Exception as e:
        st.error(f"Error getting past games: {e}")
        return pd.DataFrame()

def analyze_past_game(game_row, model_data, team_names):
    """Analyze a past game and show AI prediction vs actual result"""
    if not model_data:
        return None
    
    try:
        # Get team names
        home_id = int(game_row['home_team_id'])
        away_id = int(game_row['away_team_id'])
        home_name = team_names.get(home_id, f"Team {home_id}")
        away_name = team_names.get(away_id, f"Team {away_id}")
        match_date = str(game_row.get('date_event', 'TBD'))[:10]
        league_id = int(game_row.get('league_id', 0))
        
        # Get actual results
        actual_home_score = int(game_row.get('home_score', 0))
        actual_away_score = int(game_row.get('away_score', 0))
        actual_home_win = game_row.get('home_win', 0)  # 1 if home won, 0 if away won
        
        # CRITICAL FIX: Create features WITHOUT using the actual result
        # We need to simulate what the AI would have predicted BEFORE the game
        feature_cols = model_data.get('feature_columns', [])
        
        # Remove any columns that contain future information
        excluded_cols = ['home_win', 'home_score', 'away_score', 'result']
        clean_feature_cols = [col for col in feature_cols if col not in excluded_cols]
        
        X = []
        for col in clean_feature_cols:
            X.append(game_row.get(col, 0.0))
        X = np.array(X).reshape(1, -1)
        
        # Get models
        models = model_data.get('models', {})
        clf = models.get('clf')
        
        if not clf:
            return None
        
        # Make AI prediction using only historical features
        if hasattr(clf, 'predict_proba'):
            proba = clf.predict_proba(X)
            ai_home_win_prob = proba[0, 1] if len(proba[0]) > 1 else proba[0, 0]
        else:
            pred = clf.predict(X)[0]
            ai_home_win_prob = 1.0 if pred == 1 else 0.0
        
        # Get score predictions
        reg_home = models.get('reg_home')
        reg_away = models.get('reg_away')
        
        predicted_home_score = 0
        predicted_away_score = 0
        
        if reg_home and reg_away:
            try:
                predicted_home_score = max(0, reg_home.predict(X)[0])
                predicted_away_score = max(0, reg_away.predict(X)[0])
            except:
                predicted_home_score = 20  # Default fallback
                predicted_away_score = 18
        
        # Determine AI prediction
        ai_predicted_winner = "Home" if ai_home_win_prob > 0.5 else "Away"
        actual_winner = "Home" if actual_home_win == 1 else "Away"
        
        # Calculate accuracy
        ai_correct = (ai_predicted_winner == actual_winner)
        
        # Calculate confidence
        confidence = max(ai_home_win_prob, 1 - ai_home_win_prob)
        
        # Calculate score accuracy
        home_score_diff = abs(predicted_home_score - actual_home_score)
        away_score_diff = abs(predicted_away_score - actual_away_score)
        avg_score_diff = (home_score_diff + away_score_diff) / 2
        
        return {
            'home_team': home_name,
            'away_team': away_name,
            'date': match_date,
            'actual_home_score': actual_home_score,
            'actual_away_score': actual_away_score,
            'predicted_home_score': int(round(predicted_home_score)),
            'predicted_away_score': int(round(predicted_away_score)),
            'actual_winner': actual_winner,
            'ai_predicted_winner': ai_predicted_winner,
            'ai_home_win_prob': ai_home_win_prob,
            'confidence': confidence,
            'ai_correct': ai_correct,
            'avg_score_diff': avg_score_diff,
            'home_score_diff': home_score_diff,
            'away_score_diff': away_score_diff
        }
        
    except Exception as e:
        st.error(f"Analysis error: {e}")
        return None

def make_expert_prediction(game_row, model_data, team_names):
    """Make prediction using hybrid AI + odds system for maximum accuracy"""
    if not model_data:
        return None
    
    try:
        # Get team names
        home_id = int(game_row['home_team_id'])
        away_id = int(game_row['away_team_id'])
        home_name = team_names.get(home_id, f"Team {home_id}")
        away_name = team_names.get(away_id, f"Team {away_id}")
        match_date = str(game_row.get('date_event', 'TBD'))[:10]
        league_id = int(game_row.get('league_id', 0))
        
        # Get Highlightly API data first for hybrid prediction (cached for 30 minutes)
        highlightly_data = {}
        if HIGHLIGHTLY_AVAILABLE:
            try:
                highlightly_data = get_highlightly_data(home_name, away_name, league_id, match_date)
            except Exception as e:
                # Don't show warning for cached data - it's expected
                pass
        
        # Get feature columns and prepare data
        feature_cols = model_data.get('feature_columns', [])
        X = []
        for col in feature_cols:
            X.append(game_row.get(col, 0.0))
        X = np.array(X).reshape(1, -1)
        
        # Get models
        models = model_data.get('models', {})
        clf = models.get('clf')
        
        # Skip XGBoost models if not available
        if not clf and 'gbdt_clf' in models:
            if XGBOOST_AVAILABLE:
                clf = models.get('gbdt_clf')
            else:
                st.warning("XGBoost model available but XGBoost not installed. Skipping predictions.")
                return None
        
        if not clf:
            return None
        
        # Make AI prediction
        if hasattr(clf, 'predict_proba'):
            proba = clf.predict_proba(X)
            ai_home_win_prob = proba[0, 1] if len(proba[0]) > 1 else proba[0, 0]
        else:
            pred = clf.predict(X)[0]
            ai_home_win_prob = 1.0 if pred == 1 else 0.0
        
        # Get score predictions
        reg_home = models.get('reg_home')
        reg_away = models.get('reg_away')
        
        predicted_home_score = 0
        predicted_away_score = 0
        
        if reg_home and reg_away:
            try:
                predicted_home_score = max(0, reg_home.predict(X)[0])
                predicted_away_score = max(0, reg_away.predict(X)[0])
            except:
                predicted_home_score = 20  # Default fallback
                predicted_away_score = 18
        
        # HYBRID PREDICTION: Combine AI + Manual Odds (if provided in session)
        # Prefer stable ID-based key, fallback to name-based
        id_key_pred = f"manual_odds_by_ids::{home_id}::{away_id}::{match_date}"
        manual_key = f"manual_odds::{home_name}::{away_name}::{match_date}"
        manual_odds = st.session_state.get(id_key_pred) or st.session_state.get(manual_key)
        if manual_odds and manual_odds.get('home') and manual_odds.get('away'):
            try:
                home_decimal = float(manual_odds['home'])
                away_decimal = float(manual_odds['away'])
                if home_decimal > 0 and away_decimal > 0:
                    # Convert decimal odds to implied probabilities and normalize
                    home_prob_raw = 1.0 / home_decimal
                    away_prob_raw = 1.0 / away_decimal
                    total_prob = home_prob_raw + away_prob_raw
                    odds_home_win_prob = home_prob_raw / total_prob
                    # Combine
                    ai_weight = 0.4
                    odds_weight = 0.6
                    hybrid_home_win_prob = ai_weight * ai_home_win_prob + odds_weight * odds_home_win_prob
                    base_confidence = max(ai_home_win_prob, 1 - ai_home_win_prob)
                    odds_confidence = max(odds_home_win_prob, 1 - odds_home_win_prob)
                    hybrid_confidence = ai_weight * base_confidence + odds_weight * odds_confidence
                    home_win_prob = hybrid_home_win_prob
                    confidence = hybrid_confidence
                    prediction_type = 'Hybrid AI + Manual Odds'
                else:
                    home_win_prob = ai_home_win_prob
                    confidence = max(ai_home_win_prob, 1 - ai_home_win_prob)
                    prediction_type = 'AI Only (Invalid Manual Odds)'
            except Exception:
                home_win_prob = ai_home_win_prob
                confidence = max(ai_home_win_prob, 1 - ai_home_win_prob)
                prediction_type = 'AI Only (Invalid Manual Odds)'
        else:
            # No manual odds
            home_win_prob = ai_home_win_prob
            confidence = max(ai_home_win_prob, 1 - ai_home_win_prob)
            prediction_type = 'AI Only (No Odds)'
        
        # Determine winner based on hybrid prediction
        if home_win_prob > 0.5:
            winner = home_name
            final_confidence = home_win_prob
        elif home_win_prob < 0.5:
            winner = away_name
            final_confidence = 1 - home_win_prob
        else:
            winner = "Draw"
            final_confidence = 0.5
        
        # Calculate match intensity
        score_diff = abs(predicted_home_score - predicted_away_score)
        if score_diff <= 2:
            intensity = "Close Thrilling Match"
        elif score_diff <= 5:
            intensity = "Competitive Game"
        elif score_diff <= 10:
            intensity = "Moderate Advantage"
        else:
            intensity = "Decisive Victory"
        
        # Confidence level
        if final_confidence >= 0.8:
            confidence_level = "High Confidence"
        elif final_confidence >= 0.65:
            confidence_level = "Moderate Confidence"
        else:
            confidence_level = "Close Match Expected"
        
        # Create hybrid prediction
        prediction = {
            'home_team': home_name,
            'away_team': away_name,
            'date': match_date,
            'winner': winner,
            'confidence': f"{final_confidence:.1%}",
            'home_score': f"{int(round(predicted_home_score))}",
            'away_score': f"{int(round(predicted_away_score))}",
            'home_win_prob': home_win_prob,
            'league_id': league_id,
            'intensity': intensity,
            'confidence_level': confidence_level,
            'score_diff': int(round(predicted_home_score - predicted_away_score)),
            'prediction_type': prediction_type,
            'ai_probability': ai_home_win_prob,
            'hybrid_probability': home_win_prob,
            'confidence_boost': final_confidence - max(ai_home_win_prob, 1 - ai_home_win_prob)
        }
        
        # Add indicators (odds now manual)
        prediction['home_team_id'] = home_id
        prediction['away_team_id'] = away_id
        prediction['has_live_data'] = bool(highlightly_data)
        prediction['live_odds_available'] = bool(st.session_state.get(id_key_pred) or st.session_state.get(manual_key))
        prediction['team_form_available'] = bool(highlightly_data.get('team_form')) if highlightly_data else False
        prediction['head_to_head_available'] = bool(highlightly_data.get('head_to_head')) if highlightly_data else False
        prediction['standings_available'] = bool(highlightly_data.get('standings')) if highlightly_data else False
        # Do not enrich with API odds anymore
        
        return prediction
        
    except Exception as e:
        st.error(f"Prediction error: {e}")
        return None


def get_league_accuracy(league_id: int) -> float:
    """Get actual model accuracy from trained models"""
    try:
        # Try optimized model registry first
        if os.path.exists('artifacts_optimized/model_registry_optimized.json'):
            with open('artifacts_optimized/model_registry_optimized.json', 'r') as f:
                registry = json.load(f)
                league_data = registry.get('leagues', {}).get(str(league_id))
                if league_data:
                    accuracy = league_data.get('performance', {}).get('winner_accuracy', 0.0)
                    return accuracy * 100  # Convert to percentage
        
        # Fallback to legacy model registry
        if os.path.exists('artifacts/model_registry.json'):
            with open('artifacts/model_registry.json', 'r') as f:
                registry = json.load(f)
                league_data = registry.get('leagues', {}).get(str(league_id))
                if league_data:
                    accuracy = league_data.get('performance', {}).get('winner_accuracy', 0.0)
                    return accuracy * 100  # Convert to percentage
    except Exception:
        pass
    
    # Fallback to default if no registry found
    return 0.0

def get_ai_rating(accuracy: float) -> str:
    """Get AI rating based on accuracy"""
    if accuracy >= 80:
        return "9/10"
    elif accuracy >= 70:
        return "8/10"
    elif accuracy >= 65:
        return "7/10"
    elif accuracy >= 60:
        return "6/10"
    elif accuracy >= 55:
        return "5/10"
    else:
        return "4/10"

def get_training_games(league_id: int) -> int:
    """Get actual number of games used for training from model registry"""
    try:
        # Try optimized model registry first
        if os.path.exists('artifacts_optimized/model_registry_optimized.json'):
            with open('artifacts_optimized/model_registry_optimized.json', 'r') as f:
                registry = json.load(f)
                league_data = registry.get('leagues', {}).get(str(league_id))
                if league_data:
                    return league_data.get('training_games', 0)
        
        # Fallback to legacy model registry
        if os.path.exists('artifacts/model_registry.json'):
            with open('artifacts/model_registry.json', 'r') as f:
                registry = json.load(f)
                league_data = registry.get('leagues', {}).get(str(league_id))
                if league_data:
                    return league_data.get('training_games', 0)
    except Exception:
        pass
    
    # Fallback to 0
    return 0

def get_total_games_count() -> int:
    """Get total games count from database"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM event')
        total_games = cursor.fetchone()[0]
        conn.close()
        return total_games
    except:
        return 1595  # Fallback to known total

def check_deployment_status():
    """Check deployment status and show helpful information"""
    status_info = {
        "models_available": 0,
        "total_leagues": len(LEAGUE_CONFIGS),
        "database_exists": os.path.exists("data.sqlite"),
        "optimized_models": 0,
        "legacy_models": 0
    }
    
    # Check model availability
    for league_id in LEAGUE_CONFIGS.keys():
        optimized_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
        legacy_path = f'artifacts/league_{league_id}_model.pkl'
        
        if os.path.exists(optimized_path):
            status_info["optimized_models"] += 1
            status_info["models_available"] += 1
        elif os.path.exists(legacy_path):
            status_info["legacy_models"] += 1
            status_info["models_available"] += 1
    
    return status_info

def main():
    st.set_page_config(
        page_title="Rugby AI Predictions",
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon="🏉"
    )
    
    # Check deployment status
    status = check_deployment_status()
    
    # Show status warning if needed
    if status["models_available"] == 0:
        st.error("⚠️ **No AI models found!** The app is waiting for GitHub Actions to train and deploy models.")
        st.info("🔧 **Next Steps:**\n1. Check GitHub Actions are running\n2. Wait for model training to complete\n3. Refresh this page")
        return
    elif status["models_available"] < status["total_leagues"]:
        st.warning(f"⚠️ **Partial Model Availability:** {status['models_available']}/{status['total_leagues']} leagues have trained models")
        st.info("🔄 Models are being trained automatically. Check back soon!")
    
    # Custom CSS for modern styling
    st.markdown("""
    <style>
    /* Global dark theme */
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    
    /* Live Match Cards */
    .live-match-card {
        background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #4b5563;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    
    .live-match-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    
        .match-date {
            color: #6c757d;
            font-size: 0.9rem;
            font-weight: 500;
            margin-right: 1rem;
        }
        
        .live-match-time {
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .match-start-time {
        font-size: 1rem;
        font-weight: 600;
        color: #9ca3af;
        background: rgba(156, 163, 175, 0.1);
        padding: 0.3rem 0.8rem;
        border-radius: 8px;
        border: 1px solid rgba(156, 163, 175, 0.3);
    }
    
    .live-game-time {
        font-size: 1rem;
        font-weight: 600;
        color: #ffffff;
        background: rgba(220, 38, 38, 0.15);
        padding: 0.3rem 0.8rem;
        border-radius: 6px;
        border: 1px solid rgba(220, 38, 38, 0.3);
    }
    
    .live-match-title {
        color: #ffffff;
        font-size: 1.4rem;
        font-weight: 700;
        margin: 0;
    }
    
    .live-match-status {
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    
    .live-match-status.not-started {
        background: linear-gradient(135deg, #6b7280 0%, #9ca3af 100%);
        color: #ffffff;
    }
    
    .live-match-status.first-half, .live-match-status.second-half {
        background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
        color: #ffffff;
    }
    
    .live-match-status.half-time {
        background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
        color: #ffffff;
    }
    
    .live-team-name {
        font-size: 1.2rem;
        font-weight: 600;
        color: #ffffff;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    
    .live-score {
        font-size: 1.3rem;
        font-weight: 700;
        color: #ffffff;
        text-align: center;
        margin-bottom: 0.3rem;
        background: rgba(220, 38, 38, 0.1);
        padding: 0.3rem 0.8rem;
        border-radius: 8px;
        border: 1px solid rgba(220, 38, 38, 0.3);
    }
    
    .predicted-score {
        font-size: 1.3rem;
        font-weight: 600;
        color: #d1d5db;
        text-align: center;
        margin-bottom: 0.3rem;
        background: rgba(107, 114, 128, 0.1);
        padding: 0.3rem 0.8rem;
        border-radius: 8px;
        border: 1px solid rgba(107, 114, 128, 0.3);
    }
    
    .live-vs-text {
        font-size: 2.5rem;
        font-weight: 800;
        color: #ffffff;
        text-align: center;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        transform: translateY(40%);
    }
    
    /* Beautiful Odds Display */
    .odds-container {
        background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        border: 1px solid #4b5563;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    
    .odds-header {
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .odds-title {
        color: #fbbf24;
        font-size: 1.4rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        letter-spacing: 0.5px;
    }
    
    .odds-row {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 0.5rem;
        gap: 2rem;
    }
    
    .odds-team {
        flex: 1;
        text-align: center;
        padding: 0.5rem;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    
    .odds-team .team-name {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e5e7eb;
        margin-bottom: 0.5rem;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    }
    
    .odds-value {
        font-size: 2.2rem;
        font-weight: 900;
        padding: 0.8rem 1.5rem;
        border-radius: 12px;
        min-width: 80px;
        display: inline-block;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
        border: 2px solid rgba(255, 255, 255, 0.1);
    }
    
    .home-odds {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: #ffffff;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
    }
    
    .away-odds {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: #ffffff;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
    }
    
    .odds-vs {
        font-size: 1.6rem;
        font-weight: 900;
        color: #ffffff;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
        background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
        padding: 0.5rem 1rem;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center;
        flex-shrink: 0;
        align-self: flex-end;
        transform: translateY(-40%);
    }
    
    .bookmaker-name {
        text-align: center;
        font-size: 1rem;
        font-weight: 700;
        color: #fbbf24;
        margin-top: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    }
    
    /* Alternative odds styling for expandable section */
    .odds-row-alt {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.3rem;
        padding: 0.3rem 0;
        border-bottom: 1px solid #374151;
    }
    
    .odds-team-alt {
        flex: 1;
        text-align: center;
    }
    
    .odds-team-alt .team-name-alt {
        font-size: 0.8rem;
        font-weight: 500;
        color: #d1d5db;
        margin-bottom: 0.2rem;
    }
    
    .odds-value-alt {
        font-size: 1.1rem;
        font-weight: 700;
        padding: 0.3rem 0.8rem;
        border-radius: 6px;
        background: linear-gradient(135deg, #4b5563 0%, #6b7280 100%);
        color: #ffffff;
        display: inline-block;
    }
    
    .odds-vs-alt {
        font-size: 1rem;
        font-weight: 600;
        color: #9ca3af;
        margin: 0 0.8rem;
    }
    
    .bookmaker-name-alt {
        text-align: center;
        font-size: 0.7rem;
        font-weight: 500;
        color: #6b7280;
        margin-top: 0.3rem;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    
    /* Clean Indicators */
    .indicators-row {
        display: flex;
        gap: 0.5rem;
        margin: 0.5rem 0;
        flex-wrap: wrap;
        justify-content: center;
    }
    
    .indicator {
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        text-align: center;
        min-width: 80px;
    }
    
    .indicator.success {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: #ffffff;
        box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
    }
    
    .indicator.info {
        background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
        color: #d1d5db;
        box-shadow: 0 2px 4px rgba(107, 114, 128, 0.2);
    }
    
    .stApp > header {
        background-color: #0e1117;
    }
    
    .stSidebar {
        background-color: #262730;
    }
    
    .stSidebar .stSelectbox > div > div {
        background-color: #262730;
        color: #fafafa;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 1rem 2rem;
        font-size: 1.2rem;
        font-weight: 600;
        box-shadow: 0 8px 32px rgba(44, 62, 80, 0.3);
        transition: all 0.3s ease;
        width: 100%;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px rgba(44, 62, 80, 0.4);
    }
    
    .stButton > button:active {
        transform: translateY(0);
    }
    
    /* Main styling */
    .main-header {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 3rem;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.2rem;
        opacity: 0.9;
    }
    
    /* Prediction card styling */
    .prediction-card {
        background: linear-gradient(145deg, #1a202c 0%, #2d3748 100%);
        border-radius: 20px;
        padding: 2rem;
        margin: 1.5rem 0;
        box-shadow: 0 15px 50px rgba(0,0,0,0.3);
        border: 1px solid rgba(74, 85, 104, 0.3);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .prediction-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
    }
    
    .prediction-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #27ae60, #2ecc71, #16a085);
    }
    
    /* Match header */
    .match-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .match-title {
        font-size: 2rem;
        font-weight: 700;
        color: #ffffff !important;
        margin: 0;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }
    
    h2.match-title {
        color: #ffffff !important;
    }
    
    .match-date {
        color: #a0aec0;
        font-size: 1rem;
        margin-top: 0.5rem;
    }
    
    /* Score display */
    .score-container {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 15px;
        padding: 2rem;
        margin: 1.5rem 0;
        text-align: center;
        border: 2px solid #dee2e6;
    }
    
    .team-name {
        font-size: 1.3rem;
        font-weight: 600;
        color: #e2e8f0;
        margin: 0.5rem 0;
        text-align: center;
    }
    
    .team-score {
        font-size: 5rem;
        font-weight: 900;
        color: #1a365d;
        text-shadow: 3px 3px 6px rgba(0,0,0,0.2);
        margin: 0;
        background: linear-gradient(135deg, #ffffff 0%, #f7fafc 100%);
        border: 3px solid #2d3748;
        border-radius: 15px;
        padding: 0.5rem 1rem;
        box-shadow: 0 8px 25px rgba(45, 55, 72, 0.15);
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 120px;
    }
    
    .vs-text {
        font-size: 3rem;
        font-weight: 800;
        color: white;
        margin: 0;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 120px;
        height: 100%;
        transform: translateY(40%);
    }
    
    /* Winner display */
    .winner-display {
        text-align: center;
        margin: 1.5rem 0;
    }
    
    .winner-text {
        font-size: 1.5rem;
        font-weight: 700;
        padding: 1rem 2rem;
        border-radius: 25px;
        display: inline-block;
        margin: 0.5rem 0;
    }
    
    .winner-home {
        background: #007a3d;
        color: white;
        box-shadow: 0 4px 15px rgba(0, 122, 61, 0.3);
    }
    
    .winner-away {
        background: #007a3d;
        color: white;
        box-shadow: 0 4px 15px rgba(0, 122, 61, 0.3);
    }
    
    .winner-draw {
        background: #007a3d;
        color: white;
        box-shadow: 0 4px 15px rgba(0, 122, 61, 0.3);
    }
    
    /* Confidence indicator */
    .confidence-bar {
        background: #e9ecef;
        border-radius: 10px;
        height: 20px;
        margin: 1rem 0;
        overflow: hidden;
        position: relative;
    }
    
    .confidence-fill {
        height: 100%;
        border-radius: 10px;
        transition: width 0.8s ease;
        position: relative;
    }
    
    .confidence-high {
        background: linear-gradient(90deg, #059669, #10b981);
    }
    
    .confidence-medium {
        background: linear-gradient(90deg, #d97706, #f59e0b);
    }
    
    .confidence-low {
        background: linear-gradient(90deg, #dc2626, #ef4444);
    }
    
    .confidence-text {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: white;
        font-weight: 600;
        font-size: 0.9rem;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }
    
    /* Intensity indicator */
    .intensity-badge {
        display: inline-block;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 600;
        margin: 0.5rem 0;
    }
    
    .intensity-close {
        background: linear-gradient(135deg, #dc2626, #ef4444);
        color: white;
    }
    
    .intensity-competitive {
        background: linear-gradient(135deg, #d97706, #f59e0b);
        color: white;
    }
    
    .intensity-moderate {
        background: linear-gradient(135deg, #2563eb, #3b82f6);
        color: white;
    }
    
    .intensity-decisive {
        background: linear-gradient(135deg, #059669, #10b981);
        color: white;
    }
    
    /* Probability display */
    .prob-container {
        background: #ffffff;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        text-align: center;
        border: 2px solid #dee2e6;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .prob-value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
        color: #2c3e50;
    }
    
    .prob-label {
        font-size: 0.9rem;
        color: #6c757d;
        margin: 0.5rem 0 0 0;
        font-weight: 600;
    }
    
    /* Summary section */
    .summary-card {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        border-radius: 20px;
        padding: 2rem;
        color: white;
        text-align: center;
        margin: 2rem 0;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    }
    
    .summary-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0 0 1.5rem 0;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
    }
    
    .summary-metric {
        text-align: center;
    }
    
    .summary-metric-value {
        font-size: 2.5rem;
        font-weight: 800;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .summary-metric-label {
        font-size: 1rem;
        opacity: 0.9;
        margin: 0.5rem 0 0 0;
    }
    
    /* Animation keyframes */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .fade-in-up {
        animation: fadeInUp 0.6s ease-out;
    }
    
    /* Custom metrics styling - available on all screen sizes */
    .custom-metrics-container {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr 1fr;
        gap: 1rem;
        margin: 1rem 0;
        padding: 1rem;
        width: 100%;
    }
    
    .custom-metric {
        background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%);
        border-radius: 15px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        border: 1px solid rgba(74, 85, 104, 0.3);
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #a0aec0;
        margin-bottom: 0.5rem;
        font-weight: 600;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 0.5rem;
    }
    
    .metric-delta {
        font-size: 0.8rem;
        color: #68d391;
        font-weight: 600;
    }
    
    /* Responsive design */
    @media (max-width: 768px) {
        .main-header h1 {
            font-size: 2rem;
        }
        
        .team-score {
            font-size: 3rem;
            min-height: 80px;
        }
        
        .vs-text {
            font-size: 1.5rem;
            min-height: 80px;
            transform: translateY(0%);
        }
        
        .live-vs-text {
            font-size: 1.8rem;
            transform: translateY(0%);
            margin: 0.5rem 0;
        }
        
        .match-title {
            font-size: 1.5rem;
        }
        
        .team-name {
            font-size: 1rem;
            margin: 0.25rem 0 0.5rem 0;
        }
        
        .team-score {
            margin-top: 0.25rem;
        }
        
        /* Center metrics on mobile */
        .stMetric {
            text-align: center;
        }
        
        .stMetric > div {
            text-align: center;
        }
        
        .stMetric > div > div {
            text-align: center;
        }
        
        .stMetric > div > div > div {
            text-align: center;
        }
        
        .stMetric > div > div > div > div {
            text-align: center;
        }
        
        /* Center all metric text */
        .stMetric * {
            text-align: center !important;
        }
        
        /* Center metric labels and arrows */
        .stMetric > div > div > div > div {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }
        
        .stMetric > div > div > div > div > div {
            text-align: center;
        }
        
        /* Center metric arrows */
        .stMetric > div > div > div > div > div > div {
            text-align: center;
        }
        
        /* Force center alignment for all metric content */
        .stMetric > div > div > div > div > div > div > div {
            text-align: center;
        }
        
        /* Center metric delta arrows */
        .stMetric > div > div > div > div > div > div > div > div {
            text-align: center;
        }
        
        /* Custom metric centering */
        .metric-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
        }
        
        .metric-container * {
            text-align: center !important;
        }
        
        /* Mobile-specific custom metrics adjustments */
        .custom-metrics-container {
            grid-template-columns: 1fr 1fr;
            gap: 0.5rem;
            padding: 0.5rem;
        }
        
        .custom-metric {
            padding: 1rem;
        }
        
        .metric-value {
            font-size: 1.5rem;
        }
    }
    
    @media (min-width: 769px) {
        .custom-metrics-container {
            grid-template-columns: 1fr 1fr 1fr 1fr;
            gap: 1rem;
            padding: 1rem;
        }
        
        .custom-metric {
            padding: 1.5rem;
        }
        
        .metric-value {
            font-size: 2rem;
        }
        
        /* Ensure vs text aligns with center of prediction scores on larger screens */
        .vs-text {
            font-size: 3rem;
            transform: translateY(60%);
        }
        
        .live-vs-text {
            font-size: 2.5rem;
            transform: translateY(60%);
        }
        
        .odds-vs {
            align-self: flex-end;
            transform: translateY(-40%);
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Modern header
    # Calculate average accuracy across all leagues
    total_accuracy = sum(get_league_accuracy(league_id) for league_id in LEAGUE_CONFIGS.keys())
    avg_accuracy = total_accuracy / len(LEAGUE_CONFIGS)
    
    st.markdown(f"""
    <div class="main-header">
        <h1>🏉 Rugby AI Predictions</h1>
        <p>Advanced AI-powered match predictions with {avg_accuracy:.1f}% average accuracy</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Clean sidebar
    with st.sidebar:
        st.header("🎯 Control Panel")
        
        
        # League selection
        available_leagues = {}
        for league_id, data in LEAGUE_CONFIGS.items():
            model_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
            old_path = f'artifacts/league_{league_id}_model.pkl'
            if os.path.exists(model_path) or os.path.exists(old_path):
                available_leagues[league_id] = data['name']
        
        if not available_leagues:
            st.error("No models found")
            return
        
        selected_league = st.selectbox(
            "Select League",
            options=list(available_leagues.keys()),
            format_func=lambda x: available_leagues[x]
        )
        
        # Clear predictions when league changes
        if hasattr(st.session_state, 'last_selected_league'):
            if st.session_state.last_selected_league != selected_league:
                if 'predictions' in st.session_state:
                    del st.session_state.predictions
                if 'league_name' in st.session_state:
                    del st.session_state.league_name
        
        st.session_state.last_selected_league = selected_league
    
    # Performance metrics - only show when no league selected
    if not selected_league:
        # Get total games from database
        total_games = get_total_games_count()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Accuracy", f"{avg_accuracy:.1f}%", "Average")
        with col2:
            st.metric("Leagues", f"{len(LEAGUE_CONFIGS)}", "Available")
        with col3:
            st.metric("Total Games", f"{total_games}", "Database")
        with col4:
            overall_rating = get_ai_rating(avg_accuracy)
            st.metric("AI Rating", overall_rating, "Based on Stats")
        
        # Model status
        if selected_league:
            model_data = load_model_safely(selected_league)
            if model_data:
                st.success("✅ Model Ready")
                model_type = model_data.get('model_type', 'unknown')
                if model_type == 'simple_legacy':
                    st.caption("Simplified AI Model")
                else:
                    st.caption("Optimized AI Model")
            else:
                st.error("❌ Model Error")
        
        st.markdown("---")
        
        st.markdown("---")
        
        # Quick stats
        st.subheader("📊 Quick Stats")
        st.metric("Accuracy", f"{avg_accuracy:.1f}%")
        st.metric("Total Games", f"{total_games}")
        st.metric("Leagues", f"{len(LEAGUE_CONFIGS)}")
    
    # Main content
    if selected_league:
        league_name = available_leagues[selected_league]
        
        # Get league-specific stats
        import sqlite3
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        
        # Get total games for this league
        cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ?', (selected_league,))
        league_total_games = cursor.fetchone()[0]
        
        # Get games with results for this league
        cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ? AND home_score IS NOT NULL AND away_score IS NOT NULL', (selected_league,))
        league_games_with_results = cursor.fetchone()[0]
        
        conn.close()
        
        # Get actual model accuracy and training info for the selected league
        model_accuracy = get_league_accuracy(selected_league)
        ai_rating = get_ai_rating(model_accuracy)
        training_games = get_training_games(selected_league)
        
        # League-specific metrics - custom centered layout
        st.markdown(f"""
        <div class="custom-metrics-container">
            <div class="custom-metric">
                <div class="metric-label">Accuracy</div>
                <div class="metric-value">{model_accuracy:.1f}%</div>
                <div class="metric-delta">Tested</div>
            </div>
            <div class="custom-metric">
                <div class="metric-label">League</div>
                <div class="metric-value">{league_name}</div>
                <div class="metric-delta">Selected</div>
            </div>
            <div class="custom-metric">
                <div class="metric-label">Games Trained</div>
                <div class="metric-value">{training_games}</div>
                <div class="metric-delta">Completed</div>
            </div>
            <div class="custom-metric">
                <div class="metric-label">AI Rating</div>
                <div class="metric-value">{ai_rating}</div>
                <div class="metric-delta">Based on Stats</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Clean league header
        st.caption("AI-Powered Match Predictions")
        
        # AI-only mode (hybrid removed)
        
        # Load model
        model_data = load_model_safely(selected_league)
        
        if not model_data:
            st.error("Unable to load model for this league")
            return
        
        # Live Matches Section (if Highlightly API is available)
        if HIGHLIGHTLY_AVAILABLE:
            st.subheader("🔴 Live Matches (Next 24 Hours)")
            
            try:
                live_matches = get_live_matches(selected_league)
                
                if live_matches:
                    st.success(f"Found {len(live_matches)} live/upcoming matches in next 24 hours")
                    
                    # Show cache status
                    import time
                    if 'last_refresh' not in st.session_state:
                        st.session_state.last_refresh = time.time()
                    
                    refresh_time = time.strftime("%H:%M:%S", time.localtime(st.session_state.last_refresh))
                    st.caption(f"💾 Data cached for 30 minutes to preserve API quota. Last refreshed: {refresh_time}")
                    
                    for match in live_matches[:15]:  # Show first 15 live matches
                        # Get live match details
                        live_home_score = match.get('home_score', 0)
                        live_away_score = match.get('away_score', 0)
                        live_state = match.get('state', 'Not started')
                        
                        # Quick predictions disabled for live matches section
                        # The detailed predictions section below shows accurate AI predictions
                        # because it uses the database with proper team IDs
                        quick_pred = None
                        
                        # Create styled live match card
                        start_time = match.get('start_time', 'TBD')
                        game_time = match.get('game_time')
                        
                        # Show game time for live matches, start time for upcoming matches
                        if live_state in ['First half', 'Second half', 'Half time'] and game_time:
                            time_display = f"⏱️ {game_time}'"
                            time_class = "live-game-time"
                        else:
                            time_display = f"🕐 {start_time}"
                            time_class = "match-start-time"
                        
                        st.markdown(f"""
                        <div class="live-match-card fade-in-up">
                            <div class="live-match-header">
                                <h3 class="live-match-title">🏉 {match['home_team']} vs {match['away_team']}</h3>
                                <div class="live-match-status {live_state.lower().replace(' ', '-')}">{live_state}</div>
                            </div>
                            <div class="live-match-time">
                                <span class="match-date">📅 {match.get('formatted_date', 'TBD')}</span>
                                <span class="{time_class}">{time_display}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Score display with live vs predicted
                        col1, col2, col3 = st.columns([2, 1, 2])
                        
                        with col1:
                            st.markdown(f"<div class='live-team-name'>{match['home_team']}</div>", unsafe_allow_html=True)
                            if quick_pred:
                                st.markdown(f"<div class='live-score'>🔴 Live: {live_home_score}</div>", unsafe_allow_html=True)
                                st.markdown(f"<div class='predicted-score'>🤖 AI: {quick_pred.get('home_score', 'TBD')}</div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div class='live-score'>🔴 Live: {live_home_score}</div>", unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown("<div class='live-vs-text'>VS</div>", unsafe_allow_html=True)
                        
                        with col3:
                            st.markdown(f"<div class='live-team-name'>{match['away_team']}</div>", unsafe_allow_html=True)
                            if quick_pred:
                                st.markdown(f"<div class='live-score'>🔴 Live: {live_away_score}</div>", unsafe_allow_html=True)
                                st.markdown(f"<div class='predicted-score'>🤖 AI: {quick_pred.get('away_score', 'TBD')}</div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div class='live-score'>🔴 Live: {live_away_score}</div>", unsafe_allow_html=True)
                        
                        # Odds Display - only show real API odds
                        if quick_pred and quick_pred.get('has_live_data') and quick_pred.get('live_odds_available') and quick_pred.get('live_odds'):
                            st.markdown("---")
                            st.markdown("**💰 Live Betting Odds**")
                            
                            odds_data = quick_pred.get('live_odds', {})
                            if odds_data:
                                # Show odds from first available bookmaker
                                first_bookmaker = list(odds_data.keys())[0]
                                bookmaker_odds = odds_data[first_bookmaker]
                                
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    home_odds = bookmaker_odds.get('home', 'N/A')
                                    st.markdown(f"**{match['home_team']}**: {home_odds}")
                                
                                with col2:
                                    st.markdown(f"**{first_bookmaker}**")
                                
                                with col3:
                                    away_odds = bookmaker_odds.get('away', 'N/A')
                                    st.markdown(f"**{match['away_team']}**: {away_odds}")
                                
                                # Show additional bookmakers if available
                                if len(odds_data) > 1:
                                    with st.expander(f"📊 More Odds ({len(odds_data)-1} more bookmakers)"):
                                        for bookmaker, odds in list(odds_data.items())[1:]:
                                            col1, col2, col3 = st.columns(3)
                                            with col1:
                                                st.write(f"{match['home_team']}: {odds.get('home', 'N/A')}")
                                            with col2:
                                                st.write(bookmaker)
                                            with col3:
                                                st.write(f"{match['away_team']}: {odds.get('away', 'N/A')}")
                        
                        # Enhanced data indicators only
                        if quick_pred and quick_pred.get('has_live_data'):
                            st.markdown("**🔴 Enhanced with Live Data:**")
                            indicators = []
                            if quick_pred.get('live_odds_available'):
                                indicators.append("💰 Odds")
                            if quick_pred.get('team_form_available'):
                                indicators.append("📈 Form")
                            if quick_pred.get('head_to_head_available'):
                                indicators.append("⚔️ H2H")
                            if quick_pred.get('standings_available'):
                                indicators.append("🏆 Standings")
                            
                            if indicators:
                                st.markdown(f"**Available**: {', '.join(indicators)}")
                        
                        st.markdown("---")
                else:
                    st.info("No live matches found for this league")
            except Exception as e:
                st.warning(f"Could not fetch live matches: {e}")
        
        # Get upcoming games
        upcoming_games = get_upcoming_games(selected_league)
        
        if len(upcoming_games) == 0:
            st.info("No upcoming games found for this league")
            return
        
        # Load teams
        team_names = get_teams()
        
        # Optional manual odds input before generating predictions
        if isinstance(upcoming_games, pd.DataFrame) and len(upcoming_games) > 0:
            st.subheader("✍️ Manual Odds (optional)")
            st.caption("Enter decimal odds for each matchup. Leave blank (0.00) to use AI only.")
            try:
                upcoming_subset_for_odds = upcoming_games.head(25)
                for _, game in upcoming_subset_for_odds.iterrows():
                    home_raw = game.get('home_team_id', 0)
                    away_raw = game.get('away_team_id', 0)
                    home_id = int(home_raw) if home_raw is not None else 0
                    away_id = int(away_raw) if away_raw is not None else 0
                    home_name = team_names.get(home_id, f"Team {home_id}")
                    away_name = team_names.get(away_id, f"Team {away_id}")
                    date_str = str(game.get('date_event', ''))[:10]
                    manual_key = f"manual_odds::{home_name}::{away_name}::{date_str}"
                    id_key = f"manual_odds_by_ids::{home_id}::{away_id}::{date_str}"
                    col_a, col_b, col_c = st.columns([2, 1, 1])
                    with col_a:
                        st.markdown(f"**{home_name} vs {away_name}** — {date_str}")
                    # Load existing values if set
                    existing = st.session_state.get(id_key) or st.session_state.get(manual_key, {})
                    existing_home = float(existing.get('home', 0.0) or 0.0)
                    existing_away = float(existing.get('away', 0.0) or 0.0)
                    with col_b:
                        home_input = st.number_input("Home", min_value=0.0, step=0.01, format="%.2f", key=f"home_input::{manual_key}", value=existing_home)
                    with col_c:
                        away_input = st.number_input("Away", min_value=0.0, step=0.01, format="%.2f", key=f"away_input::{manual_key}", value=existing_away)
                    # Persist if any provided
                    if home_input > 0 or away_input > 0:
                        st.session_state[id_key] = {"home": home_input, "away": away_input}
                        st.session_state[manual_key] = {"home": home_input, "away": away_input}
            except Exception:
                pass

        # Generate predictions button with modern styling
        st.markdown("""
        <style>
        .stButton > button {
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 1rem 2rem;
            font-size: 1.2rem;
            font-weight: 600;
            box-shadow: 0 8px 32px rgba(44, 62, 80, 0.3);
            transition: all 0.3s ease;
            width: 100%;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 40px rgba(44, 62, 80, 0.4);
        }
        
        .stButton > button:active {
            transform: translateY(0);
        }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🎯 Generate Expert Predictions", type="primary", use_container_width=True):
                with st.spinner("Analyzing matches..."):
                    predictions = []
                    seen_matchups = set()  # Track unique matchups
                    
                    if isinstance(upcoming_games, pd.DataFrame):
                        upcoming_subset = upcoming_games.head(50)  # Get more to account for duplicates
                        for _, game in upcoming_subset.iterrows():
                            # Create unique matchup key (home_team, away_team, date)
                            matchup_key = (
                                game.get('home_team_id'),
                                game.get('away_team_id'),
                                str(game.get('date_event', ''))[:10]  # Just the date part
                            )
                            
                            # Skip if we've already seen this matchup
                            if matchup_key in seen_matchups:
                                continue
                            
                            seen_matchups.add(matchup_key)
                            pred = make_expert_prediction(game, model_data, team_names)
                            if pred:
                                predictions.append(pred)
                            
                            # Limit to 25 unique predictions (increased from 10)
                            if len(predictions) >= 25:
                                break
                    else:
                        st.warning("Unable to process upcoming games data")
                        predictions = []
                    
                    # Store predictions in session state to display outside column context
                    st.session_state.predictions = predictions
                    st.session_state.league_name = league_name
        
        # Display predictions outside column context for full width
        if hasattr(st.session_state, 'predictions') and st.session_state.predictions:
            predictions = st.session_state.predictions
            league_name = st.session_state.league_name
            
            # Group predictions by date
            from collections import defaultdict
            predictions_by_date = defaultdict(list)
            for pred in predictions:
                predictions_by_date[pred['date']].append(pred)
            
            # Display predictions grouped by date
            for date in sorted(predictions_by_date.keys()):
                # Date header
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
                    padding: 1rem 2rem;
                    border-radius: 15px;
                    margin: 2rem 0 1rem 0;
                    text-align: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                ">
                    <h2 style="color: white; margin: 0; font-size: 1.5rem;">📅 {date}</h2>
                </div>
                """, unsafe_allow_html=True)
                
                # Display predictions for this date
                for i, prediction in enumerate(predictions_by_date[date]):
                    # Determine confidence level and intensity class
                    confidence_val = float(prediction.get('confidence', '50%').rstrip('%'))
                    if confidence_val >= 80:
                        conf_class = "confidence-high"
                    elif confidence_val >= 65:
                        conf_class = "confidence-medium"
                    else:
                        conf_class = "confidence-low"
                    
                    # Determine intensity class
                    intensity = prediction.get('intensity', 'Competitive Game')
                    if "Close" in intensity:
                        intensity_class = "intensity-close"
                    elif "Competitive" in intensity:
                        intensity_class = "intensity-competitive"
                    elif "Moderate" in intensity:
                        intensity_class = "intensity-moderate"
                    else:
                        intensity_class = "intensity-decisive"
                    
                    # Determine winner class
                    if prediction.get('winner') == prediction.get('home_team'):
                        winner_class = "winner-home"
                    elif prediction.get('winner') == prediction.get('away_team'):
                        winner_class = "winner-away"
                    else:
                        winner_class = "winner-draw"
                    
                    # Create prediction card using Streamlit components
                    with st.container():
                        st.markdown(f"""
                        <div class="prediction-card fade-in-up">
                            <div class="match-header">
                                <h2 class="match-title">{prediction.get('home_team', 'Home')} vs {prediction.get('away_team', 'Away')}</h2>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Score display with dividers and responsive layout
                        st.markdown("---")
                        
                        # Mobile-friendly layout: Team name above score
                        col1, col2, col3 = st.columns([2, 1, 2])
                        
                        with col1:
                            st.markdown(f"<div class='team-name'>{prediction.get('home_team', 'Home')}</div>", unsafe_allow_html=True)
                            st.markdown(f"<div class='team-score'>{prediction.get('home_score', '0')}</div>", unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown("<div class='vs-text'>VS</div>", unsafe_allow_html=True)
                        
                        with col3:
                            st.markdown(f"<div class='team-name'>{prediction.get('away_team', 'Away')}</div>", unsafe_allow_html=True)
                            st.markdown(f"<div class='team-score'>{prediction.get('away_score', '0')}</div>", unsafe_allow_html=True)
                        
                        st.markdown("---")
                        
                        # Odds display using manual odds if available
                        if prediction.get('live_odds_available'):
                            home_name = prediction.get('home_team', 'Home')
                            away_name = prediction.get('away_team', 'Away')
                            date_key = prediction.get('date', 'TBD')
                            home_id_disp = prediction.get('home_team_id')
                            away_id_disp = prediction.get('away_team_id')
                            id_key_disp = f"manual_odds_by_ids::{home_id_disp}::{away_id_disp}::{date_key}"
                            manual_key = f"manual_odds::{home_name}::{away_name}::{date_key}"
                            manual_odds = st.session_state.get(id_key_disp) or st.session_state.get(manual_key)
                            if manual_odds:
                                home_odds = manual_odds.get('home', 'N/A')
                                away_odds = manual_odds.get('away', 'N/A')
                                st.markdown(f"""
                                <div class="odds-container">
                                    <div class="odds-header">
                                        <h4 class="odds-title">💰 Manual Betting Odds</h4>
                                    </div>
                                    <div class="odds-content">
                                """, unsafe_allow_html=True)
                                st.markdown(f"""
                                <div class="odds-row">
                                    <div class="odds-team">
                                        <div class="team-name">{home_name}</div>
                                        <div class="odds-value home-odds">{home_odds}</div>
                                    </div>
                                    <div class="odds-vs">VS</div>
                                    <div class="odds-team">
                                        <div class="team-name">{away_name}</div>
                                        <div class="odds-value away-odds">{away_odds}</div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                st.markdown("</div></div>", unsafe_allow_html=True)
                            
                            # Enhanced confidence
                            if prediction.get('enhanced_confidence'):
                                enhanced_conf = prediction.get('enhanced_confidence', 0)
                                st.markdown(f"**🎯 Enhanced Confidence**: {enhanced_conf:.1%}")
                        
                        st.markdown("---")
                        
                        # Winner display
                        st.markdown(f"""
                        <div class="winner-display">
                            <div class="winner-text {winner_class}">
                                🏆 {prediction.get('winner', 'Unknown')} Wins
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Confidence bar
                        st.markdown(f"""
                        <div class="confidence-bar">
                            <div class="confidence-fill {conf_class}" style="width: {confidence_val}%">
                                <div class="confidence-text">{prediction.get('confidence', '50%')} Confidence</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Intensity badge
                        st.markdown(f"""
                        <div class="intensity-badge {intensity_class}">
                            📊 {prediction.get('intensity', 'Competitive Game')}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Hybrid prediction information
                        if prediction.get('prediction_type') == 'Hybrid AI + Live Odds':
                            st.markdown("---")
                            st.markdown("**🎯 Hybrid Prediction Analysis**")
                            
                            # Show AI vs Hybrid comparison
                            ai_prob = prediction.get('ai_probability', 0)
                            hybrid_prob = prediction.get('hybrid_probability', 0)
                            confidence_boost = prediction.get('confidence_boost', 0)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("🤖 AI Probability", f"{ai_prob:.1%}")
                            with col2:
                                st.metric("🎲 Hybrid Probability", f"{hybrid_prob:.1%}")
                            with col3:
                                boost_color = "normal" if confidence_boost >= 0 else "inverse"
                                st.metric("📈 Confidence Boost", f"{confidence_boost:+.1%}", delta_color=boost_color)
                            
                            # Show prediction type
                            st.markdown(f"**🔬 Method:** {prediction.get('prediction_type')}")
                        else:
                            # Show prediction type for non-hybrid predictions
                            st.markdown(f"**🔬 Method:** {prediction.get('prediction_type')}")
                    
            
            # Modern summary section
            high_conf = sum(1 for p in predictions if float(p.get('confidence', '50%').rstrip('%')) >= 70)
            home_wins = sum(1 for p in predictions if p.get('winner') != 'Draw' and p.get('winner') == p.get('home_team'))
            away_wins = sum(1 for p in predictions if p.get('winner') != 'Draw' and p.get('winner') == p.get('away_team'))
            draws = sum(1 for p in predictions if p.get('winner') == 'Draw')
            avg_score_diff = np.mean([abs(p.get('score_diff', 0)) for p in predictions])
            ai_count = sum(1 for p in predictions if "AI" in p.get('prediction_type', 'AI Only'))
            hybrid_count = sum(1 for p in predictions if p.get('prediction_type') in ('Hybrid AI + Live Odds', 'Hybrid AI + Manual Odds'))
            avg_confidence_boost = np.mean([p.get('confidence_boost', 0) for p in predictions if p.get('confidence_boost') is not None])
            
            st.markdown(f"""
            <div class="summary-card fade-in-up">
                <h3 class="summary-title">📊 Prediction Summary</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 2rem;">
                    <div class="summary-metric">
                        <div class="summary-metric-value">{high_conf}/{len(predictions)}</div>
                        <div class="summary-metric-label">High Confidence</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{home_wins}</div>
                        <div class="summary-metric-label">Home Wins</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{away_wins}</div>
                        <div class="summary-metric-label">Away Wins</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{draws}</div>
                        <div class="summary-metric-label">Draws</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{avg_score_diff:.1f}</div>
                        <div class="summary-metric-label">Avg Margin (pts)</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{hybrid_count}/{len(predictions)}</div>
                        <div class="summary-metric-label">Hybrid Predictions</div>
                    </div>
                    <div class="summary-metric">
                        <div class="summary-metric-value">{avg_confidence_boost:+.1%}</div>
                        <div class="summary-metric-label">Avg Confidence Boost</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    
    else:
        # Modern league selection interface
        st.markdown("""
        <div style="text-align: center; margin: 3rem 0;">
            <h2 style="color: #2c3e50; font-size: 2.5rem; margin-bottom: 1rem;">🏉 Select a League to Begin</h2>
            <p style="color: #7f8c8d; font-size: 1.2rem;">Choose from our AI-powered rugby prediction leagues</p>
        </div>
        """, unsafe_allow_html=True)
        
        # League cards in modern grid
        cols = st.columns(2)
        for i, (league_id, league_data) in enumerate(LEAGUE_CONFIGS.items()):
            with cols[i % 2]:
                # Check if model exists
                model_data = load_optimized_model(league_id)
                upcoming = get_upcoming_games(league_id)
                
                # Create modern league card
                status_color = "#27ae60" if model_data else "#f39c12"
                status_text = "✅ Ready" if model_data else "⚠️ Not Available"
                
                st.markdown(f"""
                <div style="
                    background: linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%);
                    border-radius: 20px;
                    padding: 2rem;
                    margin: 1rem 0;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    border: 1px solid rgba(255,255,255,0.2);
                    transition: all 0.3s ease;
                    text-align: center;
                ">
                    <h3 style="color: #2c3e50; font-size: 1.8rem; margin-bottom: 1rem;">{league_data['name']}</h3>
                    <p style="color: #7f8c8d; margin-bottom: 1.5rem;">AI-powered predictions</p>
                    
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                        <div style="color: {status_color}; font-weight: 600;">{status_text}</div>
                        <div style="color: #495057; font-weight: 600;">{len(upcoming)} Games</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"Select {league_data['name']}", key=f"select_{league_id}", use_container_width=True):
                    st.session_state.selected_league = league_id
                    st.rerun()

if __name__ == "__main__":
    main()
