#!/usr/bin/env python3
"""
Check ALL games for a team to see if we're missing any
"""

import sqlite3
import sys
from typing import List, Dict
from datetime import datetime

def get_all_team_games(cursor: sqlite3.Cursor, team_id: int, team_name: str) -> Dict:
    """Get ALL games for a team, no filters"""
    
    # Get ALL games (any status, any date)
    cursor.execute("""
        SELECT e.id, e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
               e.date_event, e.league_id, e.status,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        ORDER BY e.date_event DESC
    """, (team_id, team_id))
    all_games = cursor.fetchall()
    
    # Get games with scores
    cursor.execute("""
        SELECT e.id, e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
               e.date_event, e.league_id, e.status,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        ORDER BY e.date_event DESC
    """, (team_id, team_id))
    games_with_scores = cursor.fetchall()
    
    # Get past games with scores
    cursor.execute("""
        SELECT e.id, e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
               e.date_event, e.league_id, e.status,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        AND e.date_event < date('now')
        ORDER BY e.date_event DESC
    """, (team_id, team_id))
    past_games = cursor.fetchall()
    
    # Get last 5 past games (what the form calculation uses)
    cursor.execute("""
        SELECT e.id, e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
               e.date_event, e.league_id, e.status,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        AND e.date_event < date('now')
        ORDER BY e.date_event DESC
        LIMIT 5
    """, (team_id, team_id))
    last_5_games = cursor.fetchall()
    
    return {
        'all_games': all_games,
        'games_with_scores': games_with_scores,
        'past_games': past_games,
        'last_5_games': last_5_games
    }


