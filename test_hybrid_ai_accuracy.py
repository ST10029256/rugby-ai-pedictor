#!/usr/bin/env python3
"""
Test Hybrid AI Accuracy on Historical Games
Tests the exact hybrid AI system on past games without retraining
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
from prediction.hybrid_predictor import HybridPredictor

# Configuration
SPORTDEVS_API_KEY = "qwh9orOkZESulf4QBhf0IQ"
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

def test_league_accuracy(league_id: int, test_games: int = 30):
    """Test hybrid AI accuracy on historical games for a league"""
    
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
    
    # Initialize hybrid predictor
    predictor = HybridPredictor(model_path, SPORTDEVS_API_KEY)
    
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
    ai_only_correct = 0
    hybrid_correct = 0
    ai_confidence_scores = []
    hybrid_confidence_scores = []
    
    results = []
    
    for idx, game in test_data.iterrows():
        try:
            # Get actual result
            actual_home_win = int(game['home_win'])
            home_team = team_names.get(int(game['home_team_id']), f"Team {game['home_team_id']}")
            away_team = team_names.get(int(game['away_team_id']), f"Team {game['away_team_id']}")
            match_date = str(game['date_event'])[:10]
            
            # Make hybrid prediction
            event_id = game.get('event_id', 0)
            if event_id is None:
                event_id = 0
            hybrid_result = predictor.smart_ensemble(
                int(game['home_team_id']), 
                int(game['away_team_id']), 
                match_date, 
                int(event_id)
            )
            
            if hybrid_result:
                # Get AI-only prediction
                ai_pred = hybrid_result['ai_prediction']
                ai_home_win_prob = ai_pred['home_win_prob']
                ai_predicted_winner = 1 if ai_home_win_prob > 0.5 else 0
                ai_confidence = ai_pred['confidence']
                
                # Get hybrid prediction
                hybrid_home_win_prob = hybrid_result['hybrid_home_win_prob']
                hybrid_predicted_winner = 1 if hybrid_home_win_prob > 0.5 else 0
                hybrid_confidence = hybrid_result['hybrid_confidence']
                
                # Check accuracy
                ai_correct = (ai_predicted_winner == actual_home_win)
                hybrid_correct = (hybrid_predicted_winner == actual_home_win)
                
                if ai_correct:
                    ai_only_correct += 1
                if hybrid_correct:
                    hybrid_correct += 1
                
                total_predictions += 1
                ai_confidence_scores.append(ai_confidence)
                hybrid_confidence_scores.append(hybrid_confidence)
                
                # Store result
                results.append({
                    'date': match_date,
                    'home_team': home_team,
                    'away_team': away_team,
                    'actual_home_win': actual_home_win,
                    'ai_predicted': ai_predicted_winner,
                    'ai_prob': ai_home_win_prob,
                    'ai_confidence': ai_confidence,
                    'ai_correct': ai_correct,
                    'hybrid_predicted': hybrid_predicted_winner,
                    'hybrid_prob': hybrid_home_win_prob,
                    'hybrid_confidence': hybrid_confidence,
                    'hybrid_correct': hybrid_correct,
                    'bookmaker_count': hybrid_result.get('bookmaker_prediction', {}).get('bookmaker_count', 0)
                })
                
                # Print result
                status_ai = "[OK]" if ai_correct else "[X]"
                status_hybrid = "[OK]" if hybrid_correct else "[X]"
                print(f"{status_ai} AI: {ai_home_win_prob:.1%} ({ai_confidence:.0%}) | {status_hybrid} Hybrid: {hybrid_home_win_prob:.1%} ({hybrid_confidence:.0%}) | {home_team} vs {away_team}")
            
        except Exception as e:
            print(f"[ERROR] Error processing game {game.get('event_id', 'unknown')}: {e}")
            continue
    
    if total_predictions == 0:
        print("[ERROR] No predictions generated")
        return None
    
    # Calculate accuracies
    ai_accuracy = ai_only_correct / total_predictions
    hybrid_accuracy = hybrid_correct / total_predictions
    avg_ai_confidence = np.mean(ai_confidence_scores)
    avg_hybrid_confidence = np.mean(hybrid_confidence_scores)
    
    print(f"\nRESULTS for {LEAGUE_CONFIGS[league_id]['name']}:")
    print(f"   AI-Only Accuracy: {ai_accuracy:.1%} ({ai_only_correct}/{total_predictions})")
    print(f"   Hybrid Accuracy: {hybrid_accuracy:.1%} ({hybrid_correct}/{total_predictions})")
    print(f"   Improvement: {hybrid_accuracy - ai_accuracy:+.1%}")
    print(f"   Avg AI Confidence: {avg_ai_confidence:.1%}")
    print(f"   Avg Hybrid Confidence: {avg_hybrid_confidence:.1%}")
    
    return {
        'league_id': league_id,
        'league_name': LEAGUE_CONFIGS[league_id]['name'],
        'total_games': total_predictions,
        'ai_accuracy': ai_accuracy,
        'hybrid_accuracy': hybrid_accuracy,
        'improvement': hybrid_accuracy - ai_accuracy,
        'avg_ai_confidence': avg_ai_confidence,
        'avg_hybrid_confidence': avg_hybrid_confidence,
        'results': results
    }

def main():
    print("\n" + "="*80)
    print("HYBRID AI ACCURACY TEST ON HISTORICAL GAMES")
    print("="*80)
    print("Testing the exact hybrid AI system on past games without retraining")
    
    all_results = []
    
    # Test each league with smaller sample to avoid rate limiting
    for league_id in [4986, 4446, 5069]:  # Skip Rugby World Cup for now
        try:
            result = test_league_accuracy(league_id, test_games=15)  # Increased back to 15
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
        total_ai_correct = sum(r['ai_accuracy'] * r['total_games'] for r in all_results)
        total_hybrid_correct = sum(r['hybrid_accuracy'] * r['total_games'] for r in all_results)
        
        overall_ai_accuracy = total_ai_correct / total_games
        overall_hybrid_accuracy = total_hybrid_correct / total_games
        overall_improvement = overall_hybrid_accuracy - overall_ai_accuracy
        
        print(f"\nOVERALL PERFORMANCE:")
        print(f"   Total Games Tested: {total_games}")
        print(f"   AI-Only Accuracy: {overall_ai_accuracy:.1%}")
        print(f"   Hybrid Accuracy: {overall_hybrid_accuracy:.1%}")
        print(f"   Overall Improvement: {overall_improvement:+.1%}")
        
        print(f"\nBY LEAGUE:")
        for result in all_results:
            print(f"   {result['league_name']}:")
            print(f"     AI: {result['ai_accuracy']:.1%} | Hybrid: {result['hybrid_accuracy']:.1%} | Improvement: {result['improvement']:+.1%}")
        
        # Performance rating
        if overall_hybrid_accuracy >= 0.80:
            rating = "LEGENDARY (9/10)"
        elif overall_hybrid_accuracy >= 0.75:
            rating = "WORLD-CLASS (8.5/10)"
        elif overall_hybrid_accuracy >= 0.70:
            rating = "EXCELLENT (8/10)"
        elif overall_hybrid_accuracy >= 0.65:
            rating = "VERY GOOD (7.5/10)"
        else:
            rating = "GOOD (7/10)"
        
        print(f"\nFINAL RATING: {rating}")
        print(f"Your Hybrid AI is {overall_hybrid_accuracy:.1%} accurate on historical games!")
        
        if overall_improvement > 0:
            print(f"[SUCCESS] Hybrid system improves accuracy by {overall_improvement:+.1%}")
        else:
            print(f"[WARNING] Hybrid system shows {overall_improvement:+.1%} change (may need tuning)")
    
    else:
        print("[ERROR] No results generated")

if __name__ == "__main__":
    main()
