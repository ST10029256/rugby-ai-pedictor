#!/usr/bin/env python3
"""
Test AI-Only Accuracy on Historical Games
Tests the optimized AI system without SportDevs API to avoid rate limiting
"""

import os
import sys
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from prediction.features import build_feature_table, FeatureConfig

# Configuration
LEAGUE_CONFIGS = {
    4986: {"name": "Rugby Championship", "neutral_mode": False},
    4446: {"name": "United Rugby Championship", "neutral_mode": False},
    5069: {"name": "Currie Cup", "neutral_mode": False},
    4574: {"name": "Rugby World Cup", "neutral_mode": True},
}

def get_teams():
    """Get team names"""
    try:
        conn = sqlite3.connect('data.sqlite')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM team")
        teams = dict(cursor.fetchall())
        conn.close()
        return teams
    except:
        return {}

def test_league_accuracy(league_id: int, test_games: int = 20):
    """Test AI accuracy on historical games for a league"""
    
    print(f"\n{'='*80}")
    print(f"TESTING: {LEAGUE_CONFIGS[league_id]['name']}")
    print(f"{'='*80}")
    
    # Load model
    model_path = f'artifacts_optimized/league_{league_id}_model_optimized.pkl'
    if not os.path.exists(model_path):
        model_path = f'artifacts/league_{league_id}_model.pkl'
    
    if not os.path.exists(model_path):
        print(f"[ERROR] Model not found for league {league_id}")
        return None
    
    # Load model
    import pickle
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    
    # Get historical data
    conn = sqlite3.connect('data.sqlite')
    config = FeatureConfig(elo_priors=None, elo_k=24.0, 
                          neutral_mode=LEAGUE_CONFIGS[league_id]["neutral_mode"])
    df = build_feature_table(conn, config)
    conn.close()
    
    # Filter for this league with completed games
    hist = df[
        (df["league_id"] == league_id) & 
        df["home_win"].notna() &
        (df["home_score"] > 0) &  # Ensure scores exist
        (df["away_score"] > 0)
    ].copy()
    
    if len(hist) == 0:
        print(f"[ERROR] No completed games found for league {league_id}")
        return None
    
    # Get team names
    team_names = get_teams()
    
    # Test on most recent games
    test_data = hist.tail(test_games)
    
    print(f"Testing on {len(test_data)} most recent games...")
    
    # Test predictions
    correct_predictions = 0
    total_predictions = 0
    confidence_scores = []
    
    results = []
    
    for idx, game in test_data.iterrows():
        try:
            # Get actual result
            actual_home_win = int(game['home_win'])
            home_team = team_names.get(int(game['home_team_id']), f"Team {game['home_team_id']}")
            away_team = team_names.get(int(game['away_team_id']), f"Team {game['away_team_id']}")
            match_date = str(game['date_event'])[:10]
            
            # Get feature columns and prepare data
            feature_cols = model_data.get('feature_columns', [])
            X = []
            for col in feature_cols:
                X.append(game.get(col, 0.0))
            X = np.array(X).reshape(1, -1)
            
            # Get models
            models = model_data.get('models', {})
            clf = models.get('clf') or models.get('gbdt_clf')
            
            if not clf:
                continue
            
            # Make AI prediction
            if hasattr(clf, 'predict_proba'):
                proba = clf.predict_proba(X)
                home_win_prob = proba[0, 1] if len(proba[0]) > 1 else proba[0, 0]
            else:
                pred = clf.predict(X)[0]
                home_win_prob = 1.0 if pred == 1 else 0.0
            
            # Get score predictions
            reg_home = models.get('reg_home')
            reg_away = models.get('reg_away')
            
            if reg_home and reg_away:
                home_score = max(0, reg_home.predict(X)[0])
                away_score = max(0, reg_away.predict(X)[0])
            else:
                # Fallback to expected scores
                home_score = 20 + home_win_prob * 20
                away_score = 20 + (1 - home_win_prob) * 20
            
            # Determine predicted winner
            predicted_winner = 1 if home_win_prob > 0.5 else 0
            
            # Calculate confidence
            confidence = home_win_prob * 100 if home_win_prob > 0.5 else (1 - home_win_prob) * 100
            
            # Check accuracy
            is_correct = (predicted_winner == actual_home_win)
            
            if is_correct:
                correct_predictions += 1
            
            total_predictions += 1
            confidence_scores.append(confidence)
            
            # Store result
            results.append({
                'date': match_date,
                'home_team': home_team,
                'away_team': away_team,
                'actual_home_win': actual_home_win,
                'predicted_winner': predicted_winner,
                'home_win_prob': home_win_prob,
                'confidence': confidence,
                'is_correct': is_correct,
                'home_score': home_score,
                'away_score': away_score
            })
            
            # Print result
            status = "[OK]" if is_correct else "[X]"
            print(f"{status} AI: {home_win_prob:.1%} ({confidence:.0f}%) | {home_team} vs {away_team}")
            
        except Exception as e:
            print(f"[ERROR] Error processing game {game.get('event_id', 'unknown')}: {e}")
            continue
    
    if total_predictions == 0:
        print("[ERROR] No predictions generated")
        return None
    
    # Calculate accuracy
    accuracy = correct_predictions / total_predictions
    avg_confidence = np.mean(confidence_scores)
    
    print(f"\nRESULTS for {LEAGUE_CONFIGS[league_id]['name']}:")
    print(f"   AI Accuracy: {accuracy:.1%} ({correct_predictions}/{total_predictions})")
    print(f"   Avg Confidence: {avg_confidence:.1f}%")
    
    return {
        'league_id': league_id,
        'league_name': LEAGUE_CONFIGS[league_id]['name'],
        'total_games': total_predictions,
        'accuracy': accuracy,
        'avg_confidence': avg_confidence,
        'results': results
    }

