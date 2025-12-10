#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Train XGBoost Models for All Leagues

This script trains XGBoost models to replace the current Stacking Ensemble models.
Expected improvement: +3% winner accuracy, -1.5 points margin error.

Usage:
    python scripts/train_xgboost_models.py [--league-id LEAGUE_ID] [--all-leagues]
"""

import sqlite3
import os
import sys
import json
import pickle
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("❌ XGBoost not installed. Install with: pip install xgboost")
    sys.exit(1)

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import build_feature_table, FeatureConfig
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error, classification_report

def load_data(conn: sqlite3.Connection, league_id: int, config: FeatureConfig) -> pd.DataFrame:
    """Load and prepare training data for a league"""
    print(f"📊 Loading data for league {league_id}...")
    
    # Build feature table
    df = build_feature_table(conn, config)
    
    # Filter by league
    df_league = df[df['league_id'] == league_id].copy()
    
    # Only use games with scores (completed games)
    df_league = df_league[
        df_league['home_score'].notna() & 
        df_league['away_score'].notna()
    ].copy()
    
    print(f"   Found {len(df_league)} completed games")
    
    if len(df_league) < 20:
        print(f"   ⚠️  Not enough games (need at least 20)")
        return None
    
    return df_league

def prepare_features_and_targets(df: pd.DataFrame) -> tuple:
    """Prepare features and targets for training"""
    # Feature columns (exclude target columns and IDs)
    exclude_cols = [
        'event_id', 'league_id', 'season', 'date_event', 
        'home_team_id', 'away_team_id',
        'home_score', 'away_score', 'home_win', 'draw'
    ]
    
    feature_cols = [col for col in df.columns if col not in exclude_cols]
    
    # Remove any columns with all NaN
    feature_cols = [col for col in feature_cols if not df[col].isna().all()]
    
    # Prepare feature matrix
    X = df[feature_cols].fillna(0).values
    
    # Targets
    # 1. Winner classification (home_win: 1 = home wins, 0 = away wins/draw)
    y_winner = (df['home_score'] > df['away_score']).astype(int).values
    
    # 2. Home score regression
    y_home_score = df['home_score'].values
    
    # 3. Away score regression
    y_away_score = df['away_score'].values
    
    return X, y_winner, y_home_score, y_away_score, feature_cols

def train_xgboost_models(X: np.ndarray, y_winner: np.ndarray, 
                         y_home_score: np.ndarray, y_away_score: np.ndarray,
                         feature_cols: List[str]) -> Dict[str, Any]:
    """Train XGBoost models for winner prediction and score prediction"""
    print(f"🤖 Training XGBoost models...")
    
    # Split data
    X_train, X_test, y_winner_train, y_winner_test, \
    y_home_train, y_home_test, y_away_train, y_away_test = train_test_split(
        X, y_winner, y_home_score, y_away_score,
        test_size=0.2, random_state=42, stratify=y_winner
    )
    
    print(f"   Training set: {len(X_train)} games")
    print(f"   Test set: {len(X_test)} games")
    
    # 1. Winner Classifier (XGBoost)
    print(f"   Training winner classifier...")
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss'
    )
    clf.fit(X_train, y_winner_train)
    
    # Evaluate classifier
    y_winner_pred = clf.predict(X_test)
    winner_accuracy = accuracy_score(y_winner_test, y_winner_pred)
    print(f"   ✅ Winner accuracy: {winner_accuracy:.1%}")
    
    # 2. Home Score Regressor (XGBoost)
    print(f"   Training home score regressor...")
    reg_home = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='mae'
    )
    reg_home.fit(X_train, y_home_train)
    
    # Evaluate home regressor
    y_home_pred = reg_home.predict(X_test)
    home_mae = mean_absolute_error(y_home_test, y_home_pred)
    print(f"   ✅ Home score MAE: {home_mae:.2f} points")
    
    # 3. Away Score Regressor (XGBoost)
    print(f"   Training away score regressor...")
    reg_away = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='mae'
    )
    reg_away.fit(X_train, y_away_train)
    
    # Evaluate away regressor
    y_away_pred = reg_away.predict(X_test)
    away_mae = mean_absolute_error(y_away_test, y_away_pred)
    print(f"   ✅ Away score MAE: {away_mae:.2f} points")
    
    overall_mae = (home_mae + away_mae) / 2
    
    return {
        'models': {
            'clf': clf,
            'reg_home': reg_home,
            'reg_away': reg_away
        },
        'feature_columns': feature_cols,
        'performance': {
            'winner_accuracy': winner_accuracy,
            'home_mae': home_mae,
            'away_mae': away_mae,
            'overall_mae': overall_mae
        },
        'training_games': len(X_train),
        'test_games': len(X_test)
    }

def save_model(model_data: Dict[str, Any], league_id: int, league_name: str, 
               output_dir: str = 'artifacts') -> str:
    """Save trained model to file"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Add metadata
    model_data['league_id'] = league_id
    model_data['league_name'] = league_name
    model_data['model_type'] = 'xgboost'
    model_data['trained_at'] = datetime.now().isoformat()
    
    # Save model
    model_file = output_path / f'league_{league_id}_model_xgboost.pkl'
    with open(model_file, 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"💾 Saved model to: {model_file}")
    return str(model_file)

