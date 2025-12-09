"""
Firebase Cloud Functions for Rugby AI Predictor
Handles callable functions for predictions, matches, and data
"""

from firebase_functions import https_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
import os
import json
from datetime import datetime
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
                
                # Check if date is in the future
                date_event = match_data.get('date_event')
                if date_event:
                    # Handle both datetime and string dates
                    match_date = None
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
                    
                    # Only include FUTURE matches (no past matches)
                    if match_date:
                        # Only include if match is in the future
                        if match_date > now:
                            match_data['id'] = doc.id
                            # Convert date to string for JSON serialization
                            if hasattr(date_event, 'timestamp'):
                                match_data['date_event'] = match_date.isoformat()
                            elif isinstance(date_event, datetime):
                                match_data['date_event'] = match_date.isoformat()
                            
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
    Callable Cloud Function to get available leagues
    """
    try:
        league_mappings = _get_league_mappings()
        leagues = [
            {'id': league_id, 'name': name}
            for league_id, name in league_mappings.items()
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
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        logger.info("=== get_league_metrics called ===")
        data = req.data or {}
        league_id = data.get('league_id')
        
        if not league_id:
            logger.error("league_id is required")
            return {'error': 'league_id is required'}
        
        league_id_str = str(league_id)
        logger.info(f"Fetching metrics for league_id: {league_id_str}")
        
        # PRIMARY: Try to load from Firestore (fastest and most reliable)
        try:
            db = get_firestore_client()
            
            # Try individual league metrics document first (fastest)
            logger.info(f"Trying league_metrics/{league_id_str}...")
            league_metric_ref = db.collection('league_metrics').document(league_id_str)
            league_metric_doc = league_metric_ref.get()
            
            if league_metric_doc.exists:
                league_metric = league_metric_doc.to_dict()
                logger.info(f"Found league metrics in Firestore: {league_metric}")
                return {
                    'league_id': league_id,
                    'accuracy': league_metric.get('accuracy', 0.0),
                    'training_games': league_metric.get('training_games', 0),
                    'ai_rating': league_metric.get('ai_rating', 'N/A'),
                    'trained_at': league_metric.get('trained_at'),
                    'model_type': league_metric.get('model_type', 'unknown')
                }
            
            # Fallback: Try full registry document
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
                    
                    logger.info(f"Found league data in registry: accuracy={accuracy}, games={training_games}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'unknown')
                    }
        except Exception as firestore_error:
            logger.warning(f"Error loading from Firestore: {firestore_error}")
        
        # FALLBACK: Try to load from Cloud Storage
        try:
            from firebase_admin import storage
            bucket = storage.bucket()
            blob = bucket.blob('model_registry_optimized.json')
            
            if blob.exists():
                logger.info("Trying Cloud Storage...")
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
                    
                    logger.info(f"Found league data in Cloud Storage: accuracy={accuracy}, games={training_games}")
                    return {
                        'league_id': league_id,
                        'accuracy': round(accuracy, 1),
                        'training_games': training_games,
                        'ai_rating': ai_rating,
                        'trained_at': league_data.get('trained_at'),
                        'model_type': league_data.get('model_type', 'unknown')
                    }
        except Exception as storage_error:
            logger.warning(f"Error loading from storage: {storage_error}")
        
        # FALLBACK: Try to load from local file (for development or if included in deployment)
        possible_paths = [
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
                            
                            logger.info(f"✅ Found league data in local file: accuracy={accuracy:.1f}%, games={training_games}")
                            return {
                                'league_id': league_id,
                                'accuracy': round(accuracy, 1),
                                'training_games': training_games,
                                'ai_rating': ai_rating,
                                'trained_at': league_data.get('trained_at'),
                                'model_type': league_data.get('model_type', 'unknown')
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
            'trained_at': None,
            'model_type': 'unknown'
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_league_metrics: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return {'error': str(e)}
