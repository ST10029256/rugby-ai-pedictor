"""
Firebase Cloud Functions for Rugby AI Predictor
Handles callable functions for predictions, matches, and data
"""

from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
import os
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, TYPE_CHECKING

# Import Firestore Timestamp for type checking
try:
    from google.cloud.firestore_v1 import Timestamp as FirestoreTimestamp  # type: ignore
except ImportError:
    FirestoreTimestamp = None

if TYPE_CHECKING:
    from prediction.hybrid_predictor import MultiLeaguePredictor
    from prediction.enhanced_predictor import EnhancedRugbyPredictor

# For cost control, set max instances
set_global_options(max_instances=10)

# Initialize Firebase Admin (lazy initialization)
_app_initialized = False

def get_firestore_client():
    """Lazy initialization of Firestore client"""
    global _app_initialized
    if not _app_initialized:
        try:
            initialize_app()
        except ValueError:
            # Already initialized, ignore
            pass
        _app_initialized = True
    return firestore.client()

# Import prediction modules (lazy - only when needed)
def _get_league_mappings():
    """Lazy import of league mappings"""
    try:
        from prediction.config import LEAGUE_MAPPINGS
        return LEAGUE_MAPPINGS
    except ImportError:
        return {}

# Initialize predictors (lazy loading - will be imported when needed)
_predictor = None
_enhanced_predictor = None


