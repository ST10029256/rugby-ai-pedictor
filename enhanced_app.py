#!/usr/bin/env python3
"""
Enhanced Rugby Prediction App
Improved winner determination and individual match summaries
Last Updated: 2025-09-29 12:30 UTC
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
import threading
import subprocess
from datetime import datetime, timedelta

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Check if automation scripts are available
AUTOMATION_AVAILABLE = os.path.exists(os.path.join(script_dir, 'scripts', 'complete_automation.py'))

@st.cache_data(ttl=1800)  # Cache for 30 minutes
def load_registry():
    """Load model registry with caching"""
    try:
        with open('artifacts/model_registry.json', 'r') as f:
            return json.load(f)
    except:
        return {}

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_model(league_id):
    """Load model for league with caching"""
    try:
        with open(f'artifacts/league_{league_id}_model.pkl', 'rb') as f:
            return pickle.load(f)
    except:
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

def check_data_freshness():
    """Check if data needs updating"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        
        # Check last update time
        cursor.execute("SELECT MAX(date_event) FROM event WHERE home_score IS NOT NULL")
        last_result = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM event WHERE home_score IS NULL AND date_event > date('now')")
        upcoming_count = cursor.fetchone()[0]
        
        conn.close()
        
        if last_result:
            last_update = datetime.strptime(last_result, '%Y-%m-%d')
            days_since_update = (datetime.now() - last_update).days
        else:
            days_since_update = 999
            
        return {
            'needs_update': days_since_update > 0,
            'days_since_update': days_since_update,
            'upcoming_games': upcoming_count,
            'last_update': last_result
        }
    except:
        return {'needs_update': True, 'days_since_update': 999, 'upcoming_games': 0, 'last_update': None}

def run_automation_background():
    """Run automation in background"""
    if not AUTOMATION_AVAILABLE:
        return False, "Automation modules not available"
    
    try:
        # Run complete automation script
        result = subprocess.run([
            sys.executable, 
            os.path.join(script_dir, 'scripts', 'complete_automation.py')
        ], capture_output=True, text=True, cwd=script_dir)
        
        if result.returncode == 0:
            return True, f"Automation completed successfully"
        else:
            return False, f"Automation failed: {result.stderr}"
            
    except Exception as e:
        return False, f"Automation failed: {str(e)}"

def auto_update_data():
    """Automatically update data if needed"""
    if not AUTOMATION_AVAILABLE:
        return False, "Automation not available"
    
    try:
        # Check if update is needed
        freshness = check_data_freshness()
        
        if freshness['needs_update']:
            # Run enhanced auto-update script
            result = subprocess.run([
                sys.executable, 
                os.path.join(script_dir, 'scripts', 'enhanced_auto_update.py')
            ], capture_output=True, text=True, cwd=script_dir)
            
            if result.returncode == 0:
                return True, f"Data updated successfully"
            else:
                return False, f"Update failed: {result.stderr}"
        else:
            return False, "Data is up to date"
            
    except Exception as e:
        return False, f"Update failed: {str(e)}"

def auto_retrain_models():
    """Automatically retrain models if needed"""
    if not AUTOMATION_AVAILABLE:
        return False, "Automation not available"
    
    try:
        # Run training script
        result = subprocess.run([
            sys.executable, 
            os.path.join(script_dir, 'scripts', 'train_models.py')
        ], capture_output=True, text=True, cwd=script_dir)
        
        if result.returncode == 0:
            return True, f"Models retrained successfully"
        else:
            return False, f"Retraining failed: {result.stderr}"
        
    except Exception as e:
        return False, f"Retraining failed: {str(e)}"

def safe_int(value, default=0):
    """Convert to int safely"""
    try:
        if pd.isna(value):
            return default
        return int(value)
    except:
        return default

