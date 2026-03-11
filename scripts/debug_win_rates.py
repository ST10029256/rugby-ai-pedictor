#!/usr/bin/env python3
"""
Debug script to verify win rate calculations for teams
Shows detailed breakdown of games, wins, losses, and win rates
"""

import sqlite3
import sys
from datetime import datetime
from typing import List, Tuple, Optional
import argparse

def get_team_form_debug(cursor: sqlite3.Cursor, team_id: int, team_name: str, 
                        limit: int = 5, league_id: Optional[int] = None) -> Tuple[List[Tuple], dict]:
    """Get team form with detailed debugging information"""
    
    print(f"\n{'='*80}")
    print(f"🔍 DEBUGGING TEAM: {team_name} (ID: {team_id})")
    print(f"{'='*80}")
    print(f"League ID filter: {league_id if league_id else 'ALL LEAGUES'}")
    print(f"Looking for last {limit} games")
    
    results = []
    used_fallback = False
    
    # Step 1: Try league-specific query
    if league_id:
        print(f"\n📊 Step 1: Querying games from league {league_id}...")
        cursor.execute("""
            SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
                   e.date_event, e.league_id, e.id as event_id,
                   t1.name as home_team_name, t2.name as away_team_name
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.league_id = ?
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
            AND e.date_event < date('now')
            ORDER BY e.date_event DESC
            LIMIT ?
        """, (team_id, team_id, league_id, limit))
        
        rows = cursor.fetchall()
        print(f"   Found {len(rows)} games in league {league_id}")
        
        for row in rows:
            home_score, away_score, home_id, away_id, date_event, game_league_id, event_id, home_team_name, away_team_name = row
            if home_id == team_id:
                results.append((home_score, away_score, date_event, event_id, home_team_name, away_team_name, game_league_id))
            else:
                results.append((away_score, home_score, date_event, event_id, home_team_name, away_team_name, game_league_id))
    
    # Step 2: Fallback to all leagues
    if len(results) == 0:
        used_fallback = True
        print(f"\n📊 Step 2: No games in league {league_id}, querying ALL leagues...")
        cursor.execute("""
            SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
                   e.date_event, e.league_id, e.id as event_id,
                   t1.name as home_team_name, t2.name as away_team_name
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
            AND e.date_event < date('now')
            ORDER BY e.date_event DESC
            LIMIT ?
        """, (team_id, team_id, limit))
        
        rows = cursor.fetchall()
        print(f"   Found {len(rows)} games across all leagues")
        
        for row in rows:
            home_score, away_score, home_id, away_id, date_event, game_league_id, event_id, home_team_name, away_team_name = row
            if home_id == team_id:
                results.append((home_score, away_score, date_event, event_id, home_team_name, away_team_name, game_league_id))
            else:
                results.append((away_score, home_score, date_event, event_id, home_team_name, away_team_name, game_league_id))
    
    # Calculate statistics
    if results:
        wins = sum(1 for r in results if r[0] > r[1])
        draws = sum(1 for r in results if r[0] == r[1])
        losses = len(results) - wins - draws
        win_rate = (wins / len(results) * 100) if results else 0
        
        stats = {
            'total_games': len(results),
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'win_rate': win_rate,
            'used_fallback': used_fallback,
            'source': f"all leagues (fallback)" if used_fallback else (f"league {league_id}" if league_id else "all leagues")
        }
        
        print(f"\n📈 RESULTS:")
        print(f"   Total Games: {stats['total_games']}")
        print(f"   Wins: {stats['wins']}")
        print(f"   Draws: {stats['draws']}")
        print(f"   Losses: {stats['losses']}")
        print(f"   Win Rate: {stats['win_rate']:.1f}%")
        print(f"   Source: {stats['source']}")
        
        print(f"\n📋 GAME DETAILS:")
        for idx, (team_score, opp_score, date_event, event_id, home_team_name, away_team_name, game_league_id) in enumerate(results, 1):
            is_win = team_score > opp_score
            is_draw = team_score == opp_score
            result = "✅ WIN" if is_win else ("⚖️ DRAW" if is_draw else "❌ LOSS")
            
            # Determine if team was home or away
            was_home = (home_team_name == team_name)
            venue = "HOME" if was_home else "AWAY"
            
            print(f"   Game {idx} ({date_event}): {team_name} {team_score}-{opp_score} vs {away_team_name if was_home else home_team_name} [{venue}] - {result}")
            print(f"      Event ID: {event_id}, League: {game_league_id}")
    else:
        stats = {
            'total_games': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0,
            'win_rate': 0.0,
            'used_fallback': used_fallback,
            'source': 'none'
        }
        print(f"\n⚠️  NO GAMES FOUND!")
        print(f"   Checked: {'All leagues' if not league_id else f'League {league_id}'}")
    
    return results, stats


