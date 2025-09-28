#!/usr/bin/env python3
"""
Model Management System
Handles loading, saving, and managing trained models
"""

import os
import sys
import pickle
import json
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import numpy as np
import pandas as pd

# Add project root to path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelManager:
    """Manages trained models for all leagues"""
    
    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = os.path.join(project_root, artifacts_dir)
        self.models_cache = {}
        self.registry = None
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load model registry"""
        registry_path = os.path.join(self.artifacts_dir, "model_registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r') as f:
                    self.registry = json.load(f)
                logger.info("Loaded model registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.registry = {}
        else:
            self.registry = {}
            logger.warning("No model registry found")
    
    def get_model_info(self, league_id: int) -> Optional[Dict[str, Any]]:
        """Get information about a league's model"""
        if not self.registry or "leagues" not in self.registry:
            return None
        
        return self.registry["leagues"].get(str(league_id))
    
    def is_model_available(self, league_id: int) -> bool:
        """Check if a model is available for a league"""
        model_file = os.path.join(self.artifacts_dir, f"league_{league_id}_model.pkl")
        return os.path.exists(model_file)
    
    def load_model(self, league_id: int) -> Optional[Dict[str, Any]]:
        """Load a trained model for a specific league"""
        if league_id in self.models_cache:
            return self.models_cache[league_id]
        
        model_file = os.path.join(self.artifacts_dir, f"league_{league_id}_model.pkl")
        
        if not os.path.exists(model_file):
            logger.warning(f"No model found for league {league_id}")
            return None
        
        try:
            with open(model_file, 'rb') as f:
                model_package = pickle.load(f)
            
            self.models_cache[league_id] = model_package
            logger.info(f"Loaded model for league {league_id}")
            return model_package
            
        except Exception as e:
            logger.error(f"Failed to load model for league {league_id}: {e}")
            return None
    
    def get_all_available_models(self) -> Dict[int, Dict[str, Any]]:
        """Get all available models"""
        available_models = {}
        
        for league_id in [4986, 4446, 5069, 4574]:  # All league IDs
            if self.is_model_available(league_id):
                model_info = self.get_model_info(league_id)
                if model_info:
                    available_models[league_id] = model_info
        
        return available_models
    
    def predict_winner_probability(self, league_id: int, features: np.ndarray) -> Tuple[float, float]:
        """Predict winner probability for a match"""
        model_package = self.load_model(league_id)
        if not model_package:
            return 0.5, 0.5  # Default equal probability
        
        try:
            models = model_package["models"]
            clf = models["clf"]
            gbdt_clf = models["gbdt_clf"]
            
            # Ensure features are 2D
            if features.ndim == 1:
                features = features.reshape(1, -1)
            
            # Get probabilities from both models
            clf_probs = clf.predict_proba(features)[:, 1]
            gbdt_probs = gbdt_clf.predict_proba(features)[:, 1]
            
            # Ensemble average
            home_prob = 0.5 * (clf_probs[0] + gbdt_probs[0])
            away_prob = 1.0 - home_prob
            
            return home_prob, away_prob
            
        except Exception as e:
            logger.error(f"Failed to predict winner probability: {e}")
            return 0.5, 0.5
    
    def predict_scores(self, league_id: int, features: np.ndarray) -> Tuple[float, float]:
        """Predict scores for a match"""
        model_package = self.load_model(league_id)
        if not model_package:
            return 20.0, 20.0  # Default scores
        
        try:
            models = model_package["models"]
            reg_home = models["reg_home"]
            reg_away = models["reg_away"]
            scaler = model_package["scaler"]
            
            # Ensure features are 2D
            if features.ndim == 1:
                features = features.reshape(1, -1)
            
            # Scale features if needed
            if scaler is not None:
                features_scaled = scaler.transform(features)
                pred_home = reg_home.predict(features_scaled)[0]
                pred_away = reg_away.predict(features_scaled)[0]
            else:
                pred_home = reg_home.predict(features)[0]
                pred_away = reg_away.predict(features)[0]
            
            return float(pred_home), float(pred_away)
            
        except Exception as e:
            logger.error(f"Failed to predict scores: {e}")
            return 20.0, 20.0
    
    def get_model_performance(self, league_id: int) -> Optional[Dict[str, float]]:
        """Get model performance metrics"""
        model_package = self.load_model(league_id)
        if not model_package:
            return None
        
        return model_package.get("performance")
    
    def get_feature_columns(self, league_id: int) -> Optional[List[str]]:
        """Get feature columns used by a model"""
        model_package = self.load_model(league_id)
        if not model_package:
            return None
        
        return model_package.get("feature_columns")
    
    def get_team_mappings(self, league_id: int) -> Optional[Dict[str, Dict]]:
        """Get team win rate mappings"""
        model_package = self.load_model(league_id)
        if not model_package:
            return None
        
        return model_package.get("team_mappings")
    
    def clear_cache(self) -> None:
        """Clear the models cache"""
        self.models_cache.clear()
        logger.info("Cleared models cache")
    
    def get_registry_summary(self) -> Dict[str, Any]:
        """Get a summary of the model registry"""
        if not self.registry:
            return {"error": "No registry available"}
        
        summary = {
            "last_updated": self.registry.get("last_updated"),
            "total_leagues": len(self.registry.get("leagues", {})),
            "leagues": {}
        }
        
        for league_id, info in self.registry.get("leagues", {}).items():
            summary["leagues"][league_id] = {
                "name": info.get("name"),
                "trained_at": info.get("trained_at"),
                "training_games": info.get("training_games"),
                "winner_accuracy": info.get("performance", {}).get("winner_accuracy"),
                "overall_mae": info.get("performance", {}).get("overall_mae")
            }
        
        return summary

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

def main():
    """Test the model manager"""
    manager = ModelManager()
    
    # Test registry summary
    summary = manager.get_registry_summary()
    print("Model Registry Summary:")
    print(json.dumps(summary, indent=2))
    
    # Test model availability
    print("\nModel Availability:")
    for league_id in [4986, 4446, 5069, 4574]:
        available = manager.is_model_available(league_id)
        print(f"League {league_id}: {'Available' if available else 'Not Available'}")
    
    # Test model loading
    print("\nTesting model loading:")
    for league_id in [4986, 4446, 5069, 4574]:
        if manager.is_model_available(league_id):
            model_package = manager.load_model(league_id)
            if model_package:
                print(f"League {league_id}: Loaded successfully")
                print(f"  - Training games: {model_package.get('training_games')}")
                print(f"  - Trained at: {model_package.get('trained_at')}")
                print(f"  - Winner accuracy: {model_package.get('performance', {}).get('winner_accuracy', 'N/A')}")
            else:
                print(f"League {league_id}: Failed to load")

if __name__ == "__main__":
    main()
