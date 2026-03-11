"""
Get historical games with AI predictions vs actual results
Organized by year and week for display in the UI
"""

import sqlite3
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
import sys
import os

# Add parent directory to path to import prediction modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.hybrid_predictor import MultiLeaguePredictor
from prediction.db import connect

def get_week_number(date_str: str) -> int:
    """Get ISO week number from date string (YYYY-MM-DD)"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.isocalendar()[1]
    except:
        return 0

def get_year_week_key(date_str: str) -> str:
    """Get year-week key for grouping (e.g., '2024-W01')"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        year, week, _ = date_obj.isocalendar()
        return f"{year}-W{week:02d}"
    except:
        return "Unknown"

def get_completed_matches_with_predictions(
    db_path: str, 
    league_id: Optional[int] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get all completed matches with their AI predictions
    
    Returns:
        Dictionary with matches organized by year-week, plus accuracy stats
    """
    conn = connect(db_path)
    cursor = conn.cursor()
    
    # Query for completed matches with scores
    query = """
    SELECT 
        e.id,
        e.league_id,
        l.name as league_name,
        e.date_event,
        e.home_team_id,
        e.away_team_id,
        e.home_score,
        e.away_score,
        t1.name as home_team_name,
        t2.name as away_team_name,
        e.season,
        e.round,
        e.venue,
        e.status
    FROM event e
    LEFT JOIN league l ON e.league_id = l.id
    LEFT JOIN team t1 ON e.home_team_id = t1.id
    LEFT JOIN team t2 ON e.away_team_id = t2.id
    WHERE e.home_score IS NOT NULL 
    AND e.away_score IS NOT NULL
    AND e.date_event IS NOT NULL
    AND e.date_event <= date('now')
    """
    
    params = []
    if league_id:
        query += " AND e.league_id = ?"
        params.append(league_id)
    
    query += " ORDER BY e.date_event DESC, e.league_id"
    
    if limit:
        query += f" LIMIT ?"
        params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    # Initialize predictor for generating predictions
    try:
        predictor = MultiLeaguePredictor(db_path=db_path)
    except Exception as e:
        print(f"Warning: Could not initialize predictor: {e}")
        predictor = None
    
    # Organize matches by year-week
    matches_by_year_week = defaultdict(lambda: defaultdict(list))
    all_matches = []
    
    correct_predictions = 0
    total_predictions = 0
    score_errors = []
    
    for row in results:
        match_id, league_id_val, league_name, date_event, home_team_id, away_team_id, \
        home_score, away_score, home_team_name, away_team_name, season, round_num, \
        venue, status = row
        
        # Skip if missing critical data
        if not home_team_name or not away_team_name or not date_event:
            continue
        
        # Determine actual winner
        if home_score > away_score:
            actual_winner = 'Home'
            actual_winner_team = home_team_name
        elif away_score > home_score:
            actual_winner = 'Away'
            actual_winner_team = away_team_name
        else:
            actual_winner = 'Draw'
            actual_winner_team = None
        
        # Generate prediction for this match
        predicted_winner = None
        predicted_home_score = None
        predicted_away_score = None
        prediction_confidence = None
        prediction_error = None
        
        if predictor:
            try:
                pred = predictor.predict_match(
                    home_team=home_team_name,
                    away_team=away_team_name,
                    league_id=league_id_val,
                    match_date=date_event
                )
                
                predicted_home_score = pred.get('predicted_home_score', 0)
                predicted_away_score = pred.get('predicted_away_score', 0)
                prediction_confidence = pred.get('confidence', 0.5)
                predicted_winner = pred.get('predicted_winner', 'Unknown')
                
                # Check if prediction was correct
                if predicted_winner == actual_winner:
                    correct_predictions += 1
                total_predictions += 1
                
                # Calculate score prediction error
                home_error = abs(predicted_home_score - home_score)
                away_error = abs(predicted_away_score - away_score)
                prediction_error = home_error + away_error
                score_errors.append(prediction_error)
                
            except Exception as e:
                print(f"Warning: Could not generate prediction for {home_team_name} vs {away_team_name} on {date_event}: {e}")
                predicted_winner = 'Error'
        
        # Get year-week key
        year_week_key = get_year_week_key(date_event)
        year = date_event[:4] if date_event else "Unknown"
        week = get_week_number(date_event)
        
        match_data = {
            'match_id': match_id,
            'league_id': league_id_val,
            'league_name': league_name or f"League {league_id_val}",
            'date': date_event,
            'year': year,
            'week': week,
            'year_week': year_week_key,
            'season': season,
            'round': round_num,
            'venue': venue,
            'status': status,
            'home_team': home_team_name,
            'away_team': away_team_name,
            'home_team_id': home_team_id,
            'away_team_id': away_team_id,
            'actual_home_score': home_score,
            'actual_away_score': away_score,
            'actual_winner': actual_winner,
            'actual_winner_team': actual_winner_team,
            'predicted_home_score': predicted_home_score,
            'predicted_away_score': predicted_away_score,
            'predicted_winner': predicted_winner,
            'prediction_confidence': prediction_confidence,
            'prediction_error': prediction_error,
            'prediction_correct': predicted_winner == actual_winner if predicted_winner and predicted_winner != 'Error' else None,
            'score_difference': abs(home_score - away_score) if home_score and away_score else None,
            'predicted_score_difference': abs(predicted_home_score - predicted_away_score) if predicted_home_score is not None and predicted_away_score is not None else None,
        }
        
        matches_by_year_week[year][year_week_key].append(match_data)
        all_matches.append(match_data)
    
    conn.close()
    
    # Calculate accuracy statistics
    accuracy = (correct_predictions / total_predictions * 100) if total_predictions > 0 else 0
    avg_score_error = sum(score_errors) / len(score_errors) if score_errors else None
    
    # Convert defaultdict to regular dict for JSON serialization
    result = {
        'matches_by_year_week': {
            year: {
                week_key: matches
                for week_key, matches in weeks.items()
            }
            for year, weeks in matches_by_year_week.items()
        },
        'all_matches': all_matches,
        'statistics': {
            'total_matches': len(all_matches),
            'total_predictions': total_predictions,
            'correct_predictions': correct_predictions,
            'accuracy_percentage': round(accuracy, 2),
            'average_score_error': round(avg_score_error, 2) if avg_score_error else None,
        },
        'by_league': {}
    }
    
    # Group by league for easier filtering
    leagues_dict = defaultdict(list)
    for match in all_matches:
        leagues_dict[match['league_id']].append(match)
    
    for league_id_val, league_matches in leagues_dict.items():
        league_correct = sum(1 for m in league_matches if m.get('prediction_correct') is True)
        league_total = sum(1 for m in league_matches if m.get('prediction_correct') is not None)
        league_accuracy = (league_correct / league_total * 100) if league_total > 0 else 0
        
        result['by_league'][league_id_val] = {
            'league_name': league_matches[0]['league_name'] if league_matches else f"League {league_id_val}",
            'total_matches': len(league_matches),
            'total_predictions': league_total,
            'correct_predictions': league_correct,
            'accuracy_percentage': round(league_accuracy, 2),
        }
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Get historical games with predictions vs actual results')
    parser.add_argument('--db', type=str, default='data.sqlite', help='Path to SQLite database')
    parser.add_argument('--league-id', type=int, help='Filter by specific league ID')
    parser.add_argument('--limit', type=int, help='Limit number of matches returned')
    parser.add_argument('--output', type=str, help='Output JSON file path')
    parser.add_argument('--format', choices=['json', 'summary'], default='json', help='Output format')
    
    args = parser.parse_args()
    
    print(f"Fetching historical matches from {args.db}...")
    if args.league_id:
        print(f"Filtering by league ID: {args.league_id}")
    if args.limit:
        print(f"Limiting to {args.limit} matches")
    
    try:
        result = get_completed_matches_with_predictions(
            db_path=args.db,
            league_id=args.league_id,
            limit=args.limit
        )
        
        if args.format == 'summary':
            print("\n" + "="*80)
            print("HISTORICAL PREDICTIONS SUMMARY")
            print("="*80)
            print(f"\nTotal Matches: {result['statistics']['total_matches']}")
            print(f"Total Predictions Generated: {result['statistics']['total_predictions']}")
            print(f"Correct Predictions: {result['statistics']['correct_predictions']}")
            print(f"Overall Accuracy: {result['statistics']['accuracy_percentage']:.2f}%")
            if result['statistics']['average_score_error']:
                print(f"Average Score Error: {result['statistics']['average_score_error']:.2f} points")
            
            print("\n" + "-"*80)
            print("BY LEAGUE:")
            print("-"*80)
            for league_id_val, stats in result['by_league'].items():
                print(f"\n{stats['league_name']} (ID: {league_id_val}):")
                print(f"  Matches: {stats['total_matches']}")
                print(f"  Predictions: {stats['total_predictions']}")
                print(f"  Correct: {stats['correct_predictions']}")
                print(f"  Accuracy: {stats['accuracy_percentage']:.2f}%")
            
            print("\n" + "-"*80)
            print("BY YEAR-WEEK:")
            print("-"*80)
            for year in sorted(result['matches_by_year_week'].keys(), reverse=True):
                print(f"\n{year}:")
                for week_key in sorted(result['matches_by_year_week'][year].keys(), reverse=True):
                    matches = result['matches_by_year_week'][year][week_key]
                    print(f"  {week_key}: {len(matches)} matches")
        else:
            # JSON output
            output_json = json.dumps(result, indent=2, default=str)
            
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(output_json)
                print(f"\nResults saved to {args.output}")
            else:
                print(output_json)
                
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