def debug_match(cursor: sqlite3.Cursor, match_id: int):
    """Debug a specific match and its teams"""
    cursor.execute("""
        SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
               t1.name as home_team, t2.name as away_team
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.id = ?
    """, (match_id,))
    
    match = cursor.fetchone()
    if not match:
        print(f"❌ Match {match_id} not found!")
        return
    
    match_id_db, league_id, date_event, home_id, away_id, home_team, away_team = match
    print(f"\n{'='*80}")
    print(f"🏉 MATCH DEBUG: {home_team} vs {away_team}")
    print(f"{'='*80}")
    print(f"Match ID: {match_id_db}")
    print(f"League ID: {league_id}")
    print(f"Date: {date_event}")
    print(f"Home Team ID: {home_id} ({home_team})")
    print(f"Away Team ID: {away_id} ({away_team})")
    
    # Get form for both teams
    home_results, home_stats = get_team_form_debug(cursor, home_id, home_team, limit=5, league_id=league_id)
    away_results, away_stats = get_team_form_debug(cursor, away_id, away_team, limit=5, league_id=league_id)
    
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"{home_team}: {home_stats['win_rate']:.1f}% ({home_stats['wins']}W/{home_stats['draws']}D/{home_stats['losses']}L)")
    print(f"{away_team}: {away_stats['win_rate']:.1f}% ({away_stats['wins']}W/{away_stats['draws']}D/{away_stats['losses']}L)")


def debug_team(cursor: sqlite3.Cursor, team_name: str, league_id: Optional[int] = None):
    """Debug a specific team"""
    # Find team ID
    if league_id:
        cursor.execute("SELECT id, name FROM team WHERE name LIKE ? AND league_id = ?", (f"%{team_name}%", league_id))
    else:
        cursor.execute("SELECT id, name FROM team WHERE name LIKE ?", (f"%{team_name}%",))
    
    teams = cursor.fetchall()
    if not teams:
        print(f"❌ Team '{team_name}' not found!")
        return
    
    if len(teams) > 1:
        print(f"⚠️  Multiple teams found:")
        for tid, tname in teams:
            print(f"   ID: {tid}, Name: {tname}")
        print(f"Using first match: {teams[0][1]} (ID: {teams[0][0]})")
    
    team_id, team_name_found = teams[0]
    get_team_form_debug(cursor, team_id, team_name_found, limit=5, league_id=league_id)