def analyze_team_games(cursor: sqlite3.Cursor, team_id: int, team_name: str, league_id: int = None):
    """Analyze all games for a team"""
    print(f"\n{'='*80}")
    print(f"🔍 COMPLETE GAME ANALYSIS: {team_name} (ID: {team_id})")
    print(f"{'='*80}\n")
    
    games_data = get_all_team_games(cursor, team_id, team_name)
    
    print(f"📊 GAME COUNTS:")
    print(f"   Total games (any status): {len(games_data['all_games'])}")
    print(f"   Games with scores: {len(games_data['games_with_scores'])}")
    print(f"   Past games with scores: {len(games_data['past_games'])}")
    print(f"   Last 5 games (used for form): {len(games_data['last_5_games'])}\n")
    
    # Show all games with scores
    if games_data['games_with_scores']:
        print(f"{'='*80}")
        print(f"📋 ALL GAMES WITH SCORES ({len(games_data['games_with_scores'])} games)")
        print(f"{'='*80}\n")
        
        for i, game in enumerate(games_data['games_with_scores'], 1):
            event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
            was_home = home_id == team_id
            team_score = home_score if was_home else away_score
            opp_score = away_score if was_home else home_score
            opponent = away_team if was_home else home_team
            
            if team_score > opp_score:
                result = "WIN"
                icon = "✅"
            elif team_score == opp_score:
                result = "DRAW"
                icon = "⚖️"
            else:
                result = "LOSS"
                icon = "❌"
            
            is_past = date_event < datetime.now().strftime('%Y-%m-%d')
            past_marker = " (PAST)" if is_past else " (FUTURE)"
            in_last_5 = game in games_data['last_5_games']
            last_5_marker = " ⭐ (IN LAST 5)" if in_last_5 else ""
            
            print(f"   {i}. {date_event}{past_marker}: {team_name} {team_score}-{opp_score} vs {opponent} [{'HOME' if was_home else 'AWAY'}] - {icon} {result} (League: {game_league_id}){last_5_marker}")
    
    # Show games without scores
    games_without_scores = [g for g in games_data['all_games'] if g not in games_data['games_with_scores']]
    if games_without_scores:
        print(f"\n{'='*80}")
        print(f"⚠️  GAMES WITHOUT SCORES ({len(games_without_scores)} games)")
        print(f"{'='*80}\n")
        for i, game in enumerate(games_without_scores[:10], 1):
            event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
            was_home = home_id == team_id
            opponent = away_team if was_home else home_team
            print(f"   {i}. {date_event}: {team_name} vs {opponent} [{'HOME' if was_home else 'AWAY'}] - Status: {status or 'Unknown'} (League: {game_league_id})")
        if len(games_without_scores) > 10:
            print(f"   ... and {len(games_without_scores) - 10} more")
    
    # Analyze last 5 games
    if games_data['last_5_games']:
        print(f"\n{'='*80}")
        print(f"⭐ LAST 5 GAMES (USED FOR FORM CALCULATION)")
        print(f"{'='*80}\n")
        
        wins = 0
        draws = 0
        losses = 0
        
        for i, game in enumerate(games_data['last_5_games'], 1):
            event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
            was_home = home_id == team_id
            team_score = home_score if was_home else away_score
            opp_score = away_score if was_home else home_score
            opponent = away_team if was_home else home_team
            
            if team_score > opp_score:
                result = "WIN"
                icon = "✅"
                wins += 1
            elif team_score == opp_score:
                result = "DRAW"
                icon = "⚖️"
                draws += 1
            else:
                result = "LOSS"
                icon = "❌"
                losses += 1
            
            print(f"   Game {i} ({date_event}): {team_name} {team_score}-{opp_score} vs {opponent} [{'HOME' if was_home else 'AWAY'}] - {icon} {result}")
        
        win_rate = (wins / len(games_data['last_5_games']) * 100) if games_data['last_5_games'] else 0.0
        print(f"\n   📊 Summary: {wins}W/{draws}D/{losses}L = {win_rate:.1f}% win rate")
    
    # Check for missing games
    if len(games_data['past_games']) > 5:
        print(f"\n{'='*80}")
        print(f"⚠️  POTENTIAL MISSING GAMES")
        print(f"{'='*80}\n")
        print(f"   Team has {len(games_data['past_games'])} past games, but only last 5 are used for form.")
        print(f"   Games NOT included in form calculation:")
        excluded_games = games_data['past_games'][5:]
        for i, game in enumerate(excluded_games[:10], 1):
            event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
            was_home = home_id == team_id
            team_score = home_score if was_home else away_score
            opp_score = away_score if was_home else home_score
            opponent = away_team if was_home else home_team
            result = "WIN" if team_score > opp_score else ("DRAW" if team_score == opp_score else "LOSS")
            print(f"      {date_event}: {team_name} {team_score}-{opp_score} vs {opponent} - {result}")
        if len(excluded_games) > 10:
            print(f"      ... and {len(excluded_games) - 10} more")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Check all games for a team')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--team-id', type=int, help='Team ID to check')
    parser.add_argument('--team-name', help='Team name to check')
    parser.add_argument('--check-zero-teams', action='store_true', help='Check all teams with 0% win rate')
    
    args = parser.parse_args()
    
    try:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()
        
        if args.check_zero_teams:
            # Find all teams with 0% win rate
            cursor.execute("""
                SELECT DISTINCT t.id, t.name, t.league_id
                FROM team t
                JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
                WHERE e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY t.name
            """)
            teams = cursor.fetchall()
            
            zero_teams = []
            for team_id, team_name, league_id in teams:
                # Quick check for 0% win rate
                cursor.execute("""
                    SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id
                    FROM event e
                    WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                    AND e.home_score IS NOT NULL
                    AND e.away_score IS NOT NULL
                    AND e.date_event < date('now')
                    ORDER BY e.date_event DESC
                    LIMIT 5
                """, (team_id, team_id))
                games = cursor.fetchall()
                
                wins = 0
                for home_score, away_score, home_id, away_id in games:
                    if home_id == team_id:
                        if home_score > away_score:
                            wins += 1
                    else:
                        if away_score > home_score:
                            wins += 1
                
                if wins == 0 and len(games) >= 3:
                    zero_teams.append((team_id, team_name, league_id))
            
            print(f"Found {len(zero_teams)} teams with 0% win rate\n")
            for team_id, team_name, league_id in zero_teams:
                analyze_team_games(cursor, team_id, team_name, league_id)
        
        elif args.team_id:
            cursor.execute("SELECT name, league_id FROM team WHERE id = ?", (args.team_id,))
            team_info = cursor.fetchone()
            if team_info:
                team_name, league_id = team_info
                analyze_team_games(cursor, args.team_id, team_name, league_id)
            else:
                print(f"❌ Team ID {args.team_id} not found!")
        
        elif args.team_name:
            cursor.execute("SELECT id, name, league_id FROM team WHERE name LIKE ?", (f"%{args.team_name}%",))
            teams = cursor.fetchall()
            if teams:
                for team_id, team_name, league_id in teams:
                    analyze_team_games(cursor, team_id, team_name, league_id)
            else:
                print(f"❌ Team '{args.team_name}' not found!")
        
        else:
            print("❌ Please specify:")
            print("   --team-id <id>          : Check specific team")
            print("   --team-name <name>      : Check specific team")
            print("   --check-zero-teams      : Check all 0% win rate teams")
            print("\nExample:")
            print("   python scripts/check_team_all_games.py --team-name 'Newcastle Red Bulls'")
            print("   python scripts/check_team_all_games.py --check-zero-teams")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

