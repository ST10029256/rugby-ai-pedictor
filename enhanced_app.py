#!/usr/bin/env python3
"""
Enhanced Rugby AI Prediction App with Highlightly API Integration
"""

import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from prediction.hybrid_predictor import HybridPredictor
from prediction.enhanced_predictor import EnhancedRugbyPredictor
from prediction.config import LEAGUE_MAPPINGS

# Page configuration
st.set_page_config(
    page_title="🏉 Enhanced Rugby AI Predictions",
    page_icon="🏉",
    layout="wide",
    initial_sidebar_state="expanded"
)

def load_models():
    """Load AI models"""
    try:
        predictor = HybridPredictor('data.sqlite')
        return predictor, None
    except Exception as e:
        st.error(f"Error loading AI models: {e}")
        return None, str(e)

def load_enhanced_predictor():
    """Load enhanced predictor with Highlightly API"""
    try:
        api_key = os.getenv('HIGHLIGHTLY_API_KEY')
        if not api_key:
            return None, "HIGHLIGHTLY_API_KEY not set"
        
        enhanced_predictor = EnhancedRugbyPredictor('data.sqlite', api_key)
        return enhanced_predictor, None
    except Exception as e:
        return None, str(e)

def main():
    """Main application"""
    
    # Header
    st.title("🏉 Enhanced Rugby AI Prediction System")
    st.markdown("**Powered by AI + Live Data from Highlightly API**")
    st.write("---")
    
    # Load models
    predictor, error = load_models()
    if not predictor:
        st.error(f"❌ Failed to load AI models: {error}")
        return
    
    # Load enhanced predictor
    enhanced_predictor, enhanced_error = load_enhanced_predictor()
    if enhanced_predictor:
        st.success("✅ Enhanced predictor loaded with Highlightly API")
    else:
        st.warning(f"⚠️ Enhanced features unavailable: {enhanced_error}")
    
    # Sidebar
    with st.sidebar:
        st.header("🎯 Prediction Options")
        
        # League selection
        league_options = {f"{name} (ID: {league_id})": league_id 
                         for league_id, name in LEAGUE_MAPPINGS.items()}
        selected_league = st.selectbox("Select League", list(league_options.keys()))
        league_id = league_options[selected_league]
        
        # Team inputs
        st.subheader("🏈 Match Details")
        home_team = st.text_input("Home Team", placeholder="e.g., South Africa")
        away_team = st.text_input("Away Team", placeholder="e.g., New Zealand")
        
        # Date selection
        match_date = st.date_input("Match Date", value=datetime.now().date())
        
        # Prediction type
        prediction_type = st.radio(
            "Prediction Type",
            ["AI Only", "Enhanced (AI + Live Data)"],
            help="Enhanced predictions include live odds, team form, and head-to-head data"
        )
        
        # Predict button
        predict_button = st.button("🔮 Get Prediction", type="primary")
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📊 Prediction Results")
        
        if predict_button and home_team and away_team:
            try:
                with st.spinner("🤖 Analyzing match data..."):
                    if prediction_type == "Enhanced (AI + Live Data)" and enhanced_predictor:
                        # Get enhanced prediction
                        prediction = enhanced_predictor.get_enhanced_prediction(
                            home_team, away_team, league_id, str(match_date)
                        )
                        
                        # Display enhanced results
                        display_enhanced_prediction(prediction)
                        
                    else:
                        # Get basic AI prediction
                        prediction = predictor.predict_match(
                            home_team, away_team, league_id, str(match_date)
                        )
                        
                        # Display basic results
                        display_basic_prediction(prediction)
                        
            except Exception as e:
                st.error(f"❌ Prediction failed: {e}")
    
    with col2:
        st.header("📈 Live Data")
        
        if enhanced_predictor:
            try:
                with st.spinner("🔄 Loading live matches..."):
                    live_matches = enhanced_predictor.get_live_matches(league_id)
                    
                    if live_matches:
                        st.success(f"Found {len(live_matches)} live/upcoming matches")
                        
                        for match in live_matches[:5]:  # Show first 5
                            with st.expander(f"{match['home_team']} vs {match['away_team']}"):
                                st.write(f"**Date**: {match['date']}")
                                st.write(f"**State**: {match['state']}")
                                st.write(f"**League**: {match['league']}")
                                
                                if 'prediction' in match and 'error' not in match['prediction']:
                                    pred = match['prediction']
                                    st.write(f"**Predicted Winner**: {pred.get('predicted_winner', 'N/A')}")
                                    st.write(f"**Confidence**: {pred.get('confidence', 0):.1%}")
                    else:
                        st.info("No live matches found for this league")
                        
            except Exception as e:
                st.error(f"Error loading live matches: {e}")
        else:
            st.info("Enable enhanced features to see live data")

