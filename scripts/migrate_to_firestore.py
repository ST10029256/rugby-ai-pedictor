#!/usr/bin/env python3
"""
Migrate SQLite database to Firestore
Reads from SQLite and writes to Firestore collections
"""

import sqlite3
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from google.cloud import firestore  # type: ignore
    from google.cloud.firestore import SERVER_TIMESTAMP  # type: ignore
    FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None  # type: ignore
    SERVER_TIMESTAMP = None  # type: ignore
    FIRESTORE_AVAILABLE = False

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object"""
    if not date_str:
        return None
    
    # Try different date formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d/%m/%Y',
        '%m/%d/%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19], fmt)
        except (ValueError, IndexError):
            continue
    
    return None


def migrate_leagues(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Migrate leagues from SQLite to Firestore"""
    # Import LEAGUE_MAPPINGS to ensure all leagues are included
    try:
        from prediction.config import LEAGUE_MAPPINGS
    except ImportError:
        LEAGUE_MAPPINGS = {}
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM league")
    leagues = cursor.fetchall()
    
    # Get column names
    columns = [description[0] for description in cursor.description]
    
    # Track which leagues we've migrated
    migrated_ids = set()
    migrated = 0
    
    # First, migrate leagues from SQLite (skip orphaned league 85)
    for row in leagues:
        league_data = dict(zip(columns, row))
        league_id = league_data['id']
        
        # Skip orphaned league 85 (duplicate of 4986, has 0 matches)
        if league_id == 85:
            print(f"  [SKIP] Skipping orphaned league 85 (duplicate of 4986)")
            continue
        
        league_id_str = str(league_id)
        
        # Convert to Firestore format
        firestore_data = {
            'id': league_id,
            'name': league_data.get('name', ''),
            'sport': league_data.get('sport', 'Rugby'),
            'alternate_name': league_data.get('alternate_name'),
            'country': league_data.get('country'),
        }
        
        # Add timestamp if available
        if SERVER_TIMESTAMP is not None:
            firestore_data['migrated_at'] = SERVER_TIMESTAMP
        
        # Remove None values
        firestore_data = {k: v for k, v in firestore_data.items() if v is not None}
        
        firestore_db.collection('leagues').document(league_id_str).set(firestore_data)
        migrated_ids.add(league_id)
        migrated += 1
    
    # Second, add any missing leagues from LEAGUE_MAPPINGS
    for league_id, league_name in LEAGUE_MAPPINGS.items():
        if league_id not in migrated_ids:
            print(f"  [ADD] Adding missing league {league_id}: {league_name}")
            firestore_data = {
                'id': league_id,
                'name': league_name,
                'sport': 'Rugby',
            }
            
            # Add timestamp if available
            if SERVER_TIMESTAMP is not None:
                firestore_data['migrated_at'] = SERVER_TIMESTAMP
            
            firestore_db.collection('leagues').document(str(league_id)).set(firestore_data)
            migrated += 1
    
    return migrated


