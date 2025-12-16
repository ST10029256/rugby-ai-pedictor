#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare Prediction Methods: Old vs New

Old Method: Winner determined from predicted scores
New Method: Winner from classifier, scores adjusted to match

This script evaluates both methods on historical data to see which is more accurate.
"""

import sqlite3
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS
from prediction.features import build_feature_table, FeatureConfig
from prediction.hybrid_predictor import HybridPredictor

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def get_old_method_prediction(predictor: HybridPredictor, home_team_id: int, 
                             away_team_id: int, match_date: str) -> Dict[str, Any]:
    """
    Old method: Get raw predictions and determine winner from scores
    """
    try:
        # Get raw predictions using the predictor's method but without adjustments
        conn = sqlite3.connect(predictor.db_path)
        config = FeatureConfig(
            elo_priors=None,
            elo_k=24.0,
            neutral_mode=(predictor.league_id == 4574)
        )
        df = build_feature_table(conn, config)
        conn.close()
        
        match_features = df[
            (df['home_team_id'] == home_team_id) & 
            (df['away_team_id'] == away_team_id)
        ]
        
        if len(match_features) == 0:
            # Try to use team averages
            home_team_features = df[df['home_team_id'] == home_team_id]
            if len(home_team_features) == 0:
                return None
            match_features = home_team_features.iloc[-1]
        else:
            match_features = match_features.iloc[-1]
        
        # Extract feature vector
        feature_vector = []
        for col in predictor.feature_cols:
            if col in match_features.index:
                feature_vector.append(match_features[col])
            else:
                feature_vector.append(0.0)
        
        X = np.array(feature_vector).reshape(1, -1)
        
        # Get raw predictions (no adjustments)
        home_win_prob = predictor.clf_model.predict_proba(X)[0, 1]
        predicted_home_score = max(0, predictor.reg_home_model.predict(X)[0])
        predicted_away_score = max(0, predictor.reg_away_model.predict(X)[0])
        
        # OLD METHOD: Determine winner from scores (not from classifier)
        if predicted_home_score > predicted_away_score:
            predicted_winner = 'Home'
        elif predicted_away_score > predicted_home_score:
            predicted_winner = 'Away'
        else:
            # Tie - use classifier to break
            predicted_winner = 'Home' if home_win_prob > 0.5 else 'Away'
        
        return {
            'predicted_winner': predicted_winner,
            'predicted_home_score': float(predicted_home_score),
            'predicted_away_score': float(predicted_away_score),
            'home_win_prob': float(home_win_prob),
            'method': 'old'
        }
    except Exception as e:
        print(f"  ⚠️  Error in old method: {e}")
        return None

def get_new_method_prediction(predictor: HybridPredictor, home_team_id: int,
                              away_team_id: int, match_date: str) -> Dict[str, Any]:
    """
    New method: Get prediction with score adjustment based on classifier
    """
    # Use the actual get_ai_prediction but simulate the hybrid_predict logic
    # for AI-only mode (which adjusts scores)
    ai_pred = predictor.get_ai_prediction(home_team_id, away_team_id, match_date)
    
    # Simulate hybrid_predict with AI-only (effective_odds_weight == 0.0)
    home_win_prob = ai_pred['home_win_prob']
    predicted_home_score = ai_pred['predicted_home_score']
    predicted_away_score = ai_pred['predicted_away_score']
    
    # NEW METHOD: Adjust scores to match classifier (AI-only mode)
    classifier_home_wins = home_win_prob > 0.5
    score_based_home_wins = predicted_home_score > predicted_away_score
    score_margin = abs(predicted_home_score - predicted_away_score)
    total_score = predicted_home_score + predicted_away_score
    
    if classifier_home_wins != score_based_home_wins:
        # Scores and classifier disagree - adjust scores to match classifier
        if classifier_home_wins:
            min_margin = max(1.0, score_margin * 0.5)
            predicted_home_score = (total_score + min_margin) / 2
            predicted_away_score = (total_score - min_margin) / 2
        else:
            min_margin = max(1.0, score_margin * 0.5)
            predicted_away_score = (total_score + min_margin) / 2
            predicted_home_score = (total_score - min_margin) / 2
        
        predicted_home_score = max(0, round(predicted_home_score))
        predicted_away_score = max(0, round(predicted_away_score))
        
        if classifier_home_wins:
            if predicted_home_score <= predicted_away_score:
                predicted_home_score = predicted_away_score + 1
        else:
            if predicted_away_score <= predicted_home_score:
                predicted_away_score = predicted_home_score + 1
    
    elif predicted_home_score == predicted_away_score:
        if classifier_home_wins:
            predicted_home_score = predicted_away_score + 1
        else:
            predicted_away_score = predicted_home_score + 1
    
    # Determine winner from classifier (new method)
    predicted_winner = 'Home' if home_win_prob > 0.5 else 'Away'
    
    return {
        'predicted_winner': predicted_winner,
        'predicted_home_score': float(predicted_home_score),
        'predicted_away_score': float(predicted_away_score),
        'home_win_prob': float(home_win_prob),
        'method': 'new'
    }

def evaluate_method(conn: sqlite3.Connection, league_id: int, 
                   predictor: HybridPredictor, method_func) -> Dict[str, Any]:
    """Evaluate a prediction method on historical data"""
    
    # Get completed matches for this league
    query = """
        SELECT e.id, e.home_team_id, e.away_team_id, e.date_event,
               e.home_score, e.away_score, 
               ht.name as home_team, at.name as away_team
        FROM event e
        JOIN team ht ON e.home_team_id = ht.id
        JOIN team at ON e.away_team_id = at.id
        WHERE e.league_id = ? 
        AND e.home_score IS NOT NULL 
        AND e.away_score IS NOT NULL
        ORDER BY e.date_event DESC
        LIMIT 100
    """
    
    df = pd.read_sql_query(query, conn, params=(league_id,))
    
    if len(df) == 0:
        return None
    
    correct = 0
    total = 0
    score_errors = []
    inconsistencies = 0  # Cases where predicted winner doesn't match scores
    
    for _, row in df.iterrows():
        try:
            # Get prediction
            prediction = method_func(
                predictor, 
                row['home_team_id'], 
                row['away_team_id'],
                row['date_event']
            )
            
            if prediction is None:
                continue
            
            # Determine actual winner
            if row['home_score'] > row['away_score']:
                actual_winner = 'Home'
            elif row['away_score'] > row['home_score']:
                actual_winner = 'Away'
            else:
                actual_winner = 'Draw'
            
            # Check if prediction is correct
            if prediction['predicted_winner'] == actual_winner:
                correct += 1
            
            # Check for inconsistencies (winner doesn't match scores)
            score_winner = 'Home' if prediction['predicted_home_score'] > prediction['predicted_away_score'] else 'Away'
            if prediction['predicted_winner'] != score_winner:
                inconsistencies += 1
            
            # Calculate score errors
            home_error = abs(prediction['predicted_home_score'] - row['home_score'])
            away_error = abs(prediction['predicted_away_score'] - row['away_score'])
            score_errors.append((home_error + away_error) / 2)
            
            total += 1
            
        except Exception as e:
            print(f"  ⚠️  Error processing match {row['id']}: {e}")
            continue
    
    if total == 0:
        return None
    
    accuracy = correct / total
    avg_score_error = np.mean(score_errors) if score_errors else 0
    
    return {
        'accuracy': accuracy,
        'correct': correct,
        'total': total,
        'avg_score_error': avg_score_error,
        'inconsistencies': inconsistencies,
        'inconsistency_rate': inconsistencies / total if total > 0 else 0
    }

def compare_methods(league_id: int, league_name: str, db_path: str):
    """Compare old vs new method for a league"""
    
    print(f"\n{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}League: {league_name} (ID: {league_id}){Colors.END}")
    print(f"{Colors.BOLD}{'='*80}{Colors.END}")
    
    # Find model file
    model_paths = [
        f'artifacts/league_{league_id}_model_xgboost.pkl',
        f'rugby-ai-predictor/artifacts_optimized/league_{league_id}_model_xgboost.pkl',
        f'artifacts_optimized/league_{league_id}_model_xgboost.pkl',
    ]
    
    model_path = None
    for path in model_paths:
        if os.path.exists(path):
            model_path = path
            break
    
    if not model_path:
        print(f"{Colors.RED}❌ No model found for league {league_id}{Colors.END}")
        return None
    
    # Load predictor
    try:
        predictor = HybridPredictor(model_path, '', db_path)
    except Exception as e:
        print(f"{Colors.RED}❌ Error loading predictor: {e}{Colors.END}")
        return None
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Evaluate old method
    print(f"\n{Colors.CYAN}📊 Evaluating OLD method (winner from scores)...{Colors.END}")
    old_results = evaluate_method(conn, league_id, predictor, get_old_method_prediction)
    
    # Evaluate new method
    print(f"{Colors.CYAN}📊 Evaluating NEW method (winner from classifier, scores adjusted)...{Colors.END}")
    new_results = evaluate_method(conn, league_id, predictor, get_new_method_prediction)
    
    conn.close()
    
    if not old_results or not new_results:
        print(f"{Colors.RED}❌ Could not evaluate methods{Colors.END}")
        return None
    
    # Display results
    print(f"\n{Colors.BOLD}Results:{Colors.END}")
    print(f"{'Metric':<30} {'Old Method':<20} {'New Method':<20} {'Difference':<20}")
    print(f"{'-'*90}")
    
    # Accuracy
    acc_diff = new_results['accuracy'] - old_results['accuracy']
    acc_color = Colors.GREEN if acc_diff > 0 else Colors.RED if acc_diff < 0 else Colors.YELLOW
    print(f"{'Winner Accuracy':<30} {old_results['accuracy']:.1%} {'':<10} {new_results['accuracy']:.1%} {'':<10} {acc_color}{acc_diff:+.1%}{Colors.END}")
    
    # Score error
    score_diff = old_results['avg_score_error'] - new_results['avg_score_error']
    score_color = Colors.GREEN if score_diff > 0 else Colors.RED if score_diff < 0 else Colors.YELLOW
    print(f"{'Avg Score Error (pts)':<30} {old_results['avg_score_error']:.2f} {'':<10} {new_results['avg_score_error']:.2f} {'':<10} {score_color}{score_diff:+.2f}{Colors.END}")
    
    # Inconsistencies
    print(f"{'Inconsistencies':<30} {old_results['inconsistencies']}/{old_results['total']} ({old_results['inconsistency_rate']:.1%}) {'':<5} {new_results['inconsistencies']}/{new_results['total']} ({new_results['inconsistency_rate']:.1%}) {'':<5} {Colors.GREEN}✅ Fixed{Colors.END}")
    
    # Summary
    print(f"\n{Colors.BOLD}Summary:{Colors.END}")
    if acc_diff > 0:
        print(f"{Colors.GREEN}✅ NEW method is {acc_diff:.1%} more accurate!{Colors.END}")
    elif acc_diff < 0:
        print(f"{Colors.RED}❌ NEW method is {abs(acc_diff):.1%} less accurate{Colors.END}")
    else:
        print(f"{Colors.YELLOW}⚖️  Both methods have same accuracy{Colors.END}")
    
    if new_results['inconsistencies'] == 0:
        print(f"{Colors.GREEN}✅ NEW method has ZERO inconsistencies (winner always matches scores){Colors.END}")
    else:
        print(f"{Colors.YELLOW}⚠️  NEW method still has {new_results['inconsistencies']} inconsistencies{Colors.END}")
    
    return {
        'league_id': league_id,
        'league_name': league_name,
        'old': old_results,
        'new': new_results,
        'improvement': acc_diff
    }

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Compare old vs new prediction methods')
    parser.add_argument('--league-id', type=int, help='Compare specific league ID')
    parser.add_argument('--all-leagues', action='store_true', help='Compare all leagues')
    parser.add_argument('--db-path', type=str, default=None, help='Path to database')
    
    args = parser.parse_args()
    
    # Find database
    if args.db_path:
        db_path = args.db_path
    else:
        db_path = Path(__file__).parent.parent / 'data.sqlite'
        if not db_path.exists():
            db_path = Path(__file__).parent.parent / 'rugby-ai-predictor' / 'data.sqlite'
    
    if not db_path.exists():
        print(f"{Colors.RED}❌ Database not found at {db_path}{Colors.END}")
        sys.exit(1)
    
    print(f"{Colors.BOLD}🔬 Prediction Method Comparison: Old vs New{Colors.END}")
    print(f"{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"📁 Database: {db_path}")
    
    # Determine leagues to compare
    if args.league_id:
        if args.league_id not in LEAGUE_MAPPINGS:
            print(f"{Colors.RED}❌ League ID {args.league_id} not found{Colors.END}")
            sys.exit(1)
        leagues = [(args.league_id, LEAGUE_MAPPINGS[args.league_id])]
    elif args.all_leagues:
        leagues = list(LEAGUE_MAPPINGS.items())
    else:
        print(f"{Colors.RED}❌ Please specify --league-id or --all-leagues{Colors.END}")
        parser.print_help()
        sys.exit(1)
    
    # Compare each league
    results = []
    for league_id, league_name in leagues:
        result = compare_methods(league_id, league_name, str(db_path))
        if result:
            results.append(result)
    
    # Overall summary
    if len(results) > 1:
        print(f"\n{Colors.BOLD}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}Overall Summary (All Leagues):{Colors.END}")
        print(f"{'='*80}")
        
        total_old_correct = sum(r['old']['correct'] for r in results)
        total_old_total = sum(r['old']['total'] for r in results)
        total_new_correct = sum(r['new']['correct'] for r in results)
        total_new_total = sum(r['new']['total'] for r in results)
        
        overall_old_acc = total_old_correct / total_old_total if total_old_total > 0 else 0
        overall_new_acc = total_new_correct / total_new_total if total_new_total > 0 else 0
        
        print(f"\n{Colors.BOLD}Overall Winner Accuracy:{Colors.END}")
        print(f"  Old Method: {overall_old_acc:.1%} ({total_old_correct}/{total_old_total})")
        print(f"  New Method: {overall_new_acc:.1%} ({total_new_correct}/{total_new_total})")
        print(f"  Improvement: {Colors.GREEN if overall_new_acc > overall_old_acc else Colors.RED}{overall_new_acc - overall_old_acc:+.1%}{Colors.END}")
        
        total_old_inconsistencies = sum(r['old']['inconsistencies'] for r in results)
        total_new_inconsistencies = sum(r['new']['inconsistencies'] for r in results)
        
        print(f"\n{Colors.BOLD}Inconsistencies:{Colors.END}")
        print(f"  Old Method: {total_old_inconsistencies} cases where winner ≠ scores")
        print(f"  New Method: {total_new_inconsistencies} cases where winner ≠ scores")
        if total_new_inconsistencies == 0:
            print(f"  {Colors.GREEN}✅ NEW method has ZERO inconsistencies!{Colors.END}")
    
    print(f"\n{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.GREEN}✅ Comparison complete!{Colors.END}")

if __name__ == "__main__":
    main()
