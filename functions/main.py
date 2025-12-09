"""
Firebase Cloud Functions for Rugby AI Predictor
Handles callable functions for predictions, matches, and data
"""

from firebase_functions import https_fn  # type: ignore
from firebase_admin import initialize_app, firestore, storage  # type: ignore
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING

# Initialize Firebase Admin
initialize_app()

# Import prediction modules
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Type checking imports
if TYPE_CHECKING:
    from prediction.hybrid_predictor import MultiLeaguePredictor
    from prediction.enhanced_predictor import EnhancedRugbyPredictor
    from prediction.config import LEAGUE_MAPPINGS

# Runtime imports with fallback
try:
    from prediction.hybrid_predictor import MultiLeaguePredictor
    from prediction.enhanced_predictor import EnhancedRugbyPredictor
    from prediction.config import LEAGUE_MAPPINGS
except ImportError as e:
    print(f"Warning: Could not import prediction modules: {e}")
    # Create fallback types for type checking
    MultiLeaguePredictor = None  # type: ignore
    EnhancedRugbyPredictor = None  # type: ignore
    LEAGUE_MAPPINGS = {}  # type: ignore

# Initialize Firestore
db = firestore.client()

# Initialize predictors (lazy loading)
_predictor: Optional[Any] = None
_enhanced_predictor: Optional[Any] = None


def get_predictor() -> Any:
    """Get or create MultiLeaguePredictor instance"""
    global _predictor
    if _predictor is None:
        if MultiLeaguePredictor is None:
            raise ImportError("MultiLeaguePredictor not available")
        # Use Cloud Storage for database if available, otherwise local
        db_path = os.getenv('DB_PATH', '/tmp/data.sqlite')
        # Get storage bucket from environment or use default
        storage_bucket = os.getenv('MODEL_STORAGE_BUCKET') or os.getenv('STORAGE_BUCKET')
        if not storage_bucket:
            # Try to get from Firebase Storage default bucket
            try:
                from firebase_admin import storage as fb_storage
                bucket = fb_storage.bucket()
                if bucket:
                    storage_bucket = bucket.name
            except Exception:
                pass
        
        _predictor = MultiLeaguePredictor(
            db_path=db_path,
            storage_bucket=storage_bucket
        )
    return _predictor


def get_enhanced_predictor() -> Optional[Any]:
    """Get or create EnhancedRugbyPredictor instance"""
    global _enhanced_predictor
    if _enhanced_predictor is None:
        if EnhancedRugbyPredictor is None:
            return None
        api_key = os.getenv('HIGHLIGHTLY_API_KEY')
        if api_key:
            db_path = os.getenv('DB_PATH', '/tmp/data.sqlite')
            _enhanced_predictor = EnhancedRugbyPredictor(db_path, api_key)
    return _enhanced_predictor


