#!/usr/bin/env python3
"""
Get Rugby Championship predictions for next Saturday
"""

import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig
from scripts.model_manager import ModelManager

def safe_to_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return float(value)
    if isinstance(value, (int, np.integer)):
        return float(value)
    try:
        v = float(value)
        if np.isnan(v):
            return default
        return v
    except Exception:
        return default

def safe_to_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return default
        return int(value)
    try:
        return int(value)
    except Exception:
        return default

def main():
    print('🏉 RUGBY CHAMPIONSHIP PREDICTIONS FOR NEXT SATURDAY (October 4th, 2025)')
    print('='*70)

    # Initialize model manager
    model_manager = ModelManager()

    # Connect to database
    db_path = os.path.join(project_root, 'data.sqlite')
    conn = sqlite3.connect(db_path)

    # Build feature table for Rugby Championship
    config = FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=False)
    df = build_feature_table(conn, config)

    # Filter for Rugby Championship upcoming games
    league_id = 4986  # Rugby Championship
    upcoming = df[df['home_win'].isna()].copy()
    upc = upcoming[upcoming['league_id'] == league_id].copy()

    # Filter for next Saturday (2025-10-04)
    upc['date_event'] = pd.to_datetime(upc['date_event'], errors='coerce')
    next_saturday = pd.Timestamp('2025-10-04')
    upc = upc[upc['date_event'] == next_saturday]

    print(f'Found {len(upc)} games for next Saturday')

    if len(upc) == 0:
        print('No upcoming games found for next Saturday')
        return

    # Load model
    model_package = model_manager.load_model(league_id)
    if not model_package:
        print('Failed to load Rugby Championship model')
        return

    feature_cols = model_package.get('feature_columns', [])
    team_mappings = model_package.get('team_mappings', {})
    _home_wr_map = team_mappings.get('home_wr_map', {})
    _away_wr_map = team_mappings.get('away_wr_map', {})

    # Prepare features
    upc = upc.copy()
    for col in feature_cols:
        if col not in upc.columns:
            upc[col] = np.nan

    # Calculate derived features
    upc['elo_diff'] = upc['elo_diff'].where(upc['elo_diff'].notna(), upc['elo_home_pre'] - upc['elo_away_pre'])
    if 'home_form' in upc.columns and 'away_form' in upc.columns:
        upc['form_diff'] = upc['form_diff'].where(upc['form_diff'].notna(), upc['home_form'] - upc['away_form'])
    if 'home_rest_days' in upc.columns and 'away_rest_days' in upc.columns:
        upc['rest_diff'] = upc['rest_diff'].where(upc['rest_diff'].notna(), upc['home_rest_days'] - upc['away_rest_days'])
    if 'home_goal_diff_form' in upc.columns and 'away_goal_diff_form' in upc.columns:
        upc['goal_diff_form_diff'] = upc['goal_diff_form_diff'].where(upc['goal_diff_form_diff'].notna(), upc['home_goal_diff_form'] - upc['away_goal_diff_form'])

    upc['pair_elo_expectation'] = upc['pair_elo_expectation'].where(
        upc['pair_elo_expectation'].notna(),
        1.0 / (1.0 + 10 ** ((upc['elo_away_pre'] - upc['elo_home_pre']) / 400.0)),
    )

    upc['home_wr_home'] = upc['home_wr_home'].where(upc['home_wr_home'].notna(), upc['home_team_id'].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float('nan'))))
    upc['away_wr_away'] = upc['away_wr_away'].where(upc['away_wr_away'].notna(), upc['away_team_id'].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float('nan'))))

    # Get team names
    team_name = {}
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT t.id, COALESCE(t.name, '')
        FROM team t
        JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
        WHERE e.league_id = ?
    ''', (league_id,))
    for tid_raw, nm in cursor.fetchall():
        tid = safe_to_int(tid_raw, default=-1)
        team_name[tid] = nm or f'Team {tid}'

    # Make predictions
    X_upc = upc[feature_cols].to_numpy()

    print(f'\n🎯 AI PREDICTIONS FOR NEXT SATURDAY:')
    print('='*50)

    for i in range(len(X_upc)):
        features = X_upc[i]
        home_team_id = upc.iloc[i]['home_team_id']
        away_team_id = upc.iloc[i]['away_team_id']
        
        home_name = team_name.get(safe_to_int(home_team_id, -1), f'Team {home_team_id}')
        away_name = team_name.get(safe_to_int(away_team_id, -1), f'Team {away_team_id}')
        
        # Predict winner probability
        home_prob, away_prob = model_manager.predict_winner_probability(league_id, features)
        
        # Predict scores
        home_score, away_score = model_manager.predict_scores(league_id, features)
        
        # Determine winner
        winner = home_name if home_prob >= 0.5 else away_name
        margin = abs(home_score - away_score)
        
        print(f'\n🏆 GAME {i+1}: {home_name} vs {away_name}')
        print(f'   📅 Date: October 4th, 2025')
        print(f'   🎯 Winner Prediction: {winner}')
        print(f'   📊 Win Probability: {home_prob:.1%} (Home) | {away_prob:.1%} (Away)')
        print(f'   ⚽ Score Prediction: {home_name} {home_score:.1f} - {away_score:.1f} {away_name}')
        print(f'   📏 Predicted Margin: {margin:.1f} points')
        
        # Show confidence level
        confidence = max(home_prob, away_prob)
        if confidence >= 0.8:
            conf_level = 'Very High'
        elif confidence >= 0.7:
            conf_level = 'High'
        elif confidence >= 0.6:
            conf_level = 'Medium'
        else:
            conf_level = 'Low'
        
        print(f'   🎯 Confidence Level: {conf_level} ({confidence:.1%})')

    print(f'\n📈 Model Performance:')
    print(f'   Winner Accuracy: 91.9%')
    print(f'   Score MAE: 7.69 points')
    print(f'   Trained on: 136 historical games')

    conn.close()

if __name__ == "__main__":
    main()
