#!/usr/bin/env python3
"""Check URC upcoming games in database and Firestore"""

import sqlite3
from datetime import datetime, timedelta

# Check SQLite database
print("=" * 60)
print("Checking SQLite Database for URC Games")
print("=" * 60)

try:
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    # Check if event table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\nTables in database: {tables}")
    
    if 'event' in tables:
        today = datetime.now().date()
        future_date = today + timedelta(days=30)
        
        # Count upcoming URC games
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = 4446 
            AND date_event >= ? 
            AND date_event <= ? 
            AND (home_score IS NULL OR away_score IS NULL)
        """, (str(today), str(future_date)))
        count = cursor.fetchone()[0]
        print(f"\nURC upcoming games (next 30 days): {count}")
        
        # Get sample matches
        cursor.execute("""
            SELECT e.id, e.date_event, t1.name, t2.name, e.home_score, e.away_score 
            FROM event e 
            LEFT JOIN team t1 ON e.home_team_id = t1.id 
            LEFT JOIN team t2 ON e.away_team_id = t2.id 
            WHERE e.league_id = 4446 
            AND e.date_event >= ? 
            AND e.date_event <= ? 
            ORDER BY e.date_event 
            LIMIT 10
        """, (str(today), str(future_date)))
        matches = cursor.fetchall()
        
        print(f"\nSample URC matches (next 30 days):")
        if matches:
            for m in matches:
                score_str = f"{m[4]}-{m[5]}" if m[4] is not None and m[5] is not None else "TBD"
                print(f"  {m[1]} - {m[2]} vs {m[3]} (score: {score_str})")
        else:
            print("  No matches found")
        
        # Check total URC games
        cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = 4446")
        total_urc = cursor.fetchone()[0]
        print(f"\nTotal URC games in database: {total_urc}")
        
        # Check recent URC games (past 7 days)
        past_date = today - timedelta(days=7)
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = 4446 
            AND date_event >= ? 
            AND date_event <= ?
        """, (str(past_date), str(today)))
        recent_count = cursor.fetchone()[0]
        print(f"URC games in past 7 days: {recent_count}")
        
    else:
        print("\n❌ 'event' table not found in database")
    
    conn.close()
    
except Exception as e:
    print(f"\n❌ Error checking database: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Checking if URC games are being fetched from API")
print("=" * 60)

# Check the enhanced_auto_update script
try:
    with open('scripts/enhanced_auto_update.py', 'r') as f:
        content = f.read()
        
        if '4446' in content and 'United Rugby Championship' in content:
            print("✅ URC (4446) is configured in enhanced_auto_update.py")
        else:
            print("❌ URC (4446) not found in enhanced_auto_update.py")
        
        # Check if manual fixtures function exists
        if 'get_manual_urc_fixtures' in content or 'manual URC fixtures' in content:
            print("✅ Manual URC fixtures function exists")
        else:
            print("❌ Manual URC fixtures function not found")
            
        # Check if it's being called
        if 'detect_and_add_missing_games' in content:
            print("✅ detect_and_add_missing_games function exists")
            # Check if URC has empty list
            if '4446: []' in content:
                print("⚠️  WARNING: URC (4446) has empty list in missing_games_map - no manual games will be added")
        
except Exception as e:
    print(f"❌ Error checking script: {e}")
