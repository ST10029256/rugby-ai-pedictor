#!/usr/bin/env python3
"""
Test the potential International Friendlies league IDs
"""

import sys
import os
import sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

# Potential IDs found
potential_ids = [
    (72268, "Friendly International"),
    (82480, "Club Friendly"),
    (83331, "Friendly International Women"),
]

# Database path
db_path = os.path.join(os.path.dirname(__file__), '..', 'data.sqlite')
if not os.path.exists(db_path):
    db_path = os.path.join(os.path.dirname(__file__), '..', 'rugby-ai-predictor', 'data.sqlite')

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
our_league_id = 5479  # Rugby Union International Friendlies

print("="*80)
print("TESTING POTENTIAL INTERNATIONAL FRIENDLIES LEAGUE IDs")
print("="*80)

# Get teams from database
print("\n📦 Getting teams from database...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("""
        SELECT DISTINCT t.name
        FROM event e
        JOIN team t ON e.home_team_id = t.id
        WHERE e.league_id = ?
        ORDER BY t.name
    """, (our_league_id,))
    home_teams = [row[0] for row in cursor.fetchall() if row[0]]
    
    cursor.execute("""
        SELECT DISTINCT t.name
        FROM event e
        JOIN team t ON e.away_team_id = t.id
        WHERE e.league_id = ?
        ORDER BY t.name
    """, (our_league_id,))
    away_teams = [row[0] for row in cursor.fetchall() if row[0]]
    
    all_db_teams = sorted(list(set(home_teams + away_teams)))
    print(f"   Found {len(all_db_teams)} teams in database")
    print(f"   Sample: {', '.join(all_db_teams[:10])}...")
except Exception as e:
    print(f"   ❌ Error: {e}")
    all_db_teams = []

conn.close()

# Test each potential ID
print("\n" + "="*80)
for league_id, league_name in potential_ids:
    print(f"\n📊 Testing ID {league_id}: {league_name}")
    print("-" * 80)
    
    # Try multiple seasons
    api_teams = []
    api_season = None
    
    for year in [2025, 2024, 2023, 2022]:
        try:
            standings = client.get_standings(league_id=league_id, season=year)
            
            if standings and isinstance(standings, dict) and not standings.get('_rate_limited'):
                groups = standings.get('groups', [])
                if groups and len(groups) > 0:
                    teams = groups[0].get('standings', [])
                    if teams:
                        api_teams = [t.get('team', {}).get('name', '') for t in teams if t.get('team', {}).get('name')]
                        api_season = year
                        print(f"   ✅ Found standings for season {year}: {len(api_teams)} teams")
                        print(f"      Teams: {', '.join(api_teams[:10])}...")
                        break
        except Exception as e:
            if '404' not in str(e):
                continue
    
    if not api_teams:
        print(f"   ❌ No standings data available (as expected for friendlies)")
        continue
    
    # Compare with database teams
    if all_db_teams and api_teams:
        # Normalize team names
        db_teams_normalized = {name.lower().strip(): name for name in all_db_teams}
        api_teams_normalized = {name.lower().strip(): name for name in api_teams}
        
        # Find matches
        matches = []
        for db_name_lower, db_name in db_teams_normalized.items():
            # Try exact match
            if db_name_lower in api_teams_normalized:
                matches.append((db_name, api_teams_normalized[db_name_lower]))
            else:
                # Try partial match
                for api_name_lower, api_name in api_teams_normalized.items():
                    if db_name_lower in api_name_lower or api_name_lower in db_name_lower:
                        matches.append((db_name, api_name))
                        break
        
        print(f"\n   📊 Comparison with database:")
        print(f"      ✅ Matches: {len(matches)}/{len(all_db_teams)} ({len(matches)/len(all_db_teams)*100:.1f}%)")
        if matches:
            print(f"      Sample matches: {', '.join([m[0] for m in matches[:5]])}...")
        
        # Check if this looks like international friendlies
        international_keywords = ['england', 'ireland', 'scotland', 'wales', 'france', 'italy',
                                 'new zealand', 'south africa', 'australia', 'argentina',
                                 'barbarians']
        international_count = sum(1 for team in api_teams 
                                 if any(kw in team.lower() for kw in international_keywords))
        
        if international_count > len(api_teams) * 0.5:
            print(f"      ✅ LIKELY MATCH - {international_count}/{len(api_teams)} teams are international teams")
        else:
            print(f"      ⚠️  Only {international_count}/{len(api_teams)} teams are international teams")

print("\n" + "="*80)
print("Test Complete")
print("="*80)
print("\n💡 Recommendation:")
print("   - ID 72268 (Friendly International) is most likely the correct one")
print("   - However, friendlies typically don't have standings")
print("   - Consider keeping it as null/None in the mapping")