def get_predictor():
    """Get or create MultiLeaguePredictor instance (lazy import)

    NOTE:
    -----
    The current `MultiLeaguePredictor` implementation still expects a SQLite
    database with an `event` table (used by `build_feature_table`), so using a
    special value like ``db_path='firestore'`` will cause SQLite to create an
    empty file with no tables, leading to:

        pandas.errors.DatabaseError: no such table: event

    To avoid this, we point `db_path` at a real SQLite file that contains the
    `event` table. In Cloud Functions, make sure a copy of `data.sqlite`
    lives alongside this `main.py` (i.e. in the `rugby-ai-predictor/` folder),
    or set the `DB_PATH` environment variable to an absolute path.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    global _predictor
    if _predictor is None:
        try:
            from prediction.hybrid_predictor import MultiLeaguePredictor as MLP

            # Resolve database path – prefer explicit env var, otherwise local file
            db_path = os.getenv("DB_PATH")
            if not db_path:
                # Default to a bundled SQLite file in the same directory as this module
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            logger.info(f"Initializing MultiLeaguePredictor with db_path={db_path!r}")

            # Models will be loaded from Cloud Storage
            storage_bucket = os.getenv("MODEL_STORAGE_BUCKET", "rugby-ai-61fd0.firebasestorage.app")
            logger.info(f"Using storage bucket: {storage_bucket}")
            sportdevs_api_key = os.getenv("SPORTDEVS_API_KEY", "")
            
            # Pass all parameters explicitly to match the signature
            try:
                _predictor = MLP(
                    db_path=db_path,
                    sportdevs_api_key=sportdevs_api_key,
                    artifacts_dir="artifacts",
                    storage_bucket=storage_bucket,
                )
                logger.info("MultiLeaguePredictor initialized successfully")
            except TypeError as e:
                # Fallback: try without storage_bucket (for older versions)
                logger.warning(f"Failed with storage_bucket, trying without: {e}")
                _predictor = MLP(
                    db_path=db_path,
                    sportdevs_api_key=sportdevs_api_key,
                    artifacts_dir="artifacts",
                )
                logger.info("MultiLeaguePredictor initialized without storage_bucket")
        except ImportError as e:
            raise ImportError(f"Could not import MultiLeaguePredictor: {e}")
        except Exception as e:
            raise Exception(f"Could not initialize MultiLeaguePredictor: {e}")
    return _predictor


def get_enhanced_predictor():
    """Get or create EnhancedRugbyPredictor instance (lazy import)"""
    global _enhanced_predictor
    if _enhanced_predictor is None:
        try:
            from prediction.enhanced_predictor import EnhancedRugbyPredictor as ERP
            api_key = os.getenv('HIGHLIGHTLY_API_KEY', '9c27c5f8-9437-4d42-8cc9-5179d3290a5b')
            if api_key:
                # Reuse the same DB path strategy as `get_predictor`
                db_path = os.getenv("DB_PATH")
                if not db_path:
                    db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                _enhanced_predictor = ERP(db_path, api_key)
        except (ImportError, Exception):
            pass  # Enhanced predictor is optional
    return _enhanced_predictor


def get_news_service(predictor=None):
    """Get or create NewsService instance with API clients"""
    import logging
    logger = logging.getLogger(__name__)
    
    from prediction.news_service import NewsService
    from prediction.sportdevs_client import SportDevsClient
    from prediction.sportsdb_client import TheSportsDBClient
    from prediction.config import load_config
    
    db_path = os.getenv("DB_PATH")
    if not db_path:
        # Try multiple possible paths
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same directory as main.py
            os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent directory
            os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root directory
            "/tmp/data.sqlite",  # Firebase Functions temp directory
        ]
        for path in possible_paths:
            if os.path.exists(path):
                db_path = path
                logger.info(f"Found database at: {path}")
                break
        else:
            # Default to same directory as main.py
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            logger.warning(f"Database not found in any expected location, using default: {db_path}")
    
    logger.info(f"NewsService using database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")
    
    # Initialize API clients (optional - will work without them)
    sportdevs_client = None
    sportsdb_client = None
    
    try:
        # SportDevs client (optional)
        sportdevs_key = os.getenv("SPORTDEVS_API_KEY", "")
        if sportdevs_key:
            sportdevs_client = SportDevsClient(api_key=sportdevs_key)
    except Exception as e:
        logger.warning(f"Could not initialize SportDevs client: {e}")
    
    try:
        # TheSportsDB client (for logos)
        config = load_config()
        sportsdb_client = TheSportsDBClient(
            base_url=config.base_url,
            api_key=config.api_key,
            rate_limit_rpm=config.rate_limit_rpm
        )
    except Exception as e:
        logger.warning(f"Could not initialize TheSportsDB client: {e}")
    
    # Initialize social media fetcher (optional)
    social_media_fetcher = None
    try:
        from prediction.social_media_fetcher import SocialMediaFetcher
        social_media_fetcher = SocialMediaFetcher()
    except Exception as e:
        logger.warning(f"Could not initialize SocialMediaFetcher: {e}")
    
    return NewsService(
        db_path=db_path,
        predictor=predictor,
        sportdevs_client=sportdevs_client,
        sportsdb_client=sportsdb_client,
        social_media_fetcher=social_media_fetcher
    )


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
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== predict_match called ===")
        data = req.data or {}
        logger.info(f"Request data: {data}")
        
        home_team = data.get('home_team')
        away_team = data.get('away_team')
        league_id = data.get('league_id')
        match_date = data.get('match_date')
        enhanced = data.get('enhanced', False)
        
        logger.info(f"Parameters: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}, enhanced={enhanced}")
        
        # Type checking and validation
        if not all([home_team, away_team, league_id, match_date]):
            logger.error(f"Missing required fields: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}")
            return {'error': 'Missing required fields'}
        
        # Ensure types are correct
        if not isinstance(home_team, str) or not isinstance(away_team, str) or not isinstance(match_date, str):
            logger.error(f"Invalid field types: home_team type={type(home_team)}, away_team type={type(away_team)}, match_date type={type(match_date)}")
            return {'error': 'Invalid field types'}
        
        # Convert league_id to int (we know it's not None from the check above)
        if league_id is None:
            logger.error("league_id is None")
            return {'error': 'Invalid league_id'}
        
        try:
            league_id_int = int(league_id)
            logger.info(f"Converted league_id to int: {league_id_int}")
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert league_id to int: {e}")
            return {'error': 'Invalid league_id'}
        
        if enhanced:
            logger.info("Using enhanced predictor...")
            try:
                predictor = get_enhanced_predictor()
                if predictor:
                    logger.info("Enhanced predictor obtained, calling get_enhanced_prediction...")
                    prediction = predictor.get_enhanced_prediction(
                        str(home_team), str(away_team), league_id_int, str(match_date)
                    )
                    logger.info(f"Enhanced prediction received: {prediction}")
                else:
                    logger.error("Enhanced predictor not available")
                    return {'error': 'Enhanced predictor not available'}
            except FileNotFoundError as fnf:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Model not found for enhanced predictor: {fnf}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Model not found for league {league_id_int}. Please ensure models are uploaded to Cloud Storage.'}
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Enhanced prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Enhanced prediction failed: {str(e)}'}
        else:
            try:
                logger.info("Using standard predictor...")
                predictor = get_predictor()
                logger.info("Predictor obtained, calling predict_match...")
                prediction = predictor.predict_match(
                    str(home_team), str(away_team), league_id_int, str(match_date)
                )
                logger.info(f"Prediction received: {prediction}")
            except FileNotFoundError as fnf:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Model file not found: {fnf}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Model not found for league {league_id_int}. Please ensure models are uploaded to Cloud Storage. Details: {str(fnf)}'}
            except ImportError as import_err:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Import error: {import_err}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Failed to import required modules: {str(import_err)}'}
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                return {'error': f'Prediction failed: {str(e)}'}
        
        # Save prediction to Firestore if we have event_id or can find it
        try:
            event_id = data.get('event_id') or prediction.get('event_id') or prediction.get('match_id')
            
            # If no event_id provided, try to find it from database
            if not event_id:
                try:
                    import sqlite3
                    db_path = os.getenv("DB_PATH")
                    if not db_path:
                        db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                    
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Try to find event_id by matching teams and date
                        query = """
                        SELECT e.id FROM event e
                        LEFT JOIN team ht ON e.home_team_id = ht.id
                        LEFT JOIN team at ON e.away_team_id = at.id
                        WHERE e.league_id = ? 
                          AND (ht.name = ? OR ht.name LIKE ? OR ? LIKE '%' || ht.name || '%')
                          AND (at.name = ? OR at.name LIKE ? OR ? LIKE '%' || at.name || '%')
                          AND e.date_event LIKE ?
                        ORDER BY e.date_event DESC
                        LIMIT 1
                        """
                        
                        date_pattern = f"{match_date}%"
                        cursor.execute(query, (
                            league_id_int,
                            home_team, f"%{home_team}%", home_team,
                            away_team, f"%{away_team}%", away_team,
                            date_pattern
                        ))
                        result = cursor.fetchone()
                        if result:
                            event_id = result[0]
                        conn.close()
                except Exception as db_error:
                    logger.debug(f"Could not find event_id from database: {db_error}")
            
            # Save to Firestore if we have event_id and prediction data
            if event_id and prediction and not prediction.get('error'):
                try:
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    
                    # Extract predicted winner - always verify against scores for consistency
                    home_score = prediction.get('predicted_home_score', 0)
                    away_score = prediction.get('predicted_away_score', 0)
                    
                    # Determine winner from scores (most reliable source)
                    if home_score > away_score:
                        score_based_winner = home_team
                    elif away_score > home_score:
                        score_based_winner = away_team
                    else:
                        score_based_winner = 'Draw'
                    
                    # Get predicted_winner from prediction, but always verify against scores
                    predicted_winner = prediction.get('winner') or prediction.get('predicted_winner')
                    
                    # Convert 'Home'/'Away' to team names if needed
                    if predicted_winner == 'Home':
                        predicted_winner = home_team
                    elif predicted_winner == 'Away':
                        predicted_winner = away_team
                    
                    # Safety check: if predicted_winner doesn't match scores, use score-based winner
                    if predicted_winner:
                        if (predicted_winner == home_team and home_score <= away_score) or \
                           (predicted_winner == away_team and away_score <= home_score):
                            # Mismatch detected - use score-based winner
                            predicted_winner = score_based_winner
                    else:
                        # No predicted_winner provided, use score-based
                        predicted_winner = score_based_winner
                    
                    # Prepare prediction data to save
                    prediction_data = {
                        'event_id': int(event_id),
                        'league_id': league_id_int,
                        'home_team': home_team,
                        'away_team': away_team,
                        'match_date': match_date,
                        'predicted_winner': predicted_winner,
                        'winner': predicted_winner,  # Also save as 'winner' for compatibility
                        'predicted_home_score': prediction.get('predicted_home_score'),
                        'predicted_away_score': prediction.get('predicted_away_score'),
                        'home_win_prob': prediction.get('home_win_prob'),
                        'confidence': prediction.get('confidence'),
                        'prediction_type': prediction.get('prediction_type', 'AI Only'),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    }
                    
                    # Add any additional prediction fields
                    if 'ai_probability' in prediction:
                        prediction_data['ai_probability'] = prediction.get('ai_probability')
                    if 'hybrid_probability' in prediction:
                        prediction_data['hybrid_probability'] = prediction.get('hybrid_probability')
                    if 'confidence_boost' in prediction:
                        prediction_data['confidence_boost'] = prediction.get('confidence_boost')
                    
                    prediction_ref.set(prediction_data, merge=True)
                    logger.info(f"✅ Saved prediction to Firestore for event_id: {event_id}")
                except Exception as firestore_error:
                    logger.warning(f"Could not save prediction to Firestore: {firestore_error}")
        except Exception as save_error:
            logger.warning(f"Error saving prediction: {save_error}")
        
        logger.info("=== predict_match completed successfully ===")
        return prediction
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== predict_match exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return {'error': str(e), 'traceback': error_trace}


@https_fn.on_request()
def predict_match_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for match prediction with explicit CORS support
    Supports both GET and POST requests
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Handle CORS preflight
    if req.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return https_fn.Response('', status=204, headers=headers)
    
    try:
        logger.info("=== predict_match_http called ===")
        
        # Get data from request
        if req.method == 'POST':
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:  # GET
            data = dict(req.args)
        
        logger.info(f"Request data: {data}")
        
        home_team = data.get('home_team')
        away_team = data.get('away_team')
        league_id = data.get('league_id')
        match_date = data.get('match_date')
        enhanced = data.get('enhanced', False)
        
        logger.info(f"Parameters: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}, enhanced={enhanced}")
        
        # Type checking and validation
        if not all([home_team, away_team, league_id, match_date]):
            logger.error(f"Missing required fields: home_team={home_team}, away_team={away_team}, league_id={league_id}, match_date={match_date}")
            response_data = {'error': 'Missing required fields'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Ensure types are correct
        if not isinstance(home_team, str) or not isinstance(away_team, str) or not isinstance(match_date, str):
            logger.error(f"Invalid field types: home_team type={type(home_team)}, away_team type={type(away_team)}, match_date type={type(match_date)}")
            response_data = {'error': 'Invalid field types'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Convert league_id to int
        try:
            league_id_int = int(league_id) if league_id is not None else 0
            if league_id_int == 0:
                raise ValueError("league_id cannot be 0 or None")
            logger.info(f"Converted league_id to int: {league_id_int}")
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert league_id to int: {e}")
            response_data = {'error': 'Invalid league_id'}
            headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        # Get prediction
        if enhanced:
            logger.info("Using enhanced predictor...")
            predictor = get_enhanced_predictor()
            if predictor:
                logger.info("Enhanced predictor obtained, calling get_enhanced_prediction...")
                prediction = predictor.get_enhanced_prediction(
                    str(home_team), str(away_team), league_id_int, str(match_date)
                )
                logger.info(f"Enhanced prediction received: {prediction}")
            else:
                logger.error("Enhanced predictor not available")
                response_data = {'error': 'Enhanced predictor not available'}
                headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
                return https_fn.Response(json.dumps(response_data), status=503, headers=headers)
        else:
            try:
                logger.info("Using standard predictor...")
                predictor = get_predictor()
                logger.info("Predictor obtained, calling predict_match...")
                prediction = predictor.predict_match(
                    str(home_team), str(away_team), league_id_int, str(match_date)
                )
                logger.info(f"Prediction received: {prediction}")
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Prediction failed: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                response_data = {'error': f'Prediction failed: {str(e)}', 'traceback': error_trace}
                headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
                return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        # Save prediction to Firestore (same logic as predict_match)
        try:
            event_id = data.get('event_id') or prediction.get('event_id') or prediction.get('match_id')
            
            # If no event_id provided, try to find it from database
            if not event_id:
                try:
                    import sqlite3
                    db_path = os.getenv("DB_PATH")
                    if not db_path:
                        db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                    
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Try to find event_id by matching teams and date
                        query = """
                        SELECT e.id FROM event e
                        LEFT JOIN team ht ON e.home_team_id = ht.id
                        LEFT JOIN team at ON e.away_team_id = at.id
                        WHERE e.league_id = ? 
                          AND (ht.name = ? OR ht.name LIKE ? OR ? LIKE '%' || ht.name || '%')
                          AND (at.name = ? OR at.name LIKE ? OR ? LIKE '%' || at.name || '%')
                          AND e.date_event LIKE ?
                        ORDER BY e.date_event DESC
                        LIMIT 1
                        """
                        
                        date_pattern = f"{match_date}%"
                        cursor.execute(query, (
                            league_id_int,
                            home_team, f"%{home_team}%", home_team,
                            away_team, f"%{away_team}%", away_team,
                            date_pattern
                        ))
                        result = cursor.fetchone()
                        if result:
                            event_id = result[0]
                        conn.close()
                except Exception as db_error:
                    logger.debug(f"Could not find event_id from database: {db_error}")
            
            # Save to Firestore if we have event_id and prediction data
            if event_id and prediction and not prediction.get('error'):
                try:
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    
                    # Extract predicted winner - always verify against scores for consistency
                    home_score = prediction.get('predicted_home_score', 0)
                    away_score = prediction.get('predicted_away_score', 0)
                    
                    # Determine winner from scores (most reliable source)
                    if home_score > away_score:
                        score_based_winner = home_team
                    elif away_score > home_score:
                        score_based_winner = away_team
                    else:
                        score_based_winner = 'Draw'
                    
                    # Get predicted_winner from prediction, but always verify against scores
                    predicted_winner = prediction.get('winner') or prediction.get('predicted_winner')
                    
                    # Convert 'Home'/'Away' to team names if needed
                    if predicted_winner == 'Home':
                        predicted_winner = home_team
                    elif predicted_winner == 'Away':
                        predicted_winner = away_team
                    
                    # Safety check: if predicted_winner doesn't match scores, use score-based winner
                    if predicted_winner:
                        if (predicted_winner == home_team and home_score <= away_score) or \
                           (predicted_winner == away_team and away_score <= home_score):
                            # Mismatch detected - use score-based winner
                            predicted_winner = score_based_winner
                    else:
                        # No predicted_winner provided, use score-based
                        predicted_winner = score_based_winner
                    
                    # Prepare prediction data to save
                    prediction_data = {
                        'event_id': int(event_id),
                        'league_id': league_id_int,
                        'home_team': home_team,
                        'away_team': away_team,
                        'match_date': match_date,
                        'predicted_winner': predicted_winner,
                        'winner': predicted_winner,  # Also save as 'winner' for compatibility
                        'predicted_home_score': prediction.get('predicted_home_score'),
                        'predicted_away_score': prediction.get('predicted_away_score'),
                        'home_win_prob': prediction.get('home_win_prob'),
                        'confidence': prediction.get('confidence'),
                        'prediction_type': prediction.get('prediction_type', 'AI Only'),
                        'created_at': firestore.SERVER_TIMESTAMP,
                    }
                    
                    # Add any additional prediction fields
                    if 'ai_probability' in prediction:
                        prediction_data['ai_probability'] = prediction.get('ai_probability')
                    if 'hybrid_probability' in prediction:
                        prediction_data['hybrid_probability'] = prediction.get('hybrid_probability')
                    if 'confidence_boost' in prediction:
                        prediction_data['confidence_boost'] = prediction.get('confidence_boost')
                    
                    prediction_ref.set(prediction_data, merge=True)
                    logger.info(f"✅ Saved prediction to Firestore for event_id: {event_id}")
                except Exception as firestore_error:
                    logger.warning(f"Could not save prediction to Firestore: {firestore_error}")
        except Exception as save_error:
            logger.warning(f"Error saving prediction: {save_error}")
        
        logger.info("=== predict_match_http completed successfully ===")
        headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
        return https_fn.Response(json.dumps(prediction), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== predict_match_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {'error': str(e), 'traceback': error_trace}
        headers = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)


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
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== get_upcoming_matches called ===")
        data = req.data or {}
        league_id = data.get('league_id')
        limit = data.get('limit', 50)
        
        logger.info(f"Request data: {data}")
        logger.info(f"League ID: {league_id}, Limit: {limit}")
        
        # Query Firestore for upcoming matches
        try:
            logger.info("Getting Firestore client...")
            db = get_firestore_client()
            matches_ref = db.collection('matches')
            
            logger.info(f"Querying matches collection for league_id={league_id}")
            # Optimized query - filter by league_id and limit early
            # We'll do date filtering in Python to avoid index requirements
            if league_id:
                matches_ref = matches_ref.where('league_id', '==', int(league_id))
                logger.info(f"Applied league_id filter: {int(league_id)}")
            
            # Reduce initial fetch - only get what we need (limit early for better performance)
            # Most leagues won't have more than 100 upcoming matches
            matches_ref = matches_ref.limit(200)  # Reduced from 500 to 200 for faster queries
            logger.info("Starting to stream matches from Firestore...")
            
            matches = []
            # Use UTC-aware datetime for comparison with Firestore Timestamps
            from datetime import timezone
            now = datetime.now(timezone.utc)
            total_checked = 0
            with_scores = 0
            past_dates = 0
            no_date = 0
            date_parse_failures = 0
            sample_dates = []  # Store first few date formats we see
            
            # Collect all team IDs first for batch lookup
            team_ids_to_lookup = set()
            matches_without_teams = []
            
            for doc in matches_ref.stream():
                total_checked += 1
                match_data = doc.to_dict()
                
                if total_checked % 50 == 0:
                    logger.debug(f"Processed {total_checked} matches so far...")
                
                # Double-check league_id matches (safety check)
                match_league_id = match_data.get('league_id')
                if league_id and match_league_id != int(league_id):
                    logger.debug(f"Skipping match {doc.id}: league_id mismatch ({match_league_id} != {int(league_id)})")
                    continue  # Skip matches from other leagues
                
                # Only include matches without scores (upcoming matches)
                if match_data.get('home_score') is not None or match_data.get('away_score') is not None:
                    with_scores += 1
                    logger.debug(f"Skipping match {doc.id}: has scores (home={match_data.get('home_score')}, away={match_data.get('away_score')})")
                    continue
                
                # Check if date is in the future (or today for date-only values)
                date_event = match_data.get('date_event')
                if date_event:
                    # Handle both datetime and string dates
                    match_date = None
                    is_date_only = False
                    try:
                        # Check for Firestore Timestamp first (most common)
                        # Firestore Timestamp has both timestamp() and to_datetime() methods
                        if hasattr(date_event, 'timestamp') and callable(getattr(date_event, 'to_datetime', None)):
                            # Firestore Timestamp object - convert to datetime
                            try:
                                match_date = date_event.to_datetime()
                                # Ensure timezone-aware (Firestore returns UTC)
                                if match_date.tzinfo is None:
                                    match_date = match_date.replace(tzinfo=timezone.utc)
                            except AttributeError:
                                # Fallback: use timestamp() method
                                match_date = datetime.fromtimestamp(date_event.timestamp(), tz=timezone.utc)
                        elif isinstance(date_event, datetime):
                            match_date = date_event
                            # Ensure timezone-aware
                            if match_date.tzinfo is None:
                                match_date = match_date.replace(tzinfo=timezone.utc)
                        elif isinstance(date_event, str):
                            # Try parsing ISO format or common date formats
                            if 'T' in date_event:
                                match_date = datetime.fromisoformat(date_event.replace('Z', '+00:00'))
                            else:
                                # Date-only string (YYYY-MM-DD) - treat as "all-day" for upcoming filtering
                                is_date_only = True
                                match_date = datetime.strptime(date_event, '%Y-%m-%d')
                                # Make timezone-aware (assume UTC)
                                match_date = match_date.replace(tzinfo=timezone.utc)
                        else:
                            # Try to convert unknown type
                            raise ValueError(f"Unknown date type: {type(date_event)}")
                    except Exception as parse_error:
                        # If parsing fails, skip this match
                        date_parse_failures += 1
                        # Store sample of failed dates for debugging
                        if len(sample_dates) < 3:
                            sample_dates.append({
                                'date_event': str(date_event),
                                'type': type(date_event).__name__,
                                'error': str(parse_error),
                                'has_timestamp_attr': hasattr(date_event, 'timestamp'),
                                'has_to_datetime': hasattr(date_event, 'to_datetime') if hasattr(date_event, 'timestamp') else False
                            })
                        continue
                    
                    # Only include upcoming matches:
                    # - If we have a full datetime, require it to be in the future (UTC).
                    # - If we only have a date (YYYY-MM-DD), include today+future so it doesn't disappear right after 00:00 UTC.
                    if match_date:
                        should_include = False
                        if is_date_only:
                            should_include = match_date.date() >= now.date()
                        else:
                            should_include = match_date > now

                        if should_include:
                            match_data['id'] = doc.id
                            # Convert date to string for JSON serialization
                            if hasattr(date_event, 'timestamp'):
                                match_data['date_event'] = match_date.isoformat()
                            elif isinstance(date_event, datetime):
                                match_data['date_event'] = match_date.isoformat()
                            elif isinstance(date_event, str) and is_date_only:
                                match_data['date_event'] = match_date.date().isoformat()
                            
                            # Collect team IDs for batch lookup
                            home_team_id = match_data.get('home_team_id')
                            away_team_id = match_data.get('away_team_id')
                            
                            logger.debug(f"Match {doc.id}: future match on {match_date.isoformat()}, home_id={home_team_id}, away_id={away_team_id}")
                            
                            if home_team_id:
                                team_ids_to_lookup.add(home_team_id)
                            if away_team_id:
                                team_ids_to_lookup.add(away_team_id)
                            
                            matches_without_teams.append(match_data)
                        else:
                            past_dates += 1
                            days_ago = (now - match_date).days
                            logger.debug(f"Skipping match {doc.id}: past date ({days_ago} days ago, {match_date.isoformat()})")
                    else:
                        no_date += 1
                        # Include matches with no date (might be TBD)
                        match_data['id'] = doc.id
                        
                        # Collect team IDs for batch lookup
                        home_team_id = match_data.get('home_team_id')
                        away_team_id = match_data.get('away_team_id')
                        
                        if home_team_id:
                            team_ids_to_lookup.add(home_team_id)
                        if away_team_id:
                            team_ids_to_lookup.add(away_team_id)
                        
                        matches_without_teams.append(match_data)
            
            # Batch lookup team names (optimized - fetch all teams at once)
            team_names = {}
            if team_ids_to_lookup:
                logger.info(f"Looking up {len(team_ids_to_lookup)} unique team IDs...")
                try:
                    # Fetch all teams in batches (Firestore has a limit of 10 items per 'in' query)
                    teams_ref = db.collection('teams')
                    team_ids_list = list(team_ids_to_lookup)
                    
                    logger.info(f"Processing {len(team_ids_list)} team IDs in batches of 10...")
                    # Process in batches of 10 (Firestore 'in' query limit)
                    for i in range(0, len(team_ids_list), 10):
                        batch_ids = team_ids_list[i:i+10]
                        logger.debug(f"Fetching team batch {i//10 + 1}: {batch_ids}")
                        team_docs = teams_ref.where('id', 'in', batch_ids).stream()
                        batch_count = 0
                        for team_doc in team_docs:
                            team_data = team_doc.to_dict()
                            team_id = team_data.get('id')
                            if team_id:
                                team_names[team_id] = team_data.get('name', f'Team {team_id}')
                                batch_count += 1
                        logger.debug(f"Found {batch_count} teams in batch {i//10 + 1}")
                    
                    logger.info(f"Successfully looked up {len(team_names)} team names")
                except Exception as e:
                    logger.warning(f"Batch lookup failed: {e}, falling back to individual queries")
                    # If batch lookup fails, fallback to individual queries
                    teams_ref = db.collection('teams')
                    for team_id in team_ids_to_lookup:
                        try:
                            team_docs = teams_ref.where('id', '==', team_id).limit(1).stream()
                            for team_doc in team_docs:
                                team_data = team_doc.to_dict()
                                team_names[team_id] = team_data.get('name', f'Team {team_id}')
                                break
                        except Exception as e2:
                            logger.warning(f"Failed to lookup team {team_id}: {e2}")
                            pass
            else:
                logger.warning("No team IDs to lookup!")
            
            # Add team names to matches and filter out women's teams
            women_indicators = [' w rugby', ' women', ' womens', ' w ', ' women\'s', ' w\'s']
            logger.info(f"Processing {len(matches_without_teams)} matches, filtering women's teams...")
            
            women_filtered = 0
            for match_data in matches_without_teams:
                home_team_id = match_data.get('home_team_id')
                away_team_id = match_data.get('away_team_id')
                
                home_team_name = team_names.get(home_team_id, f'Team {home_team_id}' if home_team_id else 'Unknown')
                away_team_name = team_names.get(away_team_id, f'Team {away_team_id}' if away_team_id else 'Unknown')
                
                # Filter out women's matches
                home_lower = home_team_name.lower()
                away_lower = away_team_name.lower()
                is_women_home = any(indicator in home_lower for indicator in women_indicators)
                is_women_away = any(indicator in away_lower for indicator in women_indicators)
                
                if is_women_home or is_women_away:
                    women_filtered += 1
                    logger.debug(f"Filtered out women's match: {home_team_name} vs {away_team_name}")
                    continue  # Skip women's matches
                
                match_data['home_team'] = home_team_name
                match_data['away_team'] = away_team_name
                
                matches.append(match_data)
            
            logger.info(f"Filtered out {women_filtered} women's matches, {len(matches)} matches remaining")
            
            # Sort by date and limit (in Python, no index needed)
            def get_sort_key(match):
                date_val = match.get('date_event', '')
                if isinstance(date_val, str):
                    try:
                        return datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                    except:
                        return datetime.min
                elif hasattr(date_val, 'timestamp'):
                    return date_val.to_datetime()
                elif isinstance(date_val, datetime):
                    return date_val
                return datetime.min
            
            logger.info(f"Sorting {len(matches)} matches by date...")
            matches.sort(key=get_sort_key)
            matches = matches[:limit]
            logger.info(f"Returning {len(matches)} matches (limited to {limit})")
            
            # Include debug info
            debug_info = {
                'total_checked': total_checked,
                'with_scores': with_scores,
                'past_dates': past_dates,
                'no_date': no_date,
                'date_parse_failures': date_parse_failures,
                'matches_found': len(matches),
                'team_lookup_count': len(team_ids_to_lookup),
                'team_names_found': len(team_names),
                'women_filtered': women_filtered,
                'sample_dates': sample_dates[:3]  # First 3 samples
            }
            
            logger.info(f"=== get_upcoming_matches completed ===")
            logger.info(f"Debug info: {debug_info}")
            
            return {
                'matches': matches,
                'debug': debug_info
            }
        except Exception as firestore_error:
            # If Firestore query fails, return empty list with error details
            import traceback
            error_details = traceback.format_exc()
            return {'matches': [], 'warning': f'Firestore query failed: {str(firestore_error)}', 'error_details': error_details}
        
    except Exception as e:
        return {'error': str(e), 'matches': []}


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


@https_fn.on_request()
def get_live_matches_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for live matches with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    try:
        logger.info("=== get_live_matches_http called ===")

        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)

        league_id = data.get("league_id")
        logger.info(f"Request data: {data}, league_id={league_id}")

        enhanced_predictor = get_enhanced_predictor()
        if enhanced_predictor:
            matches = enhanced_predictor.get_live_matches(league_id)
            response_data = {"matches": matches}
            status = 200
        else:
            logger.warning("Enhanced predictor not available, returning empty matches list")
            response_data = {"matches": []}
            status = 200

        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_live_matches_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=status, headers=headers)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== get_live_matches_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {"error": str(e), "traceback": error_trace}
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)

@https_fn.on_call()
def get_leagues(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get available leagues with match counts
    """
    import sqlite3
    try:
        league_mappings = _get_league_mappings()
        
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")
        
        # Get upcoming match counts for each league
        upcoming_counts = {}
        recent_counts = {}
        
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Count upcoming matches (next 7 days)
            cursor.execute("""
                SELECT e.league_id, COUNT(*) as match_count
                FROM event e
                WHERE e.date_event >= date('now')
                AND e.date_event <= date('now', '+7 days')
                AND e.home_team_id IS NOT NULL
                AND e.away_team_id IS NOT NULL
                GROUP BY e.league_id
            """)
            
            for row in cursor.fetchall():
                league_id, count = row
                upcoming_counts[league_id] = count
            
            # Count recent completed matches (last 7 days)
            cursor.execute("""
                SELECT e.league_id, COUNT(*) as match_count
                FROM event e
                WHERE e.date_event >= date('now', '-7 days')
                AND e.date_event < date('now')
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.home_team_id IS NOT NULL
                AND e.away_team_id IS NOT NULL
                GROUP BY e.league_id
            """)
            
            for row in cursor.fetchall():
                league_id, count = row
                recent_counts[league_id] = count
            
            conn.close()
        
        leagues = []
        for league_id, name in league_mappings.items():
            upcoming = upcoming_counts.get(league_id, 0)
            recent = recent_counts.get(league_id, 0)
            has_news = upcoming > 0 or recent > 0
            
            leagues.append({
                'id': league_id,
                'name': name,
                'upcoming_matches': upcoming,
                'recent_matches': recent,
                'has_news': has_news,
                'total_news': upcoming + recent
            })
        
        return {'leagues': leagues}
        
    except Exception as e:
        print(f"Error in get_leagues: {e}")
        # Fallback to basic league list without counts
        try:
            league_mappings = _get_league_mappings()
            leagues = [
                {'id': league_id, 'name': name, 'upcoming_matches': 0, 'recent_matches': 0, 'has_news': False, 'total_news': 0}
                for league_id, name in league_mappings.items()
            ]
            return {'leagues': leagues}
        except:
            return {'error': str(e)}


