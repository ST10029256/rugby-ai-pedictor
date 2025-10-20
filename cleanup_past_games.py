#!/usr/bin/env python3
import sqlite3
from datetime import datetime

conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

today = datetime.now().date()

# Delete games from October 10 (past games that never got results)
cursor.execute("""
    DELETE FROM event 
    WHERE (home_score IS NULL OR away_score IS NULL) 
    AND date_event = '2025-10-10'
""")

deleted = cursor.rowcount
conn.commit()

print(f'Deleted {deleted} games from October 10, 2025 (past games)')

# Check remaining upcoming games
cursor.execute("""
    SELECT e.date_event, t1.name as home_team, t2.name as away_team, e.league_id 
    FROM event e 
    LEFT JOIN team t1 ON e.home_team_id = t1.id 
    LEFT JOIN team t2 ON e.away_team_id = t2.id 
    WHERE (e.home_score IS NULL OR e.away_score IS NULL) 
    AND e.league_id IN (4414, 4430, 4446)
    ORDER BY e.date_event
""")

results = cursor.fetchall()
print(f'\nRemaining upcoming games:')
for row in results:
    print(f'League {row[3]}: {row[0]} - {row[1]} vs {row[2]}')

print(f'\nTotal upcoming games: {len(results)}')

conn.close()
