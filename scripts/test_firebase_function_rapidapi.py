#!/usr/bin/env python3
"""
Test if the Firebase Function configuration matches what we expect for RapidAPI
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from prediction.highlightly_client import HighlightlyRugbyAPI

print("="*80)
print("TESTING FIREBASE FUNCTION RAPIDAPI CONFIGURATION")
print("="*80)

# Use the same API key and settings as Firebase Function
api_key = '54433ab41dmsha07945d6bccefe5p1fa4bcjsn14b167626050'
use_rapidapi = True

print(f"\n1. Initializing client with RapidAPI mode...")
print(f"   API Key: {api_key[:10]}...{api_key[-4:]}")
print(f"   Use RapidAPI: {use_rapidapi}")

client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)

print(f"\n2. Checking client configuration...")
print(f"   Base URL: {client.base_url}")
print(f"   Headers: {client.headers}")
print(f"   Use RapidAPI: {client.use_rapidapi}")

# Verify base URL
expected_base_url = "https://rugby-highlights-api.p.rapidapi.com"
if client.base_url == expected_base_url:
    print(f"   ✅ Base URL is correct: {client.base_url}")
else:
    print(f"   ❌ Base URL mismatch!")
    print(f"      Expected: {expected_base_url}")
    print(f"      Got: {client.base_url}")

# Verify headers
expected_host = "rugby-highlights-api.p.rapidapi.com"
if client.headers.get('x-rapidapi-host') == expected_host:
    print(f"   ✅ RapidAPI host header is correct: {client.headers.get('x-rapidapi-host')}")
else:
    print(f"   ❌ RapidAPI host header mismatch!")
    print(f"      Expected: {expected_host}")
    print(f"      Got: {client.headers.get('x-rapidapi-host')}")

if client.headers.get('x-rapidapi-key') == api_key:
    print(f"   ✅ RapidAPI key header is set correctly")
else:
    print(f"   ❌ RapidAPI key header mismatch!")

# Test a standings call
print(f"\n3. Testing standings API call...")
test_league_id = 65460  # United Rugby Championship (we know this works)
test_season = 2025

print(f"   Testing league ID: {test_league_id}, season: {test_season}")

try:
    standings = client.get_standings(league_id=test_league_id, season=test_season)
    
    if standings and isinstance(standings, dict):
        if standings.get('_rate_limited'):
            print(f"   ⚠️  Rate limited (429)")
        elif standings.get('_error'):
            print(f"   ❌ Error: {standings.get('_error')}")
        else:
            groups = standings.get('groups', [])
            if groups and len(groups) > 0:
                teams = groups[0].get('standings', [])
                if teams:
                    print(f"   ✅ SUCCESS! Retrieved {len(teams)} teams")
                    print(f"      League: {standings.get('league', {}).get('name', 'N/A')}")
                    print(f"      Season: {standings.get('league', {}).get('season', 'N/A')}")
                    print(f"      Sample teams: {', '.join([t.get('team', {}).get('name', '') for t in teams[:3]])}")
                else:
                    print(f"   ⚠️  No teams in standings")
            else:
                print(f"   ⚠️  No groups in standings")
    else:
        print(f"   ❌ Invalid response format")
        
except Exception as e:
    print(f"   ❌ Error calling API: {e}")
    import traceback
    print(f"   Traceback: {traceback.format_exc()}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)

print("\n💡 Summary:")
print("   - If all checks pass ✅, the Firebase Function should work correctly")
print("   - Make sure to deploy the updated function to Firebase")
print("   - Set RAPIDAPI_KEY environment variable in Firebase Console if needed")

