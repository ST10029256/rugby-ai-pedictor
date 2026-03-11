#!/usr/bin/env python3
"""Test if the enhanced_auto_update script will fetch URC games correctly"""

import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.enhanced_auto_update import fetch_games_from_sportsdb, LEAGUE_MAPPINGS
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("=" * 70)
print("Testing URC Game Fetching")
print("=" * 70)

# Get URC league info
league_id = 4446
league_info = LEAGUE_MAPPINGS[league_id]
league_name = league_info['name']
sportsdb_id = league_info['sportsdb_id']

print(f"\nLeague: {league_name}")
print(f"League ID: {league_id}")
print(f"SportsDB ID: {sportsdb_id}")

# Test fetching games (with round scanning enabled for URC)
print("\nFetching games (round scanning is automatic for URC)...")
print("-" * 70)

try:
    games = fetch_games_from_sportsdb(
        league_id=league_id,
        sportsdb_id=sportsdb_id,
        league_name=league_name,
        include_history=False,
        scan_rounds=False,  # Will be auto-enabled for URC in the code
        days_ahead=180,
        days_back=14,
    )
    
    print(f"\n✅ Successfully fetched games!")
    print(f"Total games returned: {len(games)}")
    
    # Filter for upcoming games (no scores)
    upcoming = [g for g in games if g.get('home_score') is None and g.get('away_score') is None]
    print(f"Upcoming games (no scores): {len(upcoming)}")
    
    # Group by date
    from collections import defaultdict
    by_date = defaultdict(list)
    for game in upcoming:
        date = str(game.get('date_event', 'Unknown'))
        by_date[date].append(game)
    
    if upcoming:
        print(f"\nUpcoming games by date (first 10 dates):")
        for date in sorted(by_date.keys())[:10]:
            games_on_date = by_date[date]
            print(f"  {date}: {len(games_on_date)} game(s)")
            for game in games_on_date[:2]:  # Show first 2
                print(f"    - {game.get('home_team')} vs {game.get('away_team')}")
            if len(games_on_date) > 2:
                print(f"    ... and {len(games_on_date) - 2} more")
        
        if len(by_date) > 10:
            print(f"\n  ... and {len(by_date) - 10} more dates")
        
        # Date range
        dates = [str(g.get('date_event')) for g in upcoming if g.get('date_event')]
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            print(f"\nDate range: {min_date} to {max_date}")
    else:
        print("\n⚠️  No upcoming games found!")
        print("   This might mean:")
        print("   - All games have scores (completed)")
        print("   - Date filtering excluded them")
        print("   - API rate limiting occurred")
    
    # Show games with scores (past games)
    past = [g for g in games if g.get('home_score') is not None or g.get('away_score') is not None]
    if past:
        print(f"\nPast games (with scores): {len(past)}")
    
except Exception as e:
    print(f"\n❌ Error fetching games: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Note: This test doesn't save to database, just checks if fetching works")
print("Run 'python scripts/enhanced_auto_update.py' to actually update the database")
print("=" * 70)
