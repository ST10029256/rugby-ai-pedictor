#!/usr/bin/env python3
import sqlite3
import pandas as pd

conn = sqlite3.connect('data.sqlite')

# Test the exact query from load_events_dataframe
query = """
SELECT e.id AS event_id,
       e.league_id,
       e.season,
       e.date_event,
       e.timestamp,
       e.home_team_id,
       e.away_team_id,
       e.home_score,
       e.away_score
FROM event e
WHERE e.home_team_id IS NOT NULL AND e.away_team_id IS NOT NULL AND e.date_event IS NOT NULL
ORDER BY e.date_event ASC, e.timestamp ASC, e.id ASC;
"""

df = pd.read_sql_query(query, conn)
print(f'Total rows: {len(df)}')

# Check October 2025 fixtures specifically
oct_fixtures = df[df['date_event'].str.contains('2025-10-', na=False)]
print(f'October 2025 fixtures: {len(oct_fixtures)}')
print(oct_fixtures[['event_id', 'league_id', 'date_event', 'home_team_id', 'away_team_id']].head(10))

# Test date parsing on the SQL result
print('\nTesting date parsing on SQL result:')
df["date_event_parsed"] = pd.to_datetime(df["date_event"], errors="coerce")
oct_parsed = df[df['date_event_parsed'].dt.strftime('%Y-%m').str.contains('2025-10', na=False)]
print(f'October 2025 after parsing: {len(oct_parsed)}')

# Check for NaT values in October fixtures
oct_nat = df[df['date_event'].str.contains('2025-10-', na=False) & df['date_event_parsed'].isna()]
print(f'October 2025 NaT values: {len(oct_nat)}')
if len(oct_nat) > 0:
    print('NaT October fixtures:')
    print(oct_nat[['event_id', 'league_id', 'date_event', 'date_event_parsed']].head(10))

conn.close()