@https_fn.on_call(timeout_sec=300, memory=512)  # 5 minute timeout, 512MB memory
def predict_match(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get match prediction
    
    Request data:
    {
        "home_team": "South Africa",
        "away_team": "New Zealand",
        "league_id": 4986,
        "match_date": "2025-11-22",
        "enhanced": false
    }
    """
    import traceback
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data
        home_team = data.get('home_team')
        away_team = data.get('away_team')
        league_id = data.get('league_id')
        match_date = data.get('match_date')
        enhanced = data.get('enhanced', False)
        
        logger.info(f"predict_match called: {home_team} vs {away_team}, league={league_id}, date={match_date}")
        
        # Validate inputs
        if not home_team or not away_team:
            logger.error(f"Missing team names: home={home_team}, away={away_team}")
            return {'error': 'Missing required fields: home_team and away_team are required'}
        
        if not league_id:
            logger.error("Missing league_id")
            return {'error': 'Missing required field: league_id'}
        
        if not match_date:
            logger.error("Missing match_date")
            return {'error': 'Missing required field: match_date'}
        
        try:
            league_id = int(league_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid league_id: {league_id}")
            return {'error': f'Invalid league_id: {league_id}'}
        
        # Get predictor with error handling
        predictor = None
        try:
            if enhanced:
                predictor = get_enhanced_predictor()
                if not predictor:
                    logger.warning("Enhanced predictor not available, falling back to standard")
                    predictor = get_predictor()
                else:
                    logger.info("Using enhanced predictor")
                    try:
                        prediction = predictor.get_enhanced_prediction(
                            home_team, away_team, league_id, match_date
                        )
                        logger.info(f"Prediction successful: {prediction.get('home_win_prob', 'N/A')}")
                        return prediction
                    except FileNotFoundError as fnf:
                        logger.error(f"Model not found for enhanced predictor: {fnf}")
                        return {'error': f'Model not found for league {league_id}. Please ensure models are uploaded to Cloud Storage.'}
                    except Exception as pred_err:
                        logger.error(f"Enhanced prediction failed: {pred_err}")
                        logger.error(traceback.format_exc())
                        return {'error': f'Prediction failed: {str(pred_err)}'}
            else:
                predictor = get_predictor()
                logger.info("Using standard predictor")
        except FileNotFoundError as fnf:
            logger.error(f"Model file not found: {fnf}")
            logger.error(traceback.format_exc())
            return {'error': f'Model not found for league {league_id}. Please ensure models are uploaded to Cloud Storage. Details: {str(fnf)}'}
        except ImportError as import_err:
            logger.error(f"Import error initializing predictor: {import_err}")
            logger.error(traceback.format_exc())
            return {'error': f'Failed to import required modules: {str(import_err)}'}
        except Exception as pred_init_error:
            logger.error(f"Failed to initialize predictor: {pred_init_error}")
            logger.error(traceback.format_exc())
            return {'error': f'Failed to initialize predictor: {str(pred_init_error)}'}
        
        # Make prediction with error handling
        if not predictor:
            logger.error("Predictor is None after initialization")
            return {'error': 'Predictor initialization failed'}
        
        try:
            logger.info(f"Calling predict_match: {home_team} vs {away_team}")
            prediction = predictor.predict_match(
                home_team, away_team, league_id, match_date
            )
            
            if not prediction:
                logger.error("Predictor returned None")
                return {'error': 'Prediction returned no result'}
            
            logger.info(f"Prediction successful: {prediction.get('home_win_prob', 'N/A')}")
            return prediction
            
        except FileNotFoundError as fnf:
            logger.error(f"Model file not found during prediction: {fnf}")
            logger.error(traceback.format_exc())
            return {'error': f'Model not found for league {league_id}. Please ensure models are uploaded to Cloud Storage.'}
        except Exception as pred_error:
            logger.error(f"Prediction failed: {pred_error}")
            logger.error(traceback.format_exc())
            return {'error': f'Prediction failed: {str(pred_error)}'}
        
    except Exception as e:
        logger.error(f"Unexpected error in predict_match: {e}")
        logger.error(traceback.format_exc())
        return {'error': f'Internal server error: {str(e)}'}


@https_fn.on_call()
def get_upcoming_matches(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get upcoming matches for a league
    
    Request data:
    {
        "league_id": 4986,  # optional
        "limit": 50  # optional, default 50
    }
    """
    try:
        data = req.data
        league_id = data.get('league_id')
        limit = data.get('limit', 50)
        
        # Optimize query: Filter and order efficiently
        matches_ref = db.collection('matches')
        now = datetime.now()
        
        if league_id:
            # Query with league_id first (better for indexing)
            # Note: Firestore requires composite index for: league_id, home_score, date_event
            matches_ref = matches_ref.where('league_id', '==', int(league_id))
            matches_ref = matches_ref.where('home_score', '==', None)
            matches_ref = matches_ref.where('date_event', '>=', now)
            matches_ref = matches_ref.order_by('date_event').limit(limit)
        else:
            # No league filter
            matches_ref = matches_ref.where('home_score', '==', None)
            matches_ref = matches_ref.where('date_event', '>=', now)
            matches_ref = matches_ref.order_by('date_event').limit(limit)
        
        matches = []
        for doc in matches_ref.stream():
            match_data = doc.to_dict()
            match_data['id'] = doc.id
            matches.append(match_data)
        
        return {'matches': matches}
        
    except Exception as e:
        return {'error': str(e)}


@https_fn.on_call()
def get_live_matches(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get live matches
    
    Request data:
    {
        "league_id": 4986  # optional
    }
    """
    try:
        data = req.data
        league_id = data.get('league_id')
        
        enhanced_predictor = get_enhanced_predictor()
        if enhanced_predictor:
            matches = enhanced_predictor.get_live_matches(league_id)
            return {'matches': matches}
        else:
            return {'matches': []}
            
    except Exception as e:
        return {'error': str(e)}


@https_fn.on_call()
def get_leagues(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get available leagues
    """
    try:
        if not LEAGUE_MAPPINGS:
            return {'leagues': [], 'error': 'LEAGUE_MAPPINGS not available'}
        leagues = [
            {'id': league_id, 'name': name}
            for league_id, name in LEAGUE_MAPPINGS.items()
        ]
        return {'leagues': leagues}
        
    except Exception as e:
        return {'error': str(e)}


@https_fn.on_call()
def get_league_metrics(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get league-specific metrics (accuracy, training games, etc.)
    
    Request data:
    {
        "league_id": 4414  # required
    }
    """
    try:
        data = req.data
        league_id = data.get('league_id')
        
        if not league_id:
            return {'error': 'league_id is required'}
        
        league_id_str = str(league_id)
        
        # PRIMARY: Try to load from Firestore (fastest and most reliable)
        try:
            # Try individual league metrics document first (fastest)
            league_metric_ref = db.collection('league_metrics').document(league_id_str)
            league_metric_doc = league_metric_ref.get()
            
            if league_metric_doc.exists:
                league_metric = league_metric_doc.to_dict()
                print(f"✅ Found league metrics in Firestore for league {league_id}")
                return {
                    'league_id': league_id,
                    'accuracy': league_metric.get('accuracy', 0.0),
                    'training_games': league_metric.get('training_games', 0),
                    'ai_rating': league_metric.get('ai_rating', 'N/A'),
                    'trained_at': league_metric.get('trained_at'),
                    'model_type': league_metric.get('model_type', 'unknown')
                }
            else:
                print(f"⚠️ League metrics document not found in Firestore for league {league_id}")
            
            # Fallback: Try full registry document
            registry_ref = db.collection('model_registry').document('optimized')
            registry_doc = registry_ref.get()
            
            if registry_doc.exists:
                registry = registry_doc.to_dict()
                league_data = registry.get('leagues', {}).get(league_id_str)
                
                if league_data:
                    performance = league_data.get('performance', {})
                    accuracy = performance.get('winner_accuracy', 0.0) * 100
                    training_games = league_data.get('training_games', 0)
                    
                    # Calculate AI rating based on accuracy
                    if accuracy >= 80:
                        ai_rating = '9/10'
                    elif accuracy >= 75:
                        ai_rating = '8/10'
                    elif accuracy >= 70:
                        ai_rating = '7/10'
                    elif accuracy >= 65:
                        ai_rating = '6/10'
                    elif accuracy >= 60:
                        ai_rating = '5/10'
                    else:
                        ai_rating = '4/10'
                    
                    print(f"✅ Found league data in Firestore registry for league {league_id}: accuracy={accuracy:.1f}%")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'unknown')
                    }
                else:
                    print(f"⚠️ League {league_id} not found in Firestore registry")
            else:
                print(f"⚠️ Model registry document not found in Firestore")
        except Exception as firestore_error:
            print(f"❌ Error loading from Firestore: {firestore_error}")
            import traceback
            traceback.print_exc()
        
        # FALLBACK 1: Try to load model registry from Cloud Storage
        try:
            bucket = storage.bucket()
            blob = bucket.blob('model_registry_optimized.json')
            
            if blob.exists():
                registry_json = blob.download_as_text()
                registry = json.loads(registry_json)
                
                league_data = registry.get('leagues', {}).get(league_id_str)
                
                if league_data:
                    performance = league_data.get('performance', {})
                    accuracy = performance.get('winner_accuracy', 0.0) * 100
                    training_games = league_data.get('training_games', 0)
                    
                    # Calculate AI rating based on accuracy
                    if accuracy >= 80:
                        ai_rating = '9/10'
                    elif accuracy >= 75:
                        ai_rating = '8/10'
                    elif accuracy >= 70:
                        ai_rating = '7/10'
                    elif accuracy >= 65:
                        ai_rating = '6/10'
                    elif accuracy >= 60:
                        ai_rating = '5/10'
                    else:
                        ai_rating = '4/10'
                    
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'unknown')
                    }
        except Exception as storage_error:
            print(f"Error loading from storage: {storage_error}")
        
        # FALLBACK 2: Try to load from local file if in development
        # Try multiple possible paths
        possible_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.path.dirname(__file__), 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.getcwd(), 'artifacts_optimized', 'model_registry_optimized.json'),
            '/tmp/artifacts_optimized/model_registry_optimized.json',
        ]
        
        for registry_path in possible_paths:
            try:
                if os.path.exists(registry_path):
                    print(f"Found registry at: {registry_path}")
                    with open(registry_path, 'r') as f:
                        registry = json.load(f)
                        league_data = registry.get('leagues', {}).get(league_id_str)
                        
                        if league_data:
                            performance = league_data.get('performance', {})
                            accuracy = performance.get('winner_accuracy', 0.0) * 100
                            training_games = league_data.get('training_games', 0)
                            
                            # Calculate AI rating
                            if accuracy >= 80:
                                ai_rating = '9/10'
                            elif accuracy >= 75:
                                ai_rating = '8/10'
                            elif accuracy >= 70:
                                ai_rating = '7/10'
                            elif accuracy >= 65:
                                ai_rating = '6/10'
                            elif accuracy >= 60:
                                ai_rating = '5/10'
                            else:
                                ai_rating = '4/10'
                            
                            print(f"Loaded metrics for league {league_id}: accuracy={accuracy:.1f}%, games={training_games}")
                            return {
                                'league_id': league_id,
                                'accuracy': round(accuracy, 1),
                                'training_games': training_games,
                                'ai_rating': ai_rating,
                                'trained_at': league_data.get('trained_at'),
                                'model_type': league_data.get('model_type', 'unknown')
                            }
            except Exception as file_error:
                print(f"Error loading from {registry_path}: {file_error}")
                continue
        
        # Default fallback if no data found
        print(f"⚠️ No metrics found for league {league_id} in any source. Returning defaults.")
        print(f"   To fix this, run: python scripts/upload_model_registry_to_firestore.py")
        return {
            'league_id': league_id,
            'accuracy': 0.0,
            'training_games': 0,
            'ai_rating': 'N/A',
            'trained_at': None,
            'model_type': 'unknown'
        }
        
    except Exception as e:
        return {'error': str(e)}
