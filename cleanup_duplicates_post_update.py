#!/usr/bin/env python3
"""Post-update duplicate cleanup - run after enhanced_auto_update.py"""

import sqlite3
import sys

def cleanup_duplicates(db_path='data.sqlite'):
    """Remove any duplicates that might have been created"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Running post-update duplicate cleanup...")
    
    # Find duplicates (same league, date, teams)
    cursor.execute("""
        SELECT 
            league_id,
            DATE(date_event),
            home_team_id,
            away_team_id,
            COUNT(*) as count,
            GROUP_CONCAT(id) as ids
        FROM event
        GROUP BY league_id, DATE(date_event), home_team_id, away_team_id
        HAVING COUNT(*) > 1
    """)
    
    duplicates = cursor.fetchall()
    deleted = 0
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate games - removing...")
        for dup in duplicates:
            ids = dup[5].split(',')
            # Keep first, delete rest
            for del_id in ids[1:]:
                cursor.execute("DELETE FROM event WHERE id = ?", (del_id,))
                deleted += 1
        
        conn.commit()
        print(f"Removed {deleted} duplicate events")
    else:
        print("No duplicates found - database is clean")
    
    conn.close()
    return deleted

if __name__ == "__main__":
    deleted = cleanup_duplicates()
    sys.exit(0 if deleted == 0 else 1)  # Exit with error if duplicates were found

