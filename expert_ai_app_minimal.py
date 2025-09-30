#!/usr/bin/env python3
"""
Minimal Expert AI Rugby Prediction App for Streamlit Cloud
This version avoids model loading to test basic functionality
"""

import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Configuration
LEAGUE_CONFIGS = {
    4986: {"name": "RC", "neutral_mode": False},
    4446: {"name": "URC", "neutral_mode": False},
    5069: {"name": "CC", "neutral_mode": False},
    4574: {"name": "RWC", "neutral_mode": True},
}

@st.cache_data(ttl=3600)
def get_teams():
    """Get team names with caching"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM team")
        teams = dict(cursor.fetchall())
        conn.close()
        return teams
    except Exception as e:
        st.error(f"Error loading teams: {e}")
        return {}

@st.cache_data(ttl=3600)
def get_upcoming_games(league_id: int):
    """Get upcoming games for a league"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT e.id, e.home_team_id, e.away_team_id, e.date_event, e.league_id
            FROM event e 
            WHERE e.league_id = ? AND e.home_score IS NULL AND e.away_score IS NULL
            ORDER BY e.date_event
            LIMIT 10
        """, (league_id,))
        games = cursor.fetchall()
        conn.close()
        return games
    except Exception as e:
        st.error(f"Error loading games: {e}")
        return []

def main():
    st.set_page_config(
        page_title="Rugby AI Predictions",
        layout="wide",
        initial_sidebar_state="expanded",
        page_icon="🏉"
    )
    
    # Simple header
    st.title("🏉 Rugby AI Predictions")
    st.subheader("AI-powered match predictions")
    
    # Check if required files exist
    st.sidebar.header("System Status")
    
    # File checks
    files_to_check = {
        "Database": "data.sqlite",
        "Artifacts": "artifacts",
        "Optimized Artifacts": "artifacts_optimized",
        "Prediction Module": "prediction"
    }
    
    all_files_ok = True
    for name, path in files_to_check.items():
        exists = os.path.exists(path)
        status = "✅" if exists else "❌"
        st.sidebar.write(f"{status} {name}")
        if not exists:
            all_files_ok = False
    
    if not all_files_ok:
        st.error("❌ Some required files are missing. Check the sidebar for details.")
        return
    
    # League selection
    st.sidebar.header("League Selection")
    
    available_leagues = {}
    for league_id, data in LEAGUE_CONFIGS.items():
        model_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
        old_path = f'artifacts/league_{league_id}_model.pkl'
        if os.path.exists(model_path) or os.path.exists(old_path):
            available_leagues[league_id] = data['name']
    
    if not available_leagues:
        st.error("No models found")
        return
    
    selected_league = st.sidebar.selectbox(
        "Select League",
        options=list(available_leagues.keys()),
        format_func=lambda x: available_leagues[x]
    )
    
    # Load teams
    with st.spinner("Loading teams..."):
        team_names = get_teams()
    
    if not team_names:
        st.error("Unable to load team names")
        return
    
    st.success(f"✅ Loaded {len(team_names)} teams")
    
    # Get upcoming games
    with st.spinner("Loading upcoming games..."):
        upcoming_games = get_upcoming_games(selected_league)
    
    if not upcoming_games:
        st.warning("No upcoming games found for this league")
        return
    
    st.success(f"✅ Found {len(upcoming_games)} upcoming games")
    
    # Display upcoming games
    st.header(f"Upcoming {available_leagues[selected_league]} Games")
    
    for game in upcoming_games:
        game_id, home_team_id, away_team_id, date_event, league_id = game
        
        home_team_name = team_names.get(home_team_id, f"Team {home_team_id}")
        away_team_name = team_names.get(away_team_id, f"Team {away_team_id}")
        
        # Format date
        if date_event:
            try:
                date_str = pd.to_datetime(date_event).strftime("%Y-%m-%d")
            except:
                date_str = str(date_event)
        else:
            date_str = "TBD"
        
        # Create game card
        with st.container():
            st.markdown(f"""
            <div style="
                background: linear-gradient(145deg, #1a202c 0%, #2d3748 100%);
                border-radius: 15px;
                padding: 1.5rem;
                margin: 1rem 0;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                border: 1px solid rgba(74, 85, 104, 0.3);
            ">
                <h3 style="color: #ffffff; margin: 0 0 0.5rem 0; text-align: center;">
                    {home_team_name} vs {away_team_name}
                </h3>
                <p style="color: #a0aec0; text-align: center; margin: 0;">
                    📅 {date_str}
                </p>
            </div>
            """, unsafe_allow_html=True)
    
    # Simple prediction interface
    st.header("Make Prediction")
    
    col1, col2 = st.columns(2)
    
    with col1:
        home_team = st.selectbox(
            "Home Team",
            options=list(team_names.values()),
            key="home_team"
        )
    
    with col2:
        away_team = st.selectbox(
            "Away Team",
            options=list(team_names.values()),
            key="away_team"
        )
    
    if st.button("Generate Prediction", type="primary"):
        if home_team == away_team:
            st.error("Please select different teams")
        else:
            # Simple prediction logic (without model loading)
            st.info("🎯 Prediction feature will be available once model compatibility is resolved")
            st.write(f"Selected: {home_team} vs {away_team}")
            
            # Show some basic stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Home Team", home_team)
            with col2:
                st.metric("Away Team", away_team)
            with col3:
                st.metric("League", available_leagues[selected_league])
    
    # System info
    st.header("System Information")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Python Version", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    with col2:
        st.metric("NumPy Version", np.__version__)
    with col3:
        st.metric("Pandas Version", pd.__version__)

if __name__ == "__main__":
    main()
