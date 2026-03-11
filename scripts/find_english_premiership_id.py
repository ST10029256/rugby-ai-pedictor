#!/usr/bin/env python3
"""
Find the correct league ID for English Premiership Rugby
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
import json

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

print("="*80)
print("Searching for English Premiership Rugby League ID")
print("="*80)

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)

# Try to get leagues
print("\n1. Fetching leagues from API...")
try:
    leagues = client.get_leagues(limit=100)
    if leagues and isinstance(leagues, dict):
        leagues_list = leagues.get('data', [])
        print(f"   Found {len(leagues_list)} leagues")
        
        # Search for English Premiership
        print("\n2. Searching for English Premiership Rugby...")
        matches = []
        for league in leagues_list:
            name = league.get('name', '').lower()
            league_id = league.get('id')
            
            # Check for keywords
            keywords = ['premiership', 'english', 'england', 'prem', 'gallagher']
            if any(keyword in name for keyword in keywords):
                matches.append((league_id, league.get('name', 'N/A')))
                print(f"   ✅ Found: ID {league_id} - {league.get('name', 'N/A')}")
        
        if matches:
            print(f"\n   Found {len(matches)} potential matches:")
            for league_id, name in matches:
                print(f"      - ID {league_id}: {name}")
        else:
            print("   ⚠️ No exact matches found")
            
        # Also search for common English teams
        print("\n3. Searching for English Premiership teams in matches...")
        try:
            matches_data = client.get_matches(limit=200)
            if matches_data and isinstance(matches_data, dict):
                matches_list = matches_data.get('data', [])
                print(f"   Found {len(matches_list)} matches")
                
                # Look for known English Premiership teams
                english_teams = [
                    'bath', 'bristol', 'exeter', 'gloucester', 'harlequins',
                    'leicester', 'london irish', 'newcastle', 'northampton',
                    'sale', 'saracens', 'wasps', 'worcester'
                ]
                
                found_leagues = {}
                for match in matches_list:
                    league_info = match.get('league', {})
                    home_team = match.get('homeTeam', {}).get('name', '').lower()
                    away_team = match.get('awayTeam', {}).get('name', '').lower()
                    
                    league_id = league_info.get('id')
                    league_name = league_info.get('name', '')
                    
                    # Check if either team matches English Premiership teams
                    if any(team in home_team or team in away_team for team in english_teams):
                        if league_id and league_name:
                            if league_id not in found_leagues:
                                found_leagues[league_id] = {
                                    'name': league_name,
                                    'teams': set()
                                }
                            found_leagues[league_id]['teams'].add(home_team)
                            found_leagues[league_id]['teams'].add(away_team)
                
                if found_leagues:
                    print(f"\n   Found {len(found_leagues)} leagues with English Premiership teams:")
                    for league_id, info in found_leagues.items():
                        print(f"      - ID {league_id}: {info['name']}")
                        print(f"        Teams: {', '.join(list(info['teams'])[:5])}...")
                else:
                    print("   ⚠️ No leagues found with English Premiership teams")
        except Exception as e:
            print(f"   ❌ Error fetching matches: {e}")
            
    else:
        print("   ❌ No leagues data returned")
except Exception as e:
    print(f"   ❌ Error fetching leagues: {e}")

# Test the current ID 5039 with different seasons
print("\n4. Testing current ID 5039 for different seasons...")
for year in [2025, 2024, 2023, 2022]:
    try:
        standings = client.get_standings(league_id=5039, season=year)
        if standings and isinstance(standings, dict):
            groups = standings.get('groups', [])
            league_info = standings.get('league', {})
            if groups and len(groups) > 0:
                teams = groups[0].get('standings', [])
                if teams:
                    team_names = [t.get('team', {}).get('name', 'N/A') for t in teams[:3]]
                    print(f"   Season {year}: {len(teams)} teams - {', '.join(team_names)}")
    except Exception as e:
        if '404' not in str(e):
            print(f"   Season {year}: Error - {e}")

print("\n" + "="*80)
print("Search Complete")
print("="*80)

