#!/usr/bin/env python3
"""
Test different Premiership Rugby league IDs to find the correct one
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

# Potential English Premiership IDs
premiership_ids = [
    (5039, "Current ID (shows Austrian teams)"),
    (9294, "Premiership Rugby Cup"),
    (11847, "Premiership Rugby"),
    (41632, "Premiership Rugby"),
]

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
current_year = datetime.now().year

# Known English Premiership teams
english_teams = [
    'bath', 'bristol', 'exeter', 'gloucester', 'harlequins',
    'leicester', 'london irish', 'newcastle', 'northampton',
    'sale', 'saracens', 'wasps', 'worcester', 'bears', 'chiefs',
    'tigers', 'saints', 'quins', 'sharks'
]

print("="*80)
print("Testing Premiership Rugby League IDs")
print("="*80)

for league_id, description in premiership_ids:
    print(f"\n{'='*80}")
    print(f"Testing ID {league_id}: {description}")
    print(f"{'='*80}")
    
    # Try multiple seasons
    for year in [2025, 2024, 2023, 2022]:
        try:
            standings = client.get_standings(league_id=league_id, season=year)
            
            if standings and isinstance(standings, dict):
                groups = standings.get('groups', [])
                league_info = standings.get('league', {})
                
                if groups and len(groups) > 0:
                    teams = groups[0].get('standings', [])
                    if teams:
                        team_names = [t.get('team', {}).get('name', '') for t in teams]
                        team_names_lower = [name.lower() for name in team_names]
                        
                        # Check if any teams match English Premiership teams
                        matches = [name for name in team_names_lower if any(eng_team in name for eng_team in english_teams)]
                        
                        print(f"\n   Season {year}: ✅ Found {len(teams)} teams")
                        print(f"      League: {league_info.get('name', 'N/A')}")
                        print(f"      Teams: {', '.join(team_names[:5])}...")
                        
                        if matches:
                            print(f"      ✅ MATCHES ENGLISH TEAMS: {matches}")
                        else:
                            print(f"      ⚠️ No English Premiership teams found")
                        
                        # Show full team list for 2023 or 2024 if we found data
                        if year in [2023, 2024] and len(teams) > 0:
                            print(f"\n      Full team list ({len(teams)} teams):")
                            for i, team in enumerate(teams[:10], 1):
                                team_name = team.get('team', {}).get('name', 'N/A')
                                position = team.get('position', 'N/A')
                                points = team.get('points', 'N/A')
                                print(f"         {i}. {team_name} (Pos: {position}, Pts: {points})")
                            if len(teams) > 10:
                                print(f"         ... and {len(teams) - 10} more")
                        
                        break  # Found data for this league, move to next
        except Exception as e:
            if '404' not in str(e):
                print(f"   Season {year}: Error - {e}")

print("\n" + "="*80)
print("Test Complete")
print("="*80)