def full_comprehensive_scan(cursor: sqlite3.Cursor, league_id: Optional[int] = None):
    """Comprehensive scan of all teams, matches, and potential issues"""
    print(f"\n{'='*80}")
    print(f"🔍 COMPREHENSIVE FULL SCAN")
    print(f"{'='*80}")
    print(f"League Filter: {league_id if league_id else 'ALL LEAGUES'}")
    print(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Get all teams
    if league_id:
        cursor.execute("""
            SELECT DISTINCT t.id, t.name, t.league_id 
            FROM team t 
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = ?
            ORDER BY t.name
        """, (league_id,))
    else:
        cursor.execute("""
            SELECT DISTINCT t.id, t.name, t.league_id 
            FROM team t 
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            ORDER BY t.name
        """)
    
    teams = cursor.fetchall()
    print(f"\n📊 Found {len(teams)} teams with game history")
    
    # 2. Get all upcoming matches
    if league_id:
        cursor.execute("""
            SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                   t1.name as home_team, t2.name as away_team
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE e.date_event >= date('now')
            AND e.date_event <= date('now', '+7 days')
            AND e.league_id = ?
            AND e.home_team_id IS NOT NULL
            AND e.away_team_id IS NOT NULL
            ORDER BY e.date_event ASC
        """, (league_id,))
    else:
        cursor.execute("""
            SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                   t1.name as home_team, t2.name as away_team
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE e.date_event >= date('now')
            AND e.date_event <= date('now', '+7 days')
            AND e.home_team_id IS NOT NULL
            AND e.away_team_id IS NOT NULL
            ORDER BY e.date_event ASC
        """)
    
    upcoming_matches = cursor.fetchall()
    print(f"📅 Found {len(upcoming_matches)} upcoming matches (next 7 days)")
    
    # 3. Scan all teams
    print(f"\n{'='*80}")
    print(f"📋 SCANNING ALL TEAMS")
    print(f"{'='*80}")
    
    team_stats = []
    issues = []
    
    for team_id, team_name, team_league_id in teams:
        # Get form with league filtering
        check_league_id = league_id or team_league_id
        
        # Try league-specific first
        if check_league_id:
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.league_id = ?
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id, check_league_id))
            results = cursor.fetchall()
            used_fallback = len(results) == 0
        else:
            results = []
            used_fallback = False
        
        # Fallback to all leagues
        if used_fallback:
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id))
            results = cursor.fetchall()
        
        # Process results
        form_data = []
        for row in results:
            home_score, away_score, home_id, away_id, date_event, game_league_id = row
            if home_id == team_id:
                form_data.append((home_score, away_score, date_event, game_league_id))
            else:
                form_data.append((away_score, home_score, date_event, game_league_id))
        
        # Calculate stats
        wins = sum(1 for r in form_data if r[0] > r[1])
        draws = sum(1 for r in form_data if r[0] == r[1])
        losses = len(form_data) - wins - draws
        win_rate = (wins / len(form_data) * 100) if form_data else 0
        
        team_stat = {
            'team_id': team_id,
            'team_name': team_name,
            'league_id': team_league_id,
            'games': len(form_data),
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'win_rate': win_rate,
            'used_fallback': used_fallback,
            'check_league_id': check_league_id
        }
        team_stats.append(team_stat)
        
        # Flag issues
        if len(form_data) == 0:
            issues.append({
                'type': 'NO_DATA',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'message': 'No games found in database'
            })
        elif len(form_data) < 3:
            issues.append({
                'type': 'INSUFFICIENT_DATA',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'games': len(form_data),
                'message': f'Only {len(form_data)} games found (need at least 3 for reliable stats)'
            })
        elif used_fallback and check_league_id:
            issues.append({
                'type': 'LEAGUE_FALLBACK',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'games': len(form_data),
                'message': f'No games in league {check_league_id}, using fallback from all leagues'
            })
    
    # 4. Scan upcoming matches
    print(f"\n{'='*80}")
    print(f"🏉 SCANNING UPCOMING MATCHES")
    print(f"{'='*80}")
    
    match_issues = []
    for match in upcoming_matches:
        match_id, match_league_id, match_date, home_id, away_id, home_team, away_team = match
        if not home_team or not away_team:
            match_issues.append({
                'type': 'MISSING_TEAM_NAMES',
                'match_id': match_id,
                'message': f'Match {match_id} has missing team names'
            })
            continue
        
        # Check if both teams have form data
        home_has_data = any(s['team_id'] == home_id and s['games'] > 0 for s in team_stats)
        away_has_data = any(s['team_id'] == away_id and s['games'] > 0 for s in team_stats)
        
        if not home_has_data:
            match_issues.append({
                'type': 'HOME_TEAM_NO_DATA',
                'match_id': match_id,
                'team': home_team,
                'team_id': home_id,
                'message': f'{home_team} has no game history'
            })
        
        if not away_has_data:
            match_issues.append({
                'type': 'AWAY_TEAM_NO_DATA',
                'match_id': match_id,
                'team': away_team,
                'team_id': away_id,
                'message': f'{away_team} has no game history'
            })
    
    # 5. Generate comprehensive report
    print(f"\n{'='*80}")
    print(f"📊 COMPREHENSIVE REPORT")
    print(f"{'='*80}")
    
    # Team statistics
    teams_with_data = [s for s in team_stats if s['games'] > 0]
    teams_without_data = [s for s in team_stats if s['games'] == 0]
    teams_using_fallback = [s for s in team_stats if s['used_fallback']]
    
    print(f"\n✅ TEAMS WITH DATA: {len(teams_with_data)}")
    print(f"   Teams with 5 games: {len([s for s in teams_with_data if s['games'] == 5])}")
    print(f"   Teams with 3-4 games: {len([s for s in teams_with_data if 3 <= s['games'] < 5])}")
    print(f"   Teams with 1-2 games: {len([s for s in teams_with_data if 1 <= s['games'] < 3])}")
    
    print(f"\n⚠️  TEAMS WITHOUT DATA: {len(teams_without_data)}")
    if teams_without_data:
        print(f"   First 10 teams without data:")
        for stat in teams_without_data[:10]:
            print(f"      - {stat['team_name']} (ID: {stat['team_id']}, League: {stat['league_id']})")
    
    print(f"\n🔄 TEAMS USING FALLBACK: {len(teams_using_fallback)}")
    if teams_using_fallback:
        print(f"   Teams that had no games in their league, using all leagues:")
        for stat in teams_using_fallback[:10]:
            print(f"      - {stat['team_name']} (League: {stat['check_league_id']}, Found: {stat['games']} games)")
    
    # Win rate distribution
    print(f"\n📈 WIN RATE DISTRIBUTION:")
    win_rate_ranges = {
        '100%': len([s for s in teams_with_data if s['win_rate'] == 100]),
        '80-99%': len([s for s in teams_with_data if 80 <= s['win_rate'] < 100]),
        '60-79%': len([s for s in teams_with_data if 60 <= s['win_rate'] < 80]),
        '40-59%': len([s for s in teams_with_data if 40 <= s['win_rate'] < 60]),
        '20-39%': len([s for s in teams_with_data if 20 <= s['win_rate'] < 40]),
        '1-19%': len([s for s in teams_with_data if 0 < s['win_rate'] < 20]),
        '0%': len([s for s in teams_with_data if s['win_rate'] == 0]),
    }
    for range_name, count in win_rate_ranges.items():
        print(f"   {range_name}: {count} teams")
    
    # Issues summary
    print(f"\n{'='*80}")
    print(f"⚠️  ISSUES FOUND: {len(issues) + len(match_issues)}")
    print(f"{'='*80}")
    
    if issues:
        issues_by_type = {}
        for issue in issues:
            issue_type = issue['type']
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        for issue_type, issue_list in issues_by_type.items():
            print(f"\n{issue_type}: {len(issue_list)} issues")
            for issue in issue_list[:5]:  # Show first 5 of each type
                print(f"   - {issue['team']} (ID: {issue['team_id']}): {issue['message']}")
            if len(issue_list) > 5:
                print(f"   ... and {len(issue_list) - 5} more")
    
    if match_issues:
        print(f"\nMATCH ISSUES: {len(match_issues)}")
        match_issues_by_type = {}
        for issue in match_issues:
            issue_type = issue['type']
            if issue_type not in match_issues_by_type:
                match_issues_by_type[issue_type] = []
            match_issues_by_type[issue_type].append(issue)
        
        for issue_type, issue_list in match_issues_by_type.items():
            print(f"   {issue_type}: {len(issue_list)} matches")
            for issue in issue_list[:3]:
                print(f"      - Match {issue['match_id']}: {issue['message']}")
    
    # Detailed team breakdown (top and bottom performers)
    print(f"\n{'='*80}")
    print(f"🏆 TOP PERFORMERS (Highest Win Rates)")
    print(f"{'='*80}")
    top_teams = sorted([s for s in teams_with_data if s['games'] >= 3], 
                      key=lambda x: x['win_rate'], reverse=True)[:10]
    for stat in top_teams:
        print(f"   {stat['team_name']}: {stat['win_rate']:.1f}% ({stat['wins']}W/{stat['draws']}D/{stat['losses']}L) - {stat['games']} games")
    
    print(f"\n📉 LOWEST PERFORMERS (Lowest Win Rates)")
    print(f"{'='*80}")
    bottom_teams = sorted([s for s in teams_with_data if s['games'] >= 3], 
                          key=lambda x: x['win_rate'])[:10]
    for stat in bottom_teams:
        print(f"   {stat['team_name']}: {stat['win_rate']:.1f}% ({stat['wins']}W/{stat['draws']}D/{stat['losses']}L) - {stat['games']} games")
    
    print(f"\n{'='*80}")
    print(f"✅ SCAN COMPLETE")
    print(f"{'='*80}")
    print(f"Total Teams Scanned: {len(teams)}")
    print(f"Teams with Data: {len(teams_with_data)}")
    print(f"Teams without Data: {len(teams_without_data)}")
    print(f"Upcoming Matches: {len(upcoming_matches)}")
    print(f"Total Issues Found: {len(issues) + len(match_issues)}")
    
    return {
        'teams': team_stats,
        'issues': issues,
        'match_issues': match_issues,
        'upcoming_matches': upcoming_matches
    }


