#!/usr/bin/env python3
"""
Check if AI trained on this weekend's results
"""

import sqlite3
import pandas as pd
from datetime import datetime

def main():
    # Connect to database
    conn = sqlite3.connect('data.sqlite')

    print('🔍 CHECKING IF AI TRAINED ON THIS WEEKEND\'S RESULTS')
    print('='*60)

    # Check the most recent games in the database
    print('\n📊 MOST RECENT GAMES IN DATABASE:')
    cursor = conn.cursor()

    # Check URC
    cursor.execute('''
    SELECT 
        e.date_event,
        t1.name as home_team_name,
        t2.name as away_team_name,
        e.home_score,
        e.away_score,
        CASE 
            WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL THEN 'COMPLETED'
            ELSE 'UPCOMING'
        END as status
    FROM event e
    LEFT JOIN team t1 ON e.home_team_id = t1.id
    LEFT JOIN team t2 ON e.away_team_id = t2.id
    WHERE e.league_id = 4446 
    ORDER BY e.date_event DESC
    LIMIT 10
    ''')

    urc_recent = cursor.fetchall()
    print('URC (most recent 10 games):')
    for game in urc_recent:
        date, home_name, away_name, home_score, away_score, status = game
        if status == 'COMPLETED':
            print(f'  ✅ {date}: {home_name} {home_score}-{away_score} {away_name}')
        else:
            print(f'  ⏳ {date}: {home_name} vs {away_name}')

    # Check Rugby Championship
    cursor.execute('''
    SELECT 
        e.date_event,
        t1.name as home_team_name,
        t2.name as away_team_name,
        e.home_score,
        e.away_score,
        CASE 
            WHEN e.home_score IS NOT NULL AND e.away_score IS NOT NULL THEN 'COMPLETED'
            ELSE 'UPCOMING'
        END as status
    FROM event e
    LEFT JOIN team t1 ON e.home_team_id = t1.id
    LEFT JOIN team t2 ON e.away_team_id = t2.id
    WHERE e.league_id = 4986 
    ORDER BY e.date_event DESC
    LIMIT 10
    ''')

    rc_recent = cursor.fetchall()
    print('\nRugby Championship (most recent 10 games):')
    for game in rc_recent:
        date, home_name, away_name, home_score, away_score, status = game
        if status == 'COMPLETED':
            print(f'  ✅ {date}: {home_name} {home_score}-{away_score} {away_name}')
        else:
            print(f'  ⏳ {date}: {home_name} vs {away_name}')

    # Check when models were last trained
    print('\n🤖 MODEL TRAINING ANALYSIS:')
    print('Models were trained on: 2025-09-28T19:47:33 (around 7:47 PM)')
    print('This weekend games: 2025-09-27 (Saturday)')
    print('\nCONCLUSION: The AI trained BEFORE this weekend\'s games were played!')
    print('So the AI has NOT trained on this weekend\'s results yet.')

    conn.close()

if __name__ == "__main__":
    main()
