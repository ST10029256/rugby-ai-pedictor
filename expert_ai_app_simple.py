#!/usr/bin/env python3
"""
Simplified Expert AI Rugby Prediction App for Streamlit Cloud
"""

import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Configuration
SPORTDEVS_API_KEY = os.getenv("SPORTDEVS_API_KEY", "qwh9orOkZESulf4QBhf0IQ")
LEAGUE_CONFIGS = {
    4986: {"name": "RC", "neutral_mode": False},
    4446: {"name": "URC", "neutral_mode": False},
    5069: {"name": "CC", "neutral_mode": False},
    4574: {"name": "RWC", "neutral_mode": True},
}

def load_model_safely(league_id: int):
    """Load model with error handling"""
    try:
        # Check if optimized model exists first
        optimized_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
        if os.path.exists(optimized_path):
            with open(optimized_path, 'rb') as f:
                model = pickle.load(f)
            return model
        
        # Fallback to legacy model
        model_path = f'artifacts/league_{league_id}_model.pkl'
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
            return model
        
        return None
    except Exception as e:
        st.error(f"Failed to load model for league {league_id}: {e}")
        return None

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
    
    # Load model
    with st.spinner("Loading model..."):
        model_data = load_model_safely(selected_league)
    
    if not model_data:
        st.error("Unable to load model for this league")
        return
    
    st.success(f"✅ Model loaded for {available_leagues[selected_league]}")
    
    # Load teams
    with st.spinner("Loading teams..."):
        team_names = get_teams()
    
    if not team_names:
        st.error("Unable to load team names")
        return
    
    st.success(f"✅ Loaded {len(team_names)} teams")
    
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
            # Simple prediction logic
            st.info("Prediction feature will be implemented in the full version")
            st.write(f"Selected: {home_team} vs {away_team}")
    
    # Model info
    st.header("Model Information")
    if model_data:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("League", available_leagues[selected_league])
        with col2:
            st.metric("Model Type", model_data.get('model_type', 'Unknown'))
        with col3:
            st.metric("Training Games", model_data.get('training_games', 'Unknown'))

if __name__ == "__main__":
    main()
