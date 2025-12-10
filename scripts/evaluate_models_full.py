#!/usr/bin/env python3
"""
Full Model Evaluation Script
Tests both XGBoost and Optimized models on ALL completed games (900+)
Compares actual predictions vs actual results for comprehensive accuracy evaluation
"""

import sqlite3
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import pickle
import numpy as np
import pandas as pd

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from prediction.features import build_feature_table, FeatureConfig
from prediction.hybrid_predictor import HybridPredictor, MultiLeaguePredictor

# Try to import joblib
try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    joblib = None
    JOBLIB_AVAILABLE = False

# Colors for terminal output
import sys
import platform

# Check if we're on Windows and disable colors/unicode if encoding issues
IS_WINDOWS = platform.system() == 'Windows'
if IS_WINDOWS:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

class Colors:
    if IS_WINDOWS and sys.stdout.encoding and 'cp1252' in sys.stdout.encoding.lower():
        # Use ASCII-safe characters on Windows
        GREEN = ''
        RED = ''
        YELLOW = ''
        BLUE = ''
        MAGENTA = ''
        CYAN = ''
        WHITE = ''
        BOLD = ''
        END = ''
    else:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        END = '\033[0m'

# Helper for Windows-safe symbols
def safe_symbol(symbol: str) -> str:
    """Return Windows-safe ASCII alternative for unicode symbols"""
    if IS_WINDOWS and sys.stdout.encoding and 'cp1252' in sys.stdout.encoding.lower():
        replacements = {
            '✓': '[OK]',
            '✗': '[X]',
            '≈': '[~]',
            '⚠': '[!]'
        }
        return replacements.get(symbol, symbol)
    return symbol

def load_model(model_path: str):
    """Load a model from file"""
    try:
        if JOBLIB_AVAILABLE and joblib is not None:
            return joblib.load(model_path)
        else:
            with open(model_path, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"{Colors.RED}Error loading model {model_path}: {e}{Colors.END}")
        return None