def migrate_teams(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Migrate teams from SQLite to Firestore"""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM team")
    teams = cursor.fetchall()
    
    # Get column names
    columns = [description[0] for description in cursor.description]
    
    migrated = 0
    batch = firestore_db.batch()
    batch_count = 0
    max_batch_size = 500  # Firestore batch limit
    
    for row in teams:
        team_data = dict(zip(columns, row))
        team_id = str(team_data['id'])
        
        # Convert to Firestore format
        firestore_data = {
            'id': team_data['id'],
            'league_id': team_data.get('league_id'),
            'name': team_data.get('name', ''),
            'short_name': team_data.get('short_name'),
            'alternate_name': team_data.get('alternate_name'),
            'stadium': team_data.get('stadium'),
            'formed_year': team_data.get('formed_year'),
            'country': team_data.get('country'),
            'migrated_at': SERVER_TIMESTAMP
        }
        
        # Remove None values
        firestore_data = {k: v for k, v in firestore_data.items() if v is not None}
        
        ref = firestore_db.collection('teams').document(team_id)
        batch.set(ref, firestore_data)
        batch_count += 1
        migrated += 1
        
        # Commit batch if it reaches max size
        if batch_count >= max_batch_size:
            batch.commit()
            batch = firestore_db.batch()
            batch_count = 0
            print(f"  Migrated {migrated} teams...")
    
    # Commit remaining batch
    if batch_count > 0:
        batch.commit()
    
    return migrated


def migrate_events(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Migrate events (matches) from SQLite to Firestore"""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM event ORDER BY id")
    events = cursor.fetchall()
    
    # Get column names
    columns = [description[0] for description in cursor.description]
    
    migrated = 0
    batch = firestore_db.batch()
    batch_count = 0
    max_batch_size = 500  # Firestore batch limit
    
    for row in events:
        event_data = dict(zip(columns, row))
        event_id = str(event_data['id'])
        
        # Parse date_event to datetime
        date_event = parse_date(event_data.get('date_event'))
        
        # Convert to Firestore format
        firestore_data = {
            'id': event_data['id'],
            'league_id': event_data.get('league_id'),
            'season': event_data.get('season'),
            'date_event': date_event if date_event else event_data.get('date_event'),
            'timestamp': event_data.get('timestamp'),
            'round': event_data.get('round'),
            'home_team_id': event_data.get('home_team_id'),
            'away_team_id': event_data.get('away_team_id'),
            'home_score': event_data.get('home_score'),
            'away_score': event_data.get('away_score'),
            'venue': event_data.get('venue'),
            'status': event_data.get('status'),
            'migrated_at': SERVER_TIMESTAMP
        }
        
        # Remove None values (except for scores which can be None for upcoming matches)
        firestore_data = {k: v for k, v in firestore_data.items() 
                         if v is not None or k in ['home_score', 'away_score']}
        
        ref = firestore_db.collection('matches').document(event_id)
        batch.set(ref, firestore_data)
        batch_count += 1
        migrated += 1
        
        # Commit batch if it reaches max size
        if batch_count >= max_batch_size:
            batch.commit()
            batch = firestore_db.batch()
            batch_count = 0
            print(f"  Migrated {migrated} matches...")
    
    # Commit remaining batch
    if batch_count > 0:
        batch.commit()
    
    return migrated


def migrate_seasons(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Migrate seasons from SQLite to Firestore"""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM season")
    seasons = cursor.fetchall()
    
    # Get column names
    columns = [description[0] for description in cursor.description]
    
    migrated = 0
    for row in seasons:
        season_data = dict(zip(columns, row))
        # Use composite key: league_id_season
        doc_id = f"{season_data['league_id']}_{season_data['season']}"
        
        firestore_data = {
            'league_id': season_data['league_id'],
            'season': season_data['season'],
            'migrated_at': SERVER_TIMESTAMP
        }
        
        firestore_db.collection('seasons').document(doc_id).set(firestore_data)
        migrated += 1
    
    return migrated


def main():
    """Main migration function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate SQLite database to Firestore')
    parser.add_argument('--db', default='data.sqlite', help='SQLite database path')
    parser.add_argument('--project-id', default='rugby-ai-61fd0', help='Firebase project ID')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no writes to Firestore)')
    parser.add_argument('--skip-leagues', action='store_true', help='Skip leagues migration')
    parser.add_argument('--skip-teams', action='store_true', help='Skip teams migration')
    parser.add_argument('--skip-events', action='store_true', help='Skip events migration')
    parser.add_argument('--skip-seasons', action='store_true', help='Skip seasons migration')
    
    args = parser.parse_args()
    
    # Connect to SQLite
    if not os.path.exists(args.db):
        print(f"Error: SQLite database not found: {args.db}")
        return 1
    
    sqlite_conn = sqlite3.connect(args.db)
    print(f"[OK] Connected to SQLite database: {args.db}")
    
    # Connect to Firestore
    if args.dry_run:
        print("[DRY RUN] No data will be written to Firestore")
        firestore_db = None
    else:
        if not FIRESTORE_AVAILABLE:
            print("Error: google-cloud-firestore is not installed")
            print("Install it with: pip install google-cloud-firestore")
            return 1
        firestore_db = firestore.Client(project=args.project_id)  # type: ignore
        print(f"[OK] Connected to Firestore project: {args.project_id}")
    
    print("\n" + "="*60)
    print("Starting Migration")
    print("="*60 + "\n")
    
    total_migrated = 0
    
    # Migrate leagues
    if not args.skip_leagues:
        print("[1/4] Migrating leagues...")
        if args.dry_run:
            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM league")
            count = cursor.fetchone()[0]
            print(f"  Would migrate {count} leagues")
            total_migrated += count
        else:
            count = migrate_leagues(sqlite_conn, firestore_db)
            print(f"  [OK] Migrated {count} leagues")
            total_migrated += count
        print()
    
    # Migrate teams
    if not args.skip_teams:
        print("[2/4] Migrating teams...")
        if args.dry_run:
            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM team")
            count = cursor.fetchone()[0]
            print(f"  Would migrate {count} teams")
            total_migrated += count
        else:
            count = migrate_teams(sqlite_conn, firestore_db)
            print(f"  [OK] Migrated {count} teams")
            total_migrated += count
        print()
    
    # Migrate events (matches)
    if not args.skip_events:
        print("[3/4] Migrating matches...")
        if args.dry_run:
            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM event")
            count = cursor.fetchone()[0]
            print(f"  Would migrate {count} matches")
            total_migrated += count
        else:
            count = migrate_events(sqlite_conn, firestore_db)
            print(f"  [OK] Migrated {count} matches")
            total_migrated += count
        print()
    
    # Migrate seasons
    if not args.skip_seasons:
        print("[4/4] Migrating seasons...")
        if args.dry_run:
            cursor = sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM season")
            count = cursor.fetchone()[0]
            print(f"  Would migrate {count} seasons")
            total_migrated += count
        else:
            count = migrate_seasons(sqlite_conn, firestore_db)
            print(f"  [OK] Migrated {count} seasons")
            total_migrated += count
        print()
    
    sqlite_conn.close()
    
    print("="*60)
    print(f"[OK] Migration complete! Total records: {total_migrated}")
    print("="*60)
    
    if args.dry_run:
        print("\n[INFO] Run without --dry-run to perform actual migration")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