def full_comprehensive_scan(cursor: sqlite3.Cursor, league_id: Optional[int] = None):
    """Comprehensive scan of all teams, matches, and potential issues"""
    print(f"\n{'='*80}")
    print(f"🔍 COMPREHENSIVE FULL SCAN")
    print(f"{'='*80}")
    print(f"League Filter: {league_id if league_id else 'ALL LEAGUES'}")
    print(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Get all teams
    if league_id:
        cursor.execute("""
            SELECT DISTINCT t.id, t.name, t.league_id 
            FROM team t 
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            WHERE e.league_id = ?
            ORDER BY t.name
        """, (league_id,))
    else:
        cursor.execute("""
            SELECT DISTINCT t.id, t.name, t.league_id 
            FROM team t 
            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
            ORDER BY t.name
        """)
    
    teams = cursor.fetchall()
    print(f"\n📊 Found {len(teams)} teams with game history")
    
    # 2. Get all upcoming matches
    if league_id:
        cursor.execute("""
            SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                   t1.name as home_team, t2.name as away_team
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE e.date_event >= date('now')
            AND e.date_event <= date('now', '+7 days')
            AND e.league_id = ?
            AND e.home_team_id IS NOT NULL
            AND e.away_team_id IS NOT NULL
            ORDER BY e.date_event ASC
        """, (league_id,))
    else:
        cursor.execute("""
            SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                   t1.name as home_team, t2.name as away_team
            FROM event e
            LEFT JOIN team t1 ON e.home_team_id = t1.id
            LEFT JOIN team t2 ON e.away_team_id = t2.id
            WHERE e.date_event >= date('now')
            AND e.date_event <= date('now', '+7 days')
            AND e.home_team_id IS NOT NULL
            AND e.away_team_id IS NOT NULL
            ORDER BY e.date_event ASC
        """)
    
    upcoming_matches = cursor.fetchall()
    print(f"📅 Found {len(upcoming_matches)} upcoming matches (next 7 days)")
    
    # 3. Scan all teams
    print(f"\n{'='*80}")
    print(f"📋 SCANNING ALL TEAMS")
    print(f"{'='*80}")
    print("Processing teams...")
    
    team_stats = []
    issues = []
    
    for idx, (team_id, team_name, team_league_id) in enumerate(teams, 1):
        if idx % 10 == 0:
            print(f"   Processed {idx}/{len(teams)} teams...")
        
        # Get form with league filtering
        # CRITICAL FIX: If team_league_id is None, check ALL leagues immediately
        # Don't try league-specific first if team has no league assigned
        check_league_id = league_id or team_league_id
        
        # If team has no league_id assigned, check ALL leagues directly
        if team_league_id is None and not league_id:
            # Team has no league assigned - check all leagues
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id))
            results = cursor.fetchall()
            used_fallback = False  # Not a fallback, this is the primary check
        elif check_league_id:
            # Try league-specific first
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.league_id = ?
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id, check_league_id))
            results = cursor.fetchall()
            used_fallback = len(results) == 0
        else:
            results = []
            used_fallback = False
        
        # Fallback to all leagues if league-specific search found nothing
        if used_fallback:
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id))
            results = cursor.fetchall()
        
        # Process results
        form_data = []
        for row in results:
            home_score, away_score, home_id, away_id, date_event, game_league_id = row
            if home_id == team_id:
                form_data.append((home_score, away_score, date_event, game_league_id))
            else:
                form_data.append((away_score, home_score, date_event, game_league_id))
        
        # Calculate stats
        wins = sum(1 for r in form_data if r[0] > r[1])
        draws = sum(1 for r in form_data if r[0] == r[1])
        losses = len(form_data) - wins - draws
        win_rate = (wins / len(form_data) * 100) if form_data else 0
        
        team_stat = {
            'team_id': team_id,
            'team_name': team_name,
            'league_id': team_league_id,
            'games': len(form_data),
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'win_rate': win_rate,
            'used_fallback': used_fallback,
            'check_league_id': check_league_id
        }
        team_stats.append(team_stat)
        
        # Flag issues
        if len(form_data) == 0:
            issues.append({
                'type': 'NO_DATA',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'message': 'No games found in database'
            })
        elif len(form_data) < 3:
            issues.append({
                'type': 'INSUFFICIENT_DATA',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'games': len(form_data),
                'message': f'Only {len(form_data)} games found (need at least 3 for reliable stats)'
            })
        elif used_fallback and check_league_id:
            issues.append({
                'type': 'LEAGUE_FALLBACK',
                'team': team_name,
                'team_id': team_id,
                'league_id': team_league_id,
                'games': len(form_data),
                'message': f'No games in league {check_league_id}, using fallback from all leagues'
            })
    
    # 4. Scan upcoming matches
    print(f"\n{'='*80}")
    print(f"🏉 SCANNING UPCOMING MATCHES")
    print(f"{'='*80}")
    
    match_issues = []
    for match in upcoming_matches:
        match_id, match_league_id, match_date, home_id, away_id, home_team, away_team = match
        if not home_team or not away_team:
            match_issues.append({
                'type': 'MISSING_TEAM_NAMES',
                'match_id': match_id,
                'message': f'Match {match_id} has missing team names'
            })
            continue
        
        # Check if both teams have form data
        home_has_data = any(s['team_id'] == home_id and s['games'] > 0 for s in team_stats)
        away_has_data = any(s['team_id'] == away_id and s['games'] > 0 for s in team_stats)
        
        if not home_has_data:
            match_issues.append({
                'type': 'HOME_TEAM_NO_DATA',
                'match_id': match_id,
                'team': home_team,
                'team_id': home_id,
                'message': f'{home_team} has no game history'
            })
        
        if not away_has_data:
            match_issues.append({
                'type': 'AWAY_TEAM_NO_DATA',
                'match_id': match_id,
                'team': away_team,
                'team_id': away_id,
                'message': f'{away_team} has no game history'
            })
    
    # 5. Generate comprehensive report
    print(f"\n{'='*80}")
    print(f"📊 COMPREHENSIVE REPORT")
    print(f"{'='*80}")
    
    # Team statistics
    teams_with_data = [s for s in team_stats if s['games'] > 0]
    teams_without_data = [s for s in team_stats if s['games'] == 0]
    teams_using_fallback = [s for s in team_stats if s['used_fallback']]
    
    print(f"\n✅ TEAMS WITH DATA: {len(teams_with_data)}")
    print(f"   Teams with 5 games: {len([s for s in teams_with_data if s['games'] == 5])}")
    print(f"   Teams with 3-4 games: {len([s for s in teams_with_data if 3 <= s['games'] < 5])}")
    print(f"   Teams with 1-2 games: {len([s for s in teams_with_data if 1 <= s['games'] < 3])}")
    
    print(f"\n⚠️  TEAMS WITHOUT DATA: {len(teams_without_data)}")
    if teams_without_data:
        print(f"   First 10 teams without data:")
        for stat in teams_without_data[:10]:
            print(f"      - {stat['team_name']} (ID: {stat['team_id']}, League: {stat['league_id']})")
    
    print(f"\n🔄 TEAMS USING FALLBACK: {len(teams_using_fallback)}")
    if teams_using_fallback:
        print(f"   Teams that had no games in their league, using all leagues:")
        for stat in teams_using_fallback[:10]:
            print(f"      - {stat['team_name']} (League: {stat['check_league_id']}, Found: {stat['games']} games)")
    
    # Win rate distribution
    print(f"\n📈 WIN RATE DISTRIBUTION:")
    win_rate_ranges = {
        '100%': len([s for s in teams_with_data if s['win_rate'] == 100]),
        '80-99%': len([s for s in teams_with_data if 80 <= s['win_rate'] < 100]),
        '60-79%': len([s for s in teams_with_data if 60 <= s['win_rate'] < 80]),
        '40-59%': len([s for s in teams_with_data if 40 <= s['win_rate'] < 60]),
        '20-39%': len([s for s in teams_with_data if 20 <= s['win_rate'] < 40]),
        '1-19%': len([s for s in teams_with_data if 0 < s['win_rate'] < 20]),
        '0%': len([s for s in teams_with_data if s['win_rate'] == 0]),
    }
    for range_name, count in win_rate_ranges.items():
        print(f"   {range_name}: {count} teams")
    
    # Issues summary
    print(f"\n{'='*80}")
    print(f"⚠️  ISSUES FOUND: {len(issues) + len(match_issues)}")
    print(f"{'='*80}")
    
    if issues:
        issues_by_type = {}
        for issue in issues:
            issue_type = issue['type']
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        for issue_type, issue_list in issues_by_type.items():
            print(f"\n{issue_type}: {len(issue_list)} issues")
            for issue in issue_list[:5]:  # Show first 5 of each type
                print(f"   - {issue['team']} (ID: {issue['team_id']}): {issue['message']}")
            if len(issue_list) > 5:
                print(f"   ... and {len(issue_list) - 5} more")
    
    if match_issues:
        print(f"\nMATCH ISSUES: {len(match_issues)}")
        match_issues_by_type = {}
        for issue in match_issues:
            issue_type = issue['type']
            if issue_type not in match_issues_by_type:
                match_issues_by_type[issue_type] = []
            match_issues_by_type[issue_type].append(issue)
        
        for issue_type, issue_list in match_issues_by_type.items():
            print(f"   {issue_type}: {len(issue_list)} matches")
            for issue in issue_list[:3]:
                print(f"      - Match {issue['match_id']}: {issue['message']}")
    
    # Detailed team breakdown (top and bottom performers)
    print(f"\n{'='*80}")
    print(f"🏆 TOP PERFORMERS (Highest Win Rates)")
    print(f"{'='*80}")
    top_teams = sorted([s for s in teams_with_data if s['games'] >= 3], 
                      key=lambda x: x['win_rate'], reverse=True)[:10]
    for stat in top_teams:
        print(f"   {stat['team_name']}: {stat['win_rate']:.1f}% ({stat['wins']}W/{stat['draws']}D/{stat['losses']}L) - {stat['games']} games")
    
    print(f"\n📉 LOWEST PERFORMERS (Lowest Win Rates)")
    print(f"{'='*80}")
    bottom_teams = sorted([s for s in teams_with_data if s['games'] >= 3], 
                          key=lambda x: x['win_rate'])[:10]
    for stat in bottom_teams:
        print(f"   {stat['team_name']}: {stat['win_rate']:.1f}% ({stat['wins']}W/{stat['draws']}D/{stat['losses']}L) - {stat['games']} games")
    
    print(f"\n{'='*80}")
    print(f"✅ SCAN COMPLETE")
    print(f"{'='*80}")
    print(f"Total Teams Scanned: {len(teams)}")
    print(f"Teams with Data: {len(teams_with_data)}")
    print(f"Teams without Data: {len(teams_without_data)}")
    print(f"Upcoming Matches: {len(upcoming_matches)}")
    print(f"Total Issues Found: {len(issues) + len(match_issues)}")
    
    return {
        'teams': team_stats,
        'issues': issues,
        'match_issues': match_issues,
        'upcoming_matches': upcoming_matches
    }


