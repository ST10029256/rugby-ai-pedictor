#!/usr/bin/env python3
import sqlite3
from datetime import datetime

def remove_manual_games():
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    print("Removing all manual/fake games from database...")
    
    # Find and remove games that don't have proper API data (venue, status, etc.)
    cursor.execute("""
        SELECT e.id, e.date_event, t1.name as home_team, t2.name as away_team, e.league_id
        FROM event e 
        LEFT JOIN team t1 ON e.home_team_id = t1.id 
        LEFT JOIN team t2 ON e.away_team_id = t2.id 
        WHERE (e.home_score IS NULL OR e.away_score IS NULL) 
        AND e.league_id IN (4414, 4430, 4446)
        AND (e.venue IS NULL OR e.venue = '' OR e.status IS NULL OR e.status = '')
        AND e.date_event >= '2025-10-20'
    """)
    
    manual_games = cursor.fetchall()
    
    if manual_games:
        print(f"Found {len(manual_games)} manual games to remove:")
        for game in manual_games:
            print(f"  - League {game[4]}: {game[1]} - {game[2]} vs {game[3]}")
        
        # Remove them
        cursor.execute("""
            DELETE FROM event 
            WHERE id IN ({})
        """.format(','.join(['?' for _ in manual_games])), [game[0] for game in manual_games])
        
        conn.commit()
        print(f"Removed {len(manual_games)} manual games")
    else:
        print("No manual games found to remove")
    
    # Check remaining games
    cursor.execute("""
        SELECT e.date_event, t1.name as home_team, t2.name as away_team, e.league_id, e.venue, e.status
        FROM event e 
        LEFT JOIN team t1 ON e.home_team_id = t1.id 
        LEFT JOIN team t2 ON e.away_team_id = t2.id 
        WHERE (e.home_score IS NULL OR e.away_score IS NULL) 
        AND e.league_id IN (4414, 4430, 4446)
        AND e.date_event >= '2025-10-20'
        AND e.date_event <= '2025-10-26'
        ORDER BY e.date_event
    """)
    
    remaining_games = cursor.fetchall()
    
    print(f"\nRemaining REAL games this week (Oct 20-26, 2025):")
    print("=" * 60)
    
    for game in remaining_games:
        date, home, away, league, venue, status = game
        print(f"League {league}: {date} - {home} vs {away}")
        if venue and status:
            print(f"  Venue: {venue}, Status: {status}")
    
    print(f"\nTotal REAL games this week: {len(remaining_games)}")
    
    conn.close()

if __name__ == "__main__":
    remove_manual_games()
