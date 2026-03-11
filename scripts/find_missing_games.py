#!/usr/bin/env python3
"""
Find missing games that should be included in form calculation
"""

import sqlite3
import sys
from datetime import datetime
from typing import List, Dict

def find_missing_games_for_team(cursor: sqlite3.Cursor, team_id: int, team_name: str, league_id: int = None):
    """Find games that should be included but might be missing"""
    
    print(f"\n{'='*80}")
    print(f"🔍 FINDING MISSING GAMES: {team_name} (ID: {team_id})")
    print(f"{'='*80}\n")
    
    # Get ALL past games with scores (no limit)
    if league_id:
        cursor.execute("""
            SELECT e.id, e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
                   e.date_event, e.league_id, e.status,
                   t1.name as home_team, t2.name as away_team
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.league_id = ?
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
            AND e.date_event < date('now')
            ORDER BY e.date_event DESC
        """, (team_id, team_id, league_id))
        league_games = cursor.fetchall()
        
        # Also check all leagues
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
        all_games = cursor.fetchall()
    else:
        league_games = []
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
        all_games = cursor.fetchall()
    
    print(f"📊 GAME COUNTS:")
    print(f"   Games in league {league_id}: {len(league_games) if league_id else 0}")
    print(f"   Games in ALL leagues: {len(all_games)}")
    print(f"   Games that SHOULD be used: {len(league_games) if league_games else len(all_games)}")
    print(f"   Games currently used (last 5): {min(5, len(league_games) if league_games else len(all_games))}\n")
    
    # Check for duplicates (same date, same teams)
    games_to_check = league_games if league_games else all_games
    seen_games = {}
    duplicates = []
    
    for game in games_to_check:
        event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
        key = (date_event, min(home_id, away_id), max(home_id, away_id))
        
        if key in seen_games:
            duplicates.append((seen_games[key], game))
        else:
            seen_games[key] = game
    
    if duplicates:
        print(f"⚠️  FOUND {len(duplicates)} DUPLICATE GAMES (same date, same teams):\n")
        for orig, dup in duplicates[:10]:
            orig_id, orig_home, orig_away = orig[0], orig[8], orig[9]
            dup_id, dup_home, dup_away = dup[0], dup[8], dup[9]
            print(f"   Event {orig_id}: {orig_home} vs {orig_away} on {orig[5]}")
            print(f"   Event {dup_id}: {dup_home} vs {dup_away} on {dup[5]}")
            print()
        if len(duplicates) > 10:
            print(f"   ... and {len(duplicates) - 10} more duplicates\n")
    
    # Show last 10 games (more than the 5 used)
    print(f"{'='*80}")
    print(f"📋 LAST 10 GAMES (to see if games are missing)")
    print(f"{'='*80}\n")
    
    for i, game in enumerate(games_to_check[:10], 1):
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
        
        in_last_5 = i <= 5
        marker = "⭐ (IN LAST 5)" if in_last_5 else "❌ (NOT IN LAST 5)"
        
        print(f"   {i}. {date_event}: {team_name} {team_score}-{opp_score} vs {opponent} [{game_league_id}] - {icon} {result} {marker}")
    
    # Check for games that should be more recent
    if len(games_to_check) > 5:
        print(f"\n{'='*80}")
        print(f"⚠️  GAMES NOT INCLUDED IN FORM (but should be considered)")
        print(f"{'='*80}\n")
        print(f"   Total games available: {len(games_to_check)}")
        print(f"   Games used for form: 5")
        print(f"   Games excluded: {len(games_to_check) - 5}\n")
        
        # Check if excluded games have wins
        excluded_games = games_to_check[5:]
        excluded_wins = 0
        for game in excluded_games:
            event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
            was_home = home_id == team_id
            team_score = home_score if was_home else away_score
            opp_score = away_score if was_home else home_score
            if team_score > opp_score:
                excluded_wins += 1
        
        if excluded_wins > 0:
            print(f"   ⚠️  WARNING: {excluded_wins} WIN(S) in excluded games!")
            print(f"   These wins are NOT being counted in the win rate calculation!\n")
            
            print(f"   Excluded games with WINS:")
            for game in excluded_games:
                event_id, home_score, away_score, home_id, away_id, date_event, game_league_id, status, home_team, away_team = game
                was_home = home_id == team_id
                team_score = home_score if was_home else away_score
                opp_score = away_score if was_home else home_score
                opponent = away_team if was_home else home_team
                if team_score > opp_score:
                    print(f"      {date_event}: {team_name} {team_score}-{opp_score} vs {opponent} - ✅ WIN")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Find missing games')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--team-id', type=int, help='Team ID to check')
    parser.add_argument('--team-name', help='Team name to check')
    parser.add_argument('--league-id', type=int, help='League ID filter')
    
    args = parser.parse_args()
    
    try:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()
        
        if args.team_id:
            cursor.execute("SELECT name, league_id FROM team WHERE id = ?", (args.team_id,))
            team_info = cursor.fetchone()
            if team_info:
                team_name, team_league_id = team_info
                find_missing_games_for_team(cursor, args.team_id, team_name, args.league_id or team_league_id)
            else:
                print(f"❌ Team ID {args.team_id} not found!")
        
        elif args.team_name:
            cursor.execute("SELECT id, name, league_id FROM team WHERE name LIKE ?", (f"%{args.team_name}%",))
            teams = cursor.fetchall()
            if teams:
                for team_id, team_name, team_league_id in teams:
                    find_missing_games_for_team(cursor, team_id, team_name, args.league_id or team_league_id)
            else:
                print(f"❌ Team '{args.team_name}' not found!")
        
        else:
            print("❌ Please specify --team-id or --team-name")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

