#!/usr/bin/env python3
"""Check which leagues have news/matches available"""

import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

print("=" * 80)
print("CHECKING WHICH LEAGUES HAVE NEWS/MATCHES")
print("=" * 80)

# League name mapping
LEAGUE_NAMES = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
}

# Check upcoming matches (next 7 days)
print("\n📅 UPCOMING MATCHES (Next 7 days):")
print("-" * 80)

cursor.execute("""
    SELECT e.league_id, COUNT(*) as match_count,
           MIN(e.date_event) as earliest_match,
           MAX(e.date_event) as latest_match
    FROM event e
    WHERE e.date_event >= date('now')
    AND e.date_event <= date('now', '+7 days')
    AND e.home_team_id IS NOT NULL
    AND e.away_team_id IS NOT NULL
    GROUP BY e.league_id
    ORDER BY match_count DESC
""")

upcoming_by_league = {}
for row in cursor.fetchall():
    league_id, count, earliest, latest = row
    upcoming_by_league[league_id] = {
        'count': count,
        'earliest': earliest,
        'latest': latest
    }
    league_name = LEAGUE_NAMES.get(league_id, f"League {league_id}")
    print(f"  ✅ {league_name} (ID: {league_id}): {count} matches")
    print(f"     Dates: {earliest} to {latest}")

if not upcoming_by_league:
    print("  ⚠️  No upcoming matches found in any league")

# Check recent completed matches (last 7 days)
print("\n📊 RECENT COMPLETED MATCHES (Last 7 days):")
print("-" * 80)

cursor.execute("""
    SELECT e.league_id, COUNT(*) as match_count
    FROM event e
    WHERE e.date_event >= date('now', '-7 days')
    AND e.date_event < date('now')
    AND e.home_score IS NOT NULL
    AND e.away_score IS NOT NULL
    AND e.home_team_id IS NOT NULL
    AND e.away_team_id IS NOT NULL
    GROUP BY e.league_id
    ORDER BY match_count DESC
""")

recent_by_league = {}
for row in cursor.fetchall():
    league_id, count = row
    recent_by_league[league_id] = count
    league_name = LEAGUE_NAMES.get(league_id, f"League {league_id}")
    print(f"  ✅ {league_name} (ID: {league_id}): {count} matches")

if not recent_by_league:
    print("  ⚠️  No recent completed matches found")

# Summary by league
print("\n" + "=" * 80)
print("SUMMARY BY LEAGUE:")
print("=" * 80)

for league_id, league_name in sorted(LEAGUE_NAMES.items()):
    upcoming = upcoming_by_league.get(league_id, {}).get('count', 0)
    recent = recent_by_league.get(league_id, 0)
    total = upcoming + recent
    
    status = "✅ HAS NEWS" if total > 0 else "❌ NO NEWS"
    print(f"\n{status} - {league_name} (ID: {league_id})")
    print(f"   Upcoming matches: {upcoming}")
    print(f"   Recent matches: {recent}")
    print(f"   Total: {total}")
    
    if upcoming > 0:
        info = upcoming_by_league[league_id]
        print(f"   Next match: {info['earliest']}")
        print(f"   Last match: {info['latest']}")

# Check all leagues in database
print("\n" + "=" * 80)
print("ALL LEAGUES IN DATABASE:")
print("=" * 80)

cursor.execute("""
    SELECT DISTINCT e.league_id, COUNT(*) as total_matches
    FROM event e
    WHERE e.home_team_id IS NOT NULL
    AND e.away_team_id IS NOT NULL
    GROUP BY e.league_id
    ORDER BY total_matches DESC
""")

all_leagues = {}
for row in cursor.fetchall():
    league_id, total = row
    all_leagues[league_id] = total
    league_name = LEAGUE_NAMES.get(league_id, f"League {league_id}")
    print(f"  {league_name} (ID: {league_id}): {total} total matches")

# Check for leagues in config but not in database
print("\n" + "=" * 80)
print("LEAGUES IN CONFIG BUT NOT IN DATABASE:")
print("=" * 80)

missing_leagues = []
for league_id, league_name in LEAGUE_NAMES.items():
    if league_id not in all_leagues:
        missing_leagues.append((league_id, league_name))
        print(f"  ⚠️  {league_name} (ID: {league_id}): No matches in database")

if not missing_leagues:
    print("  ✅ All configured leagues have matches in database")

# Recommendations
print("\n" + "=" * 80)
print("RECOMMENDATIONS:")
print("=" * 80)

leagues_with_news = [lid for lid in LEAGUE_NAMES.keys() if upcoming_by_league.get(lid, {}).get('count', 0) > 0 or recent_by_league.get(lid, 0) > 0]
leagues_without_news = [lid for lid in LEAGUE_NAMES.keys() if lid not in leagues_with_news]

if leagues_with_news:
    print(f"\n✅ Leagues WITH news ({len(leagues_with_news)}):")
    for lid in leagues_with_news:
        name = LEAGUE_NAMES[lid]
        upcoming = upcoming_by_league.get(lid, {}).get('count', 0)
        recent = recent_by_league.get(lid, 0)
        print(f"   - {name}: {upcoming} upcoming, {recent} recent")

if leagues_without_news:
    print(f"\n❌ Leagues WITHOUT news ({len(leagues_without_news)}):")
    for lid in leagues_without_news:
        name = LEAGUE_NAMES[lid]
        print(f"   - {name} (ID: {lid})")
    print("\n   These leagues will show empty states in the news feed.")

conn.close()

