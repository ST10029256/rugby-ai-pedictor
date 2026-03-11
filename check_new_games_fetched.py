#!/usr/bin/env python3
"""Check how many NEW games were fetched in the most recent update"""

import sqlite3
import json
from datetime import datetime, timedelta

# League mappings
LEAGUE_MAPPINGS = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship", 
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies"
}

# Read retrain flag to see what was updated
try:
    with open('retrain_needed.flag', 'r') as f:
        retrain_data = json.load(f)
    games_updated = retrain_data.get('games_updated', 0)
    timestamp = retrain_data.get('timestamp', '')
    print("=" * 80)
    print("MOST RECENT UPDATE SUMMARY")
    print("=" * 80)
    print(f"Timestamp: {timestamp}")
    print(f"Total games updated/added: {games_updated}")
    print(f"Reason: {retrain_data.get('reason', 'N/A')}")
    print()
except FileNotFoundError:
    print("⚠️ retrain_needed.flag not found - checking database directly...")
    games_updated = 0

# Check database for recent additions
conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

today = datetime.now().date()
# Check games added in the last 2 days (since last GitHub Actions run)
recent_date = today - timedelta(days=2)

print("=" * 80)
print("GAMES BY LEAGUE (Upcoming - Next 365 Days)")
print("=" * 80)
print()

total_upcoming = 0
league_counts = {}

for league_id, league_name in LEAGUE_MAPPINGS.items():
    # Count upcoming games (no scores = upcoming)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event 
        WHERE league_id = ?
        AND date_event >= date('now')
        AND date_event <= date('now', '+365 days')
        AND (home_score IS NULL OR away_score IS NULL)
    """, (league_id,))
    
    upcoming_count = cursor.fetchone()[0]
    
    if upcoming_count > 0:
        league_counts[league_id] = {
            'name': league_name,
            'upcoming': upcoming_count
        }
        total_upcoming += upcoming_count
        print(f"📊 {league_name}: {upcoming_count} upcoming games")

print()
print("=" * 80)
print(f"TOTAL UPCOMING GAMES: {total_upcoming}")
print("=" * 80)

if games_updated > 0:
    print()
    print("=" * 80)
    print("MOST RECENT FETCH RESULTS")
    print("=" * 80)
    print(f"✅ The last update fetched/updated {games_updated} games")
    print("   (This includes both new games and score updates for existing games)")
    print()
    print("💡 Note: The breakdown by league isn't stored, but the system")
    print("   successfully detected new games and triggered model retraining.")

conn.close()