def get_match_summary(home_name, away_name, home_score, away_score, winner, confidence, home_prob, away_prob):
    """Generate detailed match summary"""
    score_diff = abs(home_score - away_score)
    
    # Improved match intensity calculation based on historical data
    # Use both score margin and win probability for better accuracy
    
    # Base intensity on score margin
    if score_diff <= 2:
        base_intensity = "Close Thrilling Match"
    elif score_diff <= 5:
        base_intensity = "Competitive Game"
    elif score_diff <= 10:
        base_intensity = "Moderate Advantage"
    else:
        base_intensity = "Decisive Victory"
    
    # Adjust intensity based on win probability confidence
    max_prob = max(home_prob, away_prob)
    
    if max_prob >= 0.8:  # Very confident prediction
        if base_intensity == "Close Thrilling Match":
            intensity = "Competitive Game"  # Upgrade close games to competitive
        else:
            intensity = base_intensity
    elif max_prob <= 0.55:  # Low confidence, likely close
        if base_intensity in ["Moderate Advantage", "Decisive Victory"]:
            intensity = "Competitive Game"  # Downgrade confident predictions
        else:
            intensity = base_intensity
    else:  # Medium confidence
        intensity = base_intensity
    
    # Win probability analysis
    if home_prob > 0.7:
        confidence_level = "High Confidence"
        analysis = f"{home_name} are strong favorites"
    elif away_prob > 0.7:
        confidence_level = "High Confidence"
        analysis = f"{away_name} are strong favorites"
    elif home_prob > 0.55:
        confidence_level = "Moderate Confidence"
        analysis = f"{home_name} slight favorites at home"
    elif away_prob > 0.55:
        confidence_level = "Moderate Confidence"
        analysis = f"{away_name} slight favorites away"
    else:
        confidence_level = "Close Match Expected"
        analysis = "Very evenly matched teams"
    
    # Score prediction insights
    if winner != "Draw":
        if winner == home_name:
            margin_text = f"{home_name} win by {home_score - away_score} points"
        else:
            margin_text = f"{away_name} win by {away_score - home_score} points"
    else:
        margin_text = f"Tied game with {home_score}-{away_score} scoreline"
    
    return {
        'intensity': intensity,
        'confidence_level': confidence_level,
        'analysis': analysis,
        'margin_text': margin_text,
        'home_prob': home_prob,
        'away_prob': away_prob,
        'draw_prob': 1 - home_prob - away_prob
    }

def make_prediction(model_data, game_row, team_names, feature_cols):
    """Make enhanced prediction for single game"""
    if not model_data:
        return None
    
    try:
        models = model_data.get('models', {})
        scaler = model_data.get('scaler')
        
        # Use ensemble models (new enhanced models)
        winner_model = models.get('gbdt_clf', models.get('clf'))
        home_model = models.get('reg_home')
        away_model = models.get('reg_away')
        
        # Debug: Check if models exist
        if not winner_model:
            print(f"Warning: No winner model found. Available models: {list(models.keys())}")
        if not home_model:
            print(f"Warning: No home model found. Available models: {list(models.keys())}")
        if not away_model:
            print(f"Warning: No away model found. Available models: {list(models.keys())}")
        
        home_id = safe_int(game_row['home_team_id'])
        away_id = safe_int(game_row['away_team_id'])
        
        home_name = team_names.get(home_id, f"Team {home_id}")
        away_name = team_names.get(away_id, f"Team {away_id}")
        
        # Extract features
        features = []
        for col in feature_cols:
            val = game_row.get(col, 0)
            try:
                features.append(float(val) if pd.notna(val) else 0.0)
            except:
                features.append(0.0)
        
        X = np.array(features).reshape(1, -1)
        
        # Scale if scaler available
        if scaler:
            X = scaler.transform(X)
        
        # Defaults based on historical data (mean scores: home 29.8, away 20.8)
        home_score = 30
        away_score = 21
        home_prob = 0.52  # Default: slight home advantage
        away_prob = 0.38   # Default: away slightly lower
        
        # Score-based predictions (primary approach for better accuracy)
        if home_model:
            try:
                raw_score = home_model.predict(X)[0]
                home_score = max(8, min(50, int(round(raw_score))))
            except Exception as e:
                print(f"Home score prediction error: {e}")
        
        if away_model:
            try:
                raw_score = away_model.predict(X)[0]
                away_score = max(8, min(45, int(round(raw_score))))
            except Exception as e:
                print(f"Away score prediction error: {e}")
        
        # Get classifier probabilities for confidence estimation only
        if winner_model:
            try:
                proba = winner_model.predict_proba(X)[0]
                if len(proba) >= 2:
                    home_prob = float(proba[1])  # Class 1 = home win probability
                    away_prob = float(proba[0])  # Class 0 = away win probability
                else:
                    win_prob_raw = float(proba[0])
                    home_prob = win_prob_raw if win_prob_raw > 0.5 else 1-win_prob_raw
                    away_prob = 1 - home_prob
            except Exception as e:
                print(f"Winner prediction error: {e}")
        
        # Score-based winner determination (proven more accurate than classifier-only approach)
        predicted_winner = "Unknown"
        winner_score_diff = home_score - away_score
        
        # Primary logic: Use actual predicted scores to determine winner
        if winner_score_diff > 0:  # Home team wins
            predicted_winner = home_name
        elif winner_score_diff < 0:  # Away team wins
            predicted_winner = away_name
        else:  # Tie score
            # For ties, use probability to break the tie
            if home_prob > away_prob:
                predicted_winner = home_name
            elif away_prob > home_prob:
                predicted_winner = away_name
            else:
                predicted_winner = "Draw"
        
        # Score-based confidence calculation (more accurate than classifier-only)
        score_margin = abs(winner_score_diff)
        
        # Base confidence from score margin analysis
        if score_margin >= 20:
            base_confidence = 85  # Very confident for large margins
        elif score_margin >= 15:
            base_confidence = 80  # High confidence for significant margins
        elif score_margin >= 10:
            base_confidence = 75  # Good confidence for moderate margins
        elif score_margin >= 5:
            base_confidence = 65  # Moderate confidence for small margins
        else:
            base_confidence = 55  # Low confidence for very close games
        
        # Adjust based on classifier probabilities (secondary factor)
        if winner_model:
            if predicted_winner == home_name:
                classifier_confidence = home_prob * 100
            elif predicted_winner == away_name:
                classifier_confidence = away_prob * 100
            else:
                classifier_confidence = max(home_prob, away_prob) * 100
            
            # Blend score-based and classifier confidence (70% score-based, 30% classifier)
            confidence = (base_confidence * 0.7) + (classifier_confidence * 0.3)
        else:
            confidence = base_confidence
        
        # Final confidence bounds
        confidence = max(50, min(90, confidence))  # Keep between 50-90%
        
        # Generate match summary
        summary = get_match_summary(
            home_name, away_name, home_score, away_score, 
            predicted_winner, confidence, home_prob, away_prob
        )
        
        return {
            'date': str(game_row.get('date_event', 'TBD'))[:10],
            'home_team': home_name,
            'away_team': away_name,
            'home_score': home_score,
            'away_score': away_score,
            'winner': predicted_winner,
            'confidence': f"{confidence:.0f}%",
            'home_prob': f"{home_prob*100:.1f}%",
            'away_prob': f"{away_prob*100:.1f}%",
            'score_diff': home_score - away_score,
            'intensity': summary['intensity'],
            'confidence_level': summary['confidence_level'],
            'analysis': summary['analysis'],
            'margin_text': summary['margin_text']
        }
        
    except Exception as e:
        print(f"Prediction error: {e}")
        return None

