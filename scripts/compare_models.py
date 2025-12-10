#!/usr/bin/env python3
"""
Model Comparison Script
Compares XGBoost models (artifacts/) vs Optimized Stacking models (artifacts_optimized/)
Shows side-by-side accuracy, MAE, and performance metrics
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

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

def load_registry(filepath: str) -> Optional[Dict[str, Any]]:
    """Load model registry JSON file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"{Colors.RED}❌ File not found: {filepath}{Colors.END}")
        return None
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}❌ Error parsing JSON: {e}{Colors.END}")
        return None

def format_percentage(value: float) -> str:
    """Format value as percentage"""
    return f"{value * 100:.2f}%"

def format_float(value: float, decimals: int = 2) -> str:
    """Format float with specified decimals"""
    return f"{value:.{decimals}f}"

def compare_metric(xgboost_val: float, optimized_val: float, higher_better: bool = True) -> str:
    """Compare two metrics and return formatted string with color"""
    if xgboost_val is None or optimized_val is None:
        return f"{Colors.YELLOW}N/A{Colors.END}"
    
    if higher_better:
        better = xgboost_val > optimized_val
        diff = xgboost_val - optimized_val
    else:
        better = xgboost_val < optimized_val
        diff = optimized_val - xgboost_val
    
    if better:
        return f"{Colors.GREEN}✓ {format_float(xgboost_val)} (better by {format_float(abs(diff))}){Colors.END}"
    elif abs(diff) < 0.001:  # Essentially equal
        return f"{Colors.CYAN}≈ {format_float(xgboost_val)} (equal){Colors.END}"
    else:
        return f"{Colors.RED}✗ {format_float(xgboost_val)} (worse by {format_float(abs(diff))}){Colors.END}"

def print_header():
    """Print comparison header"""
    print(f"\n{Colors.BOLD}{'='*120}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'MODEL COMPARISON: XGBoost vs Optimized Stacking':^120}{Colors.END}")
    print(f"{Colors.BOLD}{'='*120}{Colors.END}\n")

def print_league_comparison(league_id: str, league_name: str, xgboost_data: Dict, optimized_data: Dict):
    """Print detailed comparison for a single league"""
    print(f"\n{Colors.BOLD}{Colors.WHITE}{'─'*120}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}League: {league_name} (ID: {league_id}){Colors.END}")
    print(f"{Colors.BOLD}{Colors.WHITE}{'─'*120}{Colors.END}")
    
    # Model type info
    xgboost_type = xgboost_data.get('model_type', 'unknown')
    optimized_type = optimized_data.get('model_type', 'unknown')
    print(f"\n{Colors.CYAN}Model Types:{Colors.END}")
    print(f"  XGBoost:     {Colors.BOLD}{xgboost_type}{Colors.END}")
    print(f"  Optimized:   {Colors.BOLD}{optimized_type}{Colors.END}")
    
    # Training data info
    xgboost_games = xgboost_data.get('training_games', 0)
    optimized_games = optimized_data.get('training_games', 0)
    print(f"\n{Colors.CYAN}Training Games:{Colors.END}")
    print(f"  XGBoost:     {xgboost_games}")
    print(f"  Optimized:   {optimized_games}")
    diff_games = xgboost_games - optimized_games
    if diff_games != 0:
        sign = "+" if diff_games > 0 else ""
        print(f"  Difference:  {sign}{diff_games} games")
    
    # Performance metrics
    xgboost_perf = xgboost_data.get('performance', {})
    optimized_perf = optimized_data.get('performance', {})
    
    print(f"\n{Colors.BOLD}{Colors.WHITE}Performance Metrics:{Colors.END}")
    print(f"\n{Colors.CYAN}Winner Accuracy:{Colors.END}")
    xgboost_acc = xgboost_perf.get('winner_accuracy', 0)
    optimized_acc = optimized_perf.get('winner_accuracy', 0)
    print(f"  XGBoost:     {format_percentage(xgboost_acc)}")
    print(f"  Optimized:   {format_percentage(optimized_acc)}")
    print(f"  Comparison:  {compare_metric(xgboost_acc, optimized_acc, higher_better=True)}")
    
    print(f"\n{Colors.CYAN}Mean Absolute Error (MAE) - Lower is Better:{Colors.END}")
    
    # Home MAE
    xgboost_home_mae = xgboost_perf.get('home_mae', None)
    optimized_home_mae = optimized_perf.get('home_mae', None)
    print(f"  Home Score MAE:")
    print(f"    XGBoost:     {format_float(xgboost_home_mae) if xgboost_home_mae else 'N/A'}")
    print(f"    Optimized:   {format_float(optimized_home_mae) if optimized_home_mae else 'N/A'}")
    if xgboost_home_mae and optimized_home_mae:
        print(f"    Comparison:  {compare_metric(xgboost_home_mae, optimized_home_mae, higher_better=False)}")
    
    # Away MAE
    xgboost_away_mae = xgboost_perf.get('away_mae', None)
    optimized_away_mae = optimized_perf.get('away_mae', None)
    print(f"  Away Score MAE:")
    print(f"    XGBoost:     {format_float(xgboost_away_mae) if xgboost_away_mae else 'N/A'}")
    print(f"    Optimized:   {format_float(optimized_away_mae) if optimized_away_mae else 'N/A'}")
    if xgboost_away_mae and optimized_away_mae:
        print(f"    Comparison:  {compare_metric(xgboost_away_mae, optimized_away_mae, higher_better=False)}")
    
    # Overall MAE
    xgboost_overall_mae = xgboost_perf.get('overall_mae', None)
    optimized_overall_mae = optimized_perf.get('overall_mae', None)
    print(f"  Overall MAE:")
    print(f"    XGBoost:     {format_float(xgboost_overall_mae) if xgboost_overall_mae else 'N/A'}")
    print(f"    Optimized:   {format_float(optimized_overall_mae) if optimized_overall_mae else 'N/A'}")
    if xgboost_overall_mae and optimized_overall_mae:
        print(f"    Comparison:  {compare_metric(xgboost_overall_mae, optimized_overall_mae, higher_better=False)}")
    
    # Feature selection (if available)
    if 'feature_selection' in optimized_data:
        fs = optimized_data['feature_selection']
        print(f"\n{Colors.CYAN}Feature Selection (Optimized):{Colors.END}")
        print(f"  Original:  {fs.get('original', 'N/A')} features")
        print(f"  Selected:  {fs.get('selected', 'N/A')} features")
        reduction = fs.get('original', 0) - fs.get('selected', 0)
        if reduction > 0:
            print(f"  Reduced:   {reduction} features ({format_percentage(reduction/fs.get('original', 1))})")

