#!/usr/bin/env python3
"""
Check if AI trained on this weekend's results
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import json

def main():
    # Connect to database
    conn = sqlite3.connect('data.sqlite')

    # Get this weekend's date range (Saturday-Sunday)
    today = datetime.now()
    days_since_saturday = (today.weekday() + 2) % 7  # Saturday is weekday 5
    this_saturday = today - timedelta(days=days_since_saturday)
    this_sunday = this_saturday + timedelta(days=1)

    print(f'This weekend: {this_saturday.strftime("%Y-%m-%d")} to {this_sunday.strftime("%Y-%m-%d")}')

    # Check for URC games (league_id = 4446)
    print('\n🏉 URC GAMES THIS WEEKEND:')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT 
        e.id,
        e.date_event,
        e.home_team_id,
        e.away_team_id,
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
    AND e.date_event BETWEEN ? AND ?
    ORDER BY e.date_event, e.id
    ''', (this_saturday.strftime('%Y-%m-%d'), this_sunday.strftime('%Y-%m-%d')))

    urc_games = cursor.fetchall()
    print(f'Found {len(urc_games)} URC games this weekend:')
    for game in urc_games:
        game_id, date, home_id, away_id, home_name, away_name, home_score, away_score, status = game
        if status == 'COMPLETED':
            print(f'  ✅ {home_name} {home_score}-{away_score} {away_name} ({date})')
        else:
            print(f'  ⏳ {home_name} vs {away_name} ({date})')

    # Check for Rugby Championship games (league_id = 4986)
    print('\n🏆 RUGBY CHAMPIONSHIP GAMES THIS WEEKEND:')
    cursor.execute('''
    SELECT 
        e.id,
        e.date_event,
        e.home_team_id,
        e.away_team_id,
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
    AND e.date_event BETWEEN ? AND ?
    ORDER BY e.date_event, e.id
    ''', (this_saturday.strftime('%Y-%m-%d'), this_sunday.strftime('%Y-%m-%d')))

    rc_games = cursor.fetchall()
    print(f'Found {len(rc_games)} Rugby Championship games this weekend:')
    for game in rc_games:
        game_id, date, home_id, away_id, home_name, away_name, home_score, away_score, status = game
        if status == 'COMPLETED':
            print(f'  ✅ {home_name} {home_score}-{away_score} {away_name} ({date})')
        else:
            print(f'  ⏳ {home_name} vs {away_name} ({date})')

    # Check model training dates
    print('\n🤖 MODEL TRAINING DATES:')
    try:
        with open('artifacts/model_registry.json', 'r') as f:
            registry = json.load(f)
        
        for league_id, info in registry.get('leagues', {}).items():
            league_name = info.get('name', f'League {league_id}')
            trained_at = info.get('trained_at', 'Unknown')
            training_games = info.get('training_games', 0)
            print(f'  {league_name}: Trained at {trained_at} ({training_games} games)')
    except Exception as e:
        print(f'  Could not load model registry: {e}')

    # Check last checkpoint
    print('\n📅 LAST CHECKPOINT:')
    try:
        with open('last_checkpoint.json', 'r') as f:
            checkpoint = json.load(f)
        last_check = checkpoint.get('last_check', 'Unknown')
        print(f'  Last check: {last_check}')
    except Exception as e:
        print(f'  Could not load checkpoint: {e}')

    conn.close()

if __name__ == "__main__":
    main()
