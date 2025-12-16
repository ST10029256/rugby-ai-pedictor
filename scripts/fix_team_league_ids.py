#!/usr/bin/env python3
"""
Fix team.league_id values for teams that have games but no league_id assigned
This will update teams based on the league_id of their most recent games
"""

import sqlite3
import sys
from typing import Dict, List, Tuple

def fix_team_league_ids(db_path: str, dry_run: bool = True):
    """Update team.league_id based on their actual games"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"{'='*80}")
    print(f"🔧 FIXING TEAM LEAGUE IDs")
    print(f"{'='*80}")
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will update database)'}")
    print()
    
    # Find all teams with NULL league_id that have games
    cursor.execute("""
        SELECT DISTINCT t.id, t.name, t.league_id
        FROM team t
        WHERE t.league_id IS NULL
        AND EXISTS (
            SELECT 1 FROM event e
            WHERE (e.home_team_id = t.id OR e.away_team_id = t.id)
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
        )
        ORDER BY t.name
    """)
    
    teams_to_fix = cursor.fetchall()
    print(f"Found {len(teams_to_fix)} teams with NULL league_id but have games\n")
    
    updates = []
    issues = []
    
    for team_id, team_name, current_league_id in teams_to_fix:
        # Find the most common league_id for this team's games
        cursor.execute("""
            SELECT e.league_id, COUNT(*) as game_count
            FROM event e
            WHERE (e.home_team_id = ? OR e.away_team_id = ?)
            AND e.home_score IS NOT NULL
            AND e.away_score IS NOT NULL
            AND e.date_event < date('now')
            GROUP BY e.league_id
            ORDER BY game_count DESC
            LIMIT 1
        """, (team_id, team_id))
        
        result = cursor.fetchone()
        if result:
            most_common_league_id, game_count = result
            
            # Get league name
            cursor.execute("SELECT name FROM league WHERE id = ?", (most_common_league_id,))
            league_info = cursor.fetchone()
            league_name = league_info[0] if league_info else f"Unknown (ID: {most_common_league_id})"
            
            # Check if team has games in multiple leagues
            cursor.execute("""
                SELECT COUNT(DISTINCT e.league_id)
                FROM event e
                WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event < date('now')
            """, (team_id, team_id))
            league_count = cursor.fetchone()[0]
            
            updates.append({
                'team_id': team_id,
                'team_name': team_name,
                'new_league_id': most_common_league_id,
                'league_name': league_name,
                'game_count': game_count,
                'league_count': league_count
            })
            
            if league_count > 1:
                issues.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'issue': f'Plays in {league_count} different leagues'
                })
    
    # Show summary
    print(f"{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}\n")
    print(f"Teams to update: {len(updates)}")
    print(f"Teams with multiple leagues: {len(issues)}\n")
    
    # Show updates
    print(f"{'='*80}")
    print(f"📋 PROPOSED UPDATES")
    print(f"{'='*80}\n")
    
    for update in updates[:50]:  # Show first 50
        multi_league_warning = " ⚠️ MULTI-LEAGUE" if update['league_count'] > 1 else ""
        print(f"  {update['team_name']} (ID: {update['team_id']})")
        print(f"    → League: {update['league_name']} (ID: {update['new_league_id']})")
        print(f"    → Games: {update['game_count']} in this league{multi_league_warning}")
        print()
    
    if len(updates) > 50:
        print(f"  ... and {len(updates) - 50} more teams\n")
    
    # Show multi-league issues
    if issues:
        print(f"{'='*80}")
        print(f"⚠️  TEAMS PLAYING IN MULTIPLE LEAGUES")
        print(f"{'='*80}\n")
        for issue in issues[:20]:
            print(f"  {issue['team_name']} (ID: {issue['team_id']}): {issue['issue']}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more\n")
    
    # Apply updates
    if not dry_run:
        print(f"{'='*80}")
        print(f"💾 APPLYING UPDATES")
        print(f"{'='*80}\n")
        
        updated_count = 0
        for update in updates:
            try:
                cursor.execute("""
                    UPDATE team
                    SET league_id = ?
                    WHERE id = ?
                """, (update['new_league_id'], update['team_id']))
                updated_count += 1
                if updated_count % 10 == 0:
                    print(f"  Updated {updated_count}/{len(updates)} teams...")
            except Exception as e:
                print(f"  ❌ Error updating {update['team_name']}: {e}")
        
        conn.commit()
        print(f"\n✅ Successfully updated {updated_count} teams")
    else:
        print(f"\n💡 This was a DRY RUN. To apply changes, run with --apply flag")
        print(f"   python scripts/fix_team_league_ids.py --apply")
    
    conn.close()
    return len(updates)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix team.league_id values')
    parser.add_argument('--db', default='data.sqlite', help='Database path')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry run)')
    
    args = parser.parse_args()
    
    try:
        fix_team_league_ids(args.db, dry_run=not args.apply)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

