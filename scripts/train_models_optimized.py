#!/usr/bin/env python3
"""
Optimized Model Training Script
Implements improvements:
1. Feature selection using permutation importance
2. Simplified models (HGBC vs stacking comparison)
3. Walk-forward time-based validation
4. Comparison analysis
"""

import os
import sys
import sqlite3
import pickle
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List
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
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.ensemble import StackingClassifier, StackingRegressor
from sklearn.linear_model import LogisticRegression, ElasticNet
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, mean_absolute_error, log_loss
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('model_training_optimized.log'),
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
    4551: {"name": "Super Rugby", "neutral_mode": False},
    4430: {"name": "French Top 14", "neutral_mode": False},
    4414: {"name": "English Premiership Rugby", "neutral_mode": False},
}

def get_simple_model():
    """Simple HistGradientBoosting model"""
    clf = HistGradientBoostingClassifier(
        random_state=42,
        max_iter=200,
        learning_rate=0.05,
        max_depth=8,
        min_samples_leaf=5
    )
    reg = HistGradientBoostingRegressor(
        random_state=42,
        max_iter=200,
        learning_rate=0.05,
        max_depth=8,
        min_samples_leaf=5
    )
    return clf, reg

def get_stacking_model():
    """Stacking ensemble model"""
    base_clf = [
        ('hgb', HistGradientBoostingClassifier(random_state=42, max_iter=150, learning_rate=0.05)),
        ('rf', RandomForestClassifier(n_estimators=150, random_state=42, max_depth=12)),
    ]
    
    base_reg = [
        ('hgb', HistGradientBoostingRegressor(random_state=42, max_iter=150, learning_rate=0.05)),
        ('rf', RandomForestRegressor(n_estimators=150, random_state=42, max_depth=12)),
    ]
    
    clf = StackingClassifier(
        estimators=base_clf,
        final_estimator=LogisticRegression(random_state=42, max_iter=1000),
        cv=3,
        stack_method='predict_proba'
    )
    
    reg = StackingRegressor(
        estimators=base_reg,
        final_estimator=ElasticNet(random_state=42, alpha=0.1, l1_ratio=0.5),
        cv=3
    )
    
    return clf, reg

def select_top_features(X: np.ndarray, y: np.ndarray, feature_names: List[str], 
                       n_features: int = 50, random_state: int = 42) -> List[str]:
    """Use permutation importance to select top N features"""
    logger.info(f"Selecting top {n_features} features from {len(feature_names)} total")
    
    # Train a quick model for feature selection
    model = HistGradientBoostingClassifier(random_state=random_state, max_iter=100)
    model.fit(X, y)
    
    # Calculate permutation importance
    perm_importance = permutation_importance(
        model, X, y, n_repeats=5, random_state=random_state, n_jobs=-1
    )
    
    # Get top features
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'importance': perm_importance['importances_mean']
    })
    importance_df = importance_df.sort_values('importance', ascending=False)
    
    top_features_series = importance_df.head(n_features)['feature']
    top_features: List[str] = list(top_features_series)
    
    logger.info(f"Top 10 features: {top_features[:10]}")
    
    return top_features

