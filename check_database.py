#!/usr/bin/env python3
"""Check database completeness and duplicates"""

import sqlite3
from datetime import datetime

conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

# Configured leagues
leagues = {
    4986: 'Rugby Championship',
    4446: 'United Rugby Championship',
    5069: 'Currie Cup',
    4574: 'Rugby World Cup',
    4551: 'Super Rugby',
    4430: 'French Top 14',
    4414: 'English Premiership Rugby'
}

print("=" * 100)
print("DATABASE COMPLETENESS CHECK")
print("=" * 100)

# Check total events
cursor.execute('SELECT COUNT(*) FROM event')
total_events = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(DISTINCT id) FROM event')
unique_events = cursor.fetchone()[0]

print(f"\nOVERALL STATISTICS:")
print(f"   Total events: {total_events}")
print(f"   Unique events: {unique_events}")
print(f"   Duplicates by ID: {total_events - unique_events}")

# Check each league
print(f"\nLEAGUE DATA COVERAGE:")
print("-" * 100)

for league_id, league_name in leagues.items():
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            MIN(date_event) as earliest,
            MAX(date_event) as latest,
            SUM(CASE WHEN home_score IS NOT NULL THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN home_score IS NULL THEN 1 ELSE 0 END) as upcoming
        FROM event 
        WHERE league_id = ?
    ''', (league_id,))
    
    row = cursor.fetchone()
    if row and row[0] > 0:
        total, earliest, latest, completed, upcoming = row
        status = "[OK]"
        print(f"{status} {league_name} (ID: {league_id})")
        print(f"   Total games: {total}")
        print(f"   Date range: {earliest} to {latest}")
        print(f"   Completed: {completed}, Upcoming: {upcoming}")
        print()
    else:
        print(f"[MISSING] {league_name} (ID: {league_id}): NO DATA")
        print()

# Check for duplicate games (same league, date, teams)
print(f"\nCHECKING FOR DUPLICATE GAMES:")
print("-" * 100)

cursor.execute('''
    SELECT 
        league_id,
        date_event,
        home_team_id,
        away_team_id,
        COUNT(*) as count
    FROM event
    WHERE date_event IS NOT NULL
    GROUP BY league_id, date_event, home_team_id, away_team_id
    HAVING COUNT(*) > 1
    ORDER BY league_id, date_event
''')

duplicates = cursor.fetchall()

if duplicates:
    print(f"WARNING: Found {len(duplicates)} duplicate game entries:")
    for dup in duplicates[:20]:  # Show first 20
        league_name = leagues.get(dup[0], f"Unknown ({dup[0]})")
        print(f"   League: {league_name}, Date: {dup[1]}, Teams: {dup[2]} vs {dup[3]}, Count: {dup[4]}")
    if len(duplicates) > 20:
        print(f"   ... and {len(duplicates) - 20} more")
else:
    print("OK: No duplicate games found!")

# Check for data gaps (missing dates in active seasons)
print(f"\nDATA FRESHNESS:")
print("-" * 100)

today = datetime.now().strftime('%Y-%m-%d')
cursor.execute('''
    SELECT league_id, MAX(date_event) as latest
    FROM event
    GROUP BY league_id
''')

for row in cursor.fetchall():
    league_id, latest_date = row
    league_name = leagues.get(league_id, f"Unknown ({league_id})")
    print(f"{league_name}: Latest game date = {latest_date}")

print(f"\nToday's date: {today}")

# Summary
print(f"\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

missing_leagues = [name for lid, name in leagues.items() if cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ?', (lid,)).fetchone()[0] == 0]

if missing_leagues:
    print(f"MISSING: Data for {len(missing_leagues)} league(s): {', '.join(missing_leagues)}")
else:
    print(f"OK: All 7 leagues have historical data")

if duplicates:
    print(f"WARNING: {len(duplicates)} duplicate game(s) found - consider cleanup")
else:
    print(f"OK: No duplicates found")

print(f"OK: Total {total_events} events across {len(leagues)} leagues")

conn.close()