def get_all_completed_games(db_path: str) -> List[Dict[str, Any]]:
    """Get all completed games from database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            e.id,
            e.league_id,
            e.home_team_id,
            e.away_team_id,
            e.date_event,
            e.home_score,
            e.away_score,
            e.status,
            t1.name as home_team_name,
            t2.name as away_team_name
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.home_score IS NOT NULL
          AND e.away_score IS NOT NULL
          AND e.date_event <= date('now')
          AND (e.status IS NULL OR e.status != 'Postponed' AND e.status != 'Cancelled')
        ORDER BY e.date_event DESC
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    games = []
    for row in rows:
        games.append({
            'id': row[0],
            'league_id': row[1],
            'home_team_id': row[2],
            'away_team_id': row[3],
            'date_event': row[4],
            'home_score': row[5],
            'away_score': row[6],
            'status': row[7],
            'home_team_name': row[8] or 'Unknown',
            'away_team_name': row[9] or 'Unknown'
        })
    
    conn.close()
    return games

def make_prediction_with_predictor(predictor: HybridPredictor, home_team_name: str, 
                                  away_team_name: str, league_id: int, 
                                  match_date: str) -> Optional[Dict[str, Any]]:
    """Make prediction using a HybridPredictor instance"""
    try:
        # Use the predictor's get_ai_prediction method
        # Get team IDs from database first
        conn = sqlite3.connect(predictor.db_path)
        cursor = conn.cursor()
        
        # Find team IDs
        cursor.execute("SELECT id FROM team WHERE name = ? LIMIT 1", (home_team_name,))
        home_result = cursor.fetchone()
        if not home_result:
            conn.close()
            return None
        home_team_id = home_result[0]
        
        cursor.execute("SELECT id FROM team WHERE name = ? LIMIT 1", (away_team_name,))
        away_result = cursor.fetchone()
        if not away_result:
            conn.close()
            return None
        away_team_id = away_result[0]
        
        conn.close()
        
        # Get AI prediction
        ai_pred = predictor.get_ai_prediction(home_team_id, away_team_id, match_date)
        
        if not ai_pred:
            return None
        
        # Determine predicted winner
        home_win_prob = ai_pred.get('home_win_prob', 0.5)
        away_win_prob = ai_pred.get('away_win_prob', 0.5)
        draw_prob = ai_pred.get('draw_prob', 0.0)
        
        if home_win_prob > away_win_prob and home_win_prob > draw_prob:
            predicted_winner = 'Home'
        elif away_win_prob > home_win_prob and away_win_prob > draw_prob:
            predicted_winner = 'Away'
        else:
            predicted_winner = 'Draw'
        
        return {
            'predicted_winner': predicted_winner,
            'predicted_home_score': ai_pred.get('predicted_home_score', 20.0),
            'predicted_away_score': ai_pred.get('predicted_away_score', 20.0),
            'home_win_prob': home_win_prob,
            'away_win_prob': away_win_prob,
            'draw_prob': draw_prob
        }
    
    except Exception as e:
        print(f"{Colors.YELLOW}Warning: Prediction error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        return None

def evaluate_models(db_path: str = 'data.sqlite', 
                   xgboost_dir: str = 'artifacts',
                   optimized_dir: str = 'artifacts_optimized'):
    """Evaluate both model types on all completed games"""
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'FULL MODEL EVALUATION - Testing on ALL Completed Games':^100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}\n")
    
    # Get all completed games
    print(f"{Colors.CYAN}Loading completed games from database...{Colors.END}")
    games = get_all_completed_games(db_path)
    print(f"{Colors.GREEN}{safe_symbol('✓')} Loaded {len(games)} completed games{Colors.END}\n")
    
    if len(games) == 0:
        print(f"{Colors.RED}❌ No completed games found in database{Colors.END}")
        return
    
    # Group games by league
    games_by_league = {}
    for game in games:
        league_id = game['league_id']
        if league_id not in games_by_league:
            games_by_league[league_id] = []
        games_by_league[league_id].append(game)
    
    print(f"{Colors.CYAN}Found games in {len(games_by_league)} leagues{Colors.END}\n")
    
    # Results storage
    xgboost_results = {lid: {'correct': 0, 'total': 0, 'mae_home': [], 'mae_away': [], 'mae_overall': []} 
                      for lid in games_by_league.keys()}
    optimized_results = {lid: {'correct': 0, 'total': 0, 'mae_home': [], 'mae_away': [], 'mae_overall': []} 
                        for lid in games_by_league.keys()}
    
    # Process each league
    _xgboost_predictors = {}  # Cache predictors
    _optimized_predictors = {}  # Cache predictors
    
    for league_id, league_games in games_by_league.items():
        print(f"{Colors.BOLD}{Colors.WHITE}{'─'*100}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}League {league_id}: {len(league_games)} games{Colors.END}")
        
        # Load models
        xgboost_path = os.path.join(xgboost_dir, f'league_{league_id}_model_xgboost.pkl')
        optimized_path = os.path.join(optimized_dir, f'league_{league_id}_model_optimized.pkl')
        
        xgboost_model = None
        optimized_model = None
        
        if os.path.exists(xgboost_path):
            print(f"{Colors.CYAN}Loading XGBoost model...{Colors.END}")
            xgboost_model = load_model(xgboost_path)
            if xgboost_model:
                print(f"{Colors.GREEN}{safe_symbol('✓')} XGBoost model loaded{Colors.END}")
                # Create and cache predictor
                _xgboost_predictors[league_id] = HybridPredictor(xgboost_path, '', db_path)
            else:
                print(f"{Colors.RED}{safe_symbol('✗')} Failed to load XGBoost model{Colors.END}")
        else:
            print(f"{Colors.YELLOW}{safe_symbol('⚠')} XGBoost model not found: {xgboost_path}{Colors.END}")
        
        if os.path.exists(optimized_path):
            print(f"{Colors.CYAN}Loading Optimized model...{Colors.END}")
            optimized_model = load_model(optimized_path)
            if optimized_model:
                print(f"{Colors.GREEN}{safe_symbol('✓')} Optimized model loaded{Colors.END}")
                # Create and cache predictor
                _optimized_predictors[league_id] = HybridPredictor(optimized_path, '', db_path)
            else:
                print(f"{Colors.RED}{safe_symbol('✗')} Failed to load Optimized model{Colors.END}")
        else:
            print(f"{Colors.YELLOW}{safe_symbol('⚠')} Optimized model not found: {optimized_path}{Colors.END}")
        
        if not xgboost_model and not optimized_model:
            print(f"{Colors.YELLOW}Skipping league {league_id} - no models available{Colors.END}\n")
            continue
        
        # Evaluate each game
        print(f"{Colors.CYAN}Evaluating {len(league_games)} games...{Colors.END}")
        
        for i, game in enumerate(league_games, 1):
            if i % 50 == 0:
                print(f"  Processed {i}/{len(league_games)} games...")
            
            home_score = game['home_score']
            away_score = game['away_score']
            actual_winner = 'Home' if home_score > away_score else ('Away' if away_score > home_score else 'Draw')
            
            # XGBoost prediction
            if league_id in _xgboost_predictors:
                xgboost_pred = make_prediction_with_predictor(
                    _xgboost_predictors[league_id],
                    game['home_team_name'],
                    game['away_team_name'],
                    league_id,
                    game['date_event']
                )
                
                if xgboost_pred:
                    xgboost_results[league_id]['total'] += 1
                    if xgboost_pred['predicted_winner'] == actual_winner:
                        xgboost_results[league_id]['correct'] += 1
                    
                    # Calculate MAE
                    home_mae = abs(xgboost_pred['predicted_home_score'] - home_score)
                    away_mae = abs(xgboost_pred['predicted_away_score'] - away_score)
                    overall_mae = (home_mae + away_mae) / 2
                    
                    xgboost_results[league_id]['mae_home'].append(home_mae)
                    xgboost_results[league_id]['mae_away'].append(away_mae)
                    xgboost_results[league_id]['mae_overall'].append(overall_mae)
            
            # Optimized prediction
            if league_id in _optimized_predictors:
                optimized_pred = make_prediction_with_predictor(
                    _optimized_predictors[league_id],
                    game['home_team_name'],
                    game['away_team_name'],
                    league_id,
                    game['date_event']
                )
                
                if optimized_pred:
                    optimized_results[league_id]['total'] += 1
                    if optimized_pred['predicted_winner'] == actual_winner:
                        optimized_results[league_id]['correct'] += 1
                    
                    # Calculate MAE
                    home_mae = abs(optimized_pred['predicted_home_score'] - home_score)
                    away_mae = abs(optimized_pred['predicted_away_score'] - away_score)
                    overall_mae = (home_mae + away_mae) / 2
                    
                    optimized_results[league_id]['mae_home'].append(home_mae)
                    optimized_results[league_id]['mae_away'].append(away_mae)
                    optimized_results[league_id]['mae_overall'].append(overall_mae)
        
        print(f"{Colors.GREEN}{safe_symbol('✓')} Completed evaluation{Colors.END}\n")
    
    # Print results
    print_results(xgboost_results, optimized_results, games_by_league)

def print_results(xgboost_results: Dict, optimized_results: Dict, games_by_league: Dict):
    """Print comprehensive comparison results"""
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'EVALUATION RESULTS':^100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}\n")
    
    # League-by-league comparison
    for league_id in sorted(games_by_league.keys()):
        league_games = games_by_league[league_id]
        xg_res = xgboost_results[league_id]
        opt_res = optimized_results[league_id]
        
        if xg_res['total'] == 0 and opt_res['total'] == 0:
            continue
        
        print(f"{Colors.BOLD}{Colors.WHITE}{'─'*100}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}League {league_id}: {len(league_games)} total games{Colors.END}\n")
        
        # XGBoost results
        if xg_res['total'] > 0:
            xg_acc = xg_res['correct'] / xg_res['total']
            xg_home_mae = np.mean(xg_res['mae_home']) if xg_res['mae_home'] else 0
            xg_away_mae = np.mean(xg_res['mae_away']) if xg_res['mae_away'] else 0
            xg_overall_mae = np.mean(xg_res['mae_overall']) if xg_res['mae_overall'] else 0
            
            print(f"{Colors.CYAN}XGBoost Model:{Colors.END}")
            print(f"  Games Tested:  {xg_res['total']}")
            print(f"  Winner Accuracy:  {xg_acc*100:.2f}% ({xg_res['correct']}/{xg_res['total']})")
            print(f"  Home Score MAE:   {xg_home_mae:.2f}")
            print(f"  Away Score MAE:   {xg_away_mae:.2f}")
            print(f"  Overall MAE:      {xg_overall_mae:.2f}")
        
        # Optimized results
        if opt_res['total'] > 0:
            opt_acc = opt_res['correct'] / opt_res['total']
            opt_home_mae = np.mean(opt_res['mae_home']) if opt_res['mae_home'] else 0
            opt_away_mae = np.mean(opt_res['mae_away']) if opt_res['mae_away'] else 0
            opt_overall_mae = np.mean(opt_res['mae_overall']) if opt_res['mae_overall'] else 0
            
            print(f"\n{Colors.CYAN}Optimized Model:{Colors.END}")
            print(f"  Games Tested:  {opt_res['total']}")
            print(f"  Winner Accuracy:  {opt_acc*100:.2f}% ({opt_res['correct']}/{opt_res['total']})")
            print(f"  Home Score MAE:   {opt_home_mae:.2f}")
            print(f"  Away Score MAE:   {opt_away_mae:.2f}")
            print(f"  Overall MAE:      {opt_overall_mae:.2f}")
        
        # Comparison
        if xg_res['total'] > 0 and opt_res['total'] > 0:
            print(f"\n{Colors.BOLD}{Colors.WHITE}Comparison:{Colors.END}")
            acc_diff = (xg_acc - opt_acc) * 100
            mae_diff = xg_overall_mae - opt_overall_mae
            
            if acc_diff > 0:
                print(f"  Winner Accuracy:  {Colors.GREEN}XGBoost better by {acc_diff:.2f}%{Colors.END}")
            elif acc_diff < 0:
                print(f"  Winner Accuracy:  {Colors.RED}Optimized better by {abs(acc_diff):.2f}%{Colors.END}")
            else:
                print(f"  Winner Accuracy:  {Colors.CYAN}Tie{Colors.END}")
            
            if mae_diff < 0:
                print(f"  Overall MAE:      {Colors.GREEN}XGBoost better by {abs(mae_diff):.2f} points{Colors.END}")
            elif mae_diff > 0:
                print(f"  Overall MAE:      {Colors.RED}Optimized better by {mae_diff:.2f} points{Colors.END}")
            else:
                print(f"  Overall MAE:      {Colors.CYAN}Tie{Colors.END}")
        
        print()
    
    # Overall summary
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'OVERALL SUMMARY':^100}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}\n")
    
    total_xg_games = sum(r['total'] for r in xgboost_results.values())
    total_opt_games = sum(r['total'] for r in optimized_results.values())
    total_xg_correct = sum(r['correct'] for r in xgboost_results.values())
    total_opt_correct = sum(r['correct'] for r in optimized_results.values())
    
    all_xg_mae = []
    all_opt_mae = []
    for lid in xgboost_results.keys():
        all_xg_mae.extend(xgboost_results[lid]['mae_overall'])
        all_opt_mae.extend(optimized_results[lid]['mae_overall'])
    
    if total_xg_games > 0:
        overall_xg_acc = total_xg_correct / total_xg_games
        overall_xg_mae = np.mean(all_xg_mae) if all_xg_mae else 0
        print(f"{Colors.CYAN}XGBoost Model (Overall):{Colors.END}")
        print(f"  Total Games:     {total_xg_games}")
        print(f"  Winner Accuracy: {overall_xg_acc*100:.2f}% ({total_xg_correct}/{total_xg_games})")
        print(f"  Overall MAE:     {overall_xg_mae:.2f}")
    
    if total_opt_games > 0:
        overall_opt_acc = total_opt_correct / total_opt_games
        overall_opt_mae = np.mean(all_opt_mae) if all_opt_mae else 0
        print(f"\n{Colors.CYAN}Optimized Model (Overall):{Colors.END}")
        print(f"  Total Games:     {total_opt_games}")
        print(f"  Winner Accuracy: {overall_opt_acc*100:.2f}% ({total_opt_correct}/{total_opt_games})")
        print(f"  Overall MAE:     {overall_opt_mae:.2f}")
    
    if total_xg_games > 0 and total_opt_games > 0:
        acc_diff = (overall_xg_acc - overall_opt_acc) * 100
        mae_diff = overall_xg_mae - overall_opt_mae
        
        print(f"\n{Colors.BOLD}{Colors.WHITE}Overall Winner:{Colors.END}")
        if acc_diff > 0.5:
            print(f"  {Colors.GREEN}{safe_symbol('✓')} XGBoost is better on accuracy (+{acc_diff:.2f}%){Colors.END}")
        elif acc_diff < -0.5:
            print(f"  {Colors.RED}{safe_symbol('✗')} Optimized is better on accuracy ({acc_diff:.2f}%){Colors.END}")
        else:
            print(f"  {Colors.CYAN}{safe_symbol('≈')} Models are similar on accuracy ({acc_diff:+.2f}%){Colors.END}")
        
        if abs(mae_diff) > 0.5:
            if mae_diff < 0:
                print(f"  {Colors.GREEN}{safe_symbol('✓')} XGBoost is better on MAE ({mae_diff:.2f} points lower){Colors.END}")
            else:
                print(f"  {Colors.RED}{safe_symbol('✗')} Optimized is better on MAE ({mae_diff:.2f} points lower){Colors.END}")
        else:
            print(f"  {Colors.CYAN}{safe_symbol('≈')} Models are similar on MAE ({mae_diff:+.2f} points){Colors.END}")
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*100}{Colors.END}\n")

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'data.sqlite'
    xgboost_dir = sys.argv[2] if len(sys.argv) > 2 else 'artifacts'
    optimized_dir = sys.argv[3] if len(sys.argv) > 3 else 'artifacts_optimized'
    
    evaluate_models(db_path, xgboost_dir, optimized_dir)