def print_summary(xgboost_registry: Dict, optimized_registry: Dict):
    """Print summary statistics"""
    print(f"\n{Colors.BOLD}{Colors.WHITE}{'='*120}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'SUMMARY STATISTICS':^120}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.WHITE}{'='*120}{Colors.END}\n")
    
    xgboost_leagues = xgboost_registry.get('leagues', {})
    optimized_leagues = optimized_registry.get('leagues', {})
    
    # Get common leagues
    common_league_ids = set(xgboost_leagues.keys()) & set(optimized_leagues.keys())
    
    # Calculate averages
    xgboost_accuracies = []
    optimized_accuracies = []
    xgboost_overall_maes = []
    optimized_overall_maes = []
    xgboost_better_accuracy = 0
    xgboost_better_mae = 0
    optimized_better_accuracy = 0
    optimized_better_mae = 0
    ties_accuracy = 0
    ties_mae = 0
    
    for league_id in common_league_ids:
        xgboost_perf = xgboost_leagues[league_id].get('performance', {})
        optimized_perf = optimized_leagues[league_id].get('performance', {})
        
        xgboost_acc = xgboost_perf.get('winner_accuracy', 0)
        optimized_acc = optimized_perf.get('winner_accuracy', 0)
        
        xgboost_mae = xgboost_perf.get('overall_mae', None)
        optimized_mae = optimized_perf.get('overall_mae', None)
        
        if xgboost_acc and optimized_acc:
            xgboost_accuracies.append(xgboost_acc)
            optimized_accuracies.append(optimized_acc)
            
            if abs(xgboost_acc - optimized_acc) < 0.001:
                ties_accuracy += 1
            elif xgboost_acc > optimized_acc:
                xgboost_better_accuracy += 1
            else:
                optimized_better_accuracy += 1
        
        if xgboost_mae and optimized_mae:
            xgboost_overall_maes.append(xgboost_mae)
            optimized_overall_maes.append(optimized_mae)
            
            if abs(xgboost_mae - optimized_mae) < 0.01:
                ties_mae += 1
            elif xgboost_mae < optimized_mae:
                xgboost_better_mae += 1
            else:
                optimized_better_mae += 1
    
    print(f"{Colors.CYAN}Average Winner Accuracy:{Colors.END}")
    if xgboost_accuracies:
        avg_xgboost = sum(xgboost_accuracies) / len(xgboost_accuracies)
        avg_optimized = sum(optimized_accuracies) / len(optimized_accuracies)
        print(f"  XGBoost:     {format_percentage(avg_xgboost)}")
        print(f"  Optimized:   {format_percentage(avg_optimized)}")
        diff = avg_xgboost - avg_optimized
        color = Colors.GREEN if diff > 0 else Colors.RED if diff < 0 else Colors.CYAN
        sign = "+" if diff > 0 else ""
        print(f"  Difference:  {color}{sign}{format_percentage(diff)}{Colors.END}")
    
    print(f"\n{Colors.CYAN}Average Overall MAE:{Colors.END}")
    if xgboost_overall_maes:
        avg_xgboost_mae = sum(xgboost_overall_maes) / len(xgboost_overall_maes)
        avg_optimized_mae = sum(optimized_overall_maes) / len(optimized_overall_maes)
        print(f"  XGBoost:     {format_float(avg_xgboost_mae)}")
        print(f"  Optimized:   {format_float(avg_optimized_mae)}")
        diff = avg_xgboost_mae - avg_optimized_mae
        color = Colors.GREEN if diff < 0 else Colors.RED if diff > 0 else Colors.CYAN
        sign = "+" if diff > 0 else ""
        print(f"  Difference:  {color}{sign}{format_float(diff)}{Colors.END}")
    
    print(f"\n{Colors.CYAN}Win Count (Better Performance):{Colors.END}")
    print(f"  Winner Accuracy:")
    print(f"    XGBoost:     {Colors.GREEN}{xgboost_better_accuracy}{Colors.END} leagues")
    print(f"    Optimized:   {Colors.RED}{optimized_better_accuracy}{Colors.END} leagues")
    print(f"    Ties:        {Colors.CYAN}{ties_accuracy}{Colors.END} leagues")
    
    print(f"  Overall MAE (lower is better):")
    print(f"    XGBoost:     {Colors.GREEN}{xgboost_better_mae}{Colors.END} leagues")
    print(f"    Optimized:   {Colors.RED}{optimized_better_mae}{Colors.END} leagues")
    print(f"    Ties:        {Colors.CYAN}{ties_mae}{Colors.END} leagues")
    
    print(f"\n{Colors.CYAN}Total Leagues Compared:{Colors.END} {len(common_league_ids)}")
    
    # Overall winner
    print(f"\n{Colors.BOLD}{Colors.WHITE}Overall Winner:{Colors.END}")
    if xgboost_better_accuracy > optimized_better_accuracy:
        print(f"  {Colors.GREEN}✓ XGBoost wins on accuracy ({xgboost_better_accuracy} vs {optimized_better_accuracy}){Colors.END}")
    elif optimized_better_accuracy > xgboost_better_accuracy:
        print(f"  {Colors.RED}✗ Optimized wins on accuracy ({optimized_better_accuracy} vs {xgboost_better_accuracy}){Colors.END}")
    else:
        print(f"  {Colors.CYAN}≈ Tie on accuracy ({xgboost_better_accuracy} each){Colors.END}")
    
    if xgboost_better_mae > optimized_better_mae:
        print(f"  {Colors.GREEN}✓ XGBoost wins on MAE ({xgboost_better_mae} vs {optimized_better_mae}){Colors.END}")
    elif optimized_better_mae > xgboost_better_mae:
        print(f"  {Colors.RED}✗ Optimized wins on MAE ({optimized_better_mae} vs {xgboost_better_mae}){Colors.END}")
    else:
        print(f"  {Colors.CYAN}≈ Tie on MAE ({xgboost_better_mae} each){Colors.END}")

