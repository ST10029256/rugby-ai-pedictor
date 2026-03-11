#!/usr/bin/env python3
"""Check how many games were recently added per league"""

import sqlite3
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

conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

today = datetime.now().date()
future_date = today + timedelta(days=365)

print("=" * 80)
print("RECENT GAMES FETCHED BY LEAGUE")
print("=" * 80)
print(f"Checking upcoming games (from {today} to {future_date})\n")

total_games = 0

for league_id, league_name in LEAGUE_MAPPINGS.items():
    # Count upcoming games (no scores = upcoming)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event 
        WHERE league_id = ?
        AND date_event >= ?
        AND date_event <= ?
        AND (home_score IS NULL OR away_score IS NULL)
    """, (league_id, str(today), str(future_date)))
    
    upcoming_count = cursor.fetchone()[0]
    
    # Count total games in date range
    cursor.execute("""
        SELECT COUNT(*) 
        FROM event 
        WHERE league_id = ?
        AND date_event >= ?
        AND date_event <= ?
    """, (league_id, str(today), str(future_date)))
    
    total_count = cursor.fetchone()[0]
    
    if total_count > 0:
        print(f"📊 {league_name}:")
        print(f"   Total upcoming games: {upcoming_count}")
        print(f"   Total games (all): {total_count}")
        print()
        total_games += upcoming_count

print("=" * 80)
print(f"TOTAL UPCOMING GAMES ACROSS ALL LEAGUES: {total_games}")
print("=" * 80)

conn.close()
