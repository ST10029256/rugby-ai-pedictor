import sqlite3

def verify_database_state():
    """Verify the current state of the Rugby Championship database."""
    
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    try:
        rugby_champ_id = 4986
        
        # Check total events
        cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ?', (rugby_champ_id,))
        total = cursor.fetchone()[0]
        print(f'Total Rugby Championship events: {total}')
        
        # Check for unwanted October games
        cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ? AND (date_event LIKE "%10-02%" OR date_event LIKE "%10-09%")', (rugby_champ_id,))
        oct_games = cursor.fetchone()[0]
        print(f'Games on Oct 2nd and 9th: {oct_games}')
        
        # Check for 2024-09-28 games (should be 0 after cleanup)
        cursor.execute('SELECT COUNT(*) FROM event WHERE league_id = ? AND date_event = "2024-09-28"', (rugby_champ_id,))
        sept_28_games = cursor.fetchone()[0]
        print(f'Games on 2024-09-28: {sept_28_games}')
        
        # Show upcoming games
        cursor.execute('''
            SELECT e.date_event, ht.name as home_team, at.name as away_team
            FROM event e
            JOIN team ht ON e.home_team_id = ht.id
            JOIN team at ON e.away_team_id = at.id
            WHERE e.league_id = ? AND e.date_event >= '2025-09-27'
            ORDER BY e.date_event
        ''', (rugby_champ_id,))
        
        upcoming = cursor.fetchall()
        print(f'\nUpcoming games:')
        for game in upcoming:
            print(f'  {game[0]} - {game[1]} vs {game[2]}')
        
        print(f'\nDatabase state verification complete!')
        
    finally:
        conn.close()

if __name__ == "__main__":
    verify_database_state()
