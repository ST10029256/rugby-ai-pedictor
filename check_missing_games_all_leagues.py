#!/usr/bin/env python3
"""Check how many upcoming games are missing from database across all leagues"""

import sqlite3
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict

# League mappings
LEAGUE_MAPPINGS = {
    4986: {"name": "Rugby Championship", "sportsdb_id": 4986},
    4446: {"name": "United Rugby Championship", "sportsdb_id": 4446}, 
    5069: {"name": "Currie Cup", "sportsdb_id": 5069},
    4574: {"name": "Rugby World Cup", "sportsdb_id": 4574},
    4551: {"name": "Super Rugby", "sportsdb_id": 4551},
    4430: {"name": "French Top 14", "sportsdb_id": 4430},
    4414: {"name": "English Premiership Rugby", "sportsdb_id": 4414},
    4714: {"name": "Six Nations Championship", "sportsdb_id": 4714},
    5479: {"name": "Rugby Union International Friendlies", "sportsdb_id": 5479}
}

# Max rounds per league
MAX_ROUNDS_BY_LEAGUE = {
    4446: 18,  # URC
    4414: 18,  # Premiership
    4430: 26,  # Top 14
    4551: 18,  # Super Rugby
    4714: 5,   # Six Nations
    4986: 6,   # Rugby Championship
    5069: 14,  # Currie Cup
    4574: 30,  # World Cup
    5479: 0    # Friendlies (special handling)
}

YEAR_SPAN_LEAGUE_IDS = {4414, 4430, 4446}
SINGLE_YEAR_LEAGUE_IDS = {4551, 4714, 4986, 5069, 5479}

def compute_current_seasons(sportsdb_id: int) -> list:
    """Compute current season strings to try"""
    today = datetime.now()
    year = today.year
    month = today.month
    seasons = []
    
    is_year_span = sportsdb_id in YEAR_SPAN_LEAGUE_IDS
    is_single_year = sportsdb_id in SINGLE_YEAR_LEAGUE_IDS
    
    if is_year_span:
        current_span = f"{year}-{year + 1}" if month >= 8 else f"{year - 1}-{year}"
        adjacent_span = f"{year - 1}-{year}" if current_span == f"{year}-{year + 1}" else f"{year}-{year + 1}"
        seasons.extend([current_span, adjacent_span])
    
    if is_single_year:
        seasons.extend([str(year), str(year - 1)])
    
    deduped = []
    for s in seasons:
        if s not in deduped:
            deduped.append(s)
    return deduped

def is_upcoming(event):
    """Check if event is upcoming (has date >= today and no scores)"""
    today = datetime.now().date()
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

