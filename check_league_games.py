#!/usr/bin/env python3
import sqlite3
import json

# Connect to database
conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

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

print("=" * 80)
print("COMPLETED GAMES BY LEAGUE")
print("=" * 80)

league_stats = []

for league_id, league_name in LEAGUE_MAPPINGS.items():
    # Count total games
    cursor.execute("""
        SELECT COUNT(*) FROM event 
        WHERE league_id = ?
    """, (league_id,))
    total_games = cursor.fetchone()[0]
    
    # Count completed games (with scores)
    cursor.execute("""
        SELECT COUNT(*) FROM event 
        WHERE league_id = ? 
        AND home_score IS NOT NULL 
        AND away_score IS NOT NULL
    """, (league_id,))
    completed_games = cursor.fetchone()[0]
    
    # Get date range
    cursor.execute("""
        SELECT MIN(date_event), MAX(date_event) FROM event 
        WHERE league_id = ? AND date_event IS NOT NULL
    """, (league_id,))
    date_range = cursor.fetchone()
    min_date = date_range[0] if date_range[0] else "N/A"
    max_date = date_range[1] if date_range[1] else "N/A"
    
    league_stats.append({
        'league_id': league_id,
        'name': league_name,
        'total': total_games,
        'completed': completed_games,
        'min_date': min_date,
        'max_date': max_date
    })

# Sort by completed games (descending)
league_stats.sort(key=lambda x: x['completed'], reverse=True)

print(f"\n{'League':<35} {'Total':<10} {'Completed':<12} {'Date Range':<30}")
print("-" * 80)

for stat in league_stats:
    date_range_str = f"{stat['min_date'][:10]} to {stat['max_date'][:10]}" if stat['min_date'] != "N/A" else "N/A"
    print(f"{stat['name']:<35} {stat['total']:<10} {stat['completed']:<12} {date_range_str:<30}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

total_all = sum(s['total'] for s in league_stats)
completed_all = sum(s['completed'] for s in league_stats)

print(f"Total games across all leagues: {total_all:,}")
print(f"Completed games across all leagues: {completed_all:,}")
print(f"\nLeagues with most completed games:")
for i, stat in enumerate(league_stats[:5], 1):
    print(f"  {i}. {stat['name']}: {stat['completed']:,} games")

# Compare with model registry
print("\n" + "=" * 80)
print("COMPARISON WITH MODEL REGISTRY")
print("=" * 80)

try:
    with open('artifacts/model_registry.json', 'r') as f:
        registry = json.load(f)
    
    print(f"\n{'League':<35} {'DB Games':<12} {'Registry Games':<15} {'Difference':<12}")
    print("-" * 80)
    
    for stat in league_stats:
        league_id_str = str(stat['league_id'])
        registry_data = registry.get('leagues', {}).get(league_id_str, {})
        registry_games = registry_data.get('training_games', 0)
        db_games = stat['completed']
        diff = db_games - registry_games
        
        diff_str = f"+{diff}" if diff > 0 else str(diff) if diff < 0 else "0"
        print(f"{stat['name']:<35} {db_games:<12} {registry_games:<15} {diff_str:<12}")
        
except Exception as e:
    print(f"Could not read model registry: {e}")

conn.close()

