#!/usr/bin/env python3
"""
Quick test to check if standings exist for a specific Highlightly league ID
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

# Use RapidAPI key
api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
league_id = 11847  # English Premiership Rugby (CORRECTED Highlightly ID - was 5039 which was Austrian league)
use_rapidapi = True

print("="*80)
print(f"Testing standings for English Premiership Rugby")
print(f"Highlightly League ID: {league_id}")
print(f"Using RapidAPI: {use_rapidapi}")
print("="*80)

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
current_year = datetime.now().year

# Only try 2025
for year in [current_year]:
    print(f"\n--- Testing Season {year} ---")
    try:
        standings = client.get_standings(league_id=league_id, season=year)
        
        if standings:
            print(f"✅ Response received for season {year}")
            print(f"   Type: {type(standings)}")
            
            if isinstance(standings, dict):
                print(f"   Keys: {list(standings.keys())}")
                
                groups = standings.get('groups', [])
                league_info = standings.get('league', {})
                
                print(f"   Groups: {len(groups)}")
                print(f"   League: {league_info.get('name', 'N/A')} - Season {league_info.get('season', 'N/A')}")
                
                if groups:
                    for idx, group in enumerate(groups):
                        standings_list = group.get('standings', [])
                        teams_list = group.get('teams', [])
                        print(f"   Group {idx + 1}: {len(standings_list)} standings, {len(teams_list)} teams")
                        
                        if standings_list:
                            print(f"   ✅ FOUND {len(standings_list)} TEAMS!")
                            print(f"   First team: {standings_list[0].get('team', {}).get('name', 'N/A')}")
                            print(f"   Sample data: {dict(list(standings_list[0].items())[:5])}")
                            break
                else:
                    print(f"   ⚠️ No groups found")
            else:
                print(f"   ⚠️ Response is not a dict: {standings}")
        else:
            print(f"   ❌ Empty response")
            
    except Exception as e:
        error_msg = str(e)
        if '404' in error_msg:
            print(f"   ❌ 404 Not Found - standings don't exist for season {year}")
        elif '429' in error_msg:
            print(f"   ❌ 429 Rate Limited")
            break  # Stop if rate limited
        else:
            print(f"   ❌ Error: {e}")
        
        # Check if rate limited in response
        if isinstance(standings, dict) and standings.get('_rate_limited'):
            print(f"   ❌ Rate Limited (429) - API quota exceeded")
            break

print("\n" + "="*80)
print("Test Complete")
print("="*80)