def list_teams_with_issues(cursor: sqlite3.Cursor, league_id: Optional[int] = None):
    """List all teams and their win rates to find potential issues"""
    print(f"\n{'='*80}")
    print(f"🔍 SCANNING ALL TEAMS FOR WIN RATE ISSUES")
    print(f"{'='*80}")
    
    # Get all teams
    if league_id:
        cursor.execute("SELECT id, name FROM team WHERE league_id = ?", (league_id,))
    else:
        cursor.execute("SELECT DISTINCT t.id, t.name FROM team t JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)")
    
    teams = cursor.fetchall()
    print(f"Found {len(teams)} teams to check\n")
    
    issues = []
    for team_id, team_name in teams:
        # Get form
        if league_id:
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.league_id = ?
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (team_id, team_id, league_id))
        else:
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
        
        results = []
        for row in cursor.fetchall():
            home_score, away_score, home_id, away_id = row
            if home_id == team_id:
                results.append((home_score, away_score))
            else:
                results.append((away_score, home_score))
        
        if results:
            wins = sum(1 for r in results if r[0] > r[1])
            win_rate = (wins / len(results) * 100) if results else 0
            
            # Flag potential issues
            if win_rate == 0 and len(results) == 5:
                issues.append({
                    'team': team_name,
                    'team_id': team_id,
                    'win_rate': win_rate,
                    'games': len(results),
                    'wins': wins,
                    'issue': '0% win rate with 5 games (all losses?)'
                })
            elif len(results) < 3:
                issues.append({
                    'team': team_name,
                    'team_id': team_id,
                    'win_rate': win_rate,
                    'games': len(results),
                    'wins': wins,
                    'issue': f'Only {len(results)} games found (may need more data)'
                })
    
    if issues:
        print(f"⚠️  FOUND {len(issues)} POTENTIAL ISSUES:\n")
        for issue in issues:
            print(f"   {issue['team']} (ID: {issue['team_id']}): {issue['win_rate']:.1f}% - {issue['issue']}")
            print(f"      Games: {issue['games']}, Wins: {issue['wins']}")
    else:
        print("✅ No obvious issues found!")
    
    return issues


