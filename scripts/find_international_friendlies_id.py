#!/usr/bin/env python3
"""
Search RapidAPI for Rugby Union International Friendlies league ID
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

print("="*80)
print("SEARCHING RAPIDAPI FOR INTERNATIONAL FRIENDLIES LEAGUE")
print("="*80)

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)

# Search keywords for international friendlies
keywords = [
    'international',
    'friendly',
    'friendlies',
    'test match',
    'test matches',
    'international test',
    'rugby union international'
]

print("\n1. Searching leagues by name...")
try:
    leagues = client.get_leagues(limit=100)
    if leagues and isinstance(leagues, dict):
        leagues_list = leagues.get('data', [])
        print(f"   Found {len(leagues_list)} leagues")
        
        matches = []
        for league in leagues_list:
            name = league.get('name', '').lower()
            league_id = league.get('id')
            
            # Check if any keyword matches
            for keyword in keywords:
                if keyword in name:
                    matches.append((league_id, league.get('name', 'N/A')))
                    print(f"   ✅ Found: ID {league_id} - {league.get('name', 'N/A')}")
                    break
        
        if matches:
            print(f"\n   Found {len(matches)} potential matches:")
            for league_id, name in matches:
                print(f"      - ID {league_id}: {name}")
        else:
            print("\n   ⚠️ No exact matches found in league names")
    else:
        print("   ❌ No leagues data returned")
except Exception as e:
    print(f"   ❌ Error fetching leagues: {e}")

# Search in matches for international teams
print("\n2. Searching matches for international teams...")
try:
    # Get matches and look for international teams
    matches_data = client.get_matches(limit=500)
    if matches_data and isinstance(matches_data, dict):
        matches_list = matches_data.get('data', [])
        print(f"   Found {len(matches_list)} matches")
        
        # Known international teams (national teams)
        international_teams = [
            'england', 'ireland', 'scotland', 'wales', 'france', 'italy',
            'new zealand', 'south africa', 'australia', 'argentina',
            'japan', 'fiji', 'samoa', 'tonga', 'usa', 'canada',
            'georgia', 'romania', 'portugal', 'spain', 'russia',
            'barbarians', 'world xv'
        ]
        
        found_leagues = {}
        for match in matches_list:
            league_info = match.get('league', {})
            home_team = match.get('homeTeam', {}).get('name', '').lower()
            away_team = match.get('awayTeam', {}).get('name', '').lower()
            
            league_id = league_info.get('id')
            league_name = league_info.get('name', '')
            
            # Check if either team is an international team
            is_international = any(
                intl_team in home_team or intl_team in away_team 
                for intl_team in international_teams
            )
            
            # Also check if league name suggests friendlies
            league_name_lower = league_name.lower()
            is_friendly_league = any(
                keyword in league_name_lower 
                for keyword in ['friendly', 'test', 'international']
            )
            
            if is_international or is_friendly_league:
                if league_id and league_name:
                    if league_id not in found_leagues:
                        found_leagues[league_id] = {
                            'name': league_name,
                            'teams': set(),
                            'match_count': 0
                        }
                    found_leagues[league_id]['teams'].add(home_team)
                    found_leagues[league_id]['teams'].add(away_team)
                    found_leagues[league_id]['match_count'] += 1
        
        if found_leagues:
            print(f"\n   Found {len(found_leagues)} leagues with international teams:")
            for league_id, info in sorted(found_leagues.items(), key=lambda x: x[1]['match_count'], reverse=True):
                print(f"\n      📊 ID {league_id}: {info['name']}")
                print(f"         Matches: {info['match_count']}")
                print(f"         Teams: {len(info['teams'])} unique teams")
                print(f"         Sample teams: {', '.join(list(info['teams'])[:8])}...")
                
                # Check if this looks like international friendlies
                name_lower = info['name'].lower()
                if any(kw in name_lower for kw in ['friendly', 'test', 'international']):
                    print(f"         ✅ LIKELY MATCH - Contains friendly/test/international keywords")
        else:
            print("   ⚠️ No leagues found with international teams")
    else:
        print("   ❌ No matches data returned")
except Exception as e:
    print(f"   ❌ Error fetching matches: {e}")

# Test some potential IDs from the search
print("\n3. Testing potential league IDs for standings...")
potential_ids = []
if 'found_leagues' in locals() and found_leagues:
    potential_ids = list(found_leagues.keys())[:5]  # Test top 5

if potential_ids:
    for league_id in potential_ids:
        print(f"\n   Testing ID {league_id}...")
        for year in [2025, 2024, 2023]:
            try:
                standings = client.get_standings(league_id=league_id, season=year)
                if standings and isinstance(standings, dict) and not standings.get('_rate_limited'):
                    groups = standings.get('groups', [])
                    if groups and len(groups) > 0:
                        teams = groups[0].get('standings', [])
                        if teams:
                            team_names = [t.get('team', {}).get('name', '') for t in teams[:5]]
                            print(f"      ✅ Season {year}: {len(teams)} teams - {', '.join(team_names)}...")
                            break
            except Exception as e:
                if '404' not in str(e):
                    continue
else:
    print("   ℹ️  No potential IDs to test (no leagues found with international teams)")

print("\n" + "="*80)
print("Search Complete")
print("="*80)
print("\n💡 Note: International Friendlies typically don't have standings")
print("   as they are exhibition matches, not league competitions.")

