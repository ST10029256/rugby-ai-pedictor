#!/usr/bin/env python3
"""
Model Manager for Rugby Prediction System
Handles loading and using trained models for predictions
"""

import os
import pickle
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ModelManager:
    """Manages loading and using trained rugby prediction models"""
    
    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = artifacts_dir
        self._models: Dict[int, Dict[str, Any]] = {}
        self._registry: Optional[Dict[str, Any]] = None
        self._load_registry()
    
    def _load_registry(self) -> None:
        """Load the model registry"""
        registry_path = os.path.join(self.artifacts_dir, "model_registry.json")
        try:
            if os.path.exists(registry_path):
                with open(registry_path, 'r') as f:
                    self._registry = json.load(f)
                logger.info(f"Loaded model registry from {registry_path}")
            else:
                logger.warning(f"Model registry not found at {registry_path}")
                self._registry = {}
        except Exception as e:
            logger.error(f"Error loading registry: {e}")
            self._registry = {}
    
    def is_model_available(self, league_id: int) -> bool:
        """Check if a model is available for the given league"""
        model_path = os.path.join(self.artifacts_dir, f"league_{league_id}_model.pkl")
        if not os.path.exists(model_path):
            return False
        
        # Try to load the model to check for compatibility issues
        try:
            test_load = self.load_model(league_id)
            return test_load is not None
        except Exception:
            return False
    
    def load_model(self, league_id: int) -> Optional[Dict[str, Any]]:
        """Load a trained model for the given league"""
        if league_id in self._models:
            return self._models[league_id]
        
        model_path = os.path.join(self.artifacts_dir, f"league_{league_id}_model.pkl")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found for league {league_id} at {model_path}")
        
        try:
            with open(model_path, 'rb') as f:
                model_package = pickle.load(f)
            
            self._models[league_id] = model_package
            logger.info(f"Loaded model for league {league_id}")
            return model_package
            
        except AttributeError as e:
            logger.error(f"Model compatibility error for league {league_id}: {e}")
            logger.error("This usually indicates a scikit-learn version mismatch.")
            logger.error(f"Model file location: {model_path}")
            # Don't re-raise - return None to indicate loading failure
            return None
            
        except Exception as e:
            logger.error(f"Error loading model for league {league_id}: {e}")
            logger.error(f"Model file location: {model_path}")
            # Don't re-raise - return None to indicate loading failure  
            return None
    
    def predict_winner_probability(self, league_id: int, features: pd.DataFrame | np.ndarray) -> Tuple[float, float]:
        """Predict winner probability for home and away teams"""
        try:
            model_package = self.load_model(league_id)
            
            if model_package is None:
                logger.error(f"Model loading failed for league {league_id}")
                return 0.5, 0.5  # Default to equal probability
            
            # Get the models sub-dictionary
            models_dict = model_package.get('models', {})
            classifier = models_dict.get('classifier') or models_dict.get('winner_predictor') or models_dict.get('clf')
            
            if classifier is None:
                logger.error(f"No classifier found for league {league_id}")
                logger.error(f"Models dict keys: {list(models_dict.keys()) if isinstance(models_dict, dict) else 'Not a dict'}")
                logger.error(f"Available keys: {list(model_package.keys()) if isinstance(model_package, dict) else 'Not a dict'}")
                return 0.5, 0.5  # Default to equal probability
            
            # Ensure features is a 2D array (required by scikit-learn)
            import numpy as np
            if isinstance(features, np.ndarray):
                if features.ndim == 1:
                    features = features.reshape(1, -1)  # Reshape 1D to 2D with one sample
            elif isinstance(features, pd.DataFrame):
                features = features.to_numpy()
                if features.ndim == 1:
                    features = features.reshape(1, -1)
            
            # Make prediction
            probabilities = classifier.predict_proba(features)
            
            # Return home and away probabilities
            if probabilities.shape[1] >= 2:
                home_prob = float(probabilities[0][1])  # Probability of home win
                away_prob = float(probabilities[0][0])   # Probability of away win
            else:
                # Fallback if only one class
                home_prob = float(probabilities[0][0])
                away_prob = 1.0 - home_prob
            
            return home_prob, away_prob
            
        except Exception as e:
            logger.error(f"Error predicting winner probability: {e}")
            return 0.5, 0.5  # Default to equal probability
    
    def predict_scores(self, league_id: int, features: pd.DataFrame | np.ndarray) -> Tuple[float, float]:
        """Predict scores for home and away teams"""
        try:
            model_package = self.load_model(league_id)
            
            if model_package is None:
                logger.error(f"Model loading failed for league {league_id}")
                return 0.0, 0.0  # Default to zero scores
            
            # Get the models sub-dictionary  
            models_dict = model_package.get('models', {})
            home_regressor = models_dict.get('home_regressor') or models_dict.get('home_score_predictor') or models_dict.get('reg_home')
            away_regressor = models_dict.get('away_regressor') or models_dict.get('away_score_predictor') or models_dict.get('reg_away')
            
            if home_regressor is None or away_regressor is None:
                logger.error(f"No regressors found for league {league_id}")
                logger.error(f"Models dict keys: {list(models_dict.keys()) if isinstance(models_dict, dict) else 'Not a dict'}")
                logger.error(f"Available keys: {list(model_package.keys()) if isinstance(model_package, dict) else 'Not a dict'}")
                return 0.0, 0.0  # Default to zero scores
            
            # Get the scaler if it exists (needed for Rugby Championship)
            scaler = model_package.get('scaler')
            
            # Ensure features is a 2D array (required by scikit-learn)
            import numpy as np
            if isinstance(features, np.ndarray):
                if features.ndim == 1:
                    features = features.reshape(1, -1)  # Reshape 1D to 2D with one sample
            elif isinstance(features, pd.DataFrame):
                features = features.to_numpy()
                if features.ndim == 1:
                    features = features.reshape(1, -1)
            
            # Apply scaling if scaler exists (essential for Rugby Championship)
            if scaler is not None:
                features = scaler.transform(features)
            
            # Make predictions
            home_score = float(home_regressor.predict(features)[0])
            away_score = float(away_regressor.predict(features)[0])
            
            # Ensure non-negative scores
            home_score = max(0.0, home_score)
            away_score = max(0.0, away_score)
            
            return home_score, away_score
            
        except Exception as e:
            logger.error(f"Error predicting scores: {e}")
            return 0.0, 0.0  # Default to zero scores
    
    def get_registry_summary(self) -> Dict[str, Any]:
        """Get a summary of the model registry"""
        if self._registry is None:
            return {}
        
        summary = {
            "last_updated": self._registry.get("last_updated", "Unknown"),
            "leagues": {}
        }
        
        leagues = self._registry.get("leagues", {})
        for league_id, league_info in leagues.items():
            summary["leagues"][league_id] = {
                "name": league_info.get("name", f"League {league_id}"),
                "trained_at": league_info.get("trained_at", "Unknown"),
                "training_games": league_info.get("training_games", 0),
                "performance": league_info.get("performance", {})
            }
        
        return summary
    
    def get_league_names(self) -> Dict[int, str]:
        """Get mapping of league IDs to names"""
        if self._registry is None:
            return {}
        
        leagues = self._registry.get("leagues", {})
        return {int(league_id): league_info.get("name", f"League {league_id}") 
                for league_id, league_info in leagues.items()}