def main():
    parser = argparse.ArgumentParser(description='Debug win rate calculations')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--match-id', type=int, help='Debug specific match ID')
    parser.add_argument('--team', help='Debug specific team name')
    parser.add_argument('--league-id', type=int, help='Filter by league ID')
    parser.add_argument('--scan', action='store_true', help='Scan all teams for issues')
    parser.add_argument('--full-scan', action='store_true', help='Comprehensive full scan of all teams, matches, and issues')
    parser.add_argument('--list-teams', action='store_true', help='List all teams in database')
    
    args = parser.parse_args()
    
    try:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()
        
        print(f"📊 Win Rate Debug Tool")
        print(f"Database: {args.db}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if args.list_teams:
            print(f"\n{'='*80}")
            print(f"📋 ALL TEAMS IN DATABASE")
            print(f"{'='*80}")
            if args.league_id:
                cursor.execute("SELECT id, name, league_id FROM team WHERE league_id = ? ORDER BY name", (args.league_id,))
            else:
                cursor.execute("SELECT DISTINCT t.id, t.name, t.league_id FROM team t ORDER BY t.name")
            
            teams = cursor.fetchall()
            for team_id, team_name, league_id in teams:
                print(f"   ID: {team_id:6d} | League: {league_id or 'N/A':6s} | {team_name}")
            print(f"\nTotal: {len(teams)} teams")
        
        elif args.full_scan:
            full_comprehensive_scan(cursor, args.league_id)
        
        elif args.scan:
            list_teams_with_issues(cursor, args.league_id)
        
        elif args.match_id:
            debug_match(cursor, args.match_id)
        
        elif args.team:
            debug_team(cursor, args.team, args.league_id)
        
        else:
            print("\n❌ Please specify an action:")
            print("   --match-id <id>     : Debug specific match")
            print("   --team <name>       : Debug specific team")
            print("   --scan              : Quick scan for issues")
            print("   --full-scan         : Comprehensive full scan (RECOMMENDED)")
            print("   --list-teams        : List all teams")
            print("\nExamples:")
            print("   python scripts/debug_win_rates.py --full-scan --league-id 4986")
            print("   python scripts/debug_win_rates.py --team 'Newcastle Red Bulls' --league-id 4986")
            print("   python scripts/debug_win_rates.py --match-id 2310170")
            print("   python scripts/debug_win_rates.py --scan --league-id 4986")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

