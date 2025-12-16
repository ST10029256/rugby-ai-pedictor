#!/usr/bin/env python3
"""
Remove teams that have no games from the database
"""

import sqlite3
import sys
from typing import List, Dict

def find_teams_with_no_games(cursor: sqlite3.Cursor) -> List[Dict]:
    """Find all teams that have no games"""
    teams_with_no_games = []
    
    cursor.execute("""
        SELECT id, name, league_id
        FROM team
        ORDER BY name
    """)
    all_teams = cursor.fetchall()
    
    for team_id, team_name, league_id in all_teams:
        # Check if team has any games (any status)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM event e
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
        """, (team_id, team_id))
        total_games = cursor.fetchone()[0]
        
        if total_games == 0:
            teams_with_no_games.append({
                'id': team_id,
                'name': team_name,
                'league_id': league_id
            })
    
    return teams_with_no_games


def check_team_references(cursor: sqlite3.Cursor, team_id: int) -> Dict:
    """Check if team is referenced anywhere"""
    # Check events (home team)
    cursor.execute("""
        SELECT COUNT(*) FROM event WHERE home_team_id = ?
    """, (team_id,))
    home_events = cursor.fetchone()[0]
    
    # Check events (away team)
    cursor.execute("""
        SELECT COUNT(*) FROM event WHERE away_team_id = ?
    """, (team_id,))
    away_events = cursor.fetchone()[0]
    
    return {
        'home_events': home_events,
        'away_events': away_events,
        'total_events': home_events + away_events
    }


def remove_teams_no_games(db_path: str, dry_run: bool = True):
    """Remove teams with no games from the database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"{'='*80}")
    print(f"🗑️  REMOVING TEAMS WITH NO GAMES")
    print(f"{'='*80}")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete teams)'}")
    print()
    
    # Find teams with no games
    teams_to_remove = find_teams_with_no_games(cursor)
    
    print(f"Found {len(teams_to_remove)} teams with no games\n")
    
    if not teams_to_remove:
        print("✅ No teams to remove!")
        conn.close()
        return
    
    # Verify they have no references
    print(f"{'='*80}")
    print(f"🔍 VERIFYING TEAMS HAVE NO REFERENCES")
    print(f"{'='*80}\n")
    
    teams_safe_to_remove = []
    teams_with_references = []
    
    for team in teams_to_remove:
        refs = check_team_references(cursor, team['id'])
        if refs['total_events'] == 0:
            teams_safe_to_remove.append(team)
        else:
            teams_with_references.append({
                **team,
                'references': refs
            })
    
    if teams_with_references:
        print(f"⚠️  WARNING: {len(teams_with_references)} teams have event references (will NOT be removed):")
        for team in teams_with_references:
            print(f"   - {team['name']} (ID: {team['id']}): {team['references']['total_events']} event references")
        print()
    
    # Show teams to be removed
    print(f"{'='*80}")
    print(f"📋 TEAMS TO BE REMOVED ({len(teams_safe_to_remove)} teams)")
    print(f"{'='*80}\n")
    
    # Group by category
    women_teams = [t for t in teams_safe_to_remove if 'Women' in t['name'] or 'W Rugby' in t['name']]
    english_teams = [t for t in teams_safe_to_remove if any(x in t['name'] for x in ['RUFC', 'R.F.C.', 'RFC', 'Knights', 'Pirates', 'Trailfinders'])]
    french_teams = [t for t in teams_safe_to_remove if t['name'] not in [w['name'] for w in women_teams] and t['name'] not in [e['name'] for e in english_teams]]
    
    if women_teams:
        print(f"👩 Women's Teams ({len(women_teams)}):")
        for team in sorted(women_teams, key=lambda x: x['name']):
            print(f"   - {team['name']} (ID: {team['id']})")
        print()
    
    if english_teams:
        print(f"🏴󠁧󠁢󠁥󠁮󠁧󠁿 English Lower Division ({len(english_teams)}):")
        for team in sorted(english_teams, key=lambda x: x['name']):
            print(f"   - {team['name']} (ID: {team['id']})")
        print()
    
    if french_teams:
        print(f"🇫🇷 French Lower Division ({len(french_teams)}):")
        for team in sorted(french_teams, key=lambda x: x['name']):
            print(f"   - {team['name']} (ID: {team['id']})")
        print()
    
    # Show complete list
    print(f"{'='*80}")
    print(f"📋 COMPLETE LIST")
    print(f"{'='*80}\n")
    for team in sorted(teams_safe_to_remove, key=lambda x: x['name']):
        print(f"   {team['name']} (ID: {team['id']})")
    
    # Remove teams
    if not dry_run:
        print(f"\n{'='*80}")
        print(f"💾 DELETING TEAMS")
        print(f"{'='*80}\n")
        
        deleted_count = 0
        for team in teams_safe_to_remove:
            try:
                cursor.execute("DELETE FROM team WHERE id = ?", (team['id'],))
                deleted_count += 1
                if deleted_count % 10 == 0:
                    print(f"   Deleted {deleted_count}/{len(teams_safe_to_remove)} teams...")
            except Exception as e:
                print(f"   ❌ Error deleting {team['name']}: {e}")
        
        conn.commit()
        print(f"\n✅ Successfully deleted {deleted_count} teams")
        
        # Verify deletion
        remaining = find_teams_with_no_games(cursor)
        print(f"📊 Teams with no games remaining: {len(remaining)}")
    else:
        print(f"\n💡 This was a DRY RUN. To actually delete, run with --apply flag")
        print(f"   python scripts/remove_teams_no_games.py --apply")
    
    conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Remove teams with no games')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry run)')
    
    args = parser.parse_args()
    
    try:
        remove_teams_no_games(args.db, dry_run=not args.apply)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

