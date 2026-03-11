#!/usr/bin/env python3
"""Comprehensive check of URC upcoming games in TheSportsDB API"""

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

URC_SPORTSDB_ID = 4446

print("=" * 70)
print("Comprehensive URC Upcoming Games Check")
print("=" * 70)

today = datetime.now().date()
today_str = today.strftime('%Y-%m-%d')
print(f"\nToday's date: {today_str}")
print(f"Checking for games from {today_str} onwards (no scores = upcoming)\n")

all_upcoming_games = []
seen_games = set()

# Helper function to check if game is upcoming
def is_upcoming(event):
    """Check if event is upcoming (has date >= today and no scores)"""
    date_str = event.get('dateEvent') or event.get('dateEventLocal', '')
    if not date_str:
        return False
    
    try:
        event_date = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
        if event_date < today:
            return False
        
        # Check if it has scores (if it has scores, it's completed)
        home_score = event.get('intHomeScore')
        away_score = event.get('intAwayScore')
        if home_score is not None or away_score is not None:
            return False
        
        return True
    except:
        return False

# 1. Check eventsnextleague endpoint
print("1. Checking eventsnextleague.php endpoint:")
print("-" * 70)
url = f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={URC_SPORTSDB_ID}"
try:
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        upcoming = [e for e in events if is_upcoming(e)]
        print(f"   Total events returned: {len(events)}")
        print(f"   Upcoming games (no scores): {len(upcoming)}")
        for e in upcoming:
            game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
            if game_key not in seen_games:
                seen_games.add(game_key)
                all_upcoming_games.append(e)
                print(f"   ✅ {e.get('dateEvent')} - {e.get('strHomeTeam')} vs {e.get('strAwayTeam')}")
    else:
        print(f"   ❌ Status code: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 2. Check eventsseason endpoint for current season
print("\n2. Checking eventsseason.php endpoint (current season):")
print("-" * 70)
year = today.year
month = today.month
if month >= 8:
    season = f"{year}-{year+1}"
else:
    season = f"{year-1}-{year}"

url = f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={URC_SPORTSDB_ID}&s={season}"
print(f"   Season: {season}")
try:
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        upcoming = [e for e in events if is_upcoming(e)]
        print(f"   Total events returned: {len(events)}")
        print(f"   Upcoming games (no scores): {len(upcoming)}")
        for e in upcoming:
            game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
            if game_key not in seen_games:
                seen_games.add(game_key)
                all_upcoming_games.append(e)
                print(f"   ✅ {e.get('dateEvent')} - {e.get('strHomeTeam')} vs {e.get('strAwayTeam')}")
    else:
        print(f"   ❌ Status code: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# 3. Check eventsround endpoints (sample rounds)
print("\n3. Checking eventsround.php endpoints (rounds 1-18):")
print("-" * 70)
print("   This may take a while...")
round_upcoming = defaultdict(list)

for round_num in range(1, 19):  # URC has up to 18 rounds
    url = f"https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id={URC_SPORTSDB_ID}&r={round_num}&s={season}"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            events = data.get('events', [])
            if events:
                upcoming = [e for e in events if is_upcoming(e)]
                if upcoming:
                    round_upcoming[round_num] = upcoming
                    for e in upcoming:
                        game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
                        if game_key not in seen_games:
                            seen_games.add(game_key)
                            all_upcoming_games.append(e)
        # Small delay to avoid rate limiting
        import time
        time.sleep(0.5)
    except Exception as e:
        print(f"   ⚠️  Round {round_num}: Error - {e}")
        continue

if round_upcoming:
    print(f"   Found upcoming games in {len(round_upcoming)} rounds:")
    for round_num, games in sorted(round_upcoming.items()):
        print(f"   Round {round_num}: {len(games)} upcoming games")
        for e in games[:3]:  # Show first 3
            print(f"      - {e.get('dateEvent')} - {e.get('strHomeTeam')} vs {e.get('strAwayTeam')}")
        if len(games) > 3:
            print(f"      ... and {len(games) - 3} more")
else:
    print("   No upcoming games found in any rounds")

# 4. Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total unique upcoming URC games found: {len(all_upcoming_games)}")

if all_upcoming_games:
    # Group by date
    by_date = defaultdict(list)
    for game in all_upcoming_games:
        date = game.get('dateEvent', 'Unknown')
        by_date[date].append(game)
    
    print(f"\nUpcoming games by date:")
    for date in sorted(by_date.keys()):
        games = by_date[date]
        print(f"  {date}: {len(games)} game(s)")
        for game in games:
            print(f"    - {game.get('strHomeTeam')} vs {game.get('strAwayTeam')}")
    
    # Date range
    dates = [g.get('dateEvent') for g in all_upcoming_games if g.get('dateEvent')]
    if dates:
        min_date = min(dates)
        max_date = max(dates)
        print(f"\nDate range: {min_date} to {max_date}")
        
        # Count by month
        by_month = defaultdict(int)
        for date in dates:
            month_key = date[:7]  # YYYY-MM
            by_month[month_key] += 1
        
        print(f"\nGames by month:")
        for month in sorted(by_month.keys()):
            print(f"  {month}: {by_month[month]} games")
else:
    print("\n⚠️  WARNING: No upcoming URC games found in the API!")
    print("   This could mean:")
    print("   - The URC season hasn't started yet")
    print("   - All upcoming games have been played")
    print("   - The API doesn't have upcoming fixtures loaded")
    print("   - You may need to use manual fixtures")

print("\n" + "=" * 70)