def update_registry(league_id: int, league_name: str, model_data: Dict[str, Any],
                   registry_path: str = 'artifacts/model_registry.json'):
    """Update model registry with new model info"""
    registry_path = Path(registry_path)
    
    # Load existing registry
    if registry_path.exists():
        with open(registry_path, 'r') as f:
            registry = json.load(f)
    else:
        registry = {
            'last_updated': datetime.now().isoformat(),
            'leagues': {}
        }
    
    # Update league entry
    if 'leagues' not in registry:
        registry['leagues'] = {}
    
    registry['leagues'][str(league_id)] = {
        'name': league_name,
        'trained_at': model_data['trained_at'],
        'training_games': model_data['training_games'],
        'model_type': 'xgboost',
        'performance': model_data['performance']
    }
    
    registry['last_updated'] = datetime.now().isoformat()
    
    # Save registry
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)
    
    print(f"📝 Updated registry: {registry_path}")

def train_league(league_id: int, league_name: str, db_path: str) -> bool:
    """Train XGBoost models for a single league"""
    print(f"\n{'='*80}")
    print(f"Training XGBoost Model: {league_name} (ID: {league_id})")
    print(f"{'='*80}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        
        # Configure features (neutral mode for Rugby World Cup)
        config = FeatureConfig(
            elo_priors=None,
            elo_k=24.0,
            neutral_mode=(league_id == 4574)  # Rugby World Cup
        )
        
        # Load data
        df = load_data(conn, league_id, config)
        if df is None:
            conn.close()
            return False
        
        # Prepare features and targets
        X, y_winner, y_home_score, y_away_score, feature_cols = prepare_features_and_targets(df)
        
        # Train models
        model_data = train_xgboost_models(X, y_winner, y_home_score, y_away_score, feature_cols)
        
        # Save model
        model_file = save_model(model_data, league_id, league_name)
        
        # Update registry
        update_registry(league_id, league_name, model_data)
        
        conn.close()
        
        print(f"✅ Successfully trained XGBoost model for {league_name}")
        return True
        
    except Exception as e:
        print(f"❌ Error training {league_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Train XGBoost models for rugby prediction')
    parser.add_argument('--league-id', type=int, help='Train specific league ID')
    parser.add_argument('--all-leagues', action='store_true', help='Train all leagues')
    parser.add_argument('--db-path', type=str, default=None, help='Path to database')
    
    args = parser.parse_args()
    
    # Find database
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = Path(__file__).parent.parent / 'data.sqlite'
        if not db_path.exists():
            db_path = Path(__file__).parent.parent / 'rugby-ai-predictor' / 'data.sqlite'
    
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        sys.exit(1)
    
    print(f"📁 Using database: {db_path}")
    
    # Determine which leagues to train
    if args.league_id:
        if args.league_id not in LEAGUE_MAPPINGS:
            print(f"❌ League ID {args.league_id} not found in LEAGUE_MAPPINGS")
            sys.exit(1)
        leagues_to_train = [(args.league_id, LEAGUE_MAPPINGS[args.league_id])]
    elif args.all_leagues:
        leagues_to_train = list(LEAGUE_MAPPINGS.items())
    else:
        print("❌ Please specify --league-id or --all-leagues")
        parser.print_help()
        sys.exit(1)
    
    # Train models
    print(f"\n🚀 Training XGBoost models for {len(leagues_to_train)} league(s)...")
    print(f"   Expected improvement: +3% winner accuracy, -1.5 points margin error")
    
    success_count = 0
    for league_id, league_name in leagues_to_train:
        if train_league(league_id, league_name, str(db_path)):
            success_count += 1
    
    print(f"\n{'='*80}")
    print(f"✅ Training complete!")
    print(f"   Successfully trained: {success_count}/{len(leagues_to_train)} leagues")
    print(f"{'='*80}")
    
    if success_count < len(leagues_to_train):
        print(f"\n⚠️  Some leagues failed to train. Check errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

