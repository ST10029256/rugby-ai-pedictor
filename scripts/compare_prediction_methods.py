#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to compare AI predictions vs actual results for all completed games.

For each completed game, this script:
1. Makes a prediction using the AI model (as if the game hasn't happened yet)
2. Compares predicted scores/margins vs actual scores/margins
3. Compares predicted winner vs actual winner

This shows the TRUE predictive power of the model on all games.
Focus: Score/margin accuracy is the primary quality metric.
"""

import sqlite3
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS

# Setup logging to both console and file
class TeeOutput:
    """Class to write to both console and file"""
    def __init__(self, file_path):
        self.terminal = sys.stdout
        self.log_file = open(file_path, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()
    
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()
    
    def close(self):
        self.log_file.close()

def setup_logging():
    """Setup logging to both console and file"""
    # Create logs directory if it doesn't exist
    logs_dir = Path(__file__).parent / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    # Create log file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = logs_dir / f'compare_predictions_{timestamp}.log'
    
    # Redirect stdout to TeeOutput
    sys.stdout = TeeOutput(str(log_file))
    
    return str(log_file)

def get_predictor():
    """Get the predictor instance"""
    try:
        # Try to import and initialize predictor
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor'))
        
        from prediction.hybrid_predictor import MultiLeaguePredictor
        
        db_path = os.path.join(os.path.dirname(__file__), '..', 'data.sqlite')
        if not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor', 'data.sqlite')
        
        sportdevs_api_key = os.getenv("SPORTDEVS_API_KEY", "")
        storage_bucket = os.getenv("MODEL_STORAGE_BUCKET", "rugby-ai-61fd0.firebasestorage.app")
        
        predictor = MultiLeaguePredictor(
            db_path=db_path,
            sportdevs_api_key=sportdevs_api_key,
            artifacts_dir="artifacts",
            storage_bucket=storage_bucket,
        )
        return predictor
    except Exception as e:
        print(f"   ⚠️  Error initializing predictor: {e}")
        return None

def get_firestore_client():
    """Get Firestore client"""
    try:
        from firebase_admin import firestore, initialize_app
        try:
            initialize_app()
        except ValueError:
            pass
        return firestore.client()
    except ImportError:
        return None
    except Exception as e:
        print(f"   Warning: Firestore not available: {e}")
        return None

def get_all_completed_games(conn: sqlite3.Connection, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all completed games for a league or all leagues"""
    cursor = conn.cursor()
    
    if league_id:
        query = """
        SELECT e.id, e.league_id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, 
               ht.name as home_team_name, at.name as away_team_name,
               e.date_event, e.timestamp, l.name as league_name
        FROM event e
        LEFT JOIN team ht ON e.home_team_id = ht.id
        LEFT JOIN team at ON e.away_team_id = at.id
        LEFT JOIN league l ON e.league_id = l.id
        WHERE e.league_id = ? 
          AND e.home_score IS NOT NULL 
          AND e.away_score IS NOT NULL
          AND e.status != 'Postponed'
          AND e.status != 'Cancelled'
        ORDER BY e.date_event DESC, e.timestamp DESC
        """
        cursor.execute(query, (league_id,))
    else:
        query = """
        SELECT e.id, e.league_id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, 
               ht.name as home_team_name, at.name as away_team_name,
               e.date_event, e.timestamp, l.name as league_name
        FROM event e
        LEFT JOIN team ht ON e.home_team_id = ht.id
        LEFT JOIN team at ON e.away_team_id = at.id
        LEFT JOIN league l ON e.league_id = l.id
        WHERE e.home_score IS NOT NULL 
          AND e.away_score IS NOT NULL
          AND e.status != 'Postponed'
          AND e.status != 'Cancelled'
        ORDER BY e.date_event DESC, e.timestamp DESC
        """
        cursor.execute(query)
    
    rows = cursor.fetchall()
    
    games = []
    for row in rows:
        games.append({
            'event_id': row[0],
            'league_id': row[1],
            'home_team_id': row[2],
            'away_team_id': row[3],
            'home_score': row[4],
            'away_score': row[5],
            'home_team_name': row[6] or 'Unknown',
            'away_team_name': row[7] or 'Unknown',
            'date_event': row[8],
            'timestamp': row[9],
            'league_name': row[10] or f'League {row[1]}'
        })
    
    return games

def determine_winner(home_score: int, away_score: int) -> str:
    """Determine winner from scores"""
    if home_score > away_score:
        return 'Home'
    elif away_score > home_score:
        return 'Away'
    else:
        return 'Draw'

def get_prediction_from_firestore(db, event_id: int) -> Optional[Dict[str, Any]]:
    """Get stored prediction from Firestore"""
    if db is None:
        return None
    
    try:
        prediction_ref = db.collection('predictions').document(str(event_id))
        prediction_doc = prediction_ref.get()
        if prediction_doc.exists:
            return prediction_doc.to_dict()
    except Exception:
        pass
    return None

def normalize_predicted_winner(predicted_winner: str, home_team: str, away_team: str) -> Optional[str]:
    """Normalize predicted winner to Home/Away/Draw"""
    if not predicted_winner:
        return None
    
    predicted_lower = predicted_winner.lower()
    home_lower = home_team.lower()
    away_lower = away_team.lower()
    
    if predicted_lower == 'home' or predicted_lower == home_lower or home_lower in predicted_lower:
        return 'Home'
    elif predicted_lower == 'away' or predicted_lower == away_lower or away_lower in predicted_lower:
        return 'Away'
    elif predicted_lower == 'draw':
        return 'Draw'
    
    return None

def make_prediction_for_game(predictor, game: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Make a prediction for a game using the AI model"""
    if predictor is None:
        return None
    
    try:
        home_team = game['home_team_name']
        away_team = game['away_team_name']
        league_id = game['league_id']
        
        # Format date for prediction
        date_event = game['date_event']
        if date_event:
            if isinstance(date_event, str):
                # Extract just the date part
                date_str = date_event.split(' ')[0] if ' ' in date_event else date_event
            else:
                date_str = str(date_event).split(' ')[0]
        else:
            return None
        
        # Make prediction
        prediction = predictor.predict_match(
            home_team,
            away_team,
            league_id,
            date_str
        )
        
        return prediction
    except Exception as e:
        return None

def analyze_game(game: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a single game with both methods"""
    actual_winner = determine_winner(game['home_score'], game['away_score'])
    
    # Calculate actual margin (score difference)
    actual_home_score = game['home_score']
    actual_away_score = game['away_score']
    actual_margin = abs(actual_home_score - actual_away_score)
    
    # Current logic: Use predicted_winner field
    predicted_winner = prediction.get('predicted_winner') or prediction.get('winner', '')
    normalized_predicted = normalize_predicted_winner(
        predicted_winner, 
        game['home_team_name'], 
        game['away_team_name']
    )
    
    current_correct = (normalized_predicted == actual_winner) if normalized_predicted else False
    
    # Score-influenced logic: Determine winner from predicted scores
    pred_home_score = prediction.get('predicted_home_score')
    pred_away_score = prediction.get('predicted_away_score')
    
    score_influenced_correct = False
    score_influenced_winner = None
    predicted_margin = None
    margin_error = None
    margin_error_abs = None
    
    # WINNER-INFLUENCED SCORES: Adjust predicted scores to match predicted winner
    influenced_home_score = None
    influenced_away_score = None
    influenced_margin = None
    influenced_margin_error = None
    influenced_margin_error_abs = None
    
    if pred_home_score is not None and pred_away_score is not None:
        try:
            pred_home = float(pred_home_score)
            pred_away = float(pred_away_score)
            score_influenced_winner = determine_winner(int(pred_home), int(pred_away))
            score_influenced_correct = (score_influenced_winner == actual_winner)
            
            # Calculate predicted margin
            predicted_margin = abs(pred_home - pred_away)
            
            # Calculate margin error (difference between predicted and actual margin)
            margin_error = predicted_margin - actual_margin
            margin_error_abs = abs(margin_error)
            
            # WINNER-INFLUENCED: Adjust scores so predicted winner actually wins
            if normalized_predicted:
                if normalized_predicted == 'Home':
                    # Ensure home wins: home_score > away_score
                    if pred_home <= pred_away:
                        # Adjust: make home score higher than away
                        avg_score = (pred_home + pred_away) / 2
                        influenced_home_score = avg_score + 1  # Home wins by at least 1
                        influenced_away_score = avg_score
                    else:
                        # Already correct, use original
                        influenced_home_score = pred_home
                        influenced_away_score = pred_away
                elif normalized_predicted == 'Away':
                    # Ensure away wins: away_score > home_score
                    if pred_away <= pred_home:
                        # Adjust: make away score higher than home
                        avg_score = (pred_home + pred_away) / 2
                        influenced_home_score = avg_score
                        influenced_away_score = avg_score + 1  # Away wins by at least 1
                    else:
                        # Already correct, use original
                        influenced_home_score = pred_home
                        influenced_away_score = pred_away
                elif normalized_predicted == 'Draw':
                    # Ensure draw: home_score == away_score
                    avg_score = (pred_home + pred_away) / 2
                    influenced_home_score = avg_score
                    influenced_away_score = avg_score
                
                # Calculate influenced margin and error
                if influenced_home_score is not None and influenced_away_score is not None:
                    influenced_margin = abs(influenced_home_score - influenced_away_score)
                    influenced_margin_error = influenced_margin - actual_margin
                    influenced_margin_error_abs = abs(influenced_margin_error)
        except (ValueError, TypeError):
            pass
    
    return {
        'event_id': game['event_id'],
        'league_id': game['league_id'],
        'home_team': game['home_team_name'],
        'away_team': game['away_team_name'],
        'actual_score': f"{game['home_score']}-{game['away_score']}",
        'actual_margin': actual_margin,
        'actual_winner': actual_winner,
        'predicted_winner': normalized_predicted,
        'predicted_score': f"{pred_home_score}-{pred_away_score}" if pred_home_score is not None and pred_away_score is not None else 'N/A',
        'predicted_margin': predicted_margin,
        'margin_error': margin_error,
        'margin_error_abs': margin_error_abs,
        'influenced_score': f"{influenced_home_score:.1f}-{influenced_away_score:.1f}" if influenced_home_score is not None and influenced_away_score is not None else 'N/A',
        'influenced_margin': influenced_margin,
        'influenced_margin_error': influenced_margin_error,
        'influenced_margin_error_abs': influenced_margin_error_abs,
        'score_influenced_winner': score_influenced_winner,
        'current_correct': current_correct,
        'score_influenced_correct': score_influenced_correct,
        'methods_agree': normalized_predicted == score_influenced_winner if (normalized_predicted and score_influenced_winner) else None,
        'both_correct': current_correct and score_influenced_correct,
        'only_current_correct': current_correct and not score_influenced_correct,
        'only_score_correct': not current_correct and score_influenced_correct,
        'both_wrong': not current_correct and not score_influenced_correct
    }

def analyze_league(conn: sqlite3.Connection, predictor, league_id: int, league_name: str):
    """Analyze all completed games for a league"""
    print(f"\n{'='*80}")
    print(f"League: {league_name} (ID: {league_id})")
    print(f"{'='*80}")
    
    games = get_all_completed_games(conn, league_id)
    print(f"\n📊 Total completed games: {len(games)}")
    
    if len(games) == 0:
        print("   No completed games found")
        return
    
    if predictor is None:
        print("   ⚠️  Predictor not available, cannot make predictions")
        return
    
    # Make predictions for all games
    print(f"🤖 Making AI predictions for {len(games)} games...")
    games_with_predictions = []
    
    for i, game in enumerate(games):
        if (i + 1) % 100 == 0:
            print(f"   Progress: {i + 1}/{len(games)} games processed...")
        
        prediction = make_prediction_for_game(predictor, game)
        if prediction and not prediction.get('error'):
            analysis = analyze_game(game, prediction)
            games_with_predictions.append(analysis)
    
    print(f"✅ Successfully made predictions for {len(games_with_predictions)}/{len(games)} games")
    
    if len(games_with_predictions) == 0:
        print("   ⚠️  No successful predictions made")
        return
    
    # Calculate statistics
    current_correct = sum(1 for g in games_with_predictions if g['current_correct'])
    score_correct = sum(1 for g in games_with_predictions if g['score_influenced_correct'])
    both_correct = sum(1 for g in games_with_predictions if g['both_correct'])
    only_current = sum(1 for g in games_with_predictions if g['only_current_correct'])
    only_score = sum(1 for g in games_with_predictions if g['only_score_correct'])
    both_wrong = sum(1 for g in games_with_predictions if g['both_wrong'])
    
    # Calculate margin statistics
    games_with_margins = [g for g in games_with_predictions if g['predicted_margin'] is not None]
    games_with_influenced = [g for g in games_with_predictions if g['influenced_margin'] is not None]
    
    if games_with_margins:
        avg_actual_margin = sum(g['actual_margin'] for g in games_with_margins) / len(games_with_margins)
        avg_predicted_margin = sum(g['predicted_margin'] for g in games_with_margins) / len(games_with_margins)
        avg_margin_error = sum(g['margin_error'] for g in games_with_margins) / len(games_with_margins)
        avg_margin_error_abs = sum(g['margin_error_abs'] for g in games_with_margins) / len(games_with_margins)
        
        # Margin accuracy: how often predicted margin is within X points of actual
        margin_within_3 = sum(1 for g in games_with_margins if g['margin_error_abs'] <= 3)
        margin_within_5 = sum(1 for g in games_with_margins if g['margin_error_abs'] <= 5)
        margin_within_10 = sum(1 for g in games_with_margins if g['margin_error_abs'] <= 10)
        
        # Influenced margin statistics
        if games_with_influenced:
            avg_influenced_margin = sum(g['influenced_margin'] for g in games_with_influenced) / len(games_with_influenced)
            avg_influenced_margin_error = sum(g['influenced_margin_error'] for g in games_with_influenced) / len(games_with_influenced)
            avg_influenced_margin_error_abs = sum(g['influenced_margin_error_abs'] for g in games_with_influenced) / len(games_with_influenced)
            
            influenced_margin_within_3 = sum(1 for g in games_with_influenced if g['influenced_margin_error_abs'] <= 3)
            influenced_margin_within_5 = sum(1 for g in games_with_influenced if g['influenced_margin_error_abs'] <= 5)
            influenced_margin_within_10 = sum(1 for g in games_with_influenced if g['influenced_margin_error_abs'] <= 10)
        else:
            avg_influenced_margin = 0
            avg_influenced_margin_error = 0
            avg_influenced_margin_error_abs = 0
            influenced_margin_within_3 = 0
            influenced_margin_within_5 = 0
            influenced_margin_within_10 = 0
    else:
        avg_actual_margin = 0
        avg_predicted_margin = 0
        avg_margin_error = 0
        avg_margin_error_abs = 0
        margin_within_3 = 0
        margin_within_5 = 0
        margin_within_10 = 0
        avg_influenced_margin = 0
        avg_influenced_margin_error = 0
        avg_influenced_margin_error_abs = 0
        influenced_margin_within_3 = 0
        influenced_margin_within_5 = 0
        influenced_margin_within_10 = 0
    
    total = len(games_with_predictions)
    current_accuracy = (current_correct / total * 100) if total > 0 else 0
    score_accuracy = (score_correct / total * 100) if total > 0 else 0
    improvement = score_accuracy - current_accuracy
    
    if games_with_margins:
        print(f"\n⭐ MARGIN/SCORE PREDICTION ANALYSIS (Primary Focus):")
        print(f"   Average Actual Margin: {avg_actual_margin:.1f} points")
        
        print(f"\n   📊 CURRENT METHOD (Original Predicted Scores):")
        print(f"      Average Predicted Margin: {avg_predicted_margin:.1f} points")
        print(f"      Average Margin Error: {avg_margin_error:+.1f} points")
        print(f"      Average Absolute Margin Error: {avg_margin_error_abs:.1f} points")
        print(f"      Accuracy (within 5 points): {margin_within_5}/{len(games_with_margins)} ({margin_within_5/len(games_with_margins)*100:.1f}%)")
        
        if games_with_influenced:
            print(f"\n   📊 INFLUENCED METHOD (Scores Adjusted to Match Predicted Winner):")
            print(f"      Average Influenced Margin: {avg_influenced_margin:.1f} points")
            print(f"      Average Margin Error: {avg_influenced_margin_error:+.1f} points")
            print(f"      Average Absolute Margin Error: {avg_influenced_margin_error_abs:.1f} points")
            print(f"      Accuracy (within 5 points): {influenced_margin_within_5}/{len(games_with_influenced)} ({influenced_margin_within_5/len(games_with_influenced)*100:.1f}%)")
            
            improvement = avg_margin_error_abs - avg_influenced_margin_error_abs
            accuracy_improvement = (influenced_margin_within_5/len(games_with_influenced)*100) - (margin_within_5/len(games_with_margins)*100)
            
            print(f"\n   📈 COMPARISON:")
            print(f"      Margin Error Improvement: {improvement:+.1f} points")
            print(f"      Accuracy Improvement: {accuracy_improvement:+.1f}%")
            if improvement < 0:
                print(f"      ✅ Influenced method is BETTER (lower error)")
            elif improvement > 0:
                print(f"      ⚠️  Current method is BETTER (lower error)")
            else:
                print(f"      ➡️  Both methods perform equally")
    
    print(f"\n📊 Winner Prediction Comparison:")
    print(f"   Winner from predicted_winner field:")
    print(f"      Correct: {current_correct}/{total} ({current_accuracy:.1f}%)")
    print(f"   Winner from predicted scores:")
    print(f"      Correct: {score_correct}/{total} ({score_accuracy:.1f}%)")
    print(f"   Difference: {improvement:+.1f}%")
    
    print(f"\n📈 Detailed Breakdown:")
    print(f"   Both methods correct: {both_correct} ({both_correct/total*100:.1f}%)")
    print(f"   Only current method correct: {only_current} ({only_current/total*100:.1f}%)")
    print(f"   Only score method correct: {only_score} ({only_score/total*100:.1f}%)")
    print(f"   Both methods wrong: {both_wrong} ({both_wrong/total*100:.1f}%)")
    
    # Show examples where methods disagree
    if only_current > 0 or only_score > 0:
        print(f"\n🔍 Examples where methods disagree:")
        print(f"   {'ID':<8} {'Home':<20} {'Away':<20} {'Actual':<10} {'Pred W':<8} {'Pred Score':<12} {'Score W':<8} {'Act Margin':<11} {'Pred Margin':<12} {'Error':<8} {'Result'}")
        print(f"   {'-'*8} {'-'*20} {'-'*20} {'-'*10} {'-'*8} {'-'*12} {'-'*8} {'-'*11} {'-'*12} {'-'*8} {'-'*20}")
        
        count = 0
        for g in games_with_predictions:
            if g['only_current_correct'] or g['only_score_correct']:
                if count < 10:  # Show first 10 examples
                    event_id_str = str(g['event_id'])[:8]
                    result = "✅ Current" if g['only_current_correct'] else "✅ Score"
                    pred_margin_str = f"{g['predicted_margin']:.1f}" if g['predicted_margin'] is not None else "N/A"
                    margin_error_str = f"{g['margin_error']:+.1f}" if g['margin_error'] is not None else "N/A"
                    print(f"   {event_id_str:<8} {g['home_team'][:18]:<20} {g['away_team'][:18]:<20} {g['actual_score']:<10} {str(g['predicted_winner']):<8} {g['predicted_score']:<12} {str(g['score_influenced_winner']):<8} {g['actual_margin']:<11} {pred_margin_str:<12} {margin_error_str:<8} {result}")
                    count += 1
                else:
                    break
        
        if count == 10 and (only_current + only_score) > 10:
            print(f"   ... and {only_current + only_score - 10} more examples")
    
    # Show examples with largest margin errors
    if games_with_margins:
        print(f"\n📏 Examples with largest margin errors:")
        print(f"   {'ID':<8} {'Home':<20} {'Away':<20} {'Actual':<10} {'Pred Score':<12} {'Act Margin':<11} {'Pred Margin':<12} {'Error':<8}")
        print(f"   {'-'*8} {'-'*20} {'-'*20} {'-'*10} {'-'*12} {'-'*11} {'-'*12} {'-'*8}")
        
        # Sort by absolute margin error (descending)
        sorted_by_error = sorted([g for g in games_with_margins if g['margin_error_abs'] is not None], 
                                key=lambda x: x['margin_error_abs'], reverse=True)
        
        for g in sorted_by_error[:10]:  # Top 10 largest errors
            event_id_str = str(g['event_id'])[:8]
            print(f"   {event_id_str:<8} {g['home_team'][:18]:<20} {g['away_team'][:18]:<20} {g['actual_score']:<10} {g['predicted_score']:<12} {g['actual_margin']:<11} {g['predicted_margin']:<12} {g['margin_error']:+.1f}")
    
    return {
        'league_id': league_id,
        'league_name': league_name,
        'total_games': total,
        'current_correct': current_correct,
        'score_correct': score_correct,
        'current_accuracy': current_accuracy,
        'score_accuracy': score_accuracy,
        'improvement': improvement,
        'games_with_margins': len(games_with_margins),
        'avg_margin_error_abs': avg_margin_error_abs if games_with_margins else 0,
        'margin_within_5': margin_within_5,
        'margin_within_5_pct': (margin_within_5 / len(games_with_margins) * 100) if games_with_margins else 0,
        'games_with_influenced': len(games_with_influenced) if games_with_margins else 0,
        'avg_influenced_margin_error_abs': avg_influenced_margin_error_abs if games_with_margins and games_with_influenced else 0,
        'influenced_margin_within_5': influenced_margin_within_5 if games_with_margins and games_with_influenced else 0,
        'influenced_margin_within_5_pct': (influenced_margin_within_5 / len(games_with_influenced) * 100) if games_with_margins and games_with_influenced else 0
    }

def main():
    """Main function"""
    # Setup logging
    log_file = setup_logging()
    print(f"📝 Logging to: {log_file}")
    print(f"{'='*80}")
    print(f"AI Prediction vs Actual Results Analysis")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    try:
        # Find database
        db_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'data.sqlite'),
            os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor', 'data.sqlite'),
            'data.sqlite',
        ]
        
        db_path = None
        for path in db_paths:
            if os.path.exists(path):
                db_path = path
                break
        
        if not db_path:
            print("❌ Database not found")
            return
        
        print(f"📁 Using database: {db_path}")
        
        # Connect to database
        try:
            conn = sqlite3.connect(db_path)
        except Exception as e:
            print(f"❌ Error connecting to database: {e}")
            return
        
        # Get predictor
        print("🤖 Initializing AI predictor...")
        predictor = get_predictor()
        if predictor is None:
            print("❌ Predictor not available. Cannot make predictions.")
            print("   Make sure the predictor can be initialized and models are available.")
            return
        else:
            print("✅ Predictor initialized")
        
        print(f"\n🔍 Making AI predictions for all completed games and comparing vs actual results...")
        print(f"\nThis script will:")
        print(f"   1. Get all completed games from database")
        print(f"   2. Make AI predictions for each game (as if game hasn't happened)")
        print(f"   3. Compare predicted scores/margins vs actual")
        print(f"   4. Compare predicted winner vs actual winner")
        print(f"\n⭐ Focus: Score/margin prediction accuracy is the primary quality metric.")
        print(f"   This shows the TRUE predictive power of the model.")
        
        results = []
        
        for league_id, league_name in LEAGUE_MAPPINGS.items():
            try:
                result = analyze_league(conn, predictor, league_id, league_name)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"❌ Error analyzing league {league_id}: {e}")
                import traceback
                traceback.print_exc()
        
        conn.close()
        
        # Summary across all leagues
        if results:
            print(f"\n{'='*80}")
            print("📊 SUMMARY ACROSS ALL LEAGUES")
            print(f"{'='*80}")
            
            total_games = sum(r['total_games'] for r in results)
            total_current_correct = sum(r['current_correct'] for r in results)
            total_score_correct = sum(r['score_correct'] for r in results)
            
            overall_current_accuracy = (total_current_correct / total_games * 100) if total_games > 0 else 0
            overall_score_accuracy = (total_score_correct / total_games * 100) if total_games > 0 else 0
            overall_improvement = overall_score_accuracy - overall_current_accuracy
            
            print(f"\n📈 Overall Statistics:")
            print(f"   Total games analyzed: {total_games}")
            
        # Calculate overall margin stats
        all_games_with_margins = sum(r['games_with_margins'] for r in results)
        all_games_with_influenced = sum(r['games_with_influenced'] for r in results)
        
        if all_games_with_margins > 0:
            weighted_avg_margin_error = sum(r['avg_margin_error_abs'] * r['games_with_margins'] for r in results) / all_games_with_margins
            total_margin_within_5 = sum(r['margin_within_5'] for r in results)
            overall_margin_accuracy = (total_margin_within_5 / all_games_with_margins * 100) if all_games_with_margins > 0 else 0
            
            print(f"\n   ⭐ MARGIN PREDICTION COMPARISON (Primary Metric):")
            print(f"      Games analyzed: {all_games_with_margins}")
            
            print(f"\n      CURRENT METHOD (Original Predicted Scores):")
            print(f"         Average Absolute Margin Error: {weighted_avg_margin_error:.1f} points")
            print(f"         Accuracy (within 5 points): {overall_margin_accuracy:.1f}% ({total_margin_within_5}/{all_games_with_margins})")
            
            if all_games_with_influenced > 0:
                weighted_avg_influenced_error = sum(r['avg_influenced_margin_error_abs'] * r['games_with_influenced'] for r in results) / all_games_with_influenced
                total_influenced_within_5 = sum(r['influenced_margin_within_5'] for r in results)
                overall_influenced_accuracy = (total_influenced_within_5 / all_games_with_influenced * 100) if all_games_with_influenced > 0 else 0
                
                print(f"\n      INFLUENCED METHOD (Scores Adjusted to Match Predicted Winner):")
                print(f"         Average Absolute Margin Error: {weighted_avg_influenced_error:.1f} points")
                print(f"         Accuracy (within 5 points): {overall_influenced_accuracy:.1f}% ({total_influenced_within_5}/{all_games_with_influenced})")
                
                error_improvement = weighted_avg_margin_error - weighted_avg_influenced_error
                accuracy_improvement = overall_influenced_accuracy - overall_margin_accuracy
                
                print(f"\n      📊 IMPROVEMENT:")
                print(f"         Margin Error: {error_improvement:+.1f} points")
                print(f"         Accuracy: {accuracy_improvement:+.1f}%")
                if error_improvement < 0:
                    print(f"         ✅ Influenced method is BETTER (lower error by {abs(error_improvement):.1f} points)")
                elif error_improvement > 0:
                    print(f"         ⚠️  Current method is BETTER (lower error by {error_improvement:.1f} points)")
                else:
                    print(f"         ➡️  Both methods perform equally")
            
            print(f"\n   Winner Prediction (Secondary - may be biased):")
            print(f"      Winner Method Accuracy: {overall_current_accuracy:.1f}% ({total_current_correct}/{total_games})")
            print(f"      Score Method Accuracy: {overall_score_accuracy:.1f}% ({total_score_correct}/{total_games})")
            print(f"      Difference: {overall_improvement:+.1f}%")
            print(f"      ⚠️  Note: Winner accuracy may be inflated if model was trained on these games")
            
        print(f"\n📋 Per-League Breakdown:")
        print(f"   {'League':<35} {'Games':<8} {'Current Err':<12} {'Infl Err':<12} {'Current ±5':<12} {'Infl ±5':<12} {'Improvement':<12}")
        print(f"   {'-'*35} {'-'*8} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
        for r in results:
            current_err = f"{r['avg_margin_error_abs']:.1f}" if r['games_with_margins'] > 0 else "N/A"
            infl_err = f"{r['avg_influenced_margin_error_abs']:.1f}" if r['games_with_influenced'] > 0 else "N/A"
            current_acc = f"{r['margin_within_5_pct']:.1f}%" if r['games_with_margins'] > 0 else "N/A"
            infl_acc = f"{r['influenced_margin_within_5_pct']:.1f}%" if r['games_with_influenced'] > 0 else "N/A"
            
            if r['games_with_margins'] > 0 and r['games_with_influenced'] > 0:
                improvement = r['avg_margin_error_abs'] - r['avg_influenced_margin_error_abs']
                improvement_str = f"{improvement:+.1f} pts"
            else:
                improvement_str = "N/A"
            
            print(f"   {r['league_name'][:34]:<35} {r['total_games']:<8} {current_err:<12} {infl_err:<12} {current_acc:<12} {infl_acc:<12} {improvement_str:<12}")
            
            print(f"\n💡 Key Insights:")
            if all_games_with_margins > 0:
                print(f"   ⭐ MARGIN PREDICTION QUALITY:")
                print(f"      Average error: {weighted_avg_margin_error:.1f} points")
                print(f"      {overall_margin_accuracy:.1f}% of predictions within 5 points of actual margin")
                print(f"      This is the TRUE measure of prediction quality")
            
            print(f"\n   Winner Prediction:")
            if overall_improvement > 0:
                print(f"      Score method is {overall_improvement:.1f}% better at winner prediction")
                print(f"      💡 Consider using predicted scores to determine winner")
            elif overall_improvement < 0:
                print(f"      Winner method is {abs(overall_improvement):.1f}% better")
                print(f"      💡 Current method (predicted_winner) is better")
            else:
                print(f"      Both methods perform equally")
            
            print(f"\n   💡 Key Takeaway: MARGIN ACCURACY is the primary quality metric.")
            print(f"      This shows how well the model predicts actual game outcomes.")
        
        print(f"\n{'='*80}")
        print("✅ Analysis complete!")
        print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📝 Full log saved to: {log_file}")
        print(f"{'='*80}")
    
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        print(f"📝 Error logged to: {log_file}")
    finally:
        # Restore stdout and close log file
        if isinstance(sys.stdout, TeeOutput):
            sys.stdout.close()
            sys.stdout = sys.stdout.terminal

if __name__ == '__main__':
    main()

