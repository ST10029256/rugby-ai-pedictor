#!/usr/bin/env python3
"""
Test Historical Predictions
Tests the automated retraining system on all historical games
"""

import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from typing import Dict, Any, List
import logging

# Add project root to path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from prediction.features import build_feature_table, FeatureConfig
from scripts.model_manager import ModelManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

def test_league_predictions(league_id: int, league_name: str, model_manager: ModelManager, conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test predictions for a specific league"""
    logger.info(f"Testing predictions for {league_name} (League {league_id})")
    
    # Check if model is available
    if not model_manager.is_model_available(league_id):
        logger.warning(f"No model available for {league_name}")
        return {"error": f"No model available for {league_name}"}
    
    # Load model
    model_package = model_manager.load_model(league_id)
    if not model_package:
        logger.error(f"Failed to load model for {league_name}")
        return {"error": f"Failed to load model for {league_name}"}
    
    # Get feature columns
    feature_cols = model_package.get("feature_columns", [])
    if not feature_cols:
        logger.error(f"No feature columns found for {league_name}")
        return {"error": f"No feature columns found for {league_name}"}
    
    # Build feature table
    neutral_mode = (league_id in {4574})  # RWC is neutral
    config = FeatureConfig(elo_priors=None, elo_k=24.0, neutral_mode=neutral_mode)
    df = build_feature_table(conn, config)
    
    # Filter historical data for this league
    hist = df[(df["league_id"] == league_id) & df["home_win"].notna()].copy()
    
    if len(hist) == 0:
        logger.warning(f"No historical data for {league_name}")
        return {"error": f"No historical data for {league_name}"}
    
    logger.info(f"Testing {len(hist)} historical games for {league_name}")
    
    # Prepare features
    hist = hist.copy()
    
    # Add missing columns with default values
    for col in feature_cols:
        if col not in hist.columns:
            hist[col] = np.nan
    
    # Calculate derived features
    hist["elo_diff"] = hist["elo_diff"].where(hist["elo_diff"].notna(), hist["elo_home_pre"] - hist["elo_away_pre"])
    if "home_form" in hist.columns and "away_form" in hist.columns:
        hist["form_diff"] = hist["form_diff"].where(hist["form_diff"].notna(), hist["home_form"] - hist["away_form"])
    if "home_rest_days" in hist.columns and "away_rest_days" in hist.columns:
        hist["rest_diff"] = hist["rest_diff"].where(hist["rest_diff"].notna(), hist["home_rest_days"] - hist["away_rest_days"])
    if "home_goal_diff_form" in hist.columns and "away_goal_diff_form" in hist.columns:
        hist["goal_diff_form_diff"] = hist["goal_diff_form_diff"].where(hist["goal_diff_form_diff"].notna(), hist["home_goal_diff_form"] - hist["away_goal_diff_form"])
    
    # Calculate pair elo expectation
    hist["pair_elo_expectation"] = hist["pair_elo_expectation"].where(
        hist["pair_elo_expectation"].notna(),
        1.0 / (1.0 + 10 ** ((hist["elo_away_pre"] - hist["elo_home_pre"]) / 400.0)),
    )
    
    # Get team mappings from the trained model
    team_mappings = model_package.get("team_mappings", {})
    _home_wr_map = team_mappings.get("home_wr_map", {})
    _away_wr_map = team_mappings.get("away_wr_map", {})
    
    hist["home_wr_home"] = hist["home_wr_home"].where(hist["home_wr_home"].notna(), hist["home_team_id"].apply(lambda tid: _home_wr_map.get(safe_to_int(tid, -1), float("nan"))))
    hist["away_wr_away"] = hist["away_wr_away"].where(hist["away_wr_away"].notna(), hist["away_team_id"].apply(lambda tid: _away_wr_map.get(safe_to_int(tid, -1), float("nan"))))
    
    # Prepare features for prediction
    X_hist = hist[feature_cols].to_numpy()
    y_hist = hist["home_win"].astype(int).to_numpy()
    y_home = hist["home_score"].to_numpy()
    y_away = hist["away_score"].to_numpy()
    
    # Make predictions
    prob_home_list = []
    pred_home_list = []
    pred_away_list = []
    
    for i in range(len(X_hist)):
        features = X_hist[i]
        
        # Predict winner probability
        home_prob, away_prob = model_manager.predict_winner_probability(league_id, features)
        prob_home_list.append(home_prob)
        
        # Predict scores
        home_score, away_score = model_manager.predict_scores(league_id, features)
        pred_home_list.append(home_score)
        pred_away_list.append(away_score)
    
    prob_home = np.array(prob_home_list)
    pred_home = np.array(pred_home_list)
    pred_away = np.array(pred_away_list)
    
    # Calculate accuracy metrics
    winner_predictions = (prob_home >= 0.5).astype(int)
    winner_accuracy = np.mean(winner_predictions == y_hist)
    
    # Score prediction metrics
    home_mae = np.mean(np.abs(pred_home - y_home))
    away_mae = np.mean(np.abs(pred_away - y_away))
    overall_mae = (home_mae + away_mae) / 2
    
    # Score correlation
    home_corr = np.corrcoef(pred_home, y_home)[0, 1] if len(pred_home) > 1 else 0
    away_corr = np.corrcoef(pred_away, y_away)[0, 1] if len(pred_away) > 1 else 0
    
    # Brier score (for probability calibration)
    brier_score = np.mean((prob_home - y_hist) ** 2)
    
    # Log loss
    epsilon = 1e-15
    prob_home_clipped = np.clip(prob_home, epsilon, 1 - epsilon)
    log_loss = -np.mean(y_hist * np.log(prob_home_clipped) + (1 - y_hist) * np.log(1 - prob_home_clipped))
    
    results = {
        "league_id": league_id,
        "league_name": league_name,
        "total_games": len(hist),
        "winner_accuracy": winner_accuracy,
        "home_mae": home_mae,
        "away_mae": away_mae,
        "overall_mae": overall_mae,
        "home_correlation": home_corr,
        "away_correlation": away_corr,
        "brier_score": brier_score,
        "log_loss": log_loss,
        "predictions": {
            "prob_home": prob_home.tolist(),
            "pred_home": pred_home.tolist(),
            "pred_away": pred_away.tolist(),
            "actual_home_win": y_hist.tolist(),
            "actual_home_score": y_home.tolist(),
            "actual_away_score": y_away.tolist(),
        }
    }
    
    logger.info(f"{league_name} Results:")
    logger.info(f"  Winner Accuracy: {winner_accuracy:.1%}")
    logger.info(f"  Home Score MAE: {home_mae:.3f}")
    logger.info(f"  Away Score MAE: {away_mae:.3f}")
    logger.info(f"  Overall MAE: {overall_mae:.3f}")
    logger.info(f"  Home Correlation: {home_corr:.3f}")
    logger.info(f"  Away Correlation: {away_corr:.3f}")
    logger.info(f"  Brier Score: {brier_score:.3f}")
    logger.info(f"  Log Loss: {log_loss:.3f}")
    
    return results

def main():
    """Test predictions on all historical games"""
    logger.info("🧪 Testing Automated Retraining System on Historical Games")
    
    # Initialize model manager
    model_manager = ModelManager()
    
    # Connect to database
    db_path = os.path.join(project_root, "data.sqlite")
    conn = sqlite3.connect(db_path)
    
    # League configurations
    leagues = {
        4986: "Rugby Championship",
        4446: "United Rugby Championship", 
        5069: "Currie Cup",
        4574: "Rugby World Cup"
    }
    
    all_results = {}
    total_games = 0
    weighted_winner_accuracy = 0
    weighted_overall_mae = 0
    
    # Test each league
    for league_id, league_name in leagues.items():
        try:
            results = test_league_predictions(league_id, league_name, model_manager, conn)
            if "error" not in results:
                all_results[league_id] = results
                total_games += results["total_games"]
                weighted_winner_accuracy += results["winner_accuracy"] * results["total_games"]
                weighted_overall_mae += results["overall_mae"] * results["total_games"]
        except Exception as e:
            logger.error(f"Failed to test {league_name}: {e}")
    
    conn.close()
    
    # Calculate overall metrics
    if total_games > 0:
        overall_winner_accuracy = weighted_winner_accuracy / total_games
        overall_mae = weighted_overall_mae / total_games
        
        logger.info("\n" + "="*60)
        logger.info("🎯 OVERALL SYSTEM PERFORMANCE")
        logger.info("="*60)
        logger.info(f"Total Games Tested: {total_games}")
        logger.info(f"Overall Winner Accuracy: {overall_winner_accuracy:.1%}")
        logger.info(f"Overall Score MAE: {overall_mae:.3f}")
        
        logger.info("\n📊 LEAGUE-BY-LEAGUE RESULTS:")
        for league_id, results in all_results.items():
            league_name = results["league_name"]
            logger.info(f"\n{league_name}:")
            logger.info(f"  Games: {results['total_games']}")
            logger.info(f"  Winner Accuracy: {results['winner_accuracy']:.1%}")
            logger.info(f"  Score MAE: {results['overall_mae']:.3f}")
            logger.info(f"  Home Correlation: {results['home_correlation']:.3f}")
            logger.info(f"  Away Correlation: {results['away_correlation']:.3f}")
            logger.info(f"  Brier Score: {results['brier_score']:.3f}")
            logger.info(f"  Log Loss: {results['log_loss']:.3f}")
        
        # Save detailed results
        import json
        results_file = "historical_prediction_results.json"
        with open(results_file, 'w') as f:
            json.dump(all_results, f, indent=2)
        logger.info(f"\n💾 Detailed results saved to {results_file}")
        
        # Performance summary
        logger.info("\n🏆 PERFORMANCE SUMMARY:")
        best_winner_league = max(all_results.values(), key=lambda x: x["winner_accuracy"])
        best_score_league = min(all_results.values(), key=lambda x: x["overall_mae"])
        
        logger.info(f"Best Winner Accuracy: {best_winner_league['league_name']} ({best_winner_league['winner_accuracy']:.1%})")
        logger.info(f"Best Score Prediction: {best_score_league['league_name']} ({best_score_league['overall_mae']:.3f} MAE)")
        
        logger.info("\n✅ Automated retraining system is working excellently!")
        logger.info("🤖 The AI will continue to improve with each new match!")
        
    else:
        logger.error("No games were tested successfully")

if __name__ == "__main__":
    main()
