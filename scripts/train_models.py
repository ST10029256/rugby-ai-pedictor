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
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestRegressor, GradientBoostingRegressor

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
    
    # Classification models (same for all leagues)
    base_lr = LogisticRegression(max_iter=2000, solver="lbfgs")
    calibrated_clf = CalibratedClassifierCV(base_lr, method="isotonic", cv=5)
    clf = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), calibrated_clf)
    gbdt_clf = HistGradientBoostingClassifier(random_state=42)
    
    # Regression models (league-specific)
    if league_id == 4446:  # United Rugby Championship
        reg_home = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42)
        reg_away = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42)
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

def train_league_models(league_id: int, db_path: str) -> Dict[str, Any]:
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
    hist = df[(df["league_id"] == league_id) & df["home_win"].notna()].copy()
    
    if len(hist) < 10:
        logger.warning(f"Insufficient data for league {league_id}: {len(hist)} games")
        return None
    
    # Feature columns
    feature_cols = [
        "elo_diff", "form_diff", "elo_home_pre", "elo_away_pre",
        "home_form", "away_form", "home_rest_days", "away_rest_days",
        "rest_diff", "home_goal_diff_form", "away_goal_diff_form",
        "goal_diff_form_diff", "h2h_home_rate", "season_phase", "is_home",
        # Advanced features
        "elo_ratio", "elo_sum", "form_diff_10", "h2h_recent", "rest_ratio", "home_advantage",
        "home_attack_strength", "away_attack_strength", "home_defense_strength", "away_defense_strength",
        "home_momentum", "away_momentum", "momentum_diff", "league_strength", "home_league_form", "away_league_form"
    ]
    
    present_cols = [c for c in feature_cols if c in hist.columns]
    
    # Add extra features
    extra_cols = ["home_wr_home", "away_wr_away", "pair_elo_expectation"]
    home_wr = hist.groupby("home_team_id")["home_win"].mean().astype("float64")
    away_wr = hist.assign(away_win=lambda d: (1 - d["home_win"]).astype(float)).groupby("away_team_id")["away_win"].mean().astype("float64")
    
    _home_wr_map = {safe_to_int(k): safe_to_float(v, default=float("nan")) for k, v in home_wr.items()}
    _away_wr_map = {safe_to_int(k): safe_to_float(v, default=float("nan")) for k, v in away_wr.items()}
    
    hist["home_wr_home"] = hist["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan")))
    hist["away_wr_away"] = hist["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan")))
    hist["pair_elo_expectation"] = 1.0 / (1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0))
    
    all_cols = present_cols + extra_cols
    X_hist = hist[all_cols].to_numpy()
    y_hist = hist["home_win"].astype(int).to_numpy()
    y_home = hist["home_score"].to_numpy()
    y_away = hist["away_score"].to_numpy()
    
    # Calculate time-decay weights
    weights = calculate_time_decay_weights(hist)
    
    # Apply winsorization to scores
    y_home_w = winsorize(y_home)
    y_away_w = winsorize(y_away)
    
    # Get league-specific models
    (clf, gbdt_clf), (reg_home, reg_away), scaler = get_league_specific_models(league_id)
    
    # Train classification models
    logger.info(f"Training classification models for league {league_id}")
    clf.fit(X_hist, y_hist)
    gbdt_clf.fit(X_hist, y_hist)
    
    # Train regression models
    logger.info(f"Training regression models for league {league_id}")
    if scaler is not None:
        X_hist_scaled = scaler.fit_transform(X_hist)
        reg_home.fit(X_hist_scaled, y_home_w)
        reg_away.fit(X_hist_scaled, y_away_w)
    else:
        reg_home.fit(X_hist, y_home_w)
        reg_away.fit(X_hist, y_away_w)
    
    # Calculate model performance metrics
    clf_probs = clf.predict_proba(X_hist)[:, 1]
    gbdt_probs = gbdt_clf.predict_proba(X_hist)[:, 1]
    ensemble_probs = 0.5 * (clf_probs + gbdt_probs)
    
    if scaler is not None:
        pred_home = reg_home.predict(scaler.transform(X_hist))
        pred_away = reg_away.predict(scaler.transform(X_hist))
    else:
        pred_home = reg_home.predict(X_hist)
        pred_away = reg_away.predict(X_hist)
    
    # Calculate accuracy metrics
    winner_accuracy = np.mean((ensemble_probs >= 0.5) == y_hist)
    home_mae = np.mean(np.abs(pred_home - y_home))
    away_mae = np.mean(np.abs(pred_away - y_away))
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
            "home_wr_map": _home_wr_map,
            "away_wr_map": _away_wr_map,
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
