#!/usr/bin/env python3
"""
Quick summary of which leagues have 2025 standings
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

# Updated league mappings
LEAGUE_MAPPINGS = {
    4986: ("Rugby Championship", 73119),
    4446: ("United Rugby Championship", 65460),
    5069: ("Currie Cup", 32271),
    4574: ("Rugby World Cup", 59503),
    4551: ("Super Rugby", 61205),
    4430: ("French Top 14", 14400),
    4414: ("English Premiership Rugby", 11847),  # CORRECTED
    4714: ("Six Nations Championship", 44185),
    5479: ("Rugby Union International Friendlies", 5039),
}

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
current_year = 2025

print("="*80)
print(f"CHECKING 2025 STANDINGS FOR ALL 9 LEAGUES")
print("="*80)
print()

results = {}

for our_id, (league_name, highlightly_id) in LEAGUE_MAPPINGS.items():
    print(f"📊 {league_name} (ID: {highlightly_id})...", end=" ")
    
    try:
        standings = client.get_standings(league_id=highlightly_id, season=current_year)
        
        if standings and isinstance(standings, dict):
            if standings.get('_rate_limited'):
                print("❌ Rate Limited")
                results[league_name] = "Rate Limited"
                continue
            
            groups = standings.get('groups', [])
            if groups and len(groups) > 0:
                teams = groups[0].get('standings', [])
                if teams and len(teams) > 0:
                    print(f"✅ {len(teams)} teams")
                    results[league_name] = f"✅ {len(teams)} teams"
                else:
                    print("⚠️ No teams")
                    results[league_name] = "⚠️ No teams"
            else:
                print("❌ No data")
                results[league_name] = "❌ No data"
        else:
            print("❌ No response")
            results[league_name] = "❌ No response"
    except Exception as e:
        if '404' in str(e):
            print("❌ 404 Not Found")
            results[league_name] = "❌ 404 Not Found"
        else:
            print(f"❌ Error: {e}")
            results[league_name] = f"❌ Error"

print()
print("="*80)
print("2025 STANDINGS SUMMARY")
print("="*80)
print()

for league_name, status in results.items():
    print(f"{league_name:<45} {status}")

print()
print("="*80)
leagues_with_data = [name for name, status in results.items() if "✅" in status]
print(f"✅ Leagues with 2025 standings: {len(leagues_with_data)}/{len(LEAGUE_MAPPINGS)}")
if leagues_with_data:
    print("   " + ", ".join(leagues_with_data))
print("="*80)

