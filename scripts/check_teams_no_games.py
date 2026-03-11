#!/usr/bin/env python3
"""
Check which teams have no games in the database
"""

import sqlite3
import sys
from typing import List, Tuple

def find_teams_with_no_games(db_path: str):
    """Find all teams that have no games in the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"{'='*80}")
    print(f"🔍 FINDING TEAMS WITH NO GAMES")
    print(f"{'='*80}")
    print(f"Database: {db_path}\n")
    
    # Find all teams
    cursor.execute("""
        SELECT id, name, league_id
        FROM team
        ORDER BY name
    """)
    all_teams = cursor.fetchall()
    
    print(f"Total teams in database: {len(all_teams)}\n")
    
    # Check each team for games
    teams_with_no_games = []
    teams_with_games = []
    
    for team_id, team_name, league_id in all_teams:
        # Check if team has any games (any status)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM event e
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        """, (team_id, team_id))
        total_games = cursor.fetchone()[0]
        
        # Check if team has games with scores
        cursor.execute("""
            SELECT COUNT(*) 
            FROM event e
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
        """, (team_id, team_id))
        games_with_scores = cursor.fetchone()[0]
        
        # Check if team has past games with scores
        cursor.execute("""
            SELECT COUNT(*) 
            FROM event e
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
            AND e.date_event < date('now')
        """, (team_id, team_id))
        past_games = cursor.fetchone()[0]
        
        if total_games == 0:
            teams_with_no_games.append({
                'id': team_id,
                'name': team_name,
                'league_id': league_id,
                'total_games': 0,
                'games_with_scores': 0,
                'past_games': 0
            })
        else:
            teams_with_games.append({
                'id': team_id,
                'name': team_name,
                'league_id': league_id,
                'total_games': total_games,
                'games_with_scores': games_with_scores,
                'past_games': past_games
            })
    
    # Report results
    print(f"{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}\n")
    print(f"Teams with games: {len(teams_with_games)}")
    print(f"Teams with NO games: {len(teams_with_no_games)}\n")
    
    # Show teams with no games
    if teams_with_no_games:
        print(f"{'='*80}")
        print(f"⚠️  TEAMS WITH NO GAMES ({len(teams_with_no_games)} teams)")
        print(f"{'='*80}\n")
        
        # Group by league
        by_league = {}
        no_league = []
        
        for team in teams_with_no_games:
            league_id = team['league_id']
            if league_id:
                if league_id not in by_league:
                    by_league[league_id] = []
                by_league[league_id].append(team)
            else:
                no_league.append(team)
        
        # Show teams with no league_id
        if no_league:
            print(f"📋 Teams with NO league_id assigned ({len(no_league)} teams):")
            for team in sorted(no_league, key=lambda x: x['name']):
                print(f"   - {team['name']} (ID: {team['id']})")
            print()
        
        # Show teams by league
        for league_id, teams in sorted(by_league.items()):
            cursor.execute("SELECT name FROM league WHERE id = ?", (league_id,))
            league_info = cursor.fetchone()
            league_name = league_info[0] if league_info else f"Unknown (ID: {league_id})"
            
            print(f"📋 League: {league_name} (ID: {league_id}) - {len(teams)} teams with no games:")
            for team in sorted(teams, key=lambda x: x['name']):
                print(f"   - {team['name']} (ID: {team['id']})")
            print()
        
        # Show all teams in a simple list
        print(f"{'='*80}")
        print(f"📋 COMPLETE LIST (sorted by name)")
        print(f"{'='*80}\n")
        for team in sorted(teams_with_no_games, key=lambda x: x['name']):
            league_str = f"League: {team['league_id']}" if team['league_id'] else "No league assigned"
            print(f"   {team['name']} (ID: {team['id']}, {league_str})")
    else:
        print("✅ All teams have at least one game!")
    
    # Show teams with games but no scores (for reference)
    teams_with_games_but_no_scores = [
        t for t in teams_with_games 
        if t['total_games'] > 0 and t['games_with_scores'] == 0
    ]
    
    if teams_with_games_but_no_scores:
        print(f"\n{'='*80}")
        print(f"ℹ️  TEAMS WITH GAMES BUT NO SCORES ({len(teams_with_games_but_no_scores)} teams)")
        print(f"{'='*80}\n")
        for team in sorted(teams_with_games_but_no_scores, key=lambda x: x['name'])[:20]:
            print(f"   - {team['name']} (ID: {team['id']}): {team['total_games']} games, 0 with scores")
        if len(teams_with_games_but_no_scores) > 20:
            print(f"   ... and {len(teams_with_games_but_no_scores) - 20} more")
    
    conn.close()
    return teams_with_no_games


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Find teams with no games')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--export', help='Export to CSV file')
    
    args = parser.parse_args()
    
    try:
        teams_no_games = find_teams_with_no_games(args.db)
        
        if args.export:
            import csv
            with open(args.export, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Team ID', 'Team Name', 'League ID'])
                for team in sorted(teams_no_games, key=lambda x: x['name']):
                    writer.writerow([team['id'], team['name'], team['league_id'] or ''])
            print(f"\n✅ Exported to {args.export}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

