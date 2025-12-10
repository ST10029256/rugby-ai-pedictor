#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick script to check what data exists for league 5479"""

import sqlite3
import os
from pathlib import Path

# Find database
db_path = Path(__file__).parent.parent / 'data.sqlite'
if not db_path.exists():
    db_path = Path(__file__).parent.parent / 'rugby-ai-predictor' / 'data.sqlite'

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check total events
cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = 5479")
total_events = cursor.fetchone()[0]
print(f"📊 Total events for league 5479: {total_events}")

# Check events with scores
cursor.execute("""
    SELECT COUNT(*) FROM event 
    WHERE league_id = 5479 
    AND home_score IS NOT NULL 
    AND away_score IS NOT NULL
""")
events_with_scores = cursor.fetchone()[0]
print(f"📊 Events with both scores: {events_with_scores}")

# Check events by status
cursor.execute("""
    SELECT status, COUNT(*) as count 
    FROM event 
    WHERE league_id = 5479 
    GROUP BY status
""")
status_counts = cursor.fetchall()
print(f"\n📊 Events by status:")
for status, count in status_counts:
    print(f"   {status or 'NULL'}: {count}")

# Check events with NULL scores
cursor.execute("""
    SELECT COUNT(*) FROM event 
    WHERE league_id = 5479 
    AND (home_score IS NULL OR away_score IS NULL)
""")
events_without_scores = cursor.fetchone()[0]
print(f"\n📊 Events without complete scores: {events_without_scores}")

# Sample a few events
cursor.execute("""
    SELECT id, date_event, home_score, away_score, status 
    FROM event 
    WHERE league_id = 5479 
    ORDER BY date_event DESC 
    LIMIT 10
""")
sample_events = cursor.fetchall()
print(f"\n📊 Sample events (last 10):")
for event_id, date, home_score, away_score, status in sample_events:
    print(f"   ID {event_id}: {date} | Score: {home_score}-{away_score} | Status: {status or 'NULL'}")

conn.close()