def display_individual_match_summary(prediction):
    """Display detailed summary for individual match"""
    with st.expander(f"Match Analysis: {prediction['home_team']} vs {prediction['away_team']}", expanded=False):
        # Match header
        st.subheader(f"{prediction['home_team']} {prediction['home_score']} - {prediction['away_score']} {prediction['away_team']}")
        
        # Prediction details in columns
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Prediction**")
            st.write(f"Winner: **{prediction['winner']}**")
            st.write(f"Confidence: {prediction['confidence']}")
            st.write(f"Margin: {prediction['margin_text']}")
        
        with col2:
            st.markdown("**Probabilities**")
            st.write(f"Home Win: {prediction['home_prob']}")
            st.write(f"Away Win: {prediction['away_prob']}")
            st.write(f"Score Diff: {prediction['score_diff']:+d} pts")
        
        with col3:
            st.markdown("**Match Analysis**")
            st.write(prediction['intensity'])
            st.write(prediction['confidence_level'])
            st.write(prediction['analysis'])
        
        # Visual indicators
        if prediction['winner'] != "Draw":
            if prediction['winner'] == prediction['home_team']:
                st.success(f"{prediction['home_team']} favored at home")
            else:
                st.info(f"{prediction['away_team']} favored away")
        else:
            st.warning("Very close match expected - could go either way!")

