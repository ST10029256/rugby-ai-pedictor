#!/usr/bin/env python3
"""Check if games are synced to Firestore and manually sync if needed"""

import sqlite3
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = script_dir
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    print("❌ google-cloud-firestore not installed")
    print("   Install with: pip install google-cloud-firestore")
    sys.exit(1)

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

def check_firestore_matches(project_id='rugby-ai-61fd0'):
    """Check how many matches are in Firestore per league"""
    print("=" * 80)
    print("CHECKING FIRESTORE FOR MATCHES")
    print("=" * 80)
    
    try:
        db = firestore.Client(project=project_id)
        matches_ref = db.collection('matches')
        
        # Get all matches
        all_matches = list(matches_ref.stream())
        print(f"\n📊 Total matches in Firestore: {len(all_matches)}")
        
        # Count by league
        from datetime import datetime
        today = datetime.now().date()
        
        league_counts = {}
        upcoming_counts = {}
        
        for doc in all_matches:
            data = doc.to_dict()
            league_id = data.get('league_id')
            
            if league_id:
                if league_id not in league_counts:
                    league_counts[league_id] = 0
                    upcoming_counts[league_id] = 0
                
                league_counts[league_id] += 1
                
                # Check if upcoming (no scores)
                home_score = data.get('home_score')
                away_score = data.get('away_score')
                date_event = data.get('date_event')
                
                if date_event:
                    if isinstance(date_event, datetime):
                        match_date = date_event.date()
                    elif isinstance(date_event, str):
                        try:
                            match_date = datetime.fromisoformat(date_event.replace('Z', '+00:00')).date()
                        except:
                            try:
                                match_date = datetime.strptime(date_event[:10], '%Y-%m-%d').date()
                            except:
                                match_date = None
                    else:
                        match_date = None
                    
                    if match_date and match_date >= today and (home_score is None or away_score is None):
                        upcoming_counts[league_id] += 1
        
        print("\n📊 Matches by League:")
        print("-" * 80)
        for league_id in sorted(league_counts.keys()):
            league_name = LEAGUE_MAPPINGS.get(league_id, f"League {league_id}")
            total = league_counts[league_id]
            upcoming = upcoming_counts.get(league_id, 0)
            print(f"  {league_name} (ID: {league_id}):")
            print(f"    Total: {total} matches")
            print(f"    Upcoming: {upcoming} matches")
        
        return len(all_matches), league_counts, upcoming_counts
        
    except Exception as e:
        print(f"❌ Error checking Firestore: {e}")
        import traceback
        traceback.print_exc()
        return 0, {}, {}

def check_sqlite_matches():
    """Check how many matches are in SQLite per league"""
    print("\n" + "=" * 80)
    print("CHECKING SQLITE DATABASE")
    print("=" * 80)
    
    if not os.path.exists('data.sqlite'):
        print("❌ data.sqlite not found!")
        return 0, {}, {}
    
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    from datetime import datetime, timedelta
    today = datetime.now().date()
    future_date = today + timedelta(days=365)
    
    # Count by league
    cursor.execute("""
        SELECT league_id, COUNT(*) 
        FROM event 
        WHERE date_event >= ? AND date_event <= ?
        GROUP BY league_id
    """, (str(today), str(future_date)))
    
    league_counts = {}
    for row in cursor.fetchall():
        league_id, count = row
        league_counts[league_id] = count
    
    # Count upcoming by league
    cursor.execute("""
        SELECT league_id, COUNT(*) 
        FROM event 
        WHERE date_event >= ? 
        AND date_event <= ?
        AND (home_score IS NULL OR away_score IS NULL)
        GROUP BY league_id
    """, (str(today), str(future_date)))
    
    upcoming_counts = {}
    for row in cursor.fetchall():
        league_id, count = row
        upcoming_counts[league_id] = count
    
    print(f"\n📊 Upcoming matches in SQLite (next 365 days):")
    print("-" * 80)
    for league_id in sorted(league_counts.keys()):
        league_name = LEAGUE_MAPPINGS.get(league_id, f"League {league_id}")
        total = league_counts[league_id]
        upcoming = upcoming_counts.get(league_id, 0)
        print(f"  {league_name} (ID: {league_id}):")
        print(f"    Total: {total} matches")
        print(f"    Upcoming: {upcoming} matches")
    
    conn.close()
    return sum(league_counts.values()), league_counts, upcoming_counts

if __name__ == "__main__":
    print("\n🔍 Checking Firestore vs SQLite sync status...\n")
    
    # Check SQLite
    sqlite_total, sqlite_league_counts, sqlite_upcoming = check_sqlite_matches()
    
    # Check Firestore
    firestore_total, firestore_league_counts, firestore_upcoming = check_firestore_matches()
    
    # Compare
    print("\n" + "=" * 80)
    print("SYNC STATUS COMPARISON")
    print("=" * 80)
    
    all_leagues = set(list(sqlite_league_counts.keys()) + list(firestore_league_counts.keys()))
    
    if not all_leagues:
        print("⚠️  No leagues found in either database!")
    else:
        print("\n📊 Upcoming Matches Comparison:")
        print("-" * 80)
        for league_id in sorted(all_leagues):
            league_name = LEAGUE_MAPPINGS.get(league_id, f"League {league_id}")
            sqlite_count = sqlite_upcoming.get(league_id, 0)
            firestore_count = firestore_upcoming.get(league_id, 0)
            
            status = "✅" if sqlite_count == firestore_count else "⚠️"
            diff = sqlite_count - firestore_count
            
            print(f"{status} {league_name} (ID: {league_id}):")
            print(f"    SQLite: {sqlite_count} upcoming")
            print(f"    Firestore: {firestore_count} upcoming")
            if diff != 0:
                print(f"    ⚠️  Difference: {diff} matches missing in Firestore")
    
    print("\n" + "=" * 80)
    if firestore_total == 0:
        print("❌ NO MATCHES IN FIRESTORE - Sync needed!")
        print("\n💡 To sync, run:")
        print("   python scripts/sync_to_firestore.py --db data.sqlite --project-id rugby-ai-61fd0")
    elif sqlite_total > firestore_total:
        print("⚠️  Firestore has fewer matches than SQLite - Sync needed!")
        print("\n💡 To sync, run:")
        print("   python scripts/sync_to_firestore.py --db data.sqlite --project-id rugby-ai-61fd0")
    else:
        print("✅ Firestore appears to be in sync with SQLite")
    print("=" * 80)
