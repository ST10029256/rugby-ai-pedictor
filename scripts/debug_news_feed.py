"""
Debug script to investigate why news feed is returning 0 items
"""

import sqlite3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import prediction modules
sys.path.insert(0, str(Path(__file__).parent.parent))

def find_database():
    """Find the database file"""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "data.sqlite"),
        os.path.join(os.path.dirname(__file__), "..", "rugby-ai-predictor", "data.sqlite"),
        "data.sqlite",
        os.path.join(os.getcwd(), "data.sqlite"),
    ]
    
    print("\n" + "="*80)
    print("SEARCHING FOR DATABASE FILE".center(80))
    print("="*80 + "\n")
    
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        exists = os.path.exists(abs_path)
        size = os.path.getsize(abs_path) if exists else 0
        print(f"  {'✅' if exists else '❌'} {abs_path}")
        if exists:
            print(f"     Size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
            return abs_path
    
    print("\n❌ Database file not found in any expected location!")
    return None

def test_database_connection(db_path):
    """Test database connection and basic queries"""
    print("\n" + "="*80)
    print("TESTING DATABASE CONNECTION".center(80))
    print("="*80 + "\n")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Test 1: Check if event table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='event'")
        if cursor.fetchone():
            print("✅ Event table exists")
        else:
            print("❌ Event table does NOT exist!")
            conn.close()
            return False
        
        # Test 2: Count total events
        cursor.execute("SELECT COUNT(*) FROM event")
        total_events = cursor.fetchone()[0]
        print(f"✅ Total events in database: {total_events:,}")
        
        # Test 3: Count events with scores (completed matches)
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """)
        completed_matches = cursor.fetchone()[0]
        print(f"✅ Completed matches: {completed_matches:,}")
        
        # Test 4: Count upcoming matches
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE date_event >= date('now') 
            AND date_event <= date('now', '+7 days')
            AND home_team_id IS NOT NULL 
            AND away_team_id IS NOT NULL
        """)
        upcoming_matches = cursor.fetchone()[0]
        print(f"✅ Upcoming matches (next 7 days): {upcoming_matches:,}")
        
        # Test 5: Count recent completed matches
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE date_event >= date('now', '-7 days')
            AND date_event < date('now')
            AND home_score IS NOT NULL 
            AND away_score IS NOT NULL
            AND home_team_id IS NOT NULL 
            AND away_team_id IS NOT NULL
        """)
        recent_matches = cursor.fetchone()[0]
        print(f"✅ Recent completed matches (last 7 days): {recent_matches:,}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_league_data(db_path, league_id):
    """Check data for a specific league"""
    print("\n" + "="*80)
    print(f"CHECKING DATA FOR LEAGUE {league_id}".center(80))
    print("="*80 + "\n")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if league exists in database
        cursor.execute("SELECT DISTINCT league_id FROM event WHERE league_id = ?", (league_id,))
        if cursor.fetchone():
            print(f"✅ League {league_id} exists in database")
        else:
            print(f"❌ League {league_id} NOT found in database!")
            cursor.execute("SELECT DISTINCT league_id FROM event LIMIT 10")
            available_leagues = [row[0] for row in cursor.fetchall()]
            print(f"   Available leagues: {available_leagues}")
            conn.close()
            return False
        
        # Count total matches for this league
        cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = ?", (league_id,))
        total = cursor.fetchone()[0]
        print(f"✅ Total matches for league {league_id}: {total:,}")
        
        # Count upcoming matches
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = ?
            AND date_event >= date('now') 
            AND date_event <= date('now', '+7 days')
            AND home_team_id IS NOT NULL 
            AND away_team_id IS NOT NULL
        """, (league_id,))
        upcoming = cursor.fetchone()[0]
        print(f"✅ Upcoming matches (next 7 days): {upcoming:,}")
        
        # Show sample upcoming matches
        if upcoming > 0:
            cursor.execute("""
                SELECT e.id, e.date_event, t1.name, t2.name
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.league_id = ?
                AND e.date_event >= date('now') 
                AND e.date_event <= date('now', '+7 days')
                AND e.home_team_id IS NOT NULL 
                AND e.away_team_id IS NOT NULL
                ORDER BY e.date_event ASC
                LIMIT 5
            """, (league_id,))
            print("\n   Sample upcoming matches:")
            for row in cursor.fetchall():
                match_id, date_event, home_team, away_team = row
                print(f"     - {date_event}: {home_team} vs {away_team} (ID: {match_id})")
        
        # Count recent completed matches
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = ?
            AND date_event >= date('now', '-7 days')
            AND date_event < date('now')
            AND home_score IS NOT NULL 
            AND away_score IS NOT NULL
            AND home_team_id IS NOT NULL 
            AND away_team_id IS NOT NULL
        """, (league_id,))
        recent = cursor.fetchone()[0]
        print(f"✅ Recent completed matches (last 7 days): {recent:,}")
        
        # Show sample recent matches
        if recent > 0:
            cursor.execute("""
                SELECT e.id, e.date_event, t1.name, e.home_score, t2.name, e.away_score
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.league_id = ?
                AND e.date_event >= date('now', '-7 days')
                AND e.date_event < date('now')
                AND e.home_score IS NOT NULL 
                AND e.away_score IS NOT NULL
                AND e.home_team_id IS NOT NULL 
                AND e.away_team_id IS NOT NULL
                ORDER BY e.date_event DESC
                LIMIT 5
            """, (league_id,))
            print("\n   Sample recent matches:")
            for row in cursor.fetchall():
                match_id, date_event, home_team, home_score, away_team, away_score = row
                print(f"     - {date_event}: {home_team} {home_score} - {away_score} {away_team} (ID: {match_id})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking league data: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_news_service(db_path, league_id):
    """Test the news service directly"""
    print("\n" + "="*80)
    print("TESTING NEWS SERVICE".center(80))
    print("="*80 + "\n")
    
    try:
        from prediction.news_service import NewsService
        
        print(f"Initializing NewsService with db_path: {db_path}")
        news_service = NewsService(db_path=db_path)
        
        print(f"\nCalling get_news_feed with league_id={league_id}...")
        news_items = news_service.get_news_feed(
            user_id=None,
            followed_teams=None,
            followed_leagues=None,
            league_id=league_id,
            limit=20
        )
        
        print(f"✅ get_news_feed returned {len(news_items)} items")
        
        if len(news_items) > 0:
            print("\n   Sample news items:")
            for i, item in enumerate(news_items[:5], 1):
                print(f"     {i}. [{item.type}] {item.title[:60]}...")
                print(f"        League ID: {item.league_id}, Match ID: {item.match_id}")
        else:
            print("\n❌ No news items returned!")
            print("   This suggests the news service queries are not finding matches.")
        
        return len(news_items)
        
    except Exception as e:
        print(f"❌ News service test failed: {e}")
        import traceback
        traceback.print_exc()
        return 0

def check_all_leagues_with_news(db_path):
    """Check which leagues have news"""
    print("\n" + "="*80)
    print("LEAGUES WITH NEWS (Next 7 days or Last 7 days)".center(80))
    print("="*80 + "\n")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get leagues with upcoming matches
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
        
        upcoming_leagues = cursor.fetchall()
        if upcoming_leagues:
            print("📅 Upcoming matches (next 7 days):")
            for league_id, count in upcoming_leagues:
                print(f"   League {league_id}: {count} matches")
        else:
            print("❌ No upcoming matches found")
        
        # Get leagues with recent matches
        cursor.execute("""
            SELECT e.league_id, COUNT(*) as count
            FROM event e
            WHERE e.date_event >= date('now', '-7 days')
            AND e.date_event < date('now')
            AND e.home_score IS NOT NULL 
            AND e.away_score IS NOT NULL
            AND e.home_team_id IS NOT NULL 
            AND e.away_team_id IS NOT NULL
            GROUP BY e.league_id
            ORDER BY count DESC
        """)
        
        recent_leagues = cursor.fetchall()
        if recent_leagues:
            print("\n📊 Recent matches (last 7 days):")
            for league_id, count in recent_leagues:
                print(f"   League {league_id}: {count} matches")
        else:
            print("\n❌ No recent matches found")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking leagues: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main debug function"""
    print("\n" + "="*80)
    print("NEWS FEED DEBUG SCRIPT".center(80))
    print("="*80)
    
    # Find database
    db_path = find_database()
    if not db_path:
        print("\n❌ Cannot proceed without database file!")
        return
    
    # Test database connection
    if not test_database_connection(db_path):
        print("\n❌ Database connection test failed!")
        return
    
    # Check all leagues with news
    check_all_leagues_with_news(db_path)
    
    # Test specific league (4414 - English Premiership)
    league_id = 4414
    if check_league_data(db_path, league_id):
        # Test news service
        news_count = test_news_service(db_path, league_id)
        
        if news_count == 0:
            print("\n" + "="*80)
            print("DIAGNOSIS".center(80))
            print("="*80 + "\n")
            print("❌ News service returned 0 items even though league has matches.")
            print("\nPossible causes:")
            print("  1. News service queries might be too restrictive")
            print("  2. Team names/logos might be missing (causing failures)")
            print("  3. Date filtering might be incorrect")
            print("  4. News service might be catching exceptions silently")
            print("\nNext steps:")
            print("  - Check Firebase Functions logs for errors")
            print("  - Verify database path in Firebase Functions")
            print("  - Check if news_service.py is catching exceptions")
    
    print("\n" + "="*80)
    print("DEBUG COMPLETE".center(80))
    print("="*80 + "\n")

if __name__ == "__main__":
    main()

