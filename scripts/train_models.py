#!/usr/bin/env python3
"""
Automated Model Training Script
Trains and saves league-specific models for all rugby leagues
"""

import os
import sys
import sqlite3
import pickle
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from datetime import datetime
import logging

# Add project root to path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.linear_model import LogisticRegression, ElasticNet
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestRegressor, GradientBoostingRegressor, RandomForestClassifier, VotingClassifier, VotingRegressor
from sklearn.linear_model import Ridge, Lasso
import xgboost as xgb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('model_training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# League configurations
LEAGUE_CONFIGS = {
    4986: {"name": "Rugby Championship", "neutral_mode": False},
    4446: {"name": "United Rugby Championship", "neutral_mode": False},
    5069: {"name": "Currie Cup", "neutral_mode": False},
    4574: {"name": "Rugby World Cup", "neutral_mode": True},
}

def safe_to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
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

def safe_to_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int"""
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

def winsorize(arr: np.ndarray, low: float = 0.01, high: float = 0.99) -> np.ndarray:
    """Apply winsorization to array"""
    a = np.asarray(arr, dtype=float)
    if len(a) == 0:
        return a
    lo = float(np.quantile(a, low))
    hi = float(np.quantile(a, high))
    return np.clip(a, lo, hi)

def calculate_time_decay_weights(hist_df: pd.DataFrame, half_life_days: float = 200.0) -> np.ndarray:
    """Calculate time-decay weights for training data"""
    try:
        if "date_event" in hist_df.columns:
            max_dt = pd.to_datetime(hist_df["date_event"]).max()
            days = (pd.to_datetime(hist_df["date_event"]) - max_dt).dt.days.abs().astype(float)
            weights = np.exp(-days / half_life_days).astype(float)
        else:
            weights = np.ones(len(hist_df), dtype=float)
    except Exception:
        weights = np.ones(len(hist_df), dtype=float)
    
    return weights

def get_league_specific_models(league_id: int) -> Tuple[Any, Any, Any]:
    """Get league-specific model configurations"""
    
    # ENHANCED CLASSIFICATION: Ensemble methods for better win accuracy
    base_lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    calibrated_clf = CalibratedClassifierCV(base_lr, method="isotonic", cv=5)
    clf = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), calibrated_clf)
    
    # Ensemble classifier for better win prediction
    hgb_clf = HistGradientBoostingClassifier(random_state=42, max_iter=100, learning_rate=0.1)
    rf_clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    
    # Try to use XGBoost if available, otherwise fall back to HGB
    try:
        xgb_clf = xgb.XGBClassifier(n_estimators=100, random_state=42, max_depth=6, learning_rate=0.1)
        gbdt_clf = VotingClassifier([
            ('hgb', hgb_clf),
            ('rf', rf_clf),
            ('xgb', xgb_clf)
        ], voting='soft')
    except:
        # Fallback to simpler ensemble if XGBoost not available
        gbdt_clf = VotingClassifier([
            ('hgb', hgb_clf),
            ('rf', rf_clf)
        ], voting='soft')
    
    # ENHANCED REGRESSION: Ensemble methods for better score prediction
    if league_id == 4446:  # United Rugby Championship
        # Ensemble for better score prediction
        rf_home = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42)
        hgb_home = HistGradientBoostingRegressor(random_state=42, max_iter=100, learning_rate=0.1)
        
        rf_away = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42)
        hgb_away = HistGradientBoostingRegressor(random_state=42, max_iter=100, learning_rate=0.1)
        
        try:
            xgb_home = xgb.XGBRegressor(n_estimators=100, random_state=42, max_depth=6, learning_rate=0.1)
            xgb_away = xgb.XGBRegressor(n_estimators=100, random_state=42, max_depth=6, learning_rate=0.1)
            
            reg_home = VotingRegressor([('rf', rf_home), ('hgb', hgb_home), ('xgb', xgb_home)])
            reg_away = VotingRegressor([('rf', rf_away), ('hgb', hgb_away), ('xgb', xgb_away)])
        except:
            reg_home = VotingRegressor([('rf', rf_home), ('hgb', hgb_home)])
            reg_away = VotingRegressor([('rf', rf_away), ('hgb', hgb_away)])
        
        scaler = None
    elif league_id == 4574:  # Rugby World Cup
        reg_home = HistGradientBoostingRegressor(
            learning_rate=0.05, max_iter=300, max_depth=8, 
            min_samples_leaf=3, max_features=0.9, random_state=42
        )
        reg_away = HistGradientBoostingRegressor(
            learning_rate=0.05, max_iter=300, max_depth=8, 
            min_samples_leaf=3, max_features=0.9, random_state=42
        )
        scaler = None
    elif league_id == 4986:  # Rugby Championship
        reg_home = ElasticNet(alpha=0.05, l1_ratio=0.3)
        reg_away = ElasticNet(alpha=0.05, l1_ratio=0.3)
        scaler = RobustScaler()
    elif league_id == 5069:  # Currie Cup
        reg_home = GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=8, random_state=42
        )
        reg_away = GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=8, random_state=42
        )
        scaler = None
    else:  # Default fallback
        reg_home = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
        reg_away = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
        scaler = None
    
    return (clf, gbdt_clf), (reg_home, reg_away), scaler

def train_league_models(league_id: int, db_path: str) -> Dict[str, Any] | None:
    """Train models for a specific league"""
    logger.info(f"Training models for league {league_id} ({LEAGUE_CONFIGS[league_id]['name']})")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Build feature table
    config = FeatureConfig(
        elo_priors=None, 
        elo_k=24.0, 
        neutral_mode=LEAGUE_CONFIGS[league_id]["neutral_mode"]
    )
    df = build_feature_table(conn, config)
    
    # Filter historical data for this league
    hist_filtered = df[(df["league_id"] == league_id) & df["home_win"].notna()].copy()
    hist = pd.DataFrame(hist_filtered)  # Ensure DataFrame type
    
    if len(hist) < 10:
        logger.warning(f"Insufficient data for league {league_id}: {len(hist)} games")
        return None
    
    # QUICK WIN: Use all features from the feature table (includes new advanced features)
    # Get all feature columns, excluding metadata columns
    metadata_cols = ["event_id", "league_id", "season", "date_event", "home_team_id", "away_team_id", "home_score", "away_score", "home_win"]
    all_cols = [c for c in hist.columns if c not in metadata_cols]
    
    print(f"Using {len(all_cols)} features for training (including new advanced features)")
    
    # Add critical missing features if they don't exist
    missing_cols = ["home_wr_home", "away_wr_away", "pair_elo_expectation"]
    
    for col in missing_cols:
        if col not in hist.columns:
            print(f"Warning: Missing feature {col} - adding manually")
            if col == "home_wr_home":
                home_wr_dict = dict(hist.groupby("home_team_id")["home_win"].mean())
                hist[col] = hist["home_team_id"].replace(home_wr_dict).fillna(0.5)
                all_cols.append(col)
            elif col == "away_wr_away":
                away_wr_dict = {}
                for away_id, group in hist.groupby("away_team_id"):
                    away_wins = (1 - group["home_win"]).mean()
                    away_wr_dict[away_id] = away_wins
                hist[col] = hist["away_team_id"].replace(away_wr_dict).fillna(0.5)
                all_cols.append(col)
            elif col == "pair_elo_expectation":
                hist[col] = 1.0 / (1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0))
                all_cols.append(col)

    # Convert for training - ensure proper typing
    hist_df: pd.DataFrame = hist.copy()  # Ensure DataFrame type
    
    # Convert to numpy arrays properly - extract values from pandas DataFrames/Series
    X_hist = np.asarray(hist_df[all_cols].values)
    y_hist = np.asarray(hist_df["home_win"].astype(int).values)
    y_home = np.asarray(hist_df["home_score"].values)
    y_away = np.asarray(hist_df["away_score"].values)
    
    # Calculate time-decay weights - ensure hist_df is properly typed
    weights: np.ndarray = calculate_time_decay_weights(hist_df)
    
    # Apply winsorization to scores
    y_home_w = winsorize(np.array(y_home))
    y_away_w = winsorize(np.array(y_away))
    
    # Get league-specific models
    (clf, gbdt_clf), (reg_home, reg_away), scaler = get_league_specific_models(league_id)
    
    # CRITICAL: Split data to prevent overfitting
    from sklearn.model_selection import train_test_split
    
    # Use time-based split (most recent 20% for validation)
    split_idx = int(0.8 * len(X_hist))
    X_train, X_val = X_hist[:split_idx], X_hist[split_idx:]
    y_train, y_val = y_hist[:split_idx], y_hist[split_idx:]
    y_home_train, y_home_val = y_home_w[:split_idx], y_home_w[split_idx:]
    y_away_train, y_away_val = y_away_w[:split_idx], y_away_w[split_idx:]
    weights_train, weights_val = weights[:split_idx], weights[split_idx:]
    
    logger.info(f"Training on {len(X_train)} samples, validating on {len(X_val)} samples")
    
    # Train classification models
    logger.info(f"Training classification models for league {league_id}")
    clf.fit(X_train, y_train)
    gbdt_clf.fit(X_train, y_train)
    
    # Train regression models
    logger.info(f"Training regression models for league {league_id}")
    X_val_scaled = None  # Initialize
    if scaler is not None:
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        reg_home.fit(X_train_scaled, y_home_train)
        reg_away.fit(X_train_scaled, y_away_train)
    else:
        reg_home.fit(X_train, y_home_train)
        reg_away.fit(X_train, y_away_train)
    
    # Calculate REALISTIC model performance metrics (validation set only)
    clf_probs = clf.predict_proba(X_val)[:, 1]
    gbdt_probs = gbdt_clf.predict_proba(X_val)[:, 1]
    ensemble_probs = 0.5 * (clf_probs + gbdt_probs)
    
    if scaler is not None and X_val_scaled is not None:
        pred_home = reg_home.predict(X_val_scaled)
        pred_away = reg_away.predict(X_val_scaled)
    else:
        pred_home = reg_home.predict(X_val)
        pred_away = reg_away.predict(X_val)
    
    # Calculate REALISTIC accuracy metrics on validation set
    winner_accuracy = np.mean((ensemble_probs >= 0.5) == y_val)
    home_mae = np.mean(np.abs(pred_home - y_home_val))
    away_mae = np.mean(np.abs(pred_away - y_away_val))
    overall_mae = (home_mae + away_mae) / 2
    
    logger.info(f"League {league_id} performance:")
    logger.info(f"  Winner accuracy: {winner_accuracy:.3f}")
    logger.info(f"  Home score MAE: {home_mae:.3f}")
    logger.info(f"  Away score MAE: {away_mae:.3f}")
    logger.info(f"  Overall MAE: {overall_mae:.3f}")
    
    # Prepare model package
    model_package = {
        "league_id": league_id,
        "league_name": LEAGUE_CONFIGS[league_id]["name"],
        "trained_at": datetime.now().isoformat(),
        "training_games": len(hist),
        "feature_columns": all_cols,
        "models": {
            "clf": clf,
            "gbdt_clf": gbdt_clf,
            "reg_home": reg_home,
            "reg_away": reg_away,
        },
        "scaler": scaler,
        "performance": {
            "winner_accuracy": winner_accuracy,
            "home_mae": home_mae,
            "away_mae": away_mae,
            "overall_mae": overall_mae,
        },
        "team_mappings": {
            "home_wr_map": dict(hist.groupby("home_team_id")["home_win"].mean()),
            "away_wr_map": {team_id: (1 - group["home_win"]).mean() for team_id, group in hist.groupby("away_team_id")},
        }
    }
    
    conn.close()
    return model_package

def save_models(models: Dict[int, Dict[str, Any]], output_dir: str = "artifacts") -> None:
    """Save trained models to disk"""
    os.makedirs(output_dir, exist_ok=True)
    
    for league_id, model_package in models.items():
        if model_package is None:
            continue
            
        filename = f"league_{league_id}_model.pkl"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_package, f)
        
        logger.info(f"Saved model for league {league_id} to {filepath}")
    
    # Save registry
    registry = {
        "last_updated": datetime.now().isoformat(),
        "leagues": {}
    }
    
    for league_id, model_package in models.items():
        if model_package is not None:
            registry["leagues"][league_id] = {
                "name": model_package["league_name"],
                "trained_at": model_package["trained_at"],
                "training_games": model_package["training_games"],
                "performance": model_package["performance"]
            }
    
    registry_path = os.path.join(output_dir, "model_registry.json")
    import json
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)
    
    logger.info(f"Saved model registry to {registry_path}")

def main():
    """Main training function"""
    logger.info("Starting automated model training")
    
    # Database path
    db_path = os.path.join(project_root, "data.sqlite")
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return
    
    # Train models for all leagues
    trained_models = {}
    for league_id in LEAGUE_CONFIGS.keys():
        try:
            model_package = train_league_models(league_id, db_path)
            trained_models[league_id] = model_package
        except Exception as e:
            logger.error(f"Failed to train models for league {league_id}: {e}")
            trained_models[league_id] = None
    
    # Save all models
    save_models(trained_models)
    
    # Summary
    successful_leagues = [lid for lid, model in trained_models.items() if model is not None]
    logger.info(f"Successfully trained models for {len(successful_leagues)} leagues: {successful_leagues}")
    
    if len(successful_leagues) == 0:
        logger.error("No models were successfully trained!")
        return 1
    
    logger.info("Model training completed successfully")
    return 0

if __name__ == "__main__":
    exit(main())
