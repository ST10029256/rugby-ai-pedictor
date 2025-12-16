#!/usr/bin/env python3
"""
Compare teams from database vs RapidAPI standings for all 9 leagues
"""

import sys
import os
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

# Database path
db_path = os.path.join(os.path.dirname(__file__), '..', 'data.sqlite')
if not os.path.exists(db_path):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor', 'data.sqlite')

# League mappings - Our internal ID -> (League Name, Highlightly ID)
LEAGUE_MAPPINGS = {
    4986: ("Rugby Championship", 73119),
    4446: ("United Rugby Championship", 65460),
    5069: ("Currie Cup", 32271),
    4574: ("Rugby World Cup", 59503),
    4551: ("Super Rugby", 61205),
    4430: ("French Top 14", 14400),
    4414: ("English Premiership Rugby", 11847),
    4714: ("Six Nations Championship", 44185),
    5479: ("Rugby Union International Friendlies", 72268),  # Friendly International - no standings as friendlies don't have league tables
}

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True
client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)

print("="*80)
print("COMPARING TEAMS: DATABASE vs RAPIDAPI STANDINGS")
print("="*80)
print()

# Connect to database
if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for our_id, (league_name, highlightly_id) in LEAGUE_MAPPINGS.items():
    print(f"\n{'='*80}")
    print(f"📊 {league_name} (Our ID: {our_id}, Highlightly ID: {highlightly_id if highlightly_id else 'N/A - No standings'})")
    print(f"{'='*80}")
    
    # Special note for International Friendlies
    if our_id == 5479:
        print("ℹ️  International Friendlies - No standings available (friendlies don't have league tables)")
        print("   But will check if API has any data...")
    
    # Get teams from database (using event and team tables)
    try:
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM event e
            JOIN team t ON e.home_team_id = t.id
            WHERE e.league_id = ?
            ORDER BY t.name
        """, (our_id,))
        home_teams = [row[0] for row in cursor.fetchall() if row[0]]
        
        # Also get away teams
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM event e
            JOIN team t ON e.away_team_id = t.id
            WHERE e.league_id = ?
            ORDER BY t.name
        """, (our_id,))
        away_teams = [row[0] for row in cursor.fetchall() if row[0]]
        
        # Combine and deduplicate
        all_db_teams = sorted(list(set(home_teams + away_teams)))
        
        print(f"📦 Database: {len(all_db_teams)} teams")
        if all_db_teams:
            print(f"   Sample: {', '.join(all_db_teams[:5])}...")
    except Exception as e:
        print(f"❌ Error getting teams from database: {e}")
        all_db_teams = []
    
    # Get teams from RapidAPI standings (try 2025, then 2024, then 2023)
    api_teams = []
    api_season = None
    
    for year in [2025, 2024, 2023]:
        try:
            standings = client.get_standings(league_id=highlightly_id, season=year)
            
            if standings and isinstance(standings, dict) and not standings.get('_rate_limited'):
                groups = standings.get('groups', [])
                if groups and len(groups) > 0:
                    teams = groups[0].get('standings', [])
                    if teams:
                        api_teams = [t.get('team', {}).get('name', '') for t in teams if t.get('team', {}).get('name')]
                        api_season = year
                        break
        except Exception as e:
            if '404' not in str(e):
                continue
    
    if api_teams:
        print(f"🌐 RapidAPI ({api_season}): {len(api_teams)} teams")
        print(f"   Teams: {', '.join(api_teams[:5])}...")
    else:
        print(f"🌐 RapidAPI: ❌ No standings data available")
    
    # Compare teams
    if all_db_teams and api_teams:
        # Normalize team names for comparison (lowercase, remove extra spaces)
        db_teams_normalized = {name.lower().strip(): name for name in all_db_teams}
        api_teams_normalized = {name.lower().strip(): name for name in api_teams}
        
        # Find matches
        matches = []
        db_only = []
        api_only = []
        
        for db_name_lower, db_name in db_teams_normalized.items():
            # Try exact match first
            if db_name_lower in api_teams_normalized:
                matches.append((db_name, api_teams_normalized[db_name_lower]))
            else:
                # Try partial match
                found = False
                for api_name_lower, api_name in api_teams_normalized.items():
                    # Check if one contains the other
                    if db_name_lower in api_name_lower or api_name_lower in db_name_lower:
                        matches.append((db_name, api_name))
                        found = True
                        break
                if not found:
                    db_only.append(db_name)
        
        # Find API-only teams
        for api_name_lower, api_name in api_teams_normalized.items():
            found = False
            for db_name_lower in db_teams_normalized.keys():
                if api_name_lower in db_name_lower or db_name_lower in api_name_lower:
                    found = True
                    break
            if not found:
                api_only.append(api_name)
        
        print(f"\n📊 Comparison:")
        print(f"   ✅ Matches: {len(matches)}")
        print(f"   📦 DB Only: {len(db_only)}")
        print(f"   🌐 API Only: {len(api_only)}")
        
        if db_only:
            print(f"\n   Teams in DB but not in API ({len(db_only)}):")
            for team in db_only[:10]:
                print(f"      - {team}")
            if len(db_only) > 10:
                print(f"      ... and {len(db_only) - 10} more")
        
        if api_only:
            print(f"\n   Teams in API but not in DB ({len(api_only)}):")
            for team in api_only[:10]:
                print(f"      - {team}")
            if len(api_only) > 10:
                print(f"      ... and {len(api_only) - 10} more")
        
        # Calculate match percentage
        if len(all_db_teams) > 0:
            match_pct = (len(matches) / len(all_db_teams)) * 100
            print(f"\n   Match Rate: {match_pct:.1f}% ({len(matches)}/{len(all_db_teams)})")
    elif all_db_teams and not api_teams:
        print(f"\n⚠️ Cannot compare - No API standings data available")
    elif not all_db_teams and api_teams:
        print(f"\n⚠️ Cannot compare - No teams in database for this league")
    else:
        print(f"\n⚠️ Cannot compare - No data in either source")

conn.close()

print("\n" + "="*80)
print("Comparison Complete")
print("="*80)

