#!/usr/bin/env python3
"""Test URC API endpoints to see what's being returned"""

import requests
import json
from datetime import datetime, timedelta

URC_SPORTSDB_ID = 4446

print("=" * 60)
print("Testing URC API Endpoints")
print("=" * 60)

# Test upcoming games endpoint
print("\n1. Testing eventsnextleague.php endpoint:")
url1 = f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={URC_SPORTSDB_ID}"
print(f"   URL: {url1}")
try:
    response = requests.get(url1, timeout=30)
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        print(f"   ✅ Found {len(events)} events")
        if events:
            print(f"   Sample event: {json.dumps(events[0], indent=2)}")
        else:
            print("   ⚠️  No events returned")
    else:
        print(f"   ❌ Status code: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test season endpoint
print("\n2. Testing eventsseason.php endpoint:")
today = datetime.now()
year = today.year
month = today.month
# URC season is typically Aug-May, so check current and adjacent seasons
if month >= 8:
    season = f"{year}-{year+1}"
else:
    season = f"{year-1}-{year}"

url2 = f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={URC_SPORTSDB_ID}&s={season}"
print(f"   URL: {url2}")
print(f"   Season: {season}")
try:
    response = requests.get(url2, timeout=30)
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        print(f"   ✅ Found {len(events)} events")
        
        # Filter for upcoming games
        today_str = today.strftime('%Y-%m-%d')
        upcoming = [e for e in events if e.get('dateEvent', '') >= today_str and (not e.get('intHomeScore') or not e.get('intAwayScore'))]
        print(f"   📅 Upcoming games (no scores): {len(upcoming)}")
        
        if upcoming:
            print(f"   Sample upcoming event: {json.dumps(upcoming[0], indent=2)}")
        elif events:
            print(f"   ⚠️  All events have scores (past games)")
            # Show most recent event
            if events:
                print(f"   Most recent event: {events[0].get('dateEvent')} - {events[0].get('strHomeTeam')} vs {events[0].get('strAwayTeam')}")
    else:
        print(f"   ❌ Status code: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test general league endpoint
print("\n3. Testing eventsleague.php endpoint:")
url3 = f"https://www.thesportsdb.com/api/v1/json/123/eventsleague.php?id={URC_SPORTSDB_ID}"
print(f"   URL: {url3}")
try:
    response = requests.get(url3, timeout=30)
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        print(f"   ✅ Found {len(events)} events")
        
        # Filter for upcoming games
        today_str = today.strftime('%Y-%m-%d')
        upcoming = [e for e in events if e.get('dateEvent', '') >= today_str and (not e.get('intHomeScore') or not e.get('intAwayScore'))]
        print(f"   📅 Upcoming games (no scores): {len(upcoming)}")
        
        if upcoming:
            print(f"   Sample upcoming event: {json.dumps(upcoming[0], indent=2)}")
    else:
        print(f"   ❌ Status code: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("Summary: Check if API is returning upcoming URC games")
print("=" * 60)
