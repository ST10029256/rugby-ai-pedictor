#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to check the last 10 completed games for all leagues
and see if predictions exist for them.
"""

import sqlite3
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path to import prediction modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS

def get_firestore_client():
    """Get Firestore client"""
    try:
        from firebase_admin import firestore, initialize_app
        try:
            initialize_app()
        except ValueError:
            pass  # Already initialized
        return firestore.client()
    except ImportError:
        print("⚠️  firebase_admin not available. Cannot check Firestore predictions.")
        return None
    except Exception as e:
        print(f"⚠️  Error initializing Firestore: {e}")
        return None

def get_last_10_games(conn: sqlite3.Connection, league_id: int) -> List[Dict[str, Any]]:
    """Get last 10 completed games for a league"""
    cursor = conn.cursor()
    
    query = """
    SELECT e.id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, 
           ht.name as home_team_name, at.name as away_team_name,
           e.date_event, e.timestamp, e.status
    FROM event e
    LEFT JOIN team ht ON e.home_team_id = ht.id
    LEFT JOIN team at ON e.away_team_id = at.id
    WHERE e.league_id = ? 
      AND e.home_score IS NOT NULL 
      AND e.away_score IS NOT NULL
      AND e.status != 'Postponed'
      AND e.status != 'Cancelled'
    ORDER BY e.date_event DESC, e.timestamp DESC
    LIMIT 10
    """
    
    cursor.execute(query, (league_id,))
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
            'timestamp': row[8],
            'status': row[9]
        })
    
    return games

def get_prediction_from_firestore(db, event_id: int) -> Optional[Dict[str, Any]]:
    """Get prediction from Firestore for a specific event"""
    if db is None:
        return None
    
    try:
        prediction_ref = db.collection('predictions').document(str(event_id))
        prediction_doc = prediction_ref.get()
        
        if prediction_doc.exists:
            return prediction_doc.to_dict()
        return None
    except Exception as e:
        print(f"   ⚠️  Error checking Firestore for event {event_id}: {e}")
        return None

def determine_winner(home_score: int, away_score: int) -> str:
    """Determine actual winner from scores"""
    if home_score > away_score:
        return 'Home'
    elif away_score > home_score:
        return 'Away'
    else:
        return 'Draw'

def check_league(conn: sqlite3.Connection, db, league_id: int, league_name: str):
    """Check last 10 games for a specific league"""
    print(f"\n{'='*80}")
    print(f"League: {league_name} (ID: {league_id})")
    print(f"{'='*80}")
    
    games = get_last_10_games(conn, league_id)
    
    if not games:
        print(f"❌ No completed games found for {league_name}")
        return
    
    print(f"✅ Found {len(games)} completed games")
    print(f"\n{'Date':<12} {'Home Team':<30} {'Away Team':<30} {'Score':<12} {'Winner':<10} {'Prediction':<15} {'Match'}")
    print(f"{'-'*12} {'-'*30} {'-'*30} {'-'*12} {'-'*10} {'-'*15} {'-'*5}")
    
    predictions_found = 0
    correct_predictions = 0
    
    for game in games:
        event_id = game['event_id']
        home_team = game['home_team_name']
        away_team = game['away_team_name']
        home_score = game['home_score']
        away_score = game['away_score']
        date = game['date_event'] or 'Unknown'
        
        # Determine actual winner
        actual_winner = determine_winner(home_score, away_score)
        
        # Get prediction from Firestore
        prediction = get_prediction_from_firestore(db, event_id)
        
        if prediction:
            predictions_found += 1
            predicted_winner = prediction.get('predicted_winner') or prediction.get('winner', 'N/A')
            
            # Normalize predicted winner
            if predicted_winner == home_team or predicted_winner == 'Home':
                predicted_winner = 'Home'
            elif predicted_winner == away_team or predicted_winner == 'Away':
                predicted_winner = 'Away'
            elif predicted_winner == 'Draw':
                predicted_winner = 'Draw'
            
            match = '✅' if predicted_winner == actual_winner else '❌'
            if match == '✅':
                correct_predictions += 1
        else:
            predicted_winner = 'N/A'
            match = '-'
        
        score_str = f"{home_score}-{away_score}"
        date_str = str(date)[:10] if date else 'Unknown'
        
        print(f"{date_str:<12} {home_team[:28]:<30} {away_team[:28]:<30} {score_str:<12} {actual_winner:<10} {predicted_winner:<15} {match}")
    
    print(f"\n📊 Summary:")
    print(f"   Total games: {len(games)}")
    print(f"   Predictions found: {predictions_found}")
    print(f"   Correct predictions: {correct_predictions}")
    if predictions_found > 0:
        accuracy = (correct_predictions / predictions_found) * 100
        print(f"   Accuracy: {correct_predictions}/{predictions_found} ({accuracy:.1f}%)")
    else:
        print(f"   ⚠️  No predictions found in Firestore!")
    
    if len(games) < 10:
        print(f"   ⚠️  Only {len(games)} games available (need 10 for full accuracy)")

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
        print("❌ Database not found. Tried:")
        for path in db_paths:
            print(f"   - {path}")
        return
    
    print(f"📁 Using database: {db_path}")
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return
    
    # Get Firestore client
    db = get_firestore_client()
    if db is None:
        print("⚠️  Firestore not available. Will only show game data, not predictions.")
    
    # Check all leagues
    print(f"\n🔍 Checking last 10 games for all {len(LEAGUE_MAPPINGS)} leagues...")
    
    for league_id, league_name in LEAGUE_MAPPINGS.items():
        try:
            check_league(conn, db, league_id, league_name)
        except Exception as e:
            print(f"❌ Error checking league {league_id} ({league_name}): {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()
    
    print(f"\n{'='*80}")
    print("✅ Check complete!")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()