def walk_forward_validation(X: np.ndarray, y: np.ndarray, dates: pd.Series, 
                            n_splits: int = 5) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Create time-based train/test splits (walk-forward)
    Each split trains on all data before a cutoff, tests on data after
    """
    # Sort by date
    sort_idx = dates.argsort()
    X_sorted = X[sort_idx]
    y_sorted = y[sort_idx]
    
    n_samples = len(X)
    splits = []
    
    # Use expanding window: train on all data up to a point, test on next chunk
    initial_train_size = int(0.5 * n_samples)  # Start with 50% as training
    test_size = int((n_samples - initial_train_size) / n_splits)
    
    for i in range(n_splits):
        train_end = initial_train_size + i * test_size
        test_start = train_end
        test_end = min(test_start + test_size, n_samples)
        
        if test_end <= test_start:
            break
            
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        
        splits.append((train_idx, test_idx))
        
    logger.info(f"Created {len(splits)} time-based splits")
    return splits

def train_and_evaluate(X_train: np.ndarray, y_train: np.ndarray,
                      X_test: np.ndarray, y_test: np.ndarray,
                      model_type: str, task: str = 'classification') -> Dict[str, Any] | None:
    """Train and evaluate a model"""
    
    if task == 'classification':
        # Check if y_test has sufficient label variety
        unique_test_labels = np.unique(y_test)
        unique_train_labels = np.unique(y_train)
        if len(unique_test_labels) < 2 or len(unique_train_labels) < 2:
            # Skip this split - insufficient label variety
            return None
        
        # Classification task
        if model_type == 'simple':
            clf_model, _ = get_simple_model()
        else:  # stacking
            clf_model, _ = get_stacking_model()
        
        try:
            clf_model.fit(X_train, y_train)
            y_pred = clf_model.predict(X_test)
            y_proba = clf_model.predict_proba(X_test)
            
            accuracy = accuracy_score(y_test, y_pred)
            # Use explicit labels to handle edge cases
            logloss = log_loss(y_test, y_proba, labels=[0, 1])
            
            return {
                'accuracy': float(accuracy),
                'log_loss': float(logloss)
            }
        except (ValueError, RuntimeError) as e:
            # Handle sklearn errors with imbalanced data
            logger.warning(f"  Skipping {model_type} model - sklearn error: {str(e)[:100]}")
            return None
    else:
        # Regression task
        if model_type == 'simple':
            _, reg_model = get_simple_model()
        else:  # stacking
            _, reg_model = get_stacking_model()
        
        reg_model.fit(X_train, y_train)
        y_pred = reg_model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        
        return {
            'mae': float(mae)
        }

def train_league_optimized(league_id: int, db_path: str) -> Dict[str, Any] | None:
    """Train optimized models for a league with comparison analysis"""
    logger.info(f"\n{'='*80}")
    logger.info(f"Training optimized models for league {league_id} ({LEAGUE_CONFIGS[league_id]['name']})")
    logger.info(f"{'='*80}")
    
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
    
    if len(hist) < 50:
        logger.warning(f"Insufficient data for league {league_id}: {len(hist)} games")
        conn.close()
        return None
    
    logger.info(f"Total games: {len(hist)}")
    
    # Get feature columns
    metadata_cols = ["event_id", "league_id", "season", "date_event", "home_team_id", 
                    "away_team_id", "home_score", "away_score", "home_win"]
    feature_cols = [c for c in hist.columns if c not in metadata_cols]
    
    logger.info(f"Total features before selection: {len(feature_cols)}")
    
    # Prepare data
    X_full = np.asarray(hist[feature_cols])
    y_clf = np.asarray(hist["home_win"].astype(int))
    y_home = np.asarray(hist["home_score"])
    y_away = np.asarray(hist["away_score"])
    dates = pd.Series(pd.to_datetime(hist["date_event"]).values)
    
    # Feature selection
    top_features = select_top_features(X_full, y_clf, feature_cols, n_features=50)
    feature_idx = [feature_cols.index(f) for f in top_features]
    X_selected = X_full[:, feature_idx]
    
    logger.info(f"Features after selection: {len(top_features)}")
    
    # Create walk-forward splits
    splits = walk_forward_validation(X_selected, y_clf, dates, n_splits=5)
    
    # Compare models
    results = {
        'simple': {'clf_acc': [], 'home_mae': [], 'away_mae': []},
        'stacking': {'clf_acc': [], 'home_mae': [], 'away_mae': []}
    }
    
    for split_idx, (train_idx, test_idx) in enumerate(splits):
        logger.info(f"\nSplit {split_idx + 1}/{len(splits)}: Train={len(train_idx)}, Test={len(test_idx)}")
        
        X_train, X_test = X_selected[train_idx], X_selected[test_idx]
        y_clf_train, y_clf_test = y_clf[train_idx], y_clf[test_idx]
        y_home_train, y_home_test = y_home[train_idx], y_home[test_idx]
        y_away_train, y_away_test = y_away[train_idx], y_away[test_idx]
        
        # Check if test set has sufficient label variety
        unique_test_labels = np.unique(y_clf_test)
        if len(unique_test_labels) < 2:
            logger.warning(f"  Skipping split {split_idx + 1} - insufficient label variety in test set (only {unique_test_labels})")
            continue
        
        # Test both model types
        for model_type in ['simple', 'stacking']:
            # Classification
            clf_results = train_and_evaluate(X_train, y_clf_train, X_test, y_clf_test,
                                            model_type, 'classification')
            if clf_results is None:
                continue
            results[model_type]['clf_acc'].append(clf_results['accuracy'])
            
            # Regression (home)
            home_results = train_and_evaluate(X_train, y_home_train, X_test, y_home_test,
                                             model_type, 'regression')
            if home_results:
                results[model_type]['home_mae'].append(home_results['mae'])
            else:
                continue
            
            # Regression (away)
            away_results = train_and_evaluate(X_train, y_away_train, X_test, y_away_test,
                                             model_type, 'regression')
            if away_results:
                results[model_type]['away_mae'].append(away_results['mae'])
            else:
                continue
        
        # Only log if we have results for this split
        if len(results['simple']['clf_acc']) > 0 and len(results['simple']['home_mae']) > 0:
            logger.info(f"  Simple - Acc: {results['simple']['clf_acc'][-1]:.3f}, "
                       f"Home MAE: {results['simple']['home_mae'][-1]:.2f}, "
                       f"Away MAE: {results['simple']['away_mae'][-1]:.2f}")
        if len(results['stacking']['clf_acc']) > 0 and len(results['stacking']['home_mae']) > 0:
            logger.info(f"  Stack  - Acc: {results['stacking']['clf_acc'][-1]:.3f}, "
                       f"Home MAE: {results['stacking']['home_mae'][-1]:.2f}, "
                       f"Away MAE: {results['stacking']['away_mae'][-1]:.2f}")
    
    # Check if we have any valid results
    if len(results['simple']['clf_acc']) == 0 and len(results['stacking']['clf_acc']) == 0:
        logger.warning(f"No valid splits for league {league_id} - insufficient label variety across all splits")
        logger.info("Using simple model with full dataset (no cross-validation)")
        
        # Train on full dataset without validation
        clf_model, reg_home = get_simple_model()
        _, reg_away = get_simple_model()
        
        clf_model.fit(X_selected, y_clf)
        reg_home.fit(X_selected, y_home)
        reg_away.fit(X_selected, y_away)
        
        # Estimate performance on full dataset
        y_clf_pred = clf_model.predict(X_selected)
        full_accuracy = accuracy_score(y_clf, y_clf_pred)
        
        y_home_pred = reg_home.predict(X_selected)
        y_away_pred = reg_away.predict(X_selected)
        full_home_mae = mean_absolute_error(y_home, y_home_pred)
        full_away_mae = mean_absolute_error(y_away, y_away_pred)
        
        logger.info(f"Full dataset performance: Acc={full_accuracy:.3f}, Home MAE={full_home_mae:.2f}, Away MAE={full_away_mae:.2f}")
        
        # Create model package
        model_package = {
            'league_id': league_id,
            'league_name': LEAGUE_CONFIGS[league_id]['name'],
            'trained_at': datetime.now().isoformat(),
            'training_games': len(hist),
            'model_type': 'simple',
            'feature_columns': top_features,
            'scaler': None,
            'performance': {
                'winner_accuracy': float(full_accuracy),
                'home_mae': float(full_home_mae),
                'away_mae': float(full_away_mae),
                'overall_mae': float((full_home_mae + full_away_mae) / 2)
            },
            'models': {
                'clf': clf_model,
                'reg_home': reg_home,
                'reg_away': reg_away
            }
        }
        conn.close()
        return model_package
    
    # Calculate averages
    comparison = {}
    for model_type in ['simple', 'stacking']:
        comparison[model_type] = {
            'avg_accuracy': np.mean(results[model_type]['clf_acc']),
            'std_accuracy': np.std(results[model_type]['clf_acc']),
            'avg_home_mae': np.mean(results[model_type]['home_mae']),
            'avg_away_mae': np.mean(results[model_type]['away_mae']),
            'avg_overall_mae': (np.mean(results[model_type]['home_mae']) + 
                               np.mean(results[model_type]['away_mae'])) / 2
        }
    
    # Determine winner
    simple_score = comparison['simple']['avg_accuracy'] - comparison['simple']['avg_overall_mae'] * 0.01
    stack_score = comparison['stacking']['avg_accuracy'] - comparison['stacking']['avg_overall_mae'] * 0.01
    
    winner = 'simple' if simple_score >= stack_score else 'stacking'
    
    logger.info(f"\n{'='*80}")
    logger.info(f"COMPARISON RESULTS - {LEAGUE_CONFIGS[league_id]['name']}")
    logger.info(f"{'='*80}")
    logger.info(f"Simple Model:")
    logger.info(f"  Accuracy: {comparison['simple']['avg_accuracy']:.3f} ± {comparison['simple']['std_accuracy']:.3f}")
    logger.info(f"  Overall MAE: {comparison['simple']['avg_overall_mae']:.2f}")
    logger.info(f"\nStacking Model:")
    logger.info(f"  Accuracy: {comparison['stacking']['avg_accuracy']:.3f} ± {comparison['stacking']['std_accuracy']:.3f}")
    logger.info(f"  Overall MAE: {comparison['stacking']['avg_overall_mae']:.2f}")
    logger.info(f"\n🏆 WINNER: {winner.upper()} model")
    logger.info(f"{'='*80}")
    
    # Train final model on all data using winner
    if winner == 'simple':
        final_clf, final_reg_home = get_simple_model()
        _, final_reg_away = get_simple_model()
    else:
        final_clf, final_reg_home = get_stacking_model()
        _, final_reg_away = get_stacking_model()
    
    final_clf.fit(X_selected, y_clf)
    final_reg_home.fit(X_selected, y_home)
    final_reg_away.fit(X_selected, y_away)
    
    # Package results
    model_package = {
        "league_id": league_id,
        "league_name": LEAGUE_CONFIGS[league_id]["name"],
        "trained_at": datetime.now().isoformat(),
        "training_games": len(hist),
        "optimization": "enabled",
        "feature_selection": {
            "original_features": len(feature_cols),
            "selected_features": len(top_features),
            "feature_names": top_features
        },
        "feature_columns": top_features,
        "models": {
            "clf": final_clf,
            "reg_home": final_reg_home,
            "reg_away": final_reg_away,
        },
        "scaler": None,
        "model_type": winner,
        "comparison": comparison,
        "performance": {
            "winner_accuracy": comparison[winner]['avg_accuracy'],
            "home_mae": comparison[winner]['avg_home_mae'],
            "away_mae": comparison[winner]['avg_away_mae'],
            "overall_mae": comparison[winner]['avg_overall_mae'],
        }
    }
    
    conn.close()
    return model_package

def save_models(models: Dict[int, Dict[str, Any]], output_dir: str = "artifacts_optimized") -> None:
    """Save trained models to disk"""
    os.makedirs(output_dir, exist_ok=True)
    
    for league_id, model_package in models.items():
        if model_package is None:
            continue
            
        filename = f"league_{league_id}_model_optimized.pkl"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_package, f)
        
        logger.info(f"Saved optimized model for league {league_id} to {filepath}")
    
    # Save registry
    registry = {
        "last_updated": datetime.now().isoformat(),
        "optimization_enabled": True,
        "leagues": {}
    }
    
    for league_id, model_package in models.items():
        if model_package is not None:
            registry["leagues"][league_id] = {
                "name": model_package["league_name"],
                "trained_at": model_package["trained_at"],
                "training_games": model_package["training_games"],
                "model_type": model_package["model_type"],
                "performance": model_package["performance"],
                "feature_selection": {
                    "original": model_package["feature_selection"]["original_features"],
                    "selected": model_package["feature_selection"]["selected_features"]
                }
            }
    
    registry_path = os.path.join(output_dir, "model_registry_optimized.json")
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)
    
    logger.info(f"Saved optimized model registry to {registry_path}")

def main():
    """Main training function"""
    logger.info("="*80)
    logger.info("OPTIMIZED MODEL TRAINING")
    logger.info("Improvements: Feature selection, Walk-forward validation, Model comparison")
    logger.info("="*80)
    
    # Database path
    db_path = os.path.join(project_root, "data.sqlite")
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return 1
    
    # Train models for all leagues
    trained_models = {}
    for league_id in LEAGUE_CONFIGS.keys():
        try:
            model_package = train_league_optimized(league_id, db_path)
            trained_models[league_id] = model_package
        except Exception as e:
            logger.error(f"Failed to train models for league {league_id}: {e}", exc_info=True)
            trained_models[league_id] = None
    
    # Save all models
    save_models(trained_models)
    
    # Summary
    successful_leagues = [lid for lid, model in trained_models.items() if model is not None]
    logger.info(f"\n{'='*80}")
    logger.info(f"Successfully trained optimized models for {len(successful_leagues)} leagues")
    logger.info(f"{'='*80}")
    
    # Model type summary
    for lid in successful_leagues:
        model = trained_models[lid]
        logger.info(f"{model['league_name']}: {model['model_type'].upper()} "
                   f"(Acc: {model['performance']['winner_accuracy']:.1%}, "
                   f"MAE: {model['performance']['overall_mae']:.2f})")
    
    if len(successful_leagues) == 0:
        logger.error("No models were successfully trained!")
        return 1
    
    logger.info("\nOptimized model training completed successfully")
    return 0

if __name__ == "__main__":
    exit(main())