def _calculate_last_10_games_accuracy(league_id: int) -> int:
    """
    Helper function to calculate the accuracy of the last 10 completed games for a league.
    Returns the number of correct predictions out of 10.
    This is NOT a Cloud Function - it's a helper function called internally.
    """
    import sqlite3
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
        
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at {db_path}, cannot calculate last 10 games accuracy")
            return 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get last 10 completed games with scores for this league
        query = """
        SELECT e.id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, 
               ht.name as home_team_name, at.name as away_team_name,
               e.date_event, e.timestamp
        FROM event e
        LEFT JOIN team ht ON e.home_team_id = ht.id
        LEFT JOIN team at ON e.away_team_id = at.id
        WHERE e.league_id = ? 
          AND e.home_score IS NOT NULL 
          AND e.away_score IS NOT NULL
          AND e.status != 'Postponed'
        ORDER BY e.date_event DESC, e.timestamp DESC
        LIMIT 10
        """
        
        cursor.execute(query, (league_id,))
        games = cursor.fetchall()
        conn.close()
        
        if len(games) < 10:
            logger.info(f"Only {len(games)} completed games found for league {league_id}")
            # Return 0 if we don't have 10 games yet
            return 0
        
        # Get predictor to make predictions for these games
        try:
            predictor = get_predictor()
            correct_predictions = 0
            
            for game in games:
                event_id, home_team_id, away_team_id, home_score, away_score, \
                home_team_name, away_team_name, date_event, timestamp = game
                
                # Determine actual winner
                if home_score > away_score:
                    actual_winner = 'Home'
                elif away_score > home_score:
                    actual_winner = 'Away'
                else:
                    actual_winner = 'Draw'
                
                # Make prediction (we need to predict as if the game hasn't happened yet)
                # For accuracy, we'd need to have stored predictions made before the game
                # For now, we'll use the model to predict based on pre-game data
                # This is a simplified approach - ideally predictions should be stored
                try:
                    # Try to get stored prediction from Firestore if available
                    db = get_firestore_client()
                    prediction_ref = db.collection('predictions').document(str(event_id))
                    prediction_doc = prediction_ref.get()
                    
                    if prediction_doc.exists:
                        pred_data = prediction_doc.to_dict()
                        predicted_winner = pred_data.get('predicted_winner') or pred_data.get('winner', '')
                        
                        # Normalize winner format
                        if predicted_winner == home_team_name or predicted_winner == 'Home':
                            predicted_winner = 'Home'
                        elif predicted_winner == away_team_name or predicted_winner == 'Away':
                            predicted_winner = 'Away'
                        elif predicted_winner == 'Draw':
                            predicted_winner = 'Draw'
                        else:
                            # Try to predict using the model
                            continue
                        
                        if predicted_winner == actual_winner:
                            correct_predictions += 1
                    else:
                        # No stored prediction, skip this game
                        continue
                except Exception as pred_error:
                    logger.debug(f"Error getting prediction for game {event_id}: {pred_error}")
                    continue
            
            logger.info(f"Last 10 games accuracy for league {league_id}: {correct_predictions}/10")
            return correct_predictions
            
        except Exception as pred_error:
            logger.warning(f"Error calculating predictions: {pred_error}")
            return 0
            
    except Exception as e:
        logger.warning(f"Error calculating last 10 games accuracy: {e}")
        return 0


