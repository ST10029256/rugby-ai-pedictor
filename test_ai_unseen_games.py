#!/usr/bin/env python3
"""
AI Testing Script for Unseen Games
Tests the AI model's performance on games it has never seen during training
"""

import sqlite3
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from prediction.features import build_feature_table, FeatureConfig
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

def load_model(league_id):
    """Load model for league"""
    try:
        with open(f'artifacts/league_{league_id}_model.pkl', 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        print(f"Error loading model for league {league_id}: {e}")
        return None

def get_test_games(league_id, cutoff_date=None):
    """Get games for testing - either recent games or games after a cutoff date"""
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    if cutoff_date:
        # Test on games after a specific date (truly unseen)
        query = """
        SELECT e.id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, e.date_event,
               t1.name as home_team_name, t2.name as away_team_name
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = ? 
        AND e.home_score IS NOT NULL 
        AND e.away_score IS NOT NULL
        AND e.date_event > ?
        ORDER BY e.date_event ASC
        """
        cursor.execute(query, (league_id, cutoff_date))
    else:
        # Test on most recent 20% of games
        query = """
        SELECT e.id, e.home_team_id, e.away_team_id, e.home_score, e.away_score, e.date_event,
               t1.name as home_team_name, t2.name as away_team_name
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = ? 
        AND e.home_score IS NOT NULL 
        AND e.away_score IS NOT NULL
        ORDER BY e.date_event ASC
        """
        cursor.execute(query, (league_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

def test_ai_performance(league_id, test_type="recent"):
    """
    Test AI performance on unseen games
    test_type: "recent" (most recent 20%), "cutoff" (after specific date), or "all_recent" (all recent games)
    """
    print(f"\n{'='*60}")
    print(f"TESTING AI PERFORMANCE - LEAGUE {league_id}")
    print(f"{'='*60}")
    
    # Load model
    model_data = load_model(league_id)
    if not model_data:
        print(f"ERROR Could not load model for league {league_id}")
        return None
    
    # Get league name
    league_name = model_data.get('league_name', f'League {league_id}')
    print(f"League: {league_name}")
    
    # Determine test strategy
    if test_type == "cutoff":
        # Use a cutoff date - test on games after this date
        cutoff_date = "2024-10-01"  # Test on games after October 1, 2024
        test_games = get_test_games(league_id, cutoff_date)
        print(f"Testing on games after {cutoff_date}")
    else:
        # Test on most recent games
        all_games = get_test_games(league_id)
        test_size = max(10, len(all_games) // 5)  # At least 10 games or 20%
        test_games = all_games[-test_size:]  # Most recent games
        print(f"Testing on most recent {len(test_games)} games out of {len(all_games)} total")
    
    if len(test_games) < 5:
        print(f"WARNING  Not enough test games ({len(test_games)}). Need at least 5 games for meaningful testing.")
        return None
    
    print(f"Test games: {len(test_games)}")
    
    # Get models and features
    models = model_data.get('models', {})
    winner_model = models.get('gbdt_clf', models.get('clf'))
    home_model = models.get('gbdt_reg_home', models.get('reg_home'))
    away_model = models.get('gbdt_reg_away', models.get('reg_away'))
    scaler = model_data.get('scaler')
    expected_features = model_data.get('feature_columns', [])
    
    if not winner_model:
        print("ERROR No winner prediction model found")
        return None
    
    if not home_model or not away_model:
        print("WARNING No score prediction models found - will only test win/lose")
        score_models_available = False
    else:
        score_models_available = True
    
    # Test predictions
    correct_predictions_classifier = 0
    correct_predictions_scores = 0
    total_predictions = 0
    predictions_details = []
    
    # Score prediction tracking
    home_score_errors = []
    away_score_errors = []
    total_score_errors = []
    
    print(f"\nTesting predictions on {len(test_games)} games...")
    print("-" * 60)
    
    for i, game in enumerate(test_games):
        event_id, home_id, away_id, home_score, away_score, date_event, home_team_name, away_team_name = game
        
        try:
            # Build feature table at this point in time (before the match)
            conn = sqlite3.connect('data.sqlite')
            historical_df = build_feature_table(conn, FeatureConfig(elo_k=24.0, neutral_mode=(league_id == 4574)))
            conn.close()
            
            # Find this exact match in historical data
            match_data = historical_df[
                (historical_df['home_team_id'] == home_id) & 
                (historical_df['away_team_id'] == away_id) &
                (historical_df['date_event'] == date_event)
            ]
            
            if len(match_data) == 0:
                print(f"WARNING  Game {i+1}: No feature data found for {home_team_name} vs {away_team_name}")
                continue
            
            # Get historical instance
            historical_instance = match_data.iloc[0]
            
            # Build feature vector
            feature_vector = pd.Series(index=expected_features, dtype=float)
            for feature in expected_features:
                if feature in historical_instance.index:
                    feature_vector[feature] = historical_instance[feature]
                else:
                    feature_vector[feature] = 0.0
            
            # Make predictions
            feature_array = np.array(feature_vector.values).reshape(1, -1)
            
            # Scale if scaler available
            if scaler:
                feature_array_scaled = scaler.transform(feature_array)
            else:
                feature_array_scaled = feature_array
            
            # Winner prediction (from classification model)
            predicted_proba = winner_model.predict_proba(feature_array)[0]
            
            if len(predicted_proba) >= 2:
                predicted_home_wins_classifier = predicted_proba[1] > 0.5
                confidence = max(predicted_proba[1], predicted_proba[0])
            else:
                predicted_home_wins_classifier = predicted_proba[0] > 0.5
                confidence = predicted_proba[0]
            
            # Score predictions
            predicted_home_score = None
            predicted_away_score = None
            predicted_home_wins_scores = None
            
            if score_models_available:
                try:
                    predicted_home_score = int(round(home_model.predict(feature_array_scaled)[0]))
                    predicted_away_score = int(round(away_model.predict(feature_array_scaled)[0]))
                    # Ensure reasonable score ranges
                    predicted_home_score = max(0, min(100, predicted_home_score))
                    predicted_away_score = max(0, min(100, predicted_away_score))
                    
                    # Determine winner based on predicted scores
                    predicted_home_wins_scores = predicted_home_score > predicted_away_score
                    
                except Exception as e:
                    print(f"WARNING Score prediction error: {e}")
                    predicted_home_score = None
                    predicted_away_score = None
                    predicted_home_wins_scores = None
            
            # Actual result
            actual_home_wins = home_score > away_score
            actual_winner = home_team_name if actual_home_wins else away_team_name
            
            # Winner predictions from both methods
            predicted_winner_classifier = home_team_name if predicted_home_wins_classifier else away_team_name
            predicted_winner_scores = home_team_name if predicted_home_wins_scores else away_team_name if predicted_home_wins_scores is not None else "Unknown"
            
            # Check if predictions are correct
            is_correct_classifier = predicted_home_wins_classifier == actual_home_wins
            is_correct_scores = predicted_home_wins_scores == actual_home_wins if predicted_home_wins_scores is not None else False
            
            if is_correct_classifier:
                correct_predictions_classifier += 1
            
            if is_correct_scores:
                correct_predictions_scores += 1
            
            total_predictions += 1
            
            # Calculate score errors if available
            home_score_error = None
            away_score_error = None
            total_score_error = None
            
            if score_models_available and predicted_home_score is not None and predicted_away_score is not None:
                home_score_error = abs(predicted_home_score - home_score)
                away_score_error = abs(predicted_away_score - away_score)
                total_score_error = home_score_error + away_score_error
                
                home_score_errors.append(home_score_error)
                away_score_errors.append(away_score_error)
                total_score_errors.append(total_score_error)
            
            # Store details
            predictions_details.append({
                'date': str(date_event)[:10],
                'home_team': home_team_name,
                'away_team': away_team_name,
                'actual_score': f"{home_score}-{away_score}",
                'predicted_score': f"{predicted_home_score}-{predicted_away_score}" if predicted_home_score is not None else "N/A",
                'actual_winner': actual_winner,
                'predicted_winner_classifier': predicted_winner_classifier,
                'predicted_winner_scores': predicted_winner_scores,
                'confidence': f"{confidence*100:.1f}%",
                'correct_classifier': is_correct_classifier,
                'correct_scores': is_correct_scores,
                'home_score_error': home_score_error,
                'away_score_error': away_score_error,
                'total_score_error': total_score_error
            })
            
            # Print result
            status_classifier = "CORRECT" if is_correct_classifier else "ERROR"
            status_scores = "CORRECT" if is_correct_scores else "ERROR"
            
            print(f"{status_classifier}/{status_scores} Game {i+1}: {home_team_name} vs {away_team_name}")
            print(f"   Actual: {actual_winner} ({home_score}-{away_score})")
            print(f"   Classifier: {predicted_winner_classifier} ({confidence*100:.1f}% confidence)")
            print(f"   Score-based: {predicted_winner_scores} ({predicted_home_score}-{predicted_away_score})")
            if predicted_home_score is not None and predicted_away_score is not None:
                print(f"   Score Error: {home_score_error}+{away_score_error}={total_score_error} points")
            
        except Exception as e:
            print(f"WARNING  Game {i+1}: Error processing {home_team_name} vs {away_team_name}: {e}")
            continue
    
    # Calculate final results
    if total_predictions == 0:
        print("ERROR No predictions could be made")
        return None
    
    accuracy_classifier = correct_predictions_classifier / total_predictions
    accuracy_scores = correct_predictions_scores / total_predictions
    print(f"\n{'='*60}")
    print(f"FINAL RESULTS - {league_name}")
    print(f"{'='*60}")
    print(f"WIN/LOSE PREDICTION COMPARISON:")
    print(f"   Classifier Model: {correct_predictions_classifier}/{total_predictions} ({accuracy_classifier*100:.1f}%)")
    print(f"   Score-based Model: {correct_predictions_scores}/{total_predictions} ({accuracy_scores*100:.1f}%)")
    print(f"   Difference: {accuracy_classifier*100 - accuracy_scores*100:+.1f} percentage points")
    print(f"DATE Test Period: {test_games[0][5][:10]} to {test_games[-1][5][:10]}")
    
    # Score prediction analysis
    if score_models_available and home_score_errors:
        home_mae = np.mean(home_score_errors)
        away_mae = np.mean(away_score_errors)
        overall_mae = np.mean(total_score_errors)
        
        print(f"\nSCORE PREDICTION ACCURACY:")
        print(f"   Home Score MAE: {home_mae:.1f} points")
        print(f"   Away Score MAE: {away_mae:.1f} points")
        print(f"   Overall MAE: {overall_mae:.1f} points")
        
        # Score prediction within ranges
        home_within_3 = len([e for e in home_score_errors if e <= 3])
        home_within_5 = len([e for e in home_score_errors if e <= 5])
        away_within_3 = len([e for e in away_score_errors if e <= 3])
        away_within_5 = len([e for e in away_score_errors if e <= 5])
        
        print(f"   Home Score Within 3 points: {home_within_3}/{len(home_score_errors)} ({home_within_3/len(home_score_errors)*100:.1f}%)")
        print(f"   Home Score Within 5 points: {home_within_5}/{len(home_score_errors)} ({home_within_5/len(home_score_errors)*100:.1f}%)")
        print(f"   Away Score Within 3 points: {away_within_3}/{len(away_score_errors)} ({away_within_3/len(away_score_errors)*100:.1f}%)")
        print(f"   Away Score Within 5 points: {away_within_5}/{len(away_score_errors)} ({away_within_5/len(away_score_errors)*100:.1f}%)")
    
    # Additional analysis
    if predictions_details:
        details_df = pd.DataFrame(predictions_details)
        
        # Confidence analysis
        high_conf_predictions = details_df[details_df['confidence'].str.rstrip('%').astype(float) > 70]
        if len(high_conf_predictions) > 0:
            high_conf_accuracy_classifier = high_conf_predictions['correct_classifier'].mean()
            high_conf_accuracy_scores = high_conf_predictions['correct_scores'].mean()
            print(f"TARGET High Confidence (>70%): {len(high_conf_predictions)} predictions")
            print(f"   Classifier: {high_conf_accuracy_classifier*100:.1f}% accuracy")
            print(f"   Score-based: {high_conf_accuracy_scores*100:.1f}% accuracy")
    
    return {
        'league_id': league_id,
        'league_name': league_name,
        'accuracy_classifier': accuracy_classifier,
        'accuracy_scores': accuracy_scores,
        'correct_predictions_classifier': correct_predictions_classifier,
        'correct_predictions_scores': correct_predictions_scores,
        'total_predictions': total_predictions,
        'test_games': len(test_games),
        'predictions_details': predictions_details,
        'home_mae': np.mean(home_score_errors) if home_score_errors else None,
        'away_mae': np.mean(away_score_errors) if away_score_errors else None,
        'overall_mae': np.mean(total_score_errors) if total_score_errors else None,
        'score_predictions_count': len(home_score_errors)
    }

def main():
    """Main testing function"""
    print("AI RUGBY PREDICTION TESTING")
    print("Testing AI performance on unseen games")
    print("="*60)
    
    # Load registry to get available leagues
    try:
        with open('artifacts/model_registry.json', 'r') as f:
            registry = json.load(f)
        leagues = registry.get('leagues', {})
    except:
        print("ERROR Could not load model registry")
        return
    
    if not leagues:
        print("ERROR No leagues found in registry")
        return
    
    print(f"Found {len(leagues)} leagues to test")
    
    # Test each league
    all_results = []
    for league_id, league_data in leagues.items():
        result = test_ai_performance(int(league_id), test_type="recent")
        if result:
            all_results.append(result)
    
    # Overall summary
    if all_results:
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        
        total_correct_classifier = sum(r['correct_predictions_classifier'] for r in all_results)
        total_correct_scores = sum(r['correct_predictions_scores'] for r in all_results)
        total_predictions = sum(r['total_predictions'] for r in all_results)
        overall_accuracy_classifier = total_correct_classifier / total_predictions if total_predictions > 0 else 0
        overall_accuracy_scores = total_correct_scores / total_predictions if total_predictions > 0 else 0
        
        print(f"OVERALL WIN/LOSE PREDICTION COMPARISON:")
        print(f"   Classifier Model: {overall_accuracy_classifier*100:.1f}% ({total_correct_classifier}/{total_predictions})")
        print(f"   Score-based Model: {overall_accuracy_scores*100:.1f}% ({total_correct_scores}/{total_predictions})")
        print(f"   Overall Difference: {overall_accuracy_classifier*100 - overall_accuracy_scores*100:+.1f} percentage points")
        print(f"STATS Total Test Games: {sum(r['test_games'] for r in all_results)}")
        
        print(f"\nLeague-by-League Results:")
        for result in all_results:
            diff = result['accuracy_classifier']*100 - result['accuracy_scores']*100
            print(f"  {result['league_name']}:")
            print(f"    Classifier: {result['accuracy_classifier']*100:.1f}% ({result['correct_predictions_classifier']}/{result['total_predictions']})")
            print(f"    Score-based: {result['accuracy_scores']*100:.1f}% ({result['correct_predictions_scores']}/{result['total_predictions']})")
            print(f"    Difference: {diff:+.1f} percentage points")
            if result['home_mae'] is not None:
                print(f"    Score MAE: Home {result['home_mae']:.1f}, Away {result['away_mae']:.1f}, Overall {result['overall_mae']:.1f}")
        
        # Overall score prediction summary
        score_results = [r for r in all_results if r['home_mae'] is not None]
        if score_results:
            overall_home_mae = np.mean([r['home_mae'] for r in score_results])
            overall_away_mae = np.mean([r['away_mae'] for r in score_results])
            overall_score_mae = np.mean([r['overall_mae'] for r in score_results])
            total_score_predictions = sum([r['score_predictions_count'] for r in score_results])
            
            print(f"\nOVERALL SCORE PREDICTION SUMMARY:")
            print(f"   Total Score Predictions: {total_score_predictions}")
            print(f"   Average Home Score MAE: {overall_home_mae:.1f} points")
            print(f"   Average Away Score MAE: {overall_away_mae:.1f} points")
            print(f"   Average Overall MAE: {overall_score_mae:.1f} points")
        
        # Performance assessment
        if overall_accuracy_classifier >= 0.8:
            print(f"\nEXCELLENT: Classifier model shows strong predictive performance!")
        elif overall_accuracy_classifier >= 0.65:
            print(f"\nGOOD: Classifier model shows decent predictive performance")
        else:
            print(f"\nWARNING: Classifier model needs improvement")
            
        if overall_accuracy_scores >= 0.8:
            print(f"EXCELLENT: Score-based model shows strong predictive performance!")
        elif overall_accuracy_scores >= 0.65:
            print(f"GOOD: Score-based model shows decent predictive performance")
        else:
            print(f"WARNING: Score-based model needs improvement")
            
        if abs(overall_accuracy_classifier - overall_accuracy_scores) < 0.05:
            print(f"Both models perform similarly - consider using the simpler classifier model")
        elif overall_accuracy_classifier > overall_accuracy_scores:
            print(f"Classifier model performs better - use it for win/lose predictions")
        else:
            print(f"Score-based model performs better - consider using score predictions for winner determination")
    
    else:
        print("ERROR No successful tests completed")

if __name__ == "__main__":
    main()