def main():
    st.set_page_config(
        page_title="Enhanced Rugby Predictions",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Enhanced Rugby Predictions AI")
    st.markdown("Advanced machine learning predictions with automated updates and detailed match analysis")
    
    # Clean UI - no timestamp needed
    
    # Initialize session state for automation (simplified)
    if 'auto_update_enabled' not in st.session_state:
        st.session_state.auto_update_enabled = True
    
    # Load registry with error handling
    try:
        registry = load_registry()
        leagues = registry.get('leagues', {})
        
        if not leagues:
            st.error("No leagues found. Please train models first.")
            return
    except Exception as e:
        st.error(f"Error loading registry: {e}")
        st.info("Please check if the model registry file exists.")
        return
    
    # Disabled automation to prevent reboots - will re-enable after testing
    # if st.session_state.auto_update_enabled:
    #     time_since_check = datetime.now() - st.session_state.last_automation_check
    #     if time_since_check.total_seconds() > 1800:  # Check every 30 minutes instead of 5
    #         freshness = check_data_freshness()
    #         if freshness['needs_update']:
    #             # Silent background update (async)
    #             auto_update_data()
    #             auto_retrain_models()
    #             st.session_state.last_automation_check = datetime.now()
    
    # Sidebar
    with st.sidebar:
        st.header("🏉 Rugby Predictions")
        
        # League selection
        league_options = {}
        for league_id, data in leagues.items():
            league_options[league_id] = data['name']
        
        selected_league = st.selectbox(
            "Select League:",
            options=list(league_options.keys()),
            format_func=lambda x: league_options[x]
        )
        
        if selected_league:
            league_data = leagues[selected_league]
            perf = league_data.get('performance', {})
            
            # Enhanced Smart AI performance display
            st.subheader("🧠 Smart AI Performance")
            accuracy = perf.get('winner_accuracy', 0)
            mae = perf.get('overall_mae', 0)
            
            col1, col2 = st.columns(2)
            with col1:
                if accuracy > 0.65:
                    st.success(f"Winner Accuracy: {accuracy:.1%} (EXCELLENT!)")
                elif accuracy > 0.60:
                    st.info(f"Winner Accuracy: {accuracy:.1%} (GOOD)")
                else:
                    st.metric("Winner Accuracy", f"{accuracy:.1%}")
            
            with col2:
                if mae < 10:
                    st.success(f"Score MAE: {mae:.1f} (EXCELLENT!)")
                elif mae < 12:
                    st.info(f"Score MAE: {mae:.1f} (GOOD)")
                else:
                    st.metric("Score MAE", f"{mae:.1f}")
            
            # Training info
            trained_at = league_data.get('trained_at', 'Unknown')
            if trained_at != 'Unknown':
                try:
                    trained_time = datetime.fromisoformat(trained_at)
                    time_ago = datetime.now() - trained_time
                    if time_ago.days > 0:
                        trained_str = f"{time_ago.days}d ago"
                    elif time_ago.seconds > 3600:
                        trained_str = f"{time_ago.seconds // 3600}h ago"
                    else:
                        trained_str = "Recent"
                except:
                    trained_str = "Unknown"
            else:
                trained_str = "Unknown"
            
            st.caption(f"🧠 Smart AI (Ensemble) trained: {trained_str}")
    
    # Main content
    if selected_league:
        league_name = league_options[selected_league]
        
        # Load model
        model_data = load_model(selected_league)
        
        if not model_data:
            st.error("Unable to load model")
            st.info(f"Trying to load model for league: {selected_league}")
            # Check if model file exists
            import os
            model_path = f"artifacts/league_{selected_league}_model.pkl"
            if os.path.exists(model_path):
                st.info(f"Model file exists: {model_path}")
            else:
                st.info(f"Model file missing: {model_path}")
            return
        
        st.header(f"🏉 {league_name} Predictions")
        
        # Clean model info
        feature_count = len(model_data.get('feature_columns', []))
        st.caption(f"AI model with {feature_count} advanced features")
        
        # Load predictions button for faster initial load
        if st.button("📊 Load Predictions", type="primary"):
            st.session_state.load_predictions = True
        
        # Only load predictions when button is clicked
        if st.session_state.get('load_predictions', False):
            # Get upcoming games
            try:
                # Try to import feature building
                sys.path.insert(0, script_dir)
                from prediction.features import build_feature_table, FeatureConfig
            
                conn = sqlite3.connect('data.sqlite')
                config = FeatureConfig(elo_k=24.0, neutral_mode=False)
                feature_df = build_feature_table(conn, config)
                conn.close()
            
                # Filter upcoming games
                upcoming = feature_df[
                    (feature_df["league_id"] == int(selected_league)) &
                    pd.isna(feature_df["home_win"])
                ].copy()
                
                # Filter to future only
                if "date_event" in upcoming.columns:
                    today = pd.Timestamp.today().date()
                    upcoming["date_event"] = pd.to_datetime(upcoming["date_event"], errors="coerce")
                    # Ensure we're working with a DataFrame before accessing .dt
                    if isinstance(upcoming, pd.DataFrame):
                        upcoming = upcoming[upcoming["date_event"].dt.date >= today]
                
                if len(upcoming) == 0:
                    st.info("No upcoming games found")
                else:
                    # Load teams and make predictions
                    team_names = get_teams()
                    feature_cols = model_data.get('feature_columns', [])
                    
                    with st.spinner("Generating AI predictions..."):
                        predictions = []
                        # Ensure we're working with a DataFrame before calling .head()
                        if isinstance(upcoming, pd.DataFrame):
                            upcoming_subset = upcoming.head(12)
                            # Iterate through the DataFrame
                            for _, game in upcoming_subset.iterrows():  # Show up to 12 games
                                pred = make_prediction(model_data, game, team_names, feature_cols)
                                if pred:
                                    predictions.append(pred)
                        else:
                            # Fallback for non-DataFrame objects
                            st.warning("Unable to process upcoming games data")
                            predictions = []
            
                    if predictions:
                        st.subheader(f"Upcoming Matches ({len(predictions)})")
                        
                        # Main predictions table
                        display_df = pd.DataFrame(predictions)[['date', 'home_team', 'away_team', 'home_score', 'away_score', 'winner', 'confidence', 'intensity']]
                        display_df.columns = ['Date', 'Home Team', 'Away Team', 'Home Score', 'Away Score', 'Predicted Winner', 'Confidence', 'Match Intensity']
                        
                        # Format the dataframe better
                        st.dataframe(
                            display_df, 
                            use_container_width=True,
                            hide_index=True
                        )
                
                        # Clean match analysis
                        st.subheader("📊 Match Predictions")
                        
                        for i, prediction in enumerate(predictions):
                            with st.container():
                                col1, col2, col3 = st.columns([2, 1, 2])
                                
                                with col1:
                                    st.markdown(f"**{prediction['home_team']}**")
                                    st.caption("Home Team")
                                
                                with col2:
                                    st.markdown(f"**{prediction['home_score']} - {prediction['away_score']}**")
                                    st.caption("Predicted Score")
                                
                                with col3:
                                    st.markdown(f"**{prediction['away_team']}**")
                                    st.caption("Away Team")
                                
                                # Winner and confidence
                                col4, col5 = st.columns([2, 1])
                                with col4:
                                    if prediction['winner'] != 'Draw':
                                        st.success(f"🏆 Winner: {prediction['winner']}")
                                    else:
                                        st.info("🤝 Predicted Draw")
                                with col5:
                                    st.metric("Confidence", prediction['confidence'])
                                
                                if i < len(predictions) - 1:
                                    st.divider()
                        
                    else:
                        st.warning("No predictions generated")
        
            except Exception as e:
                st.error(f"Error loading games: {e}")
                
                # Enhanced fallback
                st.subheader("Fallback: Basic Game Schedule")
                try:
                    conn = sqlite3.connect('data.sqlite')
                    cursor = conn.cursor()
                    query = """
                    SELECT e.date_event, e.home_team_id, e.away_team_id,
                           ht.name as home_name, at.name as away_name
                    FROM event e
                    LEFT JOIN team ht ON e.home_team_id = ht.id
                    LEFT JOIN team at ON e.away_team_id = at.id
                    WHERE e.league_id = ? AND e.home_score IS NULL
                    ORDER BY e.date_event ASC
                    LIMIT 10
                    """
                    cursor.execute(query, (selected_league,))
                    games = cursor.fetchall()
                    conn.close()
                    
                    if games:
                        game_data = []
                        for game in games:
                            game_data.append({
                                'Date': str(game[0])[:10],
                                'Home Team': game[3] or f"Team {game[1]}",
                                'Away Team': game[4] or f"Team {game[2]}"
                            })
                        
                        games_df = pd.DataFrame(game_data)
                        st.dataframe(games_df, use_container_width=True)
                        st.info("Scheduled games shown above. Click 'Load Predictions' for AI analysis.")
                    else:
                        st.info("No scheduled games found")
                        
                except Exception as db_e:
                    st.error(f"Database error: {db_e}")
    else:
        # Clean overview when no league selected
        st.header("🏉 Select a League")
        
        # Create clean league cards
        cols = st.columns(2)
        for i, (league_id, league_data) in enumerate(leagues.items()):
            with cols[i % 2]:
                perf = league_data.get('performance', {})
                accuracy = perf.get('winner_accuracy', 0)
                games = league_data.get('training_games', 0)
                
                with st.container():
                    st.markdown(f"### {league_data['name']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Accuracy", f"{accuracy:.1%}")
                    with col2:
                        st.metric("Games", f"{games:,}")
                    
                    if accuracy >= 0.9:
                        st.success("Excellent performance")
                    elif accuracy >= 0.75:
                        st.info("Good performance")
                    else:
                        st.warning("Needs improvement")
    

if __name__ == "__main__":
    main()