@https_fn.on_call(timeout_sec=300, memory=512)
def get_league_metrics(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Callable Cloud Function to get league-specific metrics (accuracy, training games, etc.)
    
    Request data:
    {
        "league_id": 4414  # required
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== get_league_metrics called (XGBoost v2) ===")
        data = req.data or {}
        league_id = data.get('league_id')
        
        if not league_id:
            logger.error("league_id is required")
            return {'error': 'league_id is required'}
        
        league_id_str = str(league_id)
        logger.info(f"Fetching metrics for league_id: {league_id_str}")
        
        # Calculate last 10 games accuracy
        last_10_accuracy = _calculate_last_10_games_accuracy(league_id)
        
        # PRIMARY: Try to load from Firestore (fastest and most reliable)
        try:
            db = get_firestore_client()
            
            # Try individual league metrics document first (fastest)
            logger.info(f"Trying league_metrics/{league_id_str}...")
            # Force fresh read (no cache) by using get() with transaction-like behavior
            league_metric_ref = db.collection('league_metrics').document(league_id_str)
            league_metric_doc = league_metric_ref.get()
            logger.info(f"Document read - exists: {league_metric_doc.exists}, path: {league_metric_ref.path}")
            
            if league_metric_doc.exists:
                league_metric = league_metric_doc.to_dict()
                model_type = league_metric.get('model_type', 'unknown')
                accuracy = league_metric.get('accuracy', 0.0)
                logger.info(f"Found league metrics in Firestore: model_type={model_type}, accuracy={accuracy}%, training_games={league_metric.get('training_games', 0)}")
                logger.info(f"Full league_metric data: {league_metric}")
                
                # Force XGBoost if we detect old stacking data (safety check)
                if model_type == 'stacking' and 'last_updated' in league_metric:
                    last_updated = league_metric.get('last_updated', '')
                    if '2025-12-09' in last_updated:  # Old optimized timestamp
                        logger.warning(f"WARNING: Detected old stacking data, trying to reload from XGBoost registry...")
                        # Fall through to try XGBoost registry
                    else:
                        # Get margin from performance data if available in league_metrics
                        performance = league_metric.get('performance', {})
                        overall_mae = performance.get('overall_mae', 0.0) if performance else 0.0
                        
                        # If no performance data in league_metrics, try to get from model_registry
                        if overall_mae == 0.0:
                            try:
                                registry_ref = db.collection('model_registry').document('xgboost')
                                registry_doc = registry_ref.get()
                                if registry_doc.exists:
                                    registry = registry_doc.to_dict()
                                    league_data = registry.get('leagues', {}).get(league_id_str)
                                    if league_data:
                                        perf = league_data.get('performance', {})
                                        overall_mae = perf.get('overall_mae', 0.0)
                            except Exception as e:
                                logger.debug(f"Could not get margin from model_registry: {e}")
                        
                        return {
                            'league_id': league_id,
                            'accuracy': accuracy,
                            'training_games': league_metric.get('training_games', 0),
                            'ai_rating': league_metric.get('ai_rating', 'N/A'),
                            'overall_mae': round(overall_mae, 2) if overall_mae > 0 else 0.0,
                            'trained_at': league_metric.get('trained_at'),
                            'model_type': model_type
                        }
                else:
                    # Get margin from performance data if available in league_metrics
                    performance = league_metric.get('performance', {})
                    overall_mae = performance.get('overall_mae', 0.0) if performance else 0.0
                    
                    # If no performance data in league_metrics, try to get from model_registry
                    if overall_mae == 0.0:
                        try:
                            registry_ref = db.collection('model_registry').document('xgboost')
                            registry_doc = registry_ref.get()
                            if registry_doc.exists:
                                registry = registry_doc.to_dict()
                                league_data = registry.get('leagues', {}).get(league_id_str)
                                if league_data:
                                    perf = league_data.get('performance', {})
                                    overall_mae = perf.get('overall_mae', 0.0)
                        except Exception as e:
                            logger.debug(f"Could not get margin from model_registry: {e}")
                    
                    return {
                        'league_id': league_id,
                        'accuracy': accuracy,
                        'training_games': league_metric.get('training_games', 0),
                        'ai_rating': league_metric.get('ai_rating', 'N/A'),
                        'overall_mae': round(overall_mae, 2) if overall_mae > 0 else 0.0,
                        'trained_at': league_metric.get('trained_at'),
                        'model_type': model_type
                    }
            
            # Fallback: Try XGBoost registry document first (preferred)
            logger.info("Trying model_registry/xgboost...")
            registry_ref = db.collection('model_registry').document('xgboost')
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
                    
                    # Get margin from performance data
                    overall_mae = performance.get('overall_mae', 0.0)
                    
                    logger.info(f"Found XGBoost league data in registry: accuracy={accuracy}, games={training_games}, margin={overall_mae}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'overall_mae': round(overall_mae, 2),
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'xgboost')
                    }
            
            # Fallback: Try optimized registry document (backward compatibility)
            logger.info("Trying model_registry/optimized...")
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
                    
                    # Get margin from performance data
                    overall_mae = performance.get('overall_mae', 0.0)
                    
                    logger.info(f"Found optimized league data in registry: accuracy={accuracy}, games={training_games}, margin={overall_mae}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'overall_mae': round(overall_mae, 2),
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'stacking')
                    }
        except Exception as firestore_error:
            logger.warning(f"Error loading from Firestore: {firestore_error}")
        
        # FALLBACK: Try to load from Cloud Storage (XGBoost first, then optimized)
        try:
            from firebase_admin import storage
            bucket = storage.bucket()
            
            # Try XGBoost registry first
            blob = bucket.blob('model_registry.json')
            if not blob.exists():
                blob = bucket.blob('artifacts/model_registry.json')
            
            if blob.exists():
                logger.info("Trying Cloud Storage (XGBoost registry)...")
                registry_json = blob.download_as_text()
                registry = json.loads(registry_json)
                model_type_preference = 'xgboost'
            else:
                # Fallback to optimized registry
                blob = bucket.blob('model_registry_optimized.json')
                if not blob.exists():
                    blob = bucket.blob('artifacts_optimized/model_registry_optimized.json')
                if blob.exists():
                    logger.info("Trying Cloud Storage (Optimized registry)...")
                    registry_json = blob.download_as_text()
                    registry = json.loads(registry_json)
                    model_type_preference = 'stacking'
                else:
                    raise FileNotFoundError("No registry found in Cloud Storage")
            
            if blob.exists():
                
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
                    
                    # Get margin from performance data
                    overall_mae = performance.get('overall_mae', 0.0)
                    
                    logger.info(f"Found league data in Cloud Storage: accuracy={accuracy}, games={training_games}, margin={overall_mae}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'overall_mae': round(overall_mae, 2),
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', model_type_preference if 'model_type_preference' in locals() else 'unknown')
                    }
        except Exception as storage_error:
            logger.warning(f"Error loading from storage: {storage_error}")
        
        # FALLBACK: Try to load from local file (for development or if included in deployment)
        # Try XGBoost registry first, then optimized
        possible_paths = [
            os.path.join(os.path.dirname(__file__), 'artifacts', 'model_registry.json'),
            os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'model_registry.json'),
            os.path.join(os.getcwd(), 'artifacts', 'model_registry.json'),
            '/tmp/artifacts/model_registry.json',
            os.path.join(os.path.dirname(__file__), 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.path.dirname(__file__), '..', 'artifacts_optimized', 'model_registry_optimized.json'),
            os.path.join(os.getcwd(), 'artifacts_optimized', 'model_registry_optimized.json'),
            '/tmp/artifacts_optimized/model_registry_optimized.json',
        ]
        
        for registry_path in possible_paths:
            try:
                if os.path.exists(registry_path):
                    logger.info(f"Trying local file: {registry_path}")
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
                            
                            # Determine model type from path
                            model_type = league_data.get('model_type', 'unknown')
                            if 'artifacts_optimized' in registry_path or 'optimized' in registry_path.lower():
                                model_type = league_data.get('model_type', 'stacking')
                            elif 'artifacts' in registry_path and 'optimized' not in registry_path:
                                model_type = league_data.get('model_type', 'xgboost')
                            
                            # Get margin from performance data
                            overall_mae = performance.get('overall_mae', 0.0)
                            
                            logger.info(f"✅ Found league data in local file: accuracy={accuracy:.1f}%, games={training_games}, margin={overall_mae:.2f}, type={model_type}")
                            return {
                                'league_id': league_id,
                                'accuracy': round(accuracy, 1),
                                'training_games': training_games,
                                'ai_rating': ai_rating,
                                'overall_mae': round(overall_mae, 2),
                                'trained_at': league_data.get('trained_at'),
                                'model_type': model_type
                            }
            except Exception as file_error:
                logger.debug(f"Error loading from {registry_path}: {file_error}")
                continue
        
        # Default fallback if no data found
        logger.warning(f"⚠️ No metrics found for league_id {league_id_str} in any source. Returning defaults.")
        logger.warning(f"   To fix this, run: python scripts/upload_model_registry_to_firestore.py")
        return {
            'league_id': league_id,
            'accuracy': 0.0,
            'training_games': 0,
            'ai_rating': 'N/A',
            'overall_mae': 0.0,
            'trained_at': None,
            'model_type': 'unknown'
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_league_metrics: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return {'error': str(e)}


@https_fn.on_call()
def verify_license_key(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Verify a license key and return authentication status.
    
    Request: { 'license_key': 'XXXX-XXXX-XXXX-XXXX' }
    Response: { 'valid': bool, 'expires_at': timestamp, 'subscription_type': str }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = get_firestore_client()
        license_key = req.data.get('license_key', '').strip().upper()
        
        # Normalize: remove dashes and spaces for comparison
        # Frontend sends keys without dashes, but Firestore stores with dashes
        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        logger.info(f"Verifying license key: {license_key[:8]}... (normalized: {license_key_normalized[:8]}...)")
        
        if not license_key_normalized:
            return {'valid': False, 'error': 'License key is required'}
        
        # Query Firestore - need to check both formats (with and without dashes)
        subscriptions_ref = db.collection('subscriptions')
        
        # Try exact match first (in case key is stored without dashes)
        query = subscriptions_ref.where('license_key', '==', license_key).limit(1)
        docs = list(query.stream())
        
        # If not found, try with dashes formatted (XXXX-XXXX-XXXX-XXXX)
        if not docs and len(license_key_normalized) == 16:
            formatted_key = f"{license_key_normalized[0:4]}-{license_key_normalized[4:8]}-{license_key_normalized[8:12]}-{license_key_normalized[12:16]}"
            query = subscriptions_ref.where('license_key', '==', formatted_key).limit(1)
            docs = list(query.stream())
            if docs:
                logger.info(f"Found key with formatted dashes: {formatted_key}")
        
        # If still not found, try normalized (no dashes)
        if not docs:
            query = subscriptions_ref.where('license_key', '==', license_key_normalized).limit(1)
            docs = list(query.stream())
            if docs:
                logger.info(f"Found key without dashes: {license_key_normalized}")
        
        logger.info(f"Found {len(docs)} documents matching license key")
        
        if not docs:
            # Try to list all keys for debugging (remove in production)
            all_docs = list(subscriptions_ref.limit(5).stream())
            logger.warning(f"Invalid license key attempted: {license_key} (normalized: {license_key_normalized})")
            sample_keys = [doc.to_dict().get('license_key', 'N/A')[:12] + '...' for doc in all_docs]
            logger.info(f"Sample keys in database: {sample_keys}")
            return {'valid': False, 'error': 'Invalid license key'}
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        
        # Check if subscription is active
        now = datetime.utcnow()
        expires_at = subscription.get('expires_at')
        
        if expires_at:
            # Handle Firestore Timestamp
            if hasattr(expires_at, 'timestamp'):
                expires_datetime = datetime.utcfromtimestamp(expires_at.timestamp())
            elif isinstance(expires_at, datetime):
                expires_datetime = expires_at
            else:
                expires_datetime = datetime.utcnow() + timedelta(days=30)  # Default fallback
            
            if expires_datetime < now:
                logger.warning(f"Expired license key: {license_key[:8]}...")
                return {'valid': False, 'error': 'License key has expired'}
        
        # Check if already used (optional - for single-use keys)
        if subscription.get('used', False) and not subscription.get('reusable', True):
            logger.warning(f"Already used license key: {license_key[:8]}...")
            return {'valid': False, 'error': 'License key has already been used'}
        
        # Mark as used if not reusable
        if not subscription.get('reusable', True):
            subscriptions_ref.document(subscription_id).update({'used': True, 'used_at': firestore.SERVER_TIMESTAMP})
        
        # Update last_used timestamp
        subscriptions_ref.document(subscription_id).update({'last_used': firestore.SERVER_TIMESTAMP})
        
        logger.info(f"Valid license key verified: {license_key[:8]}...")
        
        return {
            'valid': True,
            'expires_at': expires_at.timestamp() if hasattr(expires_at, 'timestamp') else None,
            'subscription_type': subscription.get('subscription_type', 'premium'),
            'email': subscription.get('email', ''),
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error verifying license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'valid': False, 'error': 'Server error verifying license key'}


@https_fn.on_request()
def verify_license_key_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for license key verification with explicit CORS support.
    This is used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)
        
        license_key = data.get('license_key', '').strip().upper()
        
        # Normalize: remove dashes and spaces for comparison
        # Frontend sends keys without dashes, but Firestore stores with dashes
        license_key_normalized = license_key.replace('-', '').replace(' ', '')
        
        if not license_key_normalized:
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'License key is required'}),
                status=400,
                headers=headers
            )
        
        # Use the same verification logic as the callable function
        db = get_firestore_client()
        subscriptions_ref = db.collection('subscriptions')
        
        # Try exact match first (in case key is stored without dashes)
        query = subscriptions_ref.where('license_key', '==', license_key).limit(1)
        docs = list(query.stream())
        
        # If not found, try with dashes formatted (XXXX-XXXX-XXXX-XXXX)
        if not docs and len(license_key_normalized) == 16:
            formatted_key = f"{license_key_normalized[0:4]}-{license_key_normalized[4:8]}-{license_key_normalized[8:12]}-{license_key_normalized[12:16]}"
            query = subscriptions_ref.where('license_key', '==', formatted_key).limit(1)
            docs = list(query.stream())
        
        # If still not found, try normalized (no dashes)
        if not docs:
            query = subscriptions_ref.where('license_key', '==', license_key_normalized).limit(1)
            docs = list(query.stream())
        
        if not docs:
            logger.warning(f"Invalid license key attempted: {license_key[:8]}... (normalized: {license_key_normalized[:8]}...)")
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'Invalid license key'}),
                status=200,
                headers=headers
            )
        
        subscription = docs[0].to_dict()
        subscription_id = docs[0].id
        
        # Check if subscription is active
        now = datetime.utcnow()
        expires_at = subscription.get('expires_at')
        
        if expires_at:
            # Handle Firestore Timestamp
            if hasattr(expires_at, 'timestamp'):
                expires_datetime = datetime.utcfromtimestamp(expires_at.timestamp())
            elif isinstance(expires_at, datetime):
                expires_datetime = expires_at
            else:
                expires_datetime = datetime.utcnow() + timedelta(days=30)
            
            if expires_datetime < now:
                logger.warning(f"Expired license key: {license_key[:8]}...")
                headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                return https_fn.Response(
                    json.dumps({'valid': False, 'error': 'License key has expired'}),
                    status=200,
                    headers=headers
                )
        
        # Check if already used (optional - for single-use keys)
        if subscription.get('used', False) and not subscription.get('reusable', True):
            logger.warning(f"Already used license key: {license_key[:8]}...")
            headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
            return https_fn.Response(
                json.dumps({'valid': False, 'error': 'License key has already been used'}),
                status=200,
                headers=headers
            )
        
        # Mark as used if not reusable
        if not subscription.get('reusable', True):
            subscriptions_ref.document(subscription_id).update({'used': True, 'used_at': firestore.SERVER_TIMESTAMP})
        
        # Update last_used timestamp
        subscriptions_ref.document(subscription_id).update({'last_used': firestore.SERVER_TIMESTAMP})
        
        logger.info(f"Valid license key verified: {license_key[:8]}...")
        
        response_data = {
            'valid': True,
            'expires_at': expires_at.timestamp() if hasattr(expires_at, 'timestamp') else None,
            'subscription_type': subscription.get('subscription_type', 'premium'),
            'email': subscription.get('email', ''),
        }
        
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        return https_fn.Response(
            json.dumps(response_data),
            status=200,
            headers=headers
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Error verifying license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        headers = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
        return https_fn.Response(
            json.dumps({'valid': False, 'error': 'Server error verifying license key'}),
            status=500,
            headers=headers
        )


@https_fn.on_call()
def generate_license_key(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Generate a new license key for a subscription purchase.
    This would typically be called by a payment webhook (Stripe, PayPal, etc.)
    
    Request: { 
        'email': 'user@example.com',
        'subscription_type': 'monthly' | 'yearly',
        'duration_days': 30 (optional, defaults based on subscription_type)
    }
    Response: { 'license_key': 'XXXX-XXXX-XXXX-XXXX', 'expires_at': timestamp }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Optional: Add admin authentication check here
        # For now, we'll allow it but you should secure this endpoint
        
        db = get_firestore_client()
        email = req.data.get('email', '').strip().lower()
        subscription_type = req.data.get('subscription_type', 'monthly')
        duration_days = req.data.get('duration_days')
        
        if not email:
            return {'error': 'Email is required'}
        
        # Set duration based on subscription type
        if not duration_days:
            if subscription_type == 'yearly':
                duration_days = 365
            elif subscription_type == 'monthly':
                duration_days = 30
            else:
                duration_days = 30  # Default
        
        # Generate a secure license key (format: XXXX-XXXX-XXXX-XXXX)
        alphabet = string.ascii_uppercase + string.digits
        key_parts = []
        for _ in range(4):
            part = ''.join(secrets.choice(alphabet) for _ in range(4))
            key_parts.append(part)
        license_key = '-'.join(key_parts)
        
        # Calculate expiration date
        expires_at = datetime.utcnow() + timedelta(days=duration_days)
        
        # Store in Firestore
        subscription_data = {
            'license_key': license_key,
            'email': email,
            'subscription_type': subscription_type,
            'created_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at,
            'used': False,
            'reusable': True,  # Allow multiple logins with same key
            'active': True,
        }
        
        doc_ref = db.collection('subscriptions').add(subscription_data)
        subscription_id = doc_ref[1].id
        
        logger.info(f"Generated license key for {email}: {license_key[:8]}...")
        
        # TODO: Send email with license key using Gmail API or email service
        # This would typically use:
        # - Gmail API (requires OAuth setup)
        # - SendGrid, Mailgun, or similar service
        # - Firebase Extensions for email
        
        return {
            'license_key': license_key,
            'expires_at': expires_at.timestamp(),
            'subscription_id': subscription_id,
            'email': email,
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating license key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'error': f'Error generating license key: {str(e)}'}


@https_fn.on_call(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def generate_license_key_with_email(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Generate a license key, save to Firestore, and send email.
    This is called after payment is processed.
    
    Request: {
        'email': 'user@example.com',
        'name': 'John Doe',
        'subscription_type': 'monthly' | '6months' | 'yearly',
        'duration_days': 30 (optional),
        'amount': 29 (optional, for records)
    }
    Response: {
        'license_key': 'XXXX-XXXX-XXXX-XXXX',
        'expires_at': timestamp,
        'subscription_id': '...',
        'email_sent': bool
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        db = get_firestore_client()
        email = req.data.get('email', '').strip().lower()
        name = req.data.get('name', '').strip()
        subscription_type = req.data.get('subscription_type', 'monthly')
        duration_days = req.data.get('duration_days')
        amount = req.data.get('amount', 0)
        
        if not email:
            return {'error': 'Email is required'}
        
        # Map subscription types to duration
        if not duration_days:
            if subscription_type == 'yearly':
                duration_days = 365
            elif subscription_type == '6months':
                duration_days = 180
            elif subscription_type == 'monthly':
                duration_days = 30
            else:
                duration_days = 30
        
        # Generate license key
        alphabet = string.ascii_uppercase + string.digits
        key_parts = []
        for _ in range(4):
            part = ''.join(secrets.choice(alphabet) for _ in range(4))
            key_parts.append(part)
        license_key = '-'.join(key_parts)
        
        # Calculate expiration date
        expires_at = datetime.utcnow() + timedelta(days=duration_days)
        
        # Store in Firestore
        subscription_data = {
            'license_key': license_key,
            'email': email,
            'name': name,
            'subscription_type': subscription_type,
            'duration_days': duration_days,
            'amount': amount,
            'created_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at,
            'used': False,
            'reusable': True,
            'active': True,
            'payment_completed': True,
            'payment_date': firestore.SERVER_TIMESTAMP,
        }
        
        doc_ref = db.collection('subscriptions').add(subscription_data)
        subscription_id = doc_ref[1].id
        
        logger.info(f"Generated license key for {email}: {license_key[:8]}... (Duration: {duration_days} days)")
        
        # Send email with license key
        email_sent = False
        email_error_message = None
        try:
            email_result = send_license_key_email(email, name, license_key, subscription_type, duration_days, expires_at)
            if isinstance(email_result, dict):
                email_sent = email_result.get('success', False)
                email_error_message = email_result.get('error', None)
            else:
                email_sent = bool(email_result)
            
            if email_sent:
                logger.info(f"Email sent successfully to {email}")
            else:
                logger.warning(f"Email sending failed for {email}, but license key was created")
                if email_error_message:
                    logger.warning(f"Email error: {email_error_message}")
        except Exception as email_error:
            logger.error(f"Error sending email: {str(email_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            email_error_message = str(email_error)
            # Don't fail the whole operation if email fails
        
        response = {
            'license_key': license_key,
            'expires_at': expires_at.timestamp(),
            'subscription_id': subscription_id,
            'email': email,
            'email_sent': email_sent,
            'duration_days': duration_days,
            'subscription_type': subscription_type,
        }
        
        if email_error_message:
            response['email_error'] = email_error_message
        
        return response
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating license key with email: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {'error': f'Error processing subscription: {str(e)}'}


def send_license_key_email(email: str, name: str, license_key: str, subscription_type: str, duration_days: int, expires_at: datetime) -> bool:
    """
    Send license key email to user.
    Returns True if email was sent successfully, False otherwise.
    
    You can implement this using:
    - SendGrid (recommended)
    - Gmail API
    - Mailgun
    - AWS SES
    - Firebase Extensions (Email Trigger)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Option 1: Using SendGrid (recommended for production)
        # Uncomment and configure if you have SendGrid API key
        # Example implementation:
        # import sendgrid
        # from sendgrid.helpers.mail import Mail, Email, To, Content
        # 
        # sg = sendgrid.SendGridAPIClient(api_key=os.getenv('SENDGRID_API_KEY'))
        # from_email = Email("noreply@rugbyai.com")  # Your verified sender
        # to_email = To(email)
        # 
        # # Format expiration date
        # expires_str = expires_at.strftime('%B %d, %Y')
        # duration_str = f"{duration_days} days" if duration_days < 365 else f"{duration_days // 365} year(s)"
        # 
        # subject = "Your Rugby AI Predictor License Key"
        # html_content = f"""
        # <html>
        # <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        #     <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        #         <h2 style="color: #22c55e;">Thank you for your subscription!</h2>
        #         <p>Hi {name},</p>
        #         <p>Your subscription to Rugby AI Predictor has been activated!</p>
        #         <div style="background: #f8fafc; border: 2px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
        #             <p style="margin: 0; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;">Your License Key</p>
        #             <p style="margin: 10px 0; font-size: 24px; font-weight: 700; color: #22c55e; letter-spacing: 3px; font-family: monospace;">{license_key}</p>
        #         </div>
        #         <p><strong>Subscription Details:</strong></p>
        #         <ul>
        #             <li>Plan: {subscription_type.title()}</li>
        #             <li>Duration: {duration_str}</li>
        #             <li>Expires: {expires_str}</li>
        #         </ul>
        #         <p>To activate your account:</p>
        #         <ol>
        #             <li>Go to the Rugby AI Predictor login page</li>
        #             <li>Enter your license key: <strong>{license_key}</strong></li>
        #             <li>Start accessing premium predictions!</li>
        #         </ol>
        #         <p style="margin-top: 30px; color: #64748b; font-size: 14px;">
        #             If you have any questions, please contact our support team.
        #         </p>
        #         <p style="margin-top: 20px;">
        #             Best regards,<br>
        #             Rugby AI Predictor Team
        #         </p>
        #     </div>
        # </body>
        # </html>
        # """
        # content = Content("text/html", html_content)
        # message = Mail(from_email, to_email, subject, content)
        # response = sg.send(message)
        # return response.status_code == 202
        
        # Option 2: Using Gmail API (requires OAuth setup)
        # See LICENSE_KEY_SETUP.md for Gmail API implementation
        
        # Option 3: Using Gmail SMTP (easiest to set up)
        # 
        # SETUP INSTRUCTIONS:
        # 1. Get Gmail App Password: https://myaccount.google.com/apppasswords
        # 2. Set as Firebase Functions secrets:
        #    firebase functions:secrets:set GMAIL_USER
        #    firebase functions:secrets:set GMAIL_APP_PASSWORD
        # 3. Deploy: firebase deploy --only functions:generate_license_key_with_email
        #
        # Try to get secrets from multiple sources:
        # 1. Environment variables (Firebase Functions v2 injects them automatically)
        # 2. Legacy Firebase Functions config
        # 3. Secret Manager API as fallback
        
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        # Try legacy config method (works with older firebase-functions versions)
        # Legacy config is available via FIREBASE_CONFIG environment variable (JSON)
        if not gmail_user or not gmail_password:
            try:
                # Legacy config is stored in FIREBASE_CONFIG as JSON
                firebase_config_str = os.getenv('FIREBASE_CONFIG')
                if firebase_config_str:
                    import json
                    firebase_config = json.loads(firebase_config_str)
                    # Config structure: {"gmail": {"user": "...", "app_password": "..."}}
                    if 'gmail' in firebase_config:
                        gmail_config = firebase_config['gmail']
                        if not gmail_user and 'user' in gmail_config:
                            gmail_user = gmail_config['user']
                        if not gmail_password and 'app_password' in gmail_config:
                            gmail_password = gmail_config['app_password']
                        if gmail_user or gmail_password:
                            logger.info("✅ Retrieved Gmail credentials from legacy config (FIREBASE_CONFIG)")
            except Exception as config_err:
                logger.debug(f"Legacy config (FIREBASE_CONFIG) not available: {config_err}")
            
            # Also try accessing via functions.config() if available
            if not gmail_user or not gmail_password:
                try:
                    # Try the functions.config() method directly
                    from firebase_functions import config as functions_config
                    if hasattr(functions_config, 'gmail'):
                        if not gmail_user:
                            gmail_user = getattr(functions_config.gmail, 'user', None)
                        if not gmail_password:
                            gmail_password = getattr(functions_config.gmail, 'app_password', None)
                        if gmail_user or gmail_password:
                            logger.info("✅ Retrieved Gmail credentials from functions.config()")
                except (ImportError, AttributeError) as e:
                    logger.debug(f"functions.config() not available: {e}")
            
            # Also try direct environment variable access (legacy config might set these directly)
            if not gmail_user:
                gmail_user = os.getenv('GMAIL_USER') or os.getenv('gmail_user')
            if not gmail_password:
                gmail_password = os.getenv('GMAIL_APP_PASSWORD') or os.getenv('gmail_app_password') or os.getenv('gmail.app_password')
        
        # If not found in env vars, try Secret Manager API directly
        if not gmail_user or not gmail_password:
            logger.info("Secrets not found in environment variables, trying Secret Manager API...")
            try:
                from google.cloud import secretmanager
                # Get project ID - try multiple sources
                project_id = (
                    os.getenv('GCP_PROJECT') or 
                    os.getenv('GOOGLE_CLOUD_PROJECT') or 
                    os.getenv('GCLOUD_PROJECT') or
                    'rugby-ai-61fd0'
                )
                logger.info(f"Using project ID: {project_id}")
                
                # Initialize client
                try:
                    client = secretmanager.SecretManagerServiceClient()
                    logger.info("Secret Manager client initialized")
                except Exception as client_err:
                    logger.error(f"Failed to initialize Secret Manager client: {client_err}")
                    raise
                
                if not gmail_user:
                    try:
                        # Try with project number first (Firebase uses project number for secrets)
                        # Firebase secrets are stored as: projects/PROJECT_NUMBER/secrets/SECRET_NAME
                        # But we can also try with project ID
                        secret_name = f"projects/{project_id}/secrets/GMAIL_USER/versions/latest"
                        logger.info(f"Attempting to access secret: {secret_name}")
                        response = client.access_secret_version(request={"name": secret_name})
                        gmail_user = response.payload.data.decode("UTF-8").strip()
                        logger.info("✅ Retrieved GMAIL_USER from Secret Manager")
                    except Exception as e:
                        # Try with project number (645506509698)
                        try:
                            secret_name = f"projects/645506509698/secrets/GMAIL_USER/versions/latest"
                            logger.info(f"Trying with project number: {secret_name}")
                            response = client.access_secret_version(request={"name": secret_name})
                            gmail_user = response.payload.data.decode("UTF-8").strip()
                            logger.info("✅ Retrieved GMAIL_USER from Secret Manager (using project number)")
                        except Exception as e2:
                            logger.error(f"❌ Could not retrieve GMAIL_USER from Secret Manager")
                            logger.error(f"Error with project ID: {str(e)}")
                            logger.error(f"Error with project number: {str(e2)}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")
                
                if not gmail_password:
                    try:
                        secret_name = f"projects/{project_id}/secrets/GMAIL_APP_PASSWORD/versions/latest"
                        logger.info(f"Attempting to access secret: {secret_name}")
                        response = client.access_secret_version(request={"name": secret_name})
                        gmail_password = response.payload.data.decode("UTF-8").strip()
                        logger.info("✅ Retrieved GMAIL_APP_PASSWORD from Secret Manager")
                    except Exception as e:
                        # Try with project number
                        try:
                            secret_name = f"projects/645506509698/secrets/GMAIL_APP_PASSWORD/versions/latest"
                            logger.info(f"Trying with project number: {secret_name}")
                            response = client.access_secret_version(request={"name": secret_name})
                            gmail_password = response.payload.data.decode("UTF-8").strip()
                            logger.info("✅ Retrieved GMAIL_APP_PASSWORD from Secret Manager (using project number)")
                        except Exception as e2:
                            logger.error(f"❌ Could not retrieve GMAIL_APP_PASSWORD from Secret Manager")
                            logger.error(f"Error with project ID: {str(e)}")
                            logger.error(f"Error with project number: {str(e2)}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")
            except ImportError as import_err:
                logger.error(f"❌ google-cloud-secret-manager not available: {import_err}")
                logger.error("Install it with: pip install google-cloud-secret-manager")
            except Exception as e:
                logger.error(f"❌ Error accessing Secret Manager: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Debug logging
        logger.info(f"Checking for Gmail credentials...")
        logger.info(f"GMAIL_USER exists: {gmail_user is not None}")
        logger.info(f"GMAIL_APP_PASSWORD exists: {gmail_password is not None}")
        if gmail_user:
            logger.info(f"GMAIL_USER value: {gmail_user[:3]}...{gmail_user[-3:] if len(gmail_user) > 6 else '***'}")
        if not gmail_user or not gmail_password:
            logger.warning("Gmail credentials not found in environment variables or Secret Manager!")
            logger.warning("Available env vars starting with GMAIL: " + str([k for k in os.environ.keys() if 'GMAIL' in k.upper()]))
            logger.warning("All env vars: " + str(list(os.environ.keys())[:20]))  # First 20 for debugging
        
        if gmail_user and gmail_password:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                # Format expiration date
                expires_str = expires_at.strftime('%B %d, %Y')
                duration_str = f"{duration_days} days" if duration_days < 365 else f"{duration_days // 365} year(s)"
                
                # Create email
                msg = MIMEMultipart('alternative')
                msg['Subject'] = "Your Rugby AI Predictor License Key"
                # Send from your Gmail address with a friendly name
                msg['From'] = f"Rugby AI Predictor <{gmail_user}>"
                msg['To'] = email
                msg['Reply-To'] = gmail_user  # Replies go back to your email
                
                # HTML email body
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #22c55e;">Thank you for your subscription!</h2>
                        <p>Hi {name},</p>
                        <p>Your subscription to Rugby AI Predictor has been activated!</p>
                        
                        <div style="background: #f8fafc; border: 2px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px;">Your License Key</p>
                            <p style="margin: 10px 0; font-size: 24px; font-weight: 700; color: #22c55e; letter-spacing: 3px; font-family: monospace;">{license_key}</p>
                        </div>
                        
                        <p><strong>Subscription Details:</strong></p>
                        <ul>
                            <li>Plan: {subscription_type.title()}</li>
                            <li>Duration: {duration_str}</li>
                            <li>Expires: {expires_str}</li>
                        </ul>
                        
                        <p>To activate your account:</p>
                        <ol>
                            <li>Go to the Rugby AI Predictor login page</li>
                            <li>Enter your license key: <strong>{license_key}</strong></li>
                            <li>Start accessing premium predictions!</li>
                        </ol>
                        
                        <p style="margin-top: 30px; color: #64748b; font-size: 14px;">
                            If you have any questions, please contact our support team.
                        </p>
                        
                        <p style="margin-top: 20px;">
                            Best regards,<br>
                            Rugby AI Predictor Team
                        </p>
                    </div>
                </body>
                </html>
                """
                
                # Plain text version
                text_body = f"""
Thank you for your subscription!

Hi {name},

Your subscription to Rugby AI Predictor has been activated!

Your License Key: {license_key}

Subscription Details:
- Plan: {subscription_type.title()}
- Duration: {duration_str}
- Expires: {expires_str}

To activate your account:
1. Go to the Rugby AI Predictor login page
2. Enter your license key: {license_key}
3. Start accessing premium predictions!

If you have any questions, please contact our support team.

Best regards,
Rugby AI Predictor Team
                """
                
                part1 = MIMEText(text_body, 'plain')
                part2 = MIMEText(html_body, 'html')
                
                msg.attach(part1)
                msg.attach(part2)
                
                # Send email via Gmail SMTP
                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(gmail_user, gmail_password)
                    server.send_message(msg)
                
                logger.info(f"Email sent successfully to {email}")
                return {'success': True}
                
            except Exception as smtp_error:
                import traceback
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"SMTP email sending failed: {str(smtp_error)}")
                logger.error(f"SMTP error type: {type(smtp_error).__name__}")
                logger.error(f"SMTP error details: {error_details}")
                # Return error details
                return {
                    'success': False,
                    'error': f"SMTP error: {str(smtp_error)}"
                }
        
        # Option 4: For testing - log the email content (if no email service configured)
        logger.warning("=" * 60)
        logger.warning("EMAIL NOT SENT - No email service configured")
        logger.warning("=" * 60)
        logger.warning(f"To: {email}")
        logger.warning(f"Subject: Your Rugby AI Predictor License Key")
        logger.warning(f"License Key: {license_key}")
        logger.warning(f"Subscription: {subscription_type} ({duration_days} days)")
        logger.warning(f"Expires: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.warning("=" * 60)
        logger.warning("To enable email sending, set GMAIL_USER and GMAIL_APP_PASSWORD environment variables")
        logger.warning("Or configure SendGrid, Mailgun, or another email service")
        logger.warning("=" * 60)
        
        # Return detailed error information
        return {
            'success': False,
            'error': 'No email service configured. Set GMAIL_USER and GMAIL_APP_PASSWORD secrets.'
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error in send_license_key_email: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': f"Email function error: {str(e)}"
        }


@https_fn.on_call(secrets=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
def test_email_config(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Test function to check if email credentials are accessible.
    Returns status of Gmail configuration.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Try all methods to get credentials
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        methods_tried = []
        methods_tried.append(f"Environment variables: GMAIL_USER={gmail_user is not None}, GMAIL_APP_PASSWORD={gmail_password is not None}")
        
        # Try legacy config via FIREBASE_CONFIG environment variable
        try:
            firebase_config_str = os.getenv('FIREBASE_CONFIG')
            if firebase_config_str:
                import json
                firebase_config = json.loads(firebase_config_str)
                if 'gmail' in firebase_config:
                    gmail_config = firebase_config['gmail']
                    if not gmail_user and 'user' in gmail_config:
                        gmail_user = gmail_config['user']
                    if not gmail_password and 'app_password' in gmail_config:
                        gmail_password = gmail_config['app_password']
                    methods_tried.append("Legacy config (FIREBASE_CONFIG): Gmail config found")
                else:
                    methods_tried.append(f"Legacy config (FIREBASE_CONFIG): Available but no gmail key. Keys: {list(firebase_config.keys())}")
            else:
                methods_tried.append("Legacy config (FIREBASE_CONFIG): Not set")
        except Exception as e:
            methods_tried.append(f"Legacy config (FIREBASE_CONFIG) error: {str(e)}")
        
        # Try functions.config() method
        try:
            from firebase_functions import config as functions_config
            if hasattr(functions_config, 'gmail'):
                methods_tried.append("functions.config(): Available")
                if not gmail_user:
                    gmail_user = getattr(functions_config.gmail, 'user', None)
                if not gmail_password:
                    gmail_password = getattr(functions_config.gmail, 'app_password', None)
            else:
                methods_tried.append("functions.config(): Available but no gmail attribute")
        except (ImportError, AttributeError) as e:
            methods_tried.append(f"functions.config(): Not available - {str(e)}")
        
        # Try Secret Manager
        if not gmail_user or not gmail_password:
            try:
                from google.cloud import secretmanager
                client = secretmanager.SecretManagerServiceClient()
                project_id = 'rugby-ai-61fd0'
                
                if not gmail_user:
                    try:
                        name = f"projects/645506509698/secrets/GMAIL_USER/versions/latest"
                        response = client.access_secret_version(request={"name": name})
                        gmail_user = response.payload.data.decode("UTF-8").strip()
                        methods_tried.append("Secret Manager: GMAIL_USER retrieved")
                    except Exception as e:
                        methods_tried.append(f"Secret Manager GMAIL_USER error: {str(e)}")
                
                if not gmail_password:
                    try:
                        name = f"projects/645506509698/secrets/GMAIL_APP_PASSWORD/versions/latest"
                        response = client.access_secret_version(request={"name": name})
                        gmail_password = response.payload.data.decode("UTF-8").strip()
                        methods_tried.append("Secret Manager: GMAIL_APP_PASSWORD retrieved")
                    except Exception as e:
                        methods_tried.append(f"Secret Manager GMAIL_APP_PASSWORD error: {str(e)}")
            except ImportError:
                methods_tried.append("Secret Manager: Package not installed")
            except Exception as e:
                methods_tried.append(f"Secret Manager error: {str(e)}")
        
        result = {
            'gmail_user_found': gmail_user is not None,
            'gmail_password_found': gmail_password is not None,
            'both_found': gmail_user is not None and gmail_password is not None,
            'methods_tried': methods_tried,
            'gmail_user_preview': gmail_user[:3] + '...' + gmail_user[-3:] if gmail_user and len(gmail_user) > 6 else 'Not found',
        }
        
        if gmail_user and gmail_password:
            result['status'] = '✅ Credentials found! Email should work.'
        else:
            result['status'] = '❌ Credentials not found. Check permissions or use legacy config.'
            result['recommendation'] = 'Try: firebase functions:config:set gmail.user="..." gmail.app_password="..."'
        
        return result
        
    except Exception as e:
        import traceback
        logger.error(f"Error in test_email_config: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'error': f'Test failed: {str(e)}',
            'both_found': False
        }


@https_fn.on_call(timeout_sec=60, memory=512)
def get_news_feed(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Get personalized news feed
    
    Request data:
    {
        "user_id": "optional_user_id",
        "followed_teams": [123, 456],
        "followed_leagues": [4446, 4986],
        "limit": 50
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        user_id = data.get('user_id')
        followed_teams = data.get('followed_teams', [])
        followed_leagues = data.get('followed_leagues', [])
        league_id = data.get('league_id')  # NEW: Primary league filter
        limit = data.get('limit', 50)
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data.sqlite"))
        logger.info(f"Using database path: {db_path}")
        logger.info(f"Database exists: {os.path.exists(db_path)}")
        
        predictor = get_predictor() if os.path.exists(db_path) else None
        news_service = get_news_service(predictor=predictor)
        
        logger.info(f"Getting news feed: user_id={user_id}, league_id={league_id}, followed_teams={followed_teams}, followed_leagues={followed_leagues}, limit={limit}")
        
        # Get news feed - LEAGUE-SPECIFIC if league_id provided
        news_items = news_service.get_news_feed(
            user_id=user_id,
            followed_teams=followed_teams,
            followed_leagues=followed_leagues,
            league_id=league_id,  # NEW: Filter by specific league
            limit=limit
        )
        
        logger.info(f"Generated {len(news_items)} news items")
        
        # Convert to dict format
        news_data = [item.to_dict() for item in news_items]
        
        return {
            'success': True,
            'news': news_data,
            'count': len(news_data)
        }
    except Exception as e:
        logger.error(f"Error in get_news_feed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'error': str(e),
            'success': False
        }


@https_fn.on_call(timeout_sec=60, memory=512)
def get_trending_topics(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Get trending rugby topics
    
    Request data:
    {
        "limit": 10
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        limit = data.get('limit', 10)
        league_id = data.get('league_id')  # NEW: League-specific trending topics
        
        # Initialize news service with API clients
        news_service = get_news_service()
        topics = news_service.get_trending_topics(limit=limit, league_id=league_id)  # NEW: Pass league_id
        
        return {
            'success': True,
            'topics': topics,
            'count': len(topics)
        }
    except Exception as e:
        logger.error(f"Error in get_trending_topics: {e}")
        return {
            'error': str(e),
            'success': False
        }


@https_fn.on_request(timeout_sec=300, memory=512)
def get_news_feed_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for news feed with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        logger.info("="*80)
        logger.info("=== get_news_feed_http CALLED ===")
        logger.info("="*80)
        logger.info(f"📥 Request method: {req.method}")
        logger.info(f"📥 Request URL: {req.url if hasattr(req, 'url') else 'N/A'}")
        
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
                logger.info(f"📥 Parsed POST data: {data}")
            except Exception as parse_error:
                logger.error(f"📥 Error parsing POST data: {parse_error}")
                data = {}
        else:
            data = dict(req.args)
            logger.info(f"📥 GET args data: {data}")
        
        user_id = data.get('user_id')
        followed_teams = data.get('followed_teams', [])
        followed_leagues = data.get('followed_leagues', [])
        league_id = data.get('league_id')  # NEW: Primary league filter
        limit = data.get('limit', 50)
        
        logger.info("="*80)
        logger.info("=== REQUEST PARAMETERS ===")
        logger.info("="*80)
        logger.info(f"📥 user_id: {user_id}")
        logger.info(f"📥 followed_teams: {followed_teams}")
        logger.info(f"📥 followed_leagues: {followed_leagues}")
        logger.info(f"📥 league_id: {league_id} (type: {type(league_id).__name__})")
        logger.info(f"📥 limit: {limit}")
        logger.info("="*80)
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH")
        if not db_path:
            # Try multiple possible paths for Firebase Functions
            # In Firebase Functions, the working directory is the function's directory (rugby-ai-predictor/)
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same dir as main.py
                os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent dir (root)
                os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root of repo
                "/tmp/data.sqlite",  # Fallback for Firebase Functions
            ]
            logger.info(f"Searching for database in {len(possible_paths)} possible locations...")
            for path in possible_paths:
                abs_path = os.path.abspath(path)
                exists = os.path.exists(abs_path)
                logger.info(f"  Checking: {abs_path} - {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
                if exists:
                    db_path = abs_path
                    logger.info(f"✅ Found database at: {db_path}")
                    break
            else:
                # Default to same directory as main.py
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                logger.warning(f"⚠️ Database not found in any expected location, using default: {db_path}")
        
        logger.info(f"Final database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")
        
        predictor = None
        try:
            if db_path and os.path.exists(db_path):
                predictor = get_predictor()
        except Exception as pred_error:
            logger.warning(f"Could not initialize predictor: {pred_error}")
            predictor = None
        
        try:
            news_service = get_news_service(predictor=predictor)
            
            # Test database connection
            try:
                import sqlite3
                test_conn = sqlite3.connect(db_path)
                test_cursor = test_conn.cursor()
                test_cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = ?", (league_id,))
                match_count = test_cursor.fetchone()[0]
                test_cursor.execute("SELECT COUNT(*) FROM event WHERE date_event >= date('now') AND date_event <= date('now', '+7 days') AND league_id = ?", (league_id,))
                upcoming_count = test_cursor.fetchone()[0]
                test_conn.close()
                logger.info(f"Database test: {match_count} total matches, {upcoming_count} upcoming matches for league {league_id}")
            except Exception as db_test_error:
                logger.warning(f"Database test failed: {db_test_error}")
        except Exception as ns_error:
            logger.error(f"Could not initialize news service: {ns_error}")
            import traceback
            logger.error(traceback.format_exc())
            # Return empty news instead of failing
            response_data = {
                'success': True,
                'news': [],
                'count': 0,
                'error': f'News service initialization failed: {str(ns_error)}'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        # Get news feed - LEAGUE-SPECIFIC if league_id provided
        try:
            logger.info(f"Calling get_news_feed with league_id={league_id}, limit={limit}")
            logger.info(f"  user_id={user_id}, followed_teams={followed_teams}, followed_leagues={followed_leagues}")
            
            # Test database query directly before calling news service
            try:
                import sqlite3
                test_conn = sqlite3.connect(db_path)
                test_cursor = test_conn.cursor()
                
                # Check upcoming matches for this league
                test_cursor.execute("""
                    SELECT COUNT(*) FROM event 
                    WHERE league_id = ? 
                    AND date_event >= date('now') 
                    AND date_event <= date('now', '+7 days')
                    AND home_team_id IS NOT NULL 
                    AND away_team_id IS NOT NULL
                """, (league_id,))
                upcoming_count = test_cursor.fetchone()[0]
                logger.info(f"  Direct DB query: {upcoming_count} upcoming matches for league {league_id}")
                
                # Check recent matches
                test_cursor.execute("""
                    SELECT COUNT(*) FROM event 
                    WHERE league_id = ? 
                    AND date_event >= date('now', '-7 days')
                    AND date_event < date('now')
                    AND home_score IS NOT NULL 
                    AND away_score IS NOT NULL
                    AND home_team_id IS NOT NULL 
                    AND away_team_id IS NOT NULL
                """, (league_id,))
                recent_count = test_cursor.fetchone()[0]
                logger.info(f"  Direct DB query: {recent_count} recent matches for league {league_id}")
                
                test_conn.close()
            except Exception as db_test_error:
                logger.warning(f"  Database test query failed: {db_test_error}")
            
            news_items = news_service.get_news_feed(
                user_id=user_id,
                followed_teams=followed_teams,
                followed_leagues=followed_leagues,
                league_id=league_id,  # NEW: Filter by specific league
                limit=limit
            )
            logger.info(f"get_news_feed returned {len(news_items)} items")
            
            if len(news_items) == 0:
                logger.warning("="*80)
                logger.warning(f"⚠️⚠️⚠️ NO NEWS ITEMS RETURNED FOR LEAGUE {league_id}! ⚠️⚠️⚠️")
                logger.warning("="*80)
                logger.warning(f"  This might indicate:")
                logger.warning(f"  1. No upcoming matches in the next 7 days for this league")
                logger.warning(f"  2. Date filtering issue (check date('now') vs actual dates)")
                logger.warning(f"  3. Database doesn't have matches for this league")
                logger.warning(f"  4. News service queries are failing silently")
                logger.warning("="*80)
            
            # Convert to dict format
            logger.info(f"Converting {len(news_items)} news items to dict format...")
            news_data = []
            for i, item in enumerate(news_items):
                try:
                    item_dict = item.to_dict()
                    news_data.append(item_dict)
                    if i < 3:  # Log first 3 items
                        logger.info(f"  Item {i+1}: type={item_dict.get('type')}, league_id={item_dict.get('league_id')}, title={item_dict.get('title', '')[:50]}")
                except Exception as convert_error:
                    logger.error(f"  Error converting item {i+1} to dict: {convert_error}")
            
            logger.info(f"✅ Converted {len(news_data)} items to dict format")
            
            # Log first few items for debugging
            if len(news_data) > 0:
                logger.info(f"📰 Sample news items (first 3):")
                for i, item in enumerate(news_data[:3], 1):
                    logger.info(f"  {i}. [{item.get('type')}] {item.get('title', '')[:50]}... (league_id: {item.get('league_id')})")
            else:
                logger.warning("📰 No news items to display!")
        except Exception as feed_error:
            logger.error(f"Error getting news feed: {feed_error}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            news_data = []
        
        # Calculate what news_service returned
        news_service_count = len(news_items) if 'news_items' in locals() else 0
        
        response_data = {
            'success': True,
            'news': news_data,
            'count': len(news_data),
            'debug': {
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'league_id': league_id,
                'predictor_available': predictor is not None,
                'request_league_id': league_id,
                'request_limit': limit,
                'news_items_count': len(news_data),
                'news_service_returned': news_service_count
            }
        }
        
        logger.info("="*80)
        logger.info("=== get_news_feed_http RESPONSE ===")
        logger.info("="*80)
        logger.info(f"✅ Success: {response_data['success']}")
        logger.info(f"📊 News count: {response_data['count']}")
        logger.info(f"🔍 Debug info:")
        for key, value in response_data['debug'].items():
            logger.info(f"   {key}: {value}")
        logger.info("="*80)
        
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_news_feed_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_news_feed_http: {e}")
        logger.error(f"Traceback: {error_trace}")
        # Return empty news array instead of error to prevent UI issues
        response_data = {
            'success': True,
            'news': [],
            'count': 0,
            'error': str(e)  # Include error for debugging but don't fail
        }
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)


@https_fn.on_request(timeout_sec=300, memory=512)
def get_trending_topics_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for trending topics with explicit CORS support.
    This is primarily used by the React frontend to avoid CORS issues.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)
    
    try:
        logger.info("=== get_trending_topics_http called ===")
        
        # Parse input
        if req.method == "POST":
            try:
                data = req.get_json(silent=True) or {}
            except Exception:
                data = {}
        else:
            data = dict(req.args)
        
        limit = data.get('limit', 10)
        league_id = data.get('league_id')  # NEW: League-specific trending topics
        
        # Initialize news service with API clients
        db_path = os.getenv("DB_PATH")
        if not db_path:
            # Try multiple possible paths for Firebase Functions
            # In Firebase Functions, the working directory is the function's directory (rugby-ai-predictor/)
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "data.sqlite"),  # Same dir as main.py
                os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),  # Parent dir (root)
                os.path.join(os.path.dirname(__file__), "..", "..", "data.sqlite"),  # Root of repo
                "/tmp/data.sqlite",  # Fallback for Firebase Functions
            ]
            logger.info(f"Searching for database in {len(possible_paths)} possible locations...")
            for path in possible_paths:
                abs_path = os.path.abspath(path)
                exists = os.path.exists(abs_path)
                logger.info(f"  Checking: {abs_path} - {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
                if exists:
                    db_path = abs_path
                    logger.info(f"✅ Found database at: {db_path}")
                    break
            else:
                # Default to same directory as main.py
                db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
                logger.warning(f"⚠️ Database not found in any expected location, using default: {db_path}")
        
        logger.info(f"Final database path: {db_path}, exists: {os.path.exists(db_path) if db_path else False}")
        
        predictor = None
        try:
            if db_path and os.path.exists(db_path):
                predictor = get_predictor()
        except Exception as pred_error:
            logger.warning(f"Could not initialize predictor: {pred_error}")
            predictor = None
        
        try:
            news_service = get_news_service(predictor=predictor)
        except Exception as ns_error:
            logger.error(f"Could not initialize news service: {ns_error}")
            # Return empty topics instead of failing
            response_data = {
                'success': True,
                'topics': [],
                'count': 0,
                'error': f'News service initialization failed: {str(ns_error)}'
            }
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
        try:
            logger.info(f"Calling get_trending_topics with league_id={league_id}, limit={limit}")
            topics = news_service.get_trending_topics(limit=limit, league_id=league_id)  # NEW: Pass league_id
            logger.info(f"get_trending_topics returned {len(topics)} topics")
        except Exception as topics_error:
            logger.error(f"Error getting trending topics: {topics_error}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            topics = []
        
        response_data = {
            'success': True,
            'topics': topics,
            'count': len(topics),
            'debug': {
                'db_path': db_path,
                'db_exists': os.path.exists(db_path) if db_path else False,
                'league_id': league_id
            }
        }
        
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        logger.info("=== get_trending_topics_http completed successfully ===")
        return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_trending_topics_http: {e}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {
            'error': str(e),
            'success': False
        }
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json",
        }
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)


@https_fn.on_request(timeout_sec=60, memory=512)
def get_league_standings_http(req: https_fn.Request) -> https_fn.Response:
    """
    Get league standings from Highlightly API
    
    Request body:
    {
        "league_id": 73119  # Highlightly league ID
    }
    """
    import logging
    import json
    from datetime import datetime
    logger = logging.getLogger(__name__)
    
    logger.info("="*80)
    logger.info("=== get_league_standings_http CALLED ===")
    logger.info("="*80)
    logger.info(f"Request method: {req.method}")
    logger.info(f"Request headers: {dict(req.headers)}")
    
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }
    
    try:
        # Parse request data
        if req.method == 'OPTIONS':
            logger.info("OPTIONS request - returning CORS preflight")
            return https_fn.Response('', status=204, headers=headers)
        
        logger.info("Parsing request JSON...")
        data = req.get_json(silent=True) or {}
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        
        highlightly_league_id = data.get('league_id')
        logger.info(f"Extracted league_id: {highlightly_league_id} (type: {type(highlightly_league_id)})")
        
        if not highlightly_league_id:
            logger.error("❌ Missing league_id in request")
            response_data = {
                'success': False,
                'error': 'league_id is required',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=400, headers=headers)
        
        logger.info(f"📊 Fetching standings for Highlightly league ID: {highlightly_league_id}")
        
        # Initialize Highlightly client
        logger.info("Importing HighlightlyRugbyAPI...")
        from prediction.highlightly_client import HighlightlyRugbyAPI
        import os
        
        logger.info("Checking for API keys...")
        # Prefer RapidAPI key, then try Highlightly key, then fallback
        # Use RapidAPI by default since it has better rate limits
        use_rapidapi = True  # Use RapidAPI by default for better reliability
        api_key = os.getenv('RAPIDAPI_KEY') or os.getenv('HIGHLIGHTLY_API_KEY') or '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
        
        if api_key:
            api_type = "RapidAPI" if use_rapidapi else "Highlightly Direct"
            logger.info(f"✅ API key found ({api_type}): {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else ''} (length: {len(api_key)})")
        else:
            logger.error("❌ No API key found in environment variables")
            logger.error("   RAPIDAPI_KEY: " + str(os.getenv('RAPIDAPI_KEY')))
            logger.error("   HIGHLIGHTLY_API_KEY: " + str(os.getenv('HIGHLIGHTLY_API_KEY')))
            response_data = {
                'success': False,
                'error': 'RAPIDAPI_KEY or HIGHLIGHTLY_API_KEY not configured',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        logger.info(f"Initializing HighlightlyRugbyAPI client (use_rapidapi={use_rapidapi})...")
        try:
            client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
            logger.info(f"✅ HighlightlyRugbyAPI client initialized successfully (using {'RapidAPI' if use_rapidapi else 'Highlightly Direct'})")
        except Exception as client_error:
            logger.error(f"❌ Failed to initialize Highlightly client: {client_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            response_data = {
                'success': False,
                'error': f'Failed to initialize API client: {str(client_error)}',
                'standings': None
            }
            return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
        
        # Try current year only (2025)
        current_year = datetime.now().year
        logger.info(f"📅 Current year: {current_year}")
        logger.info(f"🔍 Will try season: {current_year} only")
        
        standings = None
        successful_season = None
        last_error = None
        
        # Only try current year (2025)
        for year in [current_year]:
            logger.info(f"\n--- Trying season {year} ---")
            try:
                logger.info(f"Calling client.get_standings(league_id={highlightly_league_id}, season={year})...")
                standings = client.get_standings(league_id=highlightly_league_id, season=year)
                logger.info(f"✅ API call completed for season {year}")
                logger.info(f"Response type: {type(standings)}")
                
                # Check if we got rate limited (429) - API might return empty structure
                if isinstance(standings, dict):
                    # Check for explicit rate limit flag
                    if standings.get('_rate_limited'):
                        logger.error(f"   ❌ Rate limited (429) - API quota exceeded")
                        last_error = Exception("Rate limited (429) - API quota exceeded")
                        # Don't try other seasons if rate limited
                        break
                    
                    groups = standings.get('groups', [])
                    league_info = standings.get('league', {})
                    
                    logger.info(f"   Groups count: {len(groups)}")
                    logger.info(f"   League info: {league_info}")
                    
                    # Check if response is empty
                    if len(groups) == 0 and (not league_info or not league_info.get('name')):
                        logger.warning(f"⚠️ Empty response for season {year}")
                        logger.warning(f"   Full response structure: {json.dumps(standings, indent=2, default=str)}")
                        
                        # If we have an error flag, it's definitely an error
                        if standings.get('_error'):
                            logger.error(f"   ❌ API Error: {standings.get('_error')}")
                            last_error = Exception(standings.get('_error'))
                            continue
                        
                        # If rate limited flag is set, handle it
                        if standings.get('_rate_limited'):
                            logger.error(f"   ❌ Rate limited (429) - API quota exceeded")
                            last_error = Exception("Rate limited (429) - API quota exceeded")
                            break
                        
                        # Otherwise, no data for this season
                        logger.warning(f"   No standings data for season {year} - might not exist yet")
                        last_error = Exception(f"No standings data for season {year}")
                        continue
                
                if standings:
                    logger.info(f"Response keys: {list(standings.keys()) if isinstance(standings, dict) else 'N/A'}")
                    
                    if isinstance(standings, dict):
                        if standings.get('groups') or standings.get('league'):
                            groups = standings.get('groups', [])
                            logger.info(f"Found {len(groups)} groups in response")
                            
                            if groups and len(groups) > 0:
                                logger.info(f"Analyzing groups for teams/standings...")
                                for idx, group in enumerate(groups):
                                    logger.info(f"  Group {idx + 1}: keys = {list(group.keys()) if isinstance(group, dict) else 'N/A'}")
                                    if isinstance(group, dict):
                                        standings_list = group.get('standings', [])
                                        teams_list = group.get('teams', [])
                                        logger.info(f"    standings: {len(standings_list)} items")
                                        logger.info(f"    teams: {len(teams_list)} items")
                                
                                # Check if groups have teams/standings
                                has_teams = any(
                                    (g.get('standings') and len(g.get('standings', [])) > 0) or
                                    (g.get('teams') and len(g.get('teams', [])) > 0)
                                    for g in groups
                                )
                                logger.info(f"Has teams: {has_teams}")
                                
                                if has_teams:
                                    total_teams = sum(
                                        len(g.get('standings', [])) + len(g.get('teams', []))
                                        for g in groups if isinstance(g, dict)
                                    )
                                    logger.info(f"✅ Found standings for league {highlightly_league_id} (season {year})")
                                    logger.info(f"   Total teams across all groups: {total_teams}")
                                    successful_season = year
                                    break
                                else:
                                    logger.warning(f"⚠️ Groups found but no teams/standings data in season {year}")
                            else:
                                logger.warning(f"⚠️ Empty groups array for season {year}")
                        else:
                            logger.warning(f"⚠️ Response has no 'groups' or 'league' keys for season {year}")
                    else:
                        logger.warning(f"⚠️ Response is not a dict for season {year}")
                else:
                    logger.warning(f"⚠️ Empty response for season {year}")
                    
            except Exception as year_error:
                error_msg = str(year_error)
                last_error = year_error
                logger.error(f"❌ Season {year} failed with error: {year_error}")
                logger.error(f"   Error type: {type(year_error).__name__}")
                
                if '404' in error_msg:
                    logger.info(f"   404 Not Found - standings don't exist for season {year}")
                elif '429' in error_msg:
                    logger.warning(f"   429 Too Many Requests - rate limited")
                else:
                    import traceback
                    logger.error(f"   Full traceback: {traceback.format_exc()}")
                continue
        
        logger.info("\n" + "="*80)
        logger.info("=== FINAL RESULT ===")
        logger.info("="*80)
        
        if standings and successful_season:
            logger.info(f"✅ SUCCESS: Found standings for season {successful_season}")
            logger.info(f"   League ID: {highlightly_league_id}")
            logger.info(f"   Season: {successful_season}")
            
            # Log standings summary
            if isinstance(standings, dict):
                groups = standings.get('groups', [])
                league_info = standings.get('league', {})
                logger.info(f"   Groups: {len(groups)}")
                logger.info(f"   League info: {league_info.get('name', 'N/A')} - {league_info.get('season', 'N/A')}")
                
                total_teams = 0
                for group in groups:
                    if isinstance(group, dict):
                        teams_count = len(group.get('standings', [])) + len(group.get('teams', []))
                        total_teams += teams_count
                logger.info(f"   Total teams: {total_teams}")
            
            response_data = {
                'success': True,
                'standings': standings,
                'season': successful_season,
                'league_id': highlightly_league_id
            }
            logger.info(f"✅ Returning success response (status 200)")
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
        else:
            logger.warning(f"⚠️ NO STANDINGS FOUND")
            logger.warning(f"   League ID: {highlightly_league_id}")
            logger.warning(f"   Tried season: {current_year}")
            
            # Check if rate limited
            error_msg = None
            is_rate_limited = False
            if last_error:
                error_str = str(last_error)
                if '429' in error_str or 'Rate limited' in error_str or 'quota exceeded' in error_str.lower():
                    is_rate_limited = True
            
            if is_rate_limited:
                error_msg = f'API rate limit exceeded. Please try again in a few minutes. (League ID: {highlightly_league_id})'
                logger.error(f"   ❌ RATE LIMITED - API quota exceeded")
            else:
                error_msg = f'No standings data available for league {highlightly_league_id} (tried season {current_year})'
                if last_error:
                    logger.warning(f"   Last error: {last_error}")
                    error_msg += f'. Last error: {str(last_error)}'
            
            response_data = {
                'success': False,
                'error': error_msg,
                'standings': None,
                'rate_limited': is_rate_limited,
                'debug': {
                    'tried_seasons': [current_year],
                    'last_error': str(last_error) if last_error else None,
                    'league_id': highlightly_league_id
                }
            }
            logger.info(f"⚠️ Returning error response (status 200)")
            return https_fn.Response(json.dumps(response_data), status=200, headers=headers)
            
    except Exception as e:
        logger.error("="*80)
        logger.error("❌ EXCEPTION IN get_league_standings_http")
        logger.error("="*80)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_trace}")
        logger.error("="*80)
        
        response_data = {
            'success': False,
            'error': f'Server error: {str(e)}',
            'standings': None,
            'debug': {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': error_trace
            }
        }
        logger.error(f"❌ Returning error response (status 500)")
        return https_fn.Response(json.dumps(response_data), status=500, headers=headers)
    
    finally:
        logger.info("="*80)
        logger.info("=== get_league_standings_http COMPLETED ===")
        logger.info("="*80)



@https_fn.on_request(timeout_sec=120, memory=1024)
def get_historical_predictions_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for historical predictions with explicit CORS support.
    Returns historical matches organized by year and week with AI predictions vs actual results.
    
    Request body:
    {
        "league_id": 4986,  # optional, filter by league
        "year": "2026",     # optional, fetch a single calendar year (recommended)
        "limit": 100        # optional, limit number of matches
    }
    """
    import logging
    import sys
    import os
    from datetime import datetime
    from collections import defaultdict
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    logger.info("="*80)
    logger.info("=== get_historical_predictions_http CALLED ===")
    logger.info("="*80)
    
    # Handle CORS preflight (match pattern used by other HTTP functions)
    if req.method == "OPTIONS":
        logger.info("OPTIONS request - returning CORS preflight")
        preflight_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=preflight_headers)
    
    # Define response headers with CORS for all responses
    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }
    
    try:
        # Parse request data
        data = req.get_json(silent=True) or {}
        league_id = data.get('league_id')
        year = data.get('year')
        limit = data.get('limit')
        
        logger.info(f"Request data: league_id={league_id}, year={year}, limit={limit}")
        
        # Get database path
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            # If not found, try parent directory
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")
        
        logger.info(f"Using database path: {db_path}")
        
        if not os.path.exists(db_path):
            logger.error(f"Database file not found at {db_path}")
            response_data = {
                'error': f'Database file not found at {db_path}',
                'matches_by_year_week': {},
                'statistics': {},
            }
            return https_fn.Response(json.dumps(response_data), status=404, headers=response_headers)
        
        # Inline function to get historical matches with predictions
        def get_week_number(date_str: str) -> int:
            """Get ISO week number from date string (YYYY-MM-DD)"""
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                return date_obj.isocalendar()[1]
            except:
                return 0

        def get_year_week_key(date_str: str) -> str:
            """Get year-week key for grouping (e.g., '2024-W01')"""
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                year, week, _ = date_obj.isocalendar()
                return f"{year}-W{week:02d}"
            except:
                return "Unknown"
        
        # Import needed modules
        from prediction.db import connect
        predictor = get_predictor()
        
        # Connect to database
        conn = connect(db_path)
        cursor = conn.cursor()
        
        # If year is not provided, pick the most recent year that has completed matches
        # (and return all available years so the UI can switch years without loading everything at once).
        available_years = []
        selected_year = None
        try:
            year_query = """
            SELECT DISTINCT substr(e.date_event, 1, 4) AS yr
            FROM event e
            WHERE e.home_score IS NOT NULL
              AND e.away_score IS NOT NULL
              AND e.date_event IS NOT NULL
              AND e.date_event <= date('now')
            """
            year_params = []
            if league_id:
                year_query += " AND e.league_id = ?"
                year_params.append(league_id)
            year_query += " ORDER BY yr DESC"
            cursor.execute(year_query, year_params)
            available_years = [r[0] for r in cursor.fetchall() if r and r[0]]
        except Exception as e:
            logger.warning(f"Could not compute available years: {e}")
            available_years = []

        if year is None:
            selected_year = available_years[0] if available_years else None
        else:
            selected_year = str(year)

        # Query for completed matches with scores
        query = """
        SELECT 
            e.id,
            e.league_id,
            l.name as league_name,
            e.date_event,
            e.home_team_id,
            e.away_team_id,
            e.home_score,
            e.away_score,
            t1.name as home_team_name,
            t2.name as away_team_name,
            e.season,
            e.round,
            e.venue,
            e.status
        FROM event e
        LEFT JOIN league l ON e.league_id = l.id
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.home_score IS NOT NULL 
        AND e.away_score IS NOT NULL
        AND e.date_event IS NOT NULL
        AND e.date_event <= date('now')
        """
        
        params = []
        if league_id:
            query += " AND e.league_id = ?"
            params.append(league_id)

        if selected_year:
            query += " AND substr(e.date_event, 1, 4) = ?"
            params.append(selected_year)
        
        query += " ORDER BY e.date_event DESC, e.league_id"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Organize matches by year-week
        matches_by_year_week = defaultdict(lambda: defaultdict(list))
        all_matches = []
        
        correct_predictions = 0
        total_predictions = 0
        score_errors = []
        
        logger.info(f"Processing {len(results)} completed matches...")
        
        for row in results:
            match_id, league_id_val, league_name, date_event, home_team_id, away_team_id, \
            home_score, away_score, home_team_name, away_team_name, season, round_num, \
            venue, status = row
            
            # Skip if missing critical data
            if not home_team_name or not away_team_name or not date_event:
                continue
            
            # Determine actual winner
            if home_score > away_score:
                actual_winner = 'Home'
                actual_winner_team = home_team_name
            elif away_score > home_score:
                actual_winner = 'Away'
                actual_winner_team = away_team_name
            else:
                actual_winner = 'Draw'
                actual_winner_team = None
            
            # Generate prediction for this match
            predicted_winner = None
            predicted_home_score = None
            predicted_away_score = None
            prediction_confidence = None
            prediction_error = None
            
            if predictor:
                try:
                    pred = predictor.predict_match(
                        home_team=home_team_name,
                        away_team=away_team_name,
                        league_id=league_id_val,
                        match_date=date_event
                    )
                    
                    predicted_home_score = pred.get('predicted_home_score', 0)
                    predicted_away_score = pred.get('predicted_away_score', 0)
                    prediction_confidence = pred.get('confidence', 0.5)
                    predicted_winner = pred.get('predicted_winner', 'Unknown')
                    
                    # Check if prediction was correct
                    if predicted_winner == actual_winner:
                        correct_predictions += 1
                    total_predictions += 1
                    
                    # Calculate score prediction error
                    home_error = abs(predicted_home_score - home_score)
                    away_error = abs(predicted_away_score - away_score)
                    prediction_error = home_error + away_error
                    score_errors.append(prediction_error)
                    
                except Exception as e:
                    logger.warning(f"Could not generate prediction for {home_team_name} vs {away_team_name} on {date_event}: {e}")
                    predicted_winner = 'Error'
            
            # Get year-week key
            year_week_key = get_year_week_key(date_event)
            year = date_event[:4] if date_event else "Unknown"
            week = get_week_number(date_event)
            
            match_data = {
                'match_id': match_id,
                'league_id': league_id_val,
                'league_name': league_name or f"League {league_id_val}",
                'date': date_event,
                'year': year,
                'week': week,
                'year_week': year_week_key,
                'season': season,
                'round': round_num,
                'venue': venue,
                'status': status,
                'home_team': home_team_name,
                'away_team': away_team_name,
                'home_team_id': home_team_id,
                'away_team_id': away_team_id,
                'actual_home_score': home_score,
                'actual_away_score': away_score,
                'actual_winner': actual_winner,
                'actual_winner_team': actual_winner_team,
                'predicted_home_score': predicted_home_score,
                'predicted_away_score': predicted_away_score,
                'predicted_winner': predicted_winner,
                'prediction_confidence': prediction_confidence,
                'prediction_error': prediction_error,
                'prediction_correct': predicted_winner == actual_winner if predicted_winner and predicted_winner != 'Error' else None,
                'score_difference': abs(home_score - away_score) if home_score and away_score else None,
                'predicted_score_difference': abs(predicted_home_score - predicted_away_score) if predicted_home_score is not None and predicted_away_score is not None else None,
            }
            
            matches_by_year_week[year][year_week_key].append(match_data)
            all_matches.append(match_data)
        
        conn.close()
        
        # Calculate accuracy statistics
        accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
        avg_score_error = sum(score_errors) / len(score_errors) if score_errors else None
        
        # Convert defaultdict to regular dict for JSON serialization
        result = {
            'available_years': available_years,
            'selected_year': selected_year,
            'matches_by_year_week': {
                year: {
                    week_key: matches
                    for week_key, matches in weeks.items()
                }
                for year, weeks in matches_by_year_week.items()
            },
            'all_matches': all_matches,
            'statistics': {
                'total_matches': len(all_matches),
                'total_predictions': total_predictions,
                'correct_predictions': correct_predictions,
                'accuracy_percentage': round(accuracy, 2),
                'average_score_error': round(avg_score_error, 2) if avg_score_error else None,
            },
            'by_league': {}
        }
        
        # Group by league for easier filtering
        leagues_dict = defaultdict(list)
        for match in all_matches:
            leagues_dict[match['league_id']].append(match)
        
        for league_id_val, league_matches in leagues_dict.items():
            league_correct = sum(1 for m in league_matches if m.get('prediction_correct') is True)
            league_total = sum(1 for m in league_matches if m.get('prediction_correct') is not None)
            league_accuracy = (league_correct / league_total * 100) if league_total > 0 else 0
            
            result['by_league'][league_id_val] = {
                'league_name': league_matches[0]['league_name'] if league_matches else f"League {league_id_val}",
                'total_matches': len(league_matches),
                'total_predictions': league_total,
                'correct_predictions': league_correct,
                'accuracy_percentage': round(league_accuracy, 2),
            }
        
        logger.info(f"Retrieved {result['statistics']['total_matches']} matches")
        logger.info(f"Generated {result['statistics']['total_predictions']} predictions")
        logger.info(f"Accuracy: {result['statistics'].get('accuracy_percentage', 0):.2f}%")
        
        # Convert any datetime objects to strings for JSON serialization
        def convert_for_json(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_for_json(item) for item in obj]
            elif isinstance(obj, (defaultdict, set)):
                return convert_for_json(dict(obj) if isinstance(obj, defaultdict) else list(obj))
            else:
                return obj
        
        result = convert_for_json(result)
        
        logger.info("=== get_historical_predictions_http completed successfully ===")
        return https_fn.Response(json.dumps(result), status=200, headers=response_headers)
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"=== get_historical_predictions_http exception ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        response_data = {
            "error": str(e),
            "traceback": error_trace,
            "matches_by_year_week": {},
            "statistics": {},
        }
        # Always include CORS headers even on error
        return https_fn.Response(json.dumps(response_data), status=500, headers=response_headers)


@https_fn.on_request(timeout_sec=540, memory=2048)
def get_historical_backtest_http(req: https_fn.Request) -> https_fn.Response:
    """
    HTTP endpoint for TRUE historical evaluation via walk-forward backtest (unseen).

    For each week in the selected year, trains a fresh model using only matches
    strictly BEFORE that week, then predicts matches in that week.

    Request body:
    {
        "league_id": 4414,      # required
        "year": "2026",         # optional (calendar year). If omitted, uses most recent year with completed matches.
        "days_back": 3650,      # optional, how far back training history can go (default ~10y)
        "min_train_games": 30,  # optional
        "refresh": false        # optional, bypass Firestore cache
    }
    """
    import logging
    import os
    import json
    import sqlite3
    from datetime import datetime, timedelta
    from collections import defaultdict

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Handle CORS preflight
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "3600",
        }
        return https_fn.Response("", status=204, headers=headers)

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json",
    }

    try:
        data = req.get_json(silent=True) or {}
        league_id_raw = data.get("league_id")
        if league_id_raw is None:
            return https_fn.Response(
                json.dumps({"error": "league_id is required"}),
                status=400,
                headers=headers,
            )
        league_id = int(league_id_raw)

        year = data.get("year")
        refresh = bool(data.get("refresh", False))
        min_train_games = int(data.get("min_train_games", 30))
        days_back = int(data.get("days_back", 3650))

        # DB path (same logic as other endpoints)
        db_path = os.getenv("DB_PATH")
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "data.sqlite")
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(__file__), "..", "data.sqlite")

        if not os.path.exists(db_path):
            return https_fn.Response(
                json.dumps({"error": f"Database file not found at {db_path}"}),
                status=404,
                headers=headers,
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Determine available years and selected year (completed matches only)
        year_sql = """
            SELECT DISTINCT substr(e.date_event, 1, 4) AS yr
            FROM event e
            WHERE e.home_score IS NOT NULL
              AND e.away_score IS NOT NULL
              AND e.date_event IS NOT NULL
              AND e.date_event <= date('now')
              AND e.league_id = ?
            ORDER BY yr DESC
        """
        cur.execute(year_sql, (league_id,))
        available_years = [r["yr"] for r in cur.fetchall() if r and r["yr"]]

        selected_year = str(year) if year is not None else (available_years[0] if available_years else None)
        if not selected_year:
            conn.close()
            return https_fn.Response(
                json.dumps(
                    {
                        "available_years": [],
                        "selected_year": None,
                        "matches_by_year_week": {},
                        "statistics": {},
                        "error": "No completed matches found for this league",
                    }
                ),
                status=200,
                headers=headers,
            )

        # Cache in Firestore (avoid recompute)
        try:
            fs = get_firestore_client()
            cache_id = f"walk_forward::{league_id}::{selected_year}"
            cache_ref = fs.collection("backtests").document(cache_id)
            if not refresh:
                cached = cache_ref.get()
                if getattr(cached, "exists", False):
                    cached_data = cached.to_dict() or {}
                    payload = cached_data.get("data")
                    if isinstance(payload, dict) and payload.get("selected_year") == selected_year:
                        conn.close()
                        return https_fn.Response(json.dumps(payload), status=200, headers=headers)
        except Exception as cache_err:
            logger.warning(f"Backtest cache read failed (continuing without cache): {cache_err}")
            fs = None
            cache_ref = None

        # Load team/league names for display
        cur.execute("SELECT id, name FROM team")
        team_name = {int(r["id"]): r["name"] for r in cur.fetchall() if r and r["id"] is not None}
        cur.execute("SELECT id, name FROM league WHERE id = ?", (league_id,))
        row = cur.fetchone()
        league_name = row["name"] if row and row["name"] else f"League {league_id}"

        # Build feature table (chronological, pre-match features).
        # IMPORTANT: build features on a SMALL in-memory DB for this league only.
        # The full DB can be large and may cause slowdowns or memory issues in Cloud Functions.
        from prediction.features import build_feature_table, FeatureConfig
        import pandas as pd
        import xgboost as xgb

        today_iso = datetime.utcnow().date().isoformat()
        min_date_iso = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()

        # Pull only completed matches for this league within the training window
        cur.execute(
            """
            SELECT
              e.id AS id,
              e.league_id AS league_id,
              e.season AS season,
              e.date_event AS date_event,
              e.timestamp AS timestamp,
              e.home_team_id AS home_team_id,
              e.away_team_id AS away_team_id,
              e.home_score AS home_score,
              e.away_score AS away_score
            FROM event e
            WHERE e.league_id = ?
              AND e.home_team_id IS NOT NULL
              AND e.away_team_id IS NOT NULL
              AND e.date_event IS NOT NULL
              AND e.home_score IS NOT NULL
              AND e.away_score IS NOT NULL
              AND date(e.date_event) >= date(?)
              AND date(e.date_event) <= date(?)
            ORDER BY date(e.date_event) ASC, e.timestamp ASC, e.id ASC
            """,
            (league_id, min_date_iso, today_iso),
        )
        event_rows = cur.fetchall()

        # Create in-memory DB with only the columns build_feature_table needs
        mem = sqlite3.connect(":memory:")
        mem.execute(
            """
            CREATE TABLE event (
              id INTEGER PRIMARY KEY,
              league_id INTEGER,
              season TEXT,
              date_event TEXT,
              timestamp INTEGER,
              home_team_id INTEGER,
              away_team_id INTEGER,
              home_score INTEGER,
              away_score INTEGER
            )
            """
        )
        if event_rows:
            mem.executemany(
                """
                INSERT INTO event (id, league_id, season, date_event, timestamp, home_team_id, away_team_id, home_score, away_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        int(r["id"]),
                        int(r["league_id"]),
                        r["season"],
                        r["date_event"],
                        r["timestamp"],
                        int(r["home_team_id"]),
                        int(r["away_team_id"]),
                        int(r["home_score"]),
                        int(r["away_score"]),
                    )
                    for r in event_rows
                ],
            )
        mem.commit()

        config = FeatureConfig(
            elo_priors=None,
            elo_k=24.0,
            neutral_mode=(league_id == 4574 or league_id == 4714),
        )
        df = build_feature_table(mem, config)
        mem.close()

        # Completed matches only, already filtered by query; sort just in case
        df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
        df.sort_values(["date_event", "event_id"], inplace=True)

        # Calendar year filter for the evaluation set
        try:
            target_year_int = int(selected_year)
        except Exception:
            target_year_int = None
        if target_year_int is not None:
            df_eval = df[df["date_event"].dt.year == target_year_int].copy()
        else:
            df_eval = df.copy()

        if df_eval.empty:
            conn.close()
            payload = {
                "available_years": available_years,
                "selected_year": selected_year,
                "matches_by_year_week": {},
                "statistics": {},
                "by_league": {},
                "warning": "No completed matches found for selected year",
            }
            return https_fn.Response(json.dumps(payload), status=200, headers=headers)

        # Feature columns (match training script behavior)
        exclude_cols = {
            "event_id",
            "league_id",
            "season",
            "date_event",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
            "home_win",
        }
        feature_cols = [c for c in df.columns if c not in exclude_cols]
        feature_cols = [c for c in feature_cols if not df[c].isna().all()]

        # Week keys for eval matches
        def year_week_key(ts: pd.Timestamp) -> str:
            iso = ts.isocalendar()
            return f"{int(iso.year)}-W{int(iso.week):02d}"

        df_eval["year_week"] = df_eval["date_event"].apply(year_week_key)
        df_eval["year"] = df_eval["date_event"].dt.strftime("%Y")
        df_eval["week"] = df_eval["date_event"].dt.isocalendar().week.astype(int)

        # Order weeks chronologically (based on first match date in week)
        week_first_date = (
            df_eval.groupby("year_week")["date_event"].min().sort_values()
        )
        week_keys = list(week_first_date.index)

        matches_by_year_week = defaultdict(lambda: defaultdict(list))

        total_predictions = 0
        correct_predictions = 0
        draws_excluded = 0
        score_errors: list[float] = []
        weeks_evaluated = 0
        weeks_skipped = 0

        # Model hyperparams (same defaults as training)
        def train_models(train_df):
            X_train = train_df[feature_cols].fillna(0).values
            y_winner = (train_df["home_score"] > train_df["away_score"]).astype(int).values
            y_home = train_df["home_score"].values
            y_away = train_df["away_score"].values

            clf = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
            )
            clf.fit(X_train, y_winner)

            reg_home = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="mae",
            )
            reg_home.fit(X_train, y_home)

            reg_away = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="mae",
            )
            reg_away.fit(X_train, y_away)

            return clf, reg_home, reg_away

        for wk in week_keys:
            wk_start = week_first_date.loc[wk]

            # Train on all matches strictly before this week
            train_df = df[df["date_event"] < wk_start].copy()
            if len(train_df) < min_train_games:
                weeks_skipped += 1
                continue

            week_df = df_eval[df_eval["year_week"] == wk].copy()
            if week_df.empty:
                continue

            clf, reg_home, reg_away = train_models(train_df)
            weeks_evaluated += 1

            X_test = week_df[feature_cols].fillna(0).values
            home_win_prob = clf.predict_proba(X_test)[:, 1]
            pred_home = reg_home.predict(X_test)
            pred_away = reg_away.predict(X_test)

            for i, row in enumerate(week_df.itertuples(index=False)):
                # row access via attributes: event_id, league_id, season, date_event, home_team_id, away_team_id, home_score, away_score, home_win, ...
                event_id = int(getattr(row, "event_id"))
                date_event = getattr(row, "date_event")
                home_team_id = int(getattr(row, "home_team_id"))
                away_team_id = int(getattr(row, "away_team_id"))
                home_score = int(getattr(row, "home_score"))
                away_score = int(getattr(row, "away_score"))

                if home_score > away_score:
                    actual_winner = "Home"
                    actual_winner_team = team_name.get(home_team_id)
                elif away_score > home_score:
                    actual_winner = "Away"
                    actual_winner_team = team_name.get(away_team_id)
                else:
                    actual_winner = "Draw"
                    actual_winner_team = None

                p = float(home_win_prob[i])
                predicted_winner = "Home" if p >= 0.5 else "Away"

                predicted_home_score = float(max(0.0, pred_home[i]))
                predicted_away_score = float(max(0.0, pred_away[i]))

                prediction_correct = None
                if actual_winner == "Draw":
                    draws_excluded += 1
                else:
                    prediction_correct = predicted_winner == actual_winner
                    total_predictions += 1
                    if prediction_correct:
                        correct_predictions += 1

                err = abs(predicted_home_score - home_score) + abs(predicted_away_score - away_score)
                score_errors.append(float(err))

                match_year = str(getattr(row, "year"))
                match_week = int(getattr(row, "week"))
                match_year_week = str(getattr(row, "year_week"))

                matches_by_year_week[match_year][match_year_week].append(
                    {
                        "match_id": event_id,
                        "league_id": league_id,
                        "league_name": league_name,
                        "date": date_event.strftime("%Y-%m-%d") if hasattr(date_event, "strftime") else str(date_event),
                        "year": match_year,
                        "week": match_week,
                        "year_week": match_year_week,
                        "home_team": team_name.get(home_team_id, f"Team {home_team_id}"),
                        "away_team": team_name.get(away_team_id, f"Team {away_team_id}"),
                        "home_team_id": home_team_id,
                        "away_team_id": away_team_id,
                        "actual_home_score": home_score,
                        "actual_away_score": away_score,
                        "actual_winner": actual_winner,
                        "actual_winner_team": actual_winner_team,
                        "predicted_home_score": predicted_home_score,
                        "predicted_away_score": predicted_away_score,
                        "predicted_winner": predicted_winner,
                        "prediction_confidence": float(max(p, 1.0 - p)),
                        "prediction_error": float(err),
                        "prediction_correct": prediction_correct,
                        "evaluation_mode": "walk_forward_backtest",
                        "train_games_used": int(len(train_df)),
                    }
                )

        conn.close()

        accuracy = (correct_predictions / total_predictions * 100.0) if total_predictions > 0 else 0.0
        avg_score_error = (sum(score_errors) / len(score_errors)) if score_errors else None

        payload = {
            "available_years": available_years,
            "selected_year": selected_year,
            "matches_by_year_week": {y: dict(w) for y, w in matches_by_year_week.items()},
            "statistics": {
                "total_matches": sum(len(v2) for v1 in matches_by_year_week.values() for v2 in v1.values()),
                "total_predictions": total_predictions,
                "correct_predictions": correct_predictions,
                "accuracy_percentage": round(accuracy, 2),
                "average_score_error": round(avg_score_error, 2) if avg_score_error is not None else None,
                "draws_excluded": draws_excluded,
                "weeks_evaluated": weeks_evaluated,
                "weeks_skipped": weeks_skipped,
                "min_train_games": min_train_games,
                "evaluation_mode": "walk_forward_backtest",
            },
            "by_league": {
                league_id: {
                    "league_name": league_name,
                    "total_predictions": total_predictions,
                    "correct_predictions": correct_predictions,
                    "accuracy_percentage": round(accuracy, 2),
                }
            },
        }

        # Cache the result if possible
        try:
            if fs is not None and cache_ref is not None:
                try:
                    from firebase_admin import firestore as fb_firestore  # type: ignore
                    server_ts = fb_firestore.SERVER_TIMESTAMP
                except Exception:
                    server_ts = datetime.utcnow().isoformat()
                cache_ref.set(
                    {
                        "league_id": league_id,
                        "year": selected_year,
                        "mode": "walk_forward_backtest",
                        "data": payload,
                        "updated_at": server_ts,
                    },
                    merge=True,
                )
        except Exception as cache_write_err:
            logger.warning(f"Backtest cache write failed: {cache_write_err}")

        return https_fn.Response(json.dumps(payload), status=200, headers=headers)

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"Error in get_historical_backtest_http: {e}\n{err}")
        return https_fn.Response(
            json.dumps({"error": str(e), "traceback": err}),
            status=500,
            headers=headers,
        )


@https_fn.on_call(timeout_sec=60, memory=512)
def parse_social_embed(req: https_fn.CallableRequest) -> Dict[str, Any]:
    """
    Parse social media URL and return embed info
    
    Request data:
    {
        "url": "https://instagram.com/p/...",
        "context": "lineup",
        "related_data": {}
    }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = req.data or {}
        url = data.get('url')
        context = data.get('context')
        related_data = data.get('related_data', {})
        
        if not url:
            return {'error': 'URL is required', 'success': False}
        
        from prediction.social_media_service import SocialMediaService
        
        # Generate AI explanation
        ai_explanation = SocialMediaService.generate_ai_explanation(
            embed_type="social",
            context=context or "general",
            related_data=related_data
        )
        
        # Create embed object
        embed = SocialMediaService.create_embed_object(
            url=url,
            context=context,
            ai_explanation=ai_explanation
        )
        
        return {
            'success': True,
            'embed': embed
        }
    except Exception as e:
        logger.error(f"Error in parse_social_embed: {e}")
        return {
            'error': str(e),
            'success': False
        }