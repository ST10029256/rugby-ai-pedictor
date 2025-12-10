#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to analyze how accuracy is determined and calculated.
Shows:
1. Current accuracy from model registry (training accuracy)
2. How to calculate accuracy from actual game results
3. Retroactive prediction accuracy if we make predictions for completed games
"""

import sqlite3
import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS

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

def load_model_registry() -> Dict[str, Any]:
    """Load model registry from various locations"""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'artifacts_optimized', 'model_registry_optimized.json'),
        os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'model_registry.json'),
        os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor', 'artifacts_optimized', 'model_registry_optimized.json'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"   Error loading {path}: {e}")
                continue
    
    return {}

def get_training_accuracy(registry: Dict[str, Any], league_id: int) -> Optional[float]:
    """Get training accuracy from model registry"""
    league_id_str = str(league_id)
    leagues = registry.get('leagues', {})
    league_data = leagues.get(league_id_str)
    
    if league_data:
        performance = league_data.get('performance', {})
        winner_accuracy = performance.get('winner_accuracy')
        if winner_accuracy is not None:
            return winner_accuracy * 100  # Convert to percentage
    return None

def get_completed_games(conn: sqlite3.Connection, league_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Get completed games for a league"""
    cursor = conn.cursor()
    
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
      AND e.status != 'Cancelled'
    ORDER BY e.date_event DESC, e.timestamp DESC
    LIMIT ?
    """
    
    cursor.execute(query, (league_id, limit))
    rows = cursor.fetchall()
    
    games = []
    for row in rows:
        games.append({
            'event_id': row[0],
            'home_team_id': row[1],
            'away_team_id': row[2],
            'home_score': row[3],
            'away_score': row[4],
            'home_team_name': row[5] or 'Unknown',
            'away_team_name': row[6] or 'Unknown',
            'date_event': row[7],
            'timestamp': row[8]
        })
    
    return games

def determine_actual_winner(home_score: int, away_score: int) -> str:
    """Determine actual winner from scores"""
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

def calculate_accuracy_from_games(games: List[Dict[str, Any]], db, use_stored_predictions: bool = True) -> Dict[str, Any]:
    """Calculate accuracy from game results"""
    total_games = len(games)
    if total_games == 0:
        return {
            'total': 0,
            'with_predictions': 0,
            'correct': 0,
            'accuracy': 0.0,
            'method': 'No games'
        }
    
    correct = 0
    with_predictions = 0
    
    for game in games:
        actual_winner = determine_actual_winner(game['home_score'], game['away_score'])
        
        if use_stored_predictions:
            prediction = get_prediction_from_firestore(db, game['event_id'])
            if prediction:
                with_predictions += 1
                predicted_winner = prediction.get('predicted_winner') or prediction.get('winner', '')
                
                # Normalize
                if predicted_winner == game['home_team_name'] or predicted_winner == 'Home':
                    predicted_winner = 'Home'
                elif predicted_winner == game['away_team_name'] or predicted_winner == 'Away':
                    predicted_winner = 'Away'
                elif predicted_winner == 'Draw':
                    predicted_winner = 'Draw'
                else:
                    continue  # Skip if can't normalize
                
                if predicted_winner == actual_winner:
                    correct += 1
    
    if with_predictions == 0:
        return {
            'total': total_games,
            'with_predictions': 0,
            'correct': 0,
            'accuracy': 0.0,
            'method': 'No stored predictions'
        }
    
    accuracy = (correct / with_predictions) * 100
    return {
        'total': total_games,
        'with_predictions': with_predictions,
        'correct': correct,
        'accuracy': accuracy,
        'method': 'Stored predictions'
    }

def analyze_league(conn: sqlite3.Connection, db, registry: Dict[str, Any], league_id: int, league_name: str):
    """Analyze accuracy for a specific league"""
    print(f"\n{'='*80}")
    print(f"League: {league_name} (ID: {league_id})")
    print(f"{'='*80}")
    
    # 1. Training accuracy from model registry
    training_accuracy = get_training_accuracy(registry, league_id)
    if training_accuracy is not None:
        print(f"\n1. Training Accuracy (from model registry):")
        print(f"   {training_accuracy:.1f}%")
        print(f"   (This is the accuracy on the training/test set used to train the model)")
    else:
        print(f"\n1. Training Accuracy: Not found in model registry")
    
    # 2. Get completed games
    all_games = get_completed_games(conn, league_id, limit=100)
    last_10_games = all_games[:10] if len(all_games) >= 10 else all_games
    
    print(f"\n2. Completed Games Available:")
    print(f"   Total completed games: {len(all_games)}")
    print(f"   Last 10 games: {len(last_10_games)}")
    
    # 3. Check for stored predictions
    print(f"\n3. Stored Predictions Analysis:")
    stored_predictions_count = 0
    for game in last_10_games:
        if get_prediction_from_firestore(db, game['event_id']):
            stored_predictions_count += 1
    
    print(f"   Predictions in Firestore for last 10 games: {stored_predictions_count}/10")
    
    if stored_predictions_count > 0:
        # Calculate accuracy from stored predictions
        accuracy_data = calculate_accuracy_from_games(last_10_games, db, use_stored_predictions=True)
        print(f"\n4. Last 10 Games Accuracy (from stored predictions):")
        print(f"   Correct: {accuracy_data['correct']}/{accuracy_data['with_predictions']}")
        print(f"   Accuracy: {accuracy_data['accuracy']:.1f}%")
    else:
        print(f"\n4. Last 10 Games Accuracy:")
        print(f"   Cannot calculate - no predictions stored in Firestore")
        print(f"   ⚠️  This is why the widget shows N/A!")
    
    # 5. Show sample of last 10 games
    if last_10_games:
        print(f"\n5. Sample of Last 10 Games:")
        print(f"   {'Date':<12} {'Home':<25} {'Away':<25} {'Score':<12} {'Winner':<10} {'Prediction'}")
        print(f"   {'-'*12} {'-'*25} {'-'*25} {'-'*12} {'-'*10} {'-'*15}")
        for game in last_10_games[:5]:  # Show first 5
            date_str = str(game['date_event'])[:10] if game['date_event'] else 'Unknown'
            home = game['home_team_name'][:23]
            away = game['away_team_name'][:23]
            score = f"{game['home_score']}-{game['away_score']}"
            winner = determine_actual_winner(game['home_score'], game['away_score'])
            
            prediction = get_prediction_from_firestore(db, game['event_id'])
            pred_str = 'Stored' if prediction else 'None'
            
            print(f"   {date_str:<12} {home:<25} {away:<25} {score:<12} {winner:<10} {pred_str}")
        
        if len(last_10_games) > 5:
            print(f"   ... and {len(last_10_games) - 5} more games")
    
    # 6. Recommendations
    print(f"\n6. Recommendations:")
    if stored_predictions_count == 0:
        print(f"   ⚠️  No predictions are being stored in Firestore!")
        print(f"   📝 To fix this:")
        print(f"      1. Ensure predictions are saved to Firestore when made")
        print(f"      2. Check the 'predictions' collection in Firestore")
        print(f"      3. Predictions should be stored with event_id as document ID")
    else:
        print(f"   ✅ Predictions are being stored")
        print(f"   📊 Last 10 games accuracy: {accuracy_data['accuracy']:.1f}%")

def main():
    """Main function"""
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
    
    # Load model registry
    print(f"📊 Loading model registry...")
    registry = load_model_registry()
    if registry:
        print(f"✅ Model registry loaded")
    else:
        print(f"⚠️  Model registry not found")
        registry = {}
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return
    
    # Get Firestore client
    db = get_firestore_client()
    if db is None:
        print("⚠️  Firestore not available. Cannot check stored predictions.")
    else:
        print("✅ Firestore connected")
    
    print(f"\n🔍 Analyzing accuracy calculation for all {len(LEAGUE_MAPPINGS)} leagues...")
    print(f"\nThis script shows:")
    print(f"  1. Training accuracy (from model registry)")
    print(f"  2. Available completed games")
    print(f"  3. Stored predictions in Firestore")
    print(f"  4. Calculated accuracy from stored predictions")
    print(f"  5. Recommendations")
    
    for league_id, league_name in LEAGUE_MAPPINGS.items():
        try:
            analyze_league(conn, db, registry, league_id, league_name)
        except Exception as e:
            print(f"❌ Error analyzing league {league_id}: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    
    print(f"\n{'='*80}")
    print("✅ Analysis complete!")
    print(f"{'='*80}")
    print(f"\n💡 Key Findings:")
    print(f"   - Training accuracy comes from model registry (winner_accuracy)")
    print(f"   - Last 10 games accuracy requires predictions stored in Firestore")
    print(f"   - If no predictions are stored, the widget will show N/A")
    print(f"   - To show last 10 games accuracy, predictions must be saved when made")

if __name__ == '__main__':
    main()

