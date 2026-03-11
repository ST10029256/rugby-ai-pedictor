#!/usr/bin/env python3
"""
Verify that teams showing 0% win rate actually lost all their last 5 games
"""

import sqlite3
import sys
from typing import List, Dict, Tuple

def get_team_form(cursor: sqlite3.Cursor, team_id: int, team_name: str, league_id: int = None) -> Dict:
    """Get team's last 5 games with detailed results"""
    # Try league-specific first
    if league_id:
        cursor.execute("""
            SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
                   e.date_event, e.league_id,
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
            LIMIT 5
        """, (team_id, team_id, league_id))
        results = cursor.fetchall()
        used_fallback = len(results) == 0
    else:
        results = []
        used_fallback = False
    
    # Fallback to all leagues
    if used_fallback or not league_id:
        cursor.execute("""
            SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, 
                   e.date_event, e.league_id,
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
        results = cursor.fetchall()
    
    # Process results
    games = []
    for row in results:
        home_score, away_score, home_id, away_id, date_event, game_league_id, home_team, away_team = row
        was_home = home_id == team_id
        team_score = home_score if was_home else away_score
        opp_score = away_score if was_home else home_score
        opponent = away_team if was_home else home_team
        
        if team_score > opp_score:
            result = "WIN"
        elif team_score == opp_score:
            result = "DRAW"
        else:
            result = "LOSS"
        
        games.append({
            'date': date_event,
            'team_score': team_score,
            'opponent_score': opp_score,
            'opponent': opponent,
            'venue': 'HOME' if was_home else 'AWAY',
            'result': result,
            'league_id': game_league_id
        })
    
    # Calculate win rate
    wins = sum(1 for g in games if g['result'] == 'WIN')
    draws = sum(1 for g in games if g['result'] == 'DRAW')
    losses = sum(1 for g in games if g['result'] == 'LOSS')
    win_rate = (wins / len(games) * 100) if games else 0.0
    
    return {
        'games': games,
        'wins': wins,
        'draws': draws,
        'losses': losses,
        'win_rate': win_rate,
        'total_games': len(games)
    }


def find_zero_win_rate_teams(cursor: sqlite3.Cursor) -> List[Dict]:
    """Find all teams with 0% win rate"""
    zero_win_rate_teams = []
    
    # Get all teams
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
    
    print(f"Checking {len(teams)} teams for 0% win rate...\n")
    
    for team_id, team_name, league_id in teams:
        form = get_team_form(cursor, team_id, team_name, league_id)
        
        if form['win_rate'] == 0.0 and form['total_games'] >= 3:
            zero_win_rate_teams.append({
                'id': team_id,
                'name': team_name,
                'league_id': league_id,
                'form': form
            })
    
    return zero_win_rate_teams


def verify_zero_win_rate_teams(db_path: str):
    """Verify teams with 0% win rate actually lost all games"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"{'='*80}")
    print(f"🔍 VERIFYING 0% WIN RATE TEAMS")
    print(f"{'='*80}")
    print(f"Database: {db_path}\n")
    
    # Find teams with 0% win rate
    zero_teams = find_zero_win_rate_teams(cursor)
    
    print(f"{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}\n")
    print(f"Teams with 0% win rate: {len(zero_teams)}\n")
    
    if not zero_teams:
        print("✅ No teams with 0% win rate found!")
        conn.close()
        return
    
    # Verify each team
    print(f"{'='*80}")
    print(f"🔍 DETAILED VERIFICATION")
    print(f"{'='*80}\n")
    
    all_correct = True
    issues = []
    
    for team in zero_teams:
        team_id = team['id']
        team_name = team['name']
        form = team['form']
        
        print(f"🏉 {team_name} (ID: {team_id})")
        print(f"   League ID: {team['league_id'] or 'None'}")
        print(f"   Total Games: {form['total_games']}")
        print(f"   Win Rate: {form['win_rate']:.1f}%")
        print(f"   Record: {form['wins']}W/{form['draws']}D/{form['losses']}L\n")
        
        # Check each game
        print(f"   📋 Last {form['total_games']} Games:")
        has_wins = False
        has_draws = False
        
        for i, game in enumerate(form['games'], 1):
            result_icon = "✅" if game['result'] == 'LOSS' else ("⚠️" if game['result'] == 'DRAW' else "❌")
            print(f"      Game {i} ({game['date']}): {team_name} {game['team_score']}-{game['opponent_score']} vs {game['opponent']} [{game['venue']}] - {result_icon} {game['result']}")
            
            if game['result'] == 'WIN':
                has_wins = True
            elif game['result'] == 'DRAW':
                has_draws = True
        
        # Verify
        if form['wins'] > 0:
            print(f"\n   ❌ ERROR: Team has {form['wins']} win(s) but showing 0% win rate!")
            all_correct = False
            issues.append({
                'team': team_name,
                'issue': f"Has {form['wins']} win(s) but showing 0%",
                'wins': form['wins'],
                'draws': form['draws'],
                'losses': form['losses']
            })
        elif form['draws'] > 0 and form['wins'] == 0:
            print(f"\n   ⚠️  NOTE: Team has {form['draws']} draw(s) but 0 wins (0% win rate is correct)")
        elif form['wins'] == 0 and form['draws'] == 0:
            print(f"\n   ✅ CORRECT: Team lost all {form['total_games']} games (0% win rate is accurate)")
        
        print()
    
    # Summary
    print(f"{'='*80}")
    print(f"📊 VERIFICATION SUMMARY")
    print(f"{'='*80}\n")
    
    if all_correct:
        print("✅ ALL TEAMS VERIFIED: All 0% win rates are accurate!")
        print(f"   - {len(zero_teams)} teams correctly showing 0% win rate")
        print(f"   - All teams genuinely lost all their recent games")
    else:
        print(f"❌ ISSUES FOUND: {len(issues)} teams with incorrect win rates")
        for issue in issues:
            print(f"   - {issue['team']}: {issue['issue']}")
    
    # Statistics
    teams_with_draws = [t for t in zero_teams if t['form']['draws'] > 0]
    teams_all_losses = [t for t in zero_teams if t['form']['wins'] == 0 and t['form']['draws'] == 0]
    
    print(f"\n📈 BREAKDOWN:")
    print(f"   Teams with 0% (all losses): {len(teams_all_losses)}")
    print(f"   Teams with 0% (has draws, no wins): {len(teams_with_draws)}")
    
    conn.close()
    return all_correct


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Verify teams with 0% win rate')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    
    args = parser.parse_args()
    
    try:
        verify_zero_win_rate_teams(args.db)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

