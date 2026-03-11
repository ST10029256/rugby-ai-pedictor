#!/usr/bin/env python3
"""
Deep investigation script for teams showing NO_DATA
Checks extensively to find why teams appear to have no games
"""

import sqlite3
import sys
from typing import List, Tuple, Optional

def deep_check_team(cursor: sqlite3.Cursor, team_id: int, team_name: str):
    """Extensively check a team for games in ALL possible ways"""
    print(f"\n{'='*80}")
    print(f"🔍 DEEP CHECK: {team_name} (ID: {team_id})")
    print(f"{'='*80}")
    
    # 1. Check ALL games (no filters)
    print(f"\n1️⃣  CHECKING ALL GAMES (no filters):")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event e
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
    """, (team_id, team_id))
    total_games = cursor.fetchone()[0]
    print(f"   Total games (any status): {total_games}")
    
    # 2. Check games with scores
    print(f"\n2️⃣  CHECKING GAMES WITH SCORES:")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event e
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
    """, (team_id, team_id))
    games_with_scores = cursor.fetchone()[0]
    print(f"   Games with scores: {games_with_scores}")
    
    # 3. Check games by date
    print(f"\n3️⃣  CHECKING GAMES BY DATE:")
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event e
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        AND e.date_event < date('now')
    """, (team_id, team_id))
    past_games = cursor.fetchone()[0]
    print(f"   Past games with scores: {past_games}")
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event e
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        AND e.date_event >= date('now')
    """, (team_id, team_id))
    future_games = cursor.fetchone()[0]
    print(f"   Future games with scores: {future_games}")
    
    # 4. Check games by league
    print(f"\n4️⃣  CHECKING GAMES BY LEAGUE:")
    cursor.execute("""
        SELECT e.league_id, COUNT(*) as game_count
        FROM event e
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        AND e.date_event < date('now')
        GROUP BY e.league_id
        ORDER BY game_count DESC
    """, (team_id, team_id))
    league_games = cursor.fetchall()
    if league_games:
        print(f"   Games found in {len(league_games)} different leagues:")
        for league_id, count in league_games:
            cursor.execute("SELECT name FROM league WHERE id = ?", (league_id,))
            league_name = cursor.fetchone()
            league_name_str = league_name[0] if league_name else f"Unknown (ID: {league_id})"
            print(f"      League {league_id} ({league_name_str}): {count} games")
    else:
        print(f"   ⚠️  No games found in any league!")
    
    # 5. Show actual games
    print(f"\n5️⃣  SHOWING ACTUAL GAMES (last 10):")
    cursor.execute("""
        SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
               e.home_score, e.away_score,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        AND e.home_score IS NOT NULL
        AND e.away_score IS NOT NULL
        ORDER BY e.date_event DESC
        LIMIT 10
    """, (team_id, team_id))
    games = cursor.fetchall()
    
    if games:
        print(f"   Found {len(games)} games:")
        for game in games:
            event_id, game_league_id, date_event, home_id, away_id, home_score, away_score, home_team, away_team = game
            was_home = home_id == team_id
            team_score = home_score if was_home else away_score
            opp_score = away_score if was_home else home_score
            result = "WIN" if team_score > opp_score else ("DRAW" if team_score == opp_score else "LOSS")
            venue = "HOME" if was_home else "AWAY"
            print(f"      {date_event}: {team_name} {team_score}-{opp_score} vs {away_team if was_home else home_team} [{venue}] - {result}")
            print(f"         Event ID: {event_id}, League: {game_league_id}")
    else:
        print(f"   ⚠️  NO GAMES FOUND!")
    
    # 6. Check team's assigned league
    print(f"\n6️⃣  TEAM INFORMATION:")
    cursor.execute("SELECT id, name, league_id FROM team WHERE id = ?", (team_id,))
    team_info = cursor.fetchone()
    if team_info:
        tid, tname, tleague_id = team_info
        print(f"   Team ID: {tid}")
        print(f"   Team Name: {tname}")
        print(f"   Assigned League ID: {tleague_id if tleague_id else 'None (unassigned)'}")
        if tleague_id:
            cursor.execute("SELECT name FROM league WHERE id = ?", (tleague_id,))
            league_info = cursor.fetchone()
            league_name = league_info[0] if league_info else "Unknown"
            print(f"   Assigned League Name: {league_name}")
    
    return {
        'total_games': total_games,
        'games_with_scores': games_with_scores,
        'past_games': past_games,
        'future_games': future_games,
        'league_games': league_games,
        'actual_games': games
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Deep check teams showing NO_DATA')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--team-id', type=int, help='Check specific team ID')
    parser.add_argument('--team-name', help='Check specific team name')
    parser.add_argument('--check-all-no-data', action='store_true', help='Check all teams marked as NO_DATA')
    
    args = parser.parse_args()
    
    try:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()
        
        if args.check_all_no_data:
            # Get all teams that appeared as NO_DATA in the scan
            print("🔍 Checking all teams that appeared as NO_DATA...")
            
            # Get teams with no league_id assigned
            cursor.execute("""
                SELECT DISTINCT t.id, t.name, t.league_id
                FROM team t
                WHERE t.league_id IS NULL
                ORDER BY t.name
            """)
            teams_no_league = cursor.fetchall()
            
            print(f"\nFound {len(teams_no_league)} teams with no league_id assigned")
            
            issues_found = []
            for team_id, team_name, team_league_id in teams_no_league:
                # Check if they have games
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM event e
                    WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                    AND e.home_score IS NOT NULL
                    AND e.away_score IS NOT NULL
                    AND e.date_event < date('now')
                """, (team_id, team_id))
                game_count = cursor.fetchone()[0]
                
                if game_count > 0:
                    issues_found.append({
                        'team_id': team_id,
                        'team_name': team_name,
                        'games_found': game_count,
                        'issue': 'Has games but team.league_id is NULL'
                    })
            
            if issues_found:
                print(f"\n⚠️  FOUND {len(issues_found)} TEAMS WITH GAMES BUT NO LEAGUE_ID:")
                for issue in issues_found[:20]:  # Show first 20
                    print(f"   {issue['team_name']} (ID: {issue['team_id']}): {issue['games_found']} games")
                    deep_check_team(cursor, issue['team_id'], issue['team_name'])
                if len(issues_found) > 20:
                    print(f"\n   ... and {len(issues_found) - 20} more teams")
            else:
                print("\n✅ All teams with no league_id actually have no games")
        
        elif args.team_id:
            cursor.execute("SELECT name FROM team WHERE id = ?", (args.team_id,))
            team_name = cursor.fetchone()
            if team_name:
                deep_check_team(cursor, args.team_id, team_name[0])
            else:
                print(f"❌ Team ID {args.team_id} not found!")
        
        elif args.team_name:
            cursor.execute("SELECT id, name FROM team WHERE name LIKE ?", (f"%{args.team_name}%",))
            teams = cursor.fetchall()
            if teams:
                for team_id, team_name in teams:
                    deep_check_team(cursor, team_id, team_name)
            else:
                print(f"❌ Team '{args.team_name}' not found!")
        
        else:
            print("❌ Please specify:")
            print("   --team-id <id>          : Check specific team")
            print("   --team-name <name>      : Check specific team")
            print("   --check-all-no-data     : Check all NO_DATA teams")
            print("\nExample:")
            print("   python scripts/debug_teams_no_data.py --check-all-no-data")
            print("   python scripts/debug_teams_no_data.py --team-name 'Cardiff'")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