def display_basic_prediction(prediction):
    """Display basic AI prediction results"""
    
    # Winner prediction
    winner = prediction.get('predicted_winner', 'Unknown')
    confidence = prediction.get('confidence', 0)
    
    st.subheader("🏆 Predicted Winner")
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.metric(
            label="Winner",
            value=winner,
            delta=f"{confidence:.1%} confidence"
        )
    
    # Score prediction
    st.subheader("📊 Predicted Score")
    home_score = prediction.get('predicted_home_score', 0)
    away_score = prediction.get('predicted_away_score', 0)
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Home Team", f"{home_score:.1f}")
    with col2:
        st.metric("Away Team", f"{away_score:.1f}")
    
    # Additional metrics
    if 'additional_metrics' in prediction:
        metrics = prediction['additional_metrics']
        st.subheader("📈 Additional Metrics")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Home Advantage", f"{metrics.get('home_advantage', 0):.1f}")
        with col2:
            st.metric("Form Difference", f"{metrics.get('form_difference', 0):.1f}")
        with col3:
            st.metric("ELO Difference", f"{metrics.get('elo_difference', 0):.1f}")

def display_enhanced_prediction(prediction):
    """Display enhanced prediction with live data"""
    
    # Basic prediction (same as above)
    display_basic_prediction(prediction)
    
    # Enhanced data section
    st.subheader("🔴 Live Data Integration")
    
    enhanced_data = prediction.get('enhanced_data', {})
    
    # Live odds
    if enhanced_data.get('live_odds'):
        st.subheader("💰 Live Odds")
        odds = enhanced_data['live_odds']
        
        for bookmaker, markets in odds.items():
            with st.expander(f"📊 {bookmaker}"):
                for market_name, outcomes in markets.items():
                    st.write(f"**{market_name}**:")
                    for outcome in outcomes:
                        st.write(f"- {outcome.get('name', 'Unknown')}: {outcome.get('odds', 'N/A')}")
    
    # Team form
    if enhanced_data.get('team_form'):
        st.subheader("📈 Team Form (Last 5 Games)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            home_form = enhanced_data['team_form'].get('home', {})
            st.write("**Home Team Form**")
            st.write(f"Win Rate: {home_form.get('win_rate', 0):.1%}")
            st.write(f"Avg Score: {home_form.get('avg_score', 0):.1f}")
            
            for game in home_form.get('games', [])[:3]:
                st.write(f"- {game.get('date', 'N/A')}: {game.get('score', 'N/A')} {'✅' if game.get('won') else '❌'}")
        
        with col2:
            away_form = enhanced_data['team_form'].get('away', {})
            st.write("**Away Team Form**")
            st.write(f"Win Rate: {away_form.get('win_rate', 0):.1%}")
            st.write(f"Avg Score: {away_form.get('avg_score', 0):.1f}")
            
            for game in away_form.get('games', [])[:3]:
                st.write(f"- {game.get('date', 'N/A')}: {game.get('score', 'N/A')} {'✅' if game.get('won') else '❌'}")
    
    # Head-to-head
    if enhanced_data.get('head_to_head'):
        st.subheader("⚔️ Head-to-Head History")
        h2h = enhanced_data['head_to_head']
        
        if h2h:
            df_h2h = pd.DataFrame(h2h[:5])  # Show last 5 meetings
            st.dataframe(df_h2h, use_container_width=True)
        else:
            st.info("No head-to-head history available")
    
    # Highlights
    if enhanced_data.get('highlights'):
        st.subheader("🎬 Match Highlights")
        highlights = enhanced_data['highlights']
        
        for highlight in highlights[:3]:  # Show first 3 highlights
            with st.expander(f"🎥 {highlight.get('title', 'Highlight')}"):
                st.write(f"**Source**: {highlight.get('source', 'Unknown')}")
                st.write(f"**Type**: {highlight.get('type', 'Unknown')}")
                if highlight.get('description'):
                    st.write(f"**Description**: {highlight['description']}")
    
    # Overall confidence
    confidence = prediction.get('prediction_confidence', 0)
    st.subheader("🎯 Prediction Confidence")
    st.progress(confidence)
    st.write(f"**Overall Confidence**: {confidence:.1%}")
    
    # Data sources
    sources = prediction.get('data_sources', [])
    st.write(f"**Data Sources**: {', '.join(sources)}")

if __name__ == "__main__":
    main()