def main():
    print("\n" + "="*80)
    print("AI-ONLY ACCURACY TEST ON HISTORICAL GAMES")
    print("="*80)
    print("Testing the optimized AI system without SportDevs API")
    
    all_results = []
    
    # Test each league
    for league_id in [4986, 4446, 5069, 4574]:  # Include Rugby World Cup
        try:
            result = test_league_accuracy(league_id, test_games=20)
            if result:
                all_results.append(result)
        except Exception as e:
            print(f"[ERROR] Error testing league {league_id}: {e}")
            continue
    
    # Overall summary
    if all_results:
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        
        total_games = sum(r['total_games'] for r in all_results)
        total_correct = sum(r['accuracy'] * r['total_games'] for r in all_results)
        
        overall_accuracy = total_correct / total_games
        overall_confidence = np.mean([r['avg_confidence'] for r in all_results])
        
        print(f"\nOVERALL PERFORMANCE:")
        print(f"   Total Games Tested: {total_games}")
        print(f"   AI Accuracy: {overall_accuracy:.1%}")
        print(f"   Avg Confidence: {overall_confidence:.1f}%")
        
        print(f"\nBY LEAGUE:")
        for result in all_results:
            print(f"   {result['league_name']}:")
            print(f"     Accuracy: {result['accuracy']:.1%} | Confidence: {result['avg_confidence']:.1f}%")
        
        # Performance rating
        if overall_accuracy >= 0.80:
            rating = "EXCELLENT (8/10)"
        elif overall_accuracy >= 0.75:
            rating = "VERY GOOD (7.5/10)"
        elif overall_accuracy >= 0.70:
            rating = "GOOD (7/10)"
        elif overall_accuracy >= 0.65:
            rating = "FAIR (6.5/10)"
        else:
            rating = "NEEDS IMPROVEMENT (6/10)"
        
        print(f"\nFINAL RATING: {rating}")
        print(f"Your AI is {overall_accuracy:.1%} accurate on historical games!")
        
        if overall_accuracy >= 0.70:
            print(f"[SUCCESS] AI performance is solid and reliable")
        else:
            print(f"[WARNING] AI performance could be improved")
    
    else:
        print("[ERROR] No results generated")

if __name__ == "__main__":
    main()
