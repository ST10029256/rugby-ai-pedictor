#!/usr/bin/env python3
"""Check why league filtering isn't working"""

import sqlite3

conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

print("=" * 80)
print("CHECKING LEAGUE FILTERING ISSUE")
print("=" * 80)

# Check what league_id these teams' matches have
test_teams = ["Newcastle Red Bulls", "Bath Rugby", "Northampton Saints", "Glasgow", "Stormers"]

for team_name in test_teams[:3]:  # Check first 3
    print(f"\n🔍 Checking matches for: {team_name}")
    cursor.execute("""
        SELECT e.id, e.league_id, t1.name as home_team, t2.name as away_team, e.date_event
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE (t1.name LIKE ? OR t2.name LIKE ?)
        AND e.date_event >= date('now')
        AND e.date_event <= date('now', '+7 days')
        LIMIT 3
    """, (f"%{team_name}%", f"%{team_name}%"))
    
    matches = cursor.fetchall()
    for match in matches:
        match_id, league_id, home, away, date_event = match
        print(f"   Match {match_id}: {home} vs {away} | League ID: {league_id} | Date: {date_event}")

# Check how many matches exist for league 4986 (Rugby Championship)
print(f"\n{'='*80}")
print("CHECKING LEAGUE 4986 (Rugby Championship)")
print(f"{'='*80}\n")

cursor.execute("""
    SELECT COUNT(*) as count
    FROM event e
    WHERE e.league_id = 4986
    AND e.date_event >= date('now')
    AND e.date_event <= date('now', '+7 days')
""")
count_4986 = cursor.fetchone()[0]
print(f"Matches with league_id=4986 (Rugby Championship): {count_4986}")

if count_4986 > 0:
    cursor.execute("""
        SELECT e.id, e.league_id, t1.name as home_team, t2.name as away_team, e.date_event
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = 4986
        AND e.date_event >= date('now')
        AND e.date_event <= date('now', '+7 days')
        LIMIT 5
    """)
    print("\nSample Rugby Championship matches:")
    for match in cursor.fetchall():
        match_id, league_id, home, away, date_event = match
        print(f"   {home} vs {away} (League: {league_id}, Date: {date_event})")

# Check all upcoming matches by league
print(f"\n{'='*80}")
print("ALL UPCOMING MATCHES BY LEAGUE")
print(f"{'='*80}\n")

cursor.execute("""
    SELECT e.league_id, COUNT(*) as count
    FROM event e
    WHERE e.date_event >= date('now')
    AND e.date_event <= date('now', '+7 days')
    AND e.home_team_id IS NOT NULL
    AND e.away_team_id IS NOT NULL
    GROUP BY e.league_id
    ORDER BY count DESC
""")

print("League distribution:")
for row in cursor.fetchall():
    league_id, count = row
    print(f"   League {league_id}: {count} matches")

# Check if the SQL query with filter would work
print(f"\n{'='*80}")
print("TESTING SQL QUERY WITH LEAGUE FILTER")
print(f"{'='*80}\n")

filter_league_id = 4986
league_filter = "AND e.league_id = ?"
league_params = [filter_league_id]

query = f"""
    SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
           t1.name as home_team, t2.name as away_team
    FROM event e
    LEFT JOIN team t1 ON e.home_team_id = t1.id
    LEFT JOIN team t2 ON e.away_team_id = t2.id
    WHERE e.date_event >= date('now')
    AND e.date_event <= date('now', '+7 days')
    AND e.home_team_id IS NOT NULL
    AND e.away_team_id IS NOT NULL
    {league_filter}
    ORDER BY e.date_event ASC
    LIMIT 15
"""

print(f"Query with league_id={filter_league_id}:")
print(query)
print(f"\nParameters: {league_params}")

cursor.execute(query, league_params)
matches = cursor.fetchall()

print(f"\nResults: {len(matches)} matches")
for match in matches[:5]:
    match_id, league_id, date_event, home_id, away_id, home_team, away_team = match
    print(f"   {home_team} vs {away_team} (League: {league_id})")

conn.close()