def main():
    """Main comparison function"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    xgboost_registry_path = project_root / "artifacts" / "model_registry.json"
    optimized_registry_path = project_root / "artifacts_optimized" / "model_registry_optimized.json"
    
    print(f"{Colors.BOLD}Loading registries...{Colors.END}")
    xgboost_registry = load_registry(str(xgboost_registry_path))
    optimized_registry = load_registry(str(optimized_registry_path))
    
    if not xgboost_registry or not optimized_registry:
        print(f"{Colors.RED}❌ Failed to load one or both registries{Colors.END}")
        sys.exit(1)
    
    print(f"{Colors.GREEN}✓ Loaded XGBoost registry{Colors.END}")
    print(f"{Colors.GREEN}✓ Loaded Optimized registry{Colors.END}")
    
    # Print metadata
    print(f"\n{Colors.CYAN}Registry Metadata:{Colors.END}")
    print(f"  XGBoost Last Updated:   {xgboost_registry.get('last_updated', 'N/A')}")
    print(f"  Optimized Last Updated: {optimized_registry.get('last_updated', 'N/A')}")
    
    xgboost_leagues = xgboost_registry.get('leagues', {})
    optimized_leagues = optimized_registry.get('leagues', {})
    
    print_header()
    
    # Compare each league
    common_league_ids = set(xgboost_leagues.keys()) & set(optimized_leagues.keys())
    only_xgboost = set(xgboost_leagues.keys()) - set(optimized_leagues.keys())
    only_optimized = set(optimized_leagues.keys()) - set(xgboost_leagues.keys())
    
    if only_xgboost:
        print(f"\n{Colors.YELLOW}⚠️  Leagues only in XGBoost: {', '.join(only_xgboost)}{Colors.END}")
    if only_optimized:
        print(f"\n{Colors.YELLOW}⚠️  Leagues only in Optimized: {', '.join(only_optimized)}{Colors.END}")
    
    # Sort by league name for consistent output
    sorted_league_ids = sorted(common_league_ids, key=lambda lid: xgboost_leagues[lid].get('name', ''))
    
    for league_id in sorted_league_ids:
        league_name = xgboost_leagues[league_id].get('name', f'League {league_id}')
        print_league_comparison(league_id, league_name, xgboost_leagues[league_id], optimized_leagues[league_id])
    
    # Print summary
    print_summary(xgboost_registry, optimized_registry)
    
    print(f"\n{Colors.BOLD}{'='*120}{Colors.END}\n")

if __name__ == "__main__":
    main()