def get_api_upcoming_games(sportsdb_id: int, league_name: str) -> set:
    """Get all upcoming games from API"""
    print(f"  Fetching from API...")
    api_games = set()
    today = datetime.now().date()
    
    # Check eventsnextleague
    try:
        url = f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={sportsdb_id}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            events = data.get('events', [])
            for e in events:
                if is_upcoming(e):
                    game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
                    api_games.add(game_key)
    except Exception as e:
        print(f"    ⚠️  Error with eventsnextleague: {e}")
    
    # Check eventsseason
    for season in compute_current_seasons(sportsdb_id):
        try:
            url = f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={sportsdb_id}&s={season}"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                events = data.get('events', [])
                for e in events:
                    if is_upcoming(e):
                        game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
                        api_games.add(game_key)
        except Exception as e:
            print(f"    ⚠️  Error with eventsseason ({season}): {e}")
    
    # Check eventsround (sample a few rounds to get estimate)
    max_rounds = MAX_ROUNDS_BY_LEAGUE.get(sportsdb_id, 0)
    if max_rounds > 0:
        # Sample rounds 1, middle, and last to get estimate
        rounds_to_check = [1, max_rounds // 2, max_rounds] if max_rounds >= 3 else list(range(1, max_rounds + 1))
        for season in compute_current_seasons(sportsdb_id):
            for round_num in rounds_to_check:
                try:
                    url = f"https://www.thesportsdb.com/api/v1/json/123/eventsround.php?id={sportsdb_id}&r={round_num}&s={season}"
                    response = requests.get(url, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        events = data.get('events', [])
                        for e in events:
                            if is_upcoming(e):
                                game_key = (e.get('dateEvent'), e.get('strHomeTeam'), e.get('strAwayTeam'))
                                api_games.add(game_key)
                    import time
                    time.sleep(0.3)  # Rate limiting
                except Exception as e:
                    pass
    
    return api_games

def get_db_upcoming_games(conn: sqlite3.Connection, league_id: int) -> set:
    """Get all upcoming games from database"""
    cursor = conn.cursor()
    today = datetime.now().date()
    future_date = today + timedelta(days=180)
    
    cursor.execute("""
        SELECT e.date_event, t1.name, t2.name
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        WHERE e.league_id = ?
        AND e.date_event >= ?
        AND e.date_event <= ?
        AND (e.home_score IS NULL OR e.away_score IS NULL)
    """, (league_id, str(today), str(future_date)))
    
    db_games = set()
    for row in cursor.fetchall():
        date, home, away = row
        if date and home and away:
            # Normalize date format
            if isinstance(date, str):
                date_str = date[:10]  # YYYY-MM-DD
            else:
                date_str = str(date)[:10]
            game_key = (date_str, home, away)
            db_games.add(game_key)
    
    return db_games

print("=" * 80)
print("Checking Missing Games Across All Leagues")
print("=" * 80)
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Connect to database
try:
    conn = sqlite3.connect('data.sqlite')
    print("✅ Connected to database\n")
except Exception as e:
    print(f"❌ Error connecting to database: {e}")
    exit(1)

total_missing = 0
total_api = 0
total_db = 0

results = []

for league_id, league_info in LEAGUE_MAPPINGS.items():
    league_name = league_info['name']
    sportsdb_id = league_info['sportsdb_id']
    
    print(f"📊 {league_name} (ID: {league_id})")
    print("-" * 80)
    
    # Get games from API
    api_games = get_api_upcoming_games(sportsdb_id, league_name)
    
    # Get games from database
    db_games = get_db_upcoming_games(conn, league_id)
    
    # Find missing games
    missing = api_games - db_games
    
    api_count = len(api_games)
    db_count = len(db_games)
    missing_count = len(missing)
    
    total_api += api_count
    total_db += db_count
    total_missing += missing_count
    
    results.append({
        'league': league_name,
        'league_id': league_id,
        'api_games': api_count,
        'db_games': db_count,
        'missing': missing_count,
        'missing_games': list(missing)[:10]  # First 10 for display
    })
    
    print(f"  API upcoming games: {api_count}")
    print(f"  Database upcoming games: {db_count}")
    print(f"  Missing games: {missing_count}")
    
    if missing_count > 0:
        print(f"  ⚠️  Missing {missing_count} games!")
        if missing_count <= 10:
            for date, home, away in sorted(missing):
                print(f"    - {date}: {home} vs {away}")
        else:
            print(f"    (Showing first 10 of {missing_count} missing games)")
            for date, home, away in sorted(list(missing))[:10]:
                print(f"    - {date}: {home} vs {away}")
    else:
        print(f"  ✅ All upcoming games are in database!")
    
    print()

conn.close()

# Summary
print("=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total upcoming games in API: {total_api}")
print(f"Total upcoming games in database: {total_db}")
print(f"Total missing games: {total_missing}")
print()

if total_missing > 0:
    print("⚠️  MISSING GAMES BY LEAGUE:")
    print("-" * 80)
    for r in sorted(results, key=lambda x: x['missing'], reverse=True):
        if r['missing'] > 0:
            print(f"  {r['league']}: {r['missing']} missing ({r['db_games']}/{r['api_games']} in DB)")
    print()
    print("💡 To fix: Run 'python scripts/enhanced_auto_update.py' to fetch missing games")
else:
    print("✅ All upcoming games are in the database!")

print("=" * 80)
