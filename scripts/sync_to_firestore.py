#!/usr/bin/env python3
"""
Automated Firestore Sync Script
Syncs SQLite database to Firestore, excluding duplicates and only adding new/updated matches
Designed to run automatically after daily game updates
"""

import sqlite3
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
import logging

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('firestore_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_existing_match_ids(firestore_db: Any, batch_size: int = 1000) -> Set[str]:
    """
    Get all existing match IDs from Firestore to avoid duplicates
    Uses pagination to handle large collections efficiently
    """
    logger.info("Fetching existing match IDs from Firestore...")
    existing_ids = set()
    
    try:
        matches_ref = firestore_db.collection('matches')
        docs = matches_ref.limit(batch_size).stream()
        
        count = 0
        last_doc = None
        
        while True:
            batch_ids = []
            for doc in docs:
                existing_ids.add(doc.id)
                batch_ids.append(doc.id)
                last_doc = doc
                count += 1
            
            if len(batch_ids) < batch_size:
                break
            
            # Get next batch starting after last document
            if last_doc:
                docs = matches_ref.limit(batch_size).start_after(last_doc).stream()
            else:
                break
        
        logger.info(f"Found {len(existing_ids)} existing matches in Firestore")
        return existing_ids
        
    except Exception as e:
        logger.error(f"Error fetching existing match IDs: {e}")
        return set()


def get_existing_team_ids(firestore_db: Any) -> Set[int]:
    """Get all existing team IDs from Firestore"""
    logger.info("Fetching existing team IDs from Firestore...")
    existing_ids = set()
    
    try:
        teams_ref = firestore_db.collection('teams')
        for doc in teams_ref.stream():
            data = doc.to_dict()
            if 'id' in data:
                existing_ids.add(data['id'])
        
        logger.info(f"Found {len(existing_ids)} existing teams in Firestore")
        return existing_ids
        
    except Exception as e:
        logger.error(f"Error fetching existing team IDs: {e}")
        return set()


def sync_teams(sqlite_conn: sqlite3.Connection, firestore_db: Any, existing_team_ids: Set[int]) -> int:
    """Sync teams from SQLite to Firestore, skipping existing ones"""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM team")
    teams = cursor.fetchall()
    
    columns = [description[0] for description in cursor.description]
    synced = 0
    skipped = 0
    
    batch = firestore_db.batch()
    batch_count = 0
    max_batch_size = 500
    
    for row in teams:
        team_data = dict(zip(columns, row))
        team_id = team_data['id']
        
        # Skip if already exists
        if team_id in existing_team_ids:
            skipped += 1
            continue
        
        team_id_str = str(team_id)
        firestore_data = {
            'id': team_id,
            'name': team_data.get('name', ''),
            'sport': team_data.get('sport', 'Rugby'),
            'alternate_name': team_data.get('alternate_name'),
            'country': team_data.get('country'),
            'formed_year': team_data.get('formed_year'),
            'gender': team_data.get('gender'),
            'synced_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
        }
        
        # Remove None values
        firestore_data = {k: v for k, v in firestore_data.items() if v is not None}
        
        ref = firestore_db.collection('teams').document(team_id_str)
        batch.set(ref, firestore_data)
        batch_count += 1
        synced += 1
        
        if batch_count >= max_batch_size:
            batch.commit()
            batch = firestore_db.batch()
            batch_count = 0
            logger.info(f"  Synced {synced} teams...")
    
    if batch_count > 0:
        batch.commit()
    
    logger.info(f"✅ Teams: {synced} synced, {skipped} already exist")
    return synced


def sync_matches(sqlite_conn: sqlite3.Connection, firestore_db: Any, existing_match_ids: Set[str]) -> Dict[str, int]:
    """
    Sync matches from SQLite to Firestore
    Only syncs new matches or updates existing ones with new scores
    Returns: dict with counts of synced, updated, and skipped matches
    """
    cursor = sqlite_conn.cursor()
    
    # Get all matches from SQLite
    cursor.execute("""
        SELECT 
            e.id,
            e.league_id,
            e.date_event,
            e.home_team_id,
            e.away_team_id,
            e.home_score,
            e.away_score,
            e.season,
            e.round,
            e.venue,
            e.status,
            t1.name as home_team_name,
            t2.name as away_team_name
        FROM event e
        LEFT JOIN team t1 ON e.home_team_id = t1.id
        LEFT JOIN team t2 ON e.away_team_id = t2.id
        ORDER BY e.date_event DESC
    """)
    
    matches = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    
    synced = 0
    updated = 0
    skipped = 0
    
    batch = firestore_db.batch()
    batch_count = 0
    max_batch_size = 500
    
    for row in matches:
        match_data = dict(zip(columns, row))
        event_id = str(match_data['id'])
        
        # Parse date
        date_event = match_data.get('date_event')
        if date_event:
            if isinstance(date_event, str):
                try:
                    date_event = datetime.fromisoformat(date_event.replace('Z', '+00:00'))
                except:
                    try:
                        date_event = datetime.strptime(date_event[:10], '%Y-%m-%d')
                    except:
                        date_event = None
        
        firestore_data = {
            'id': match_data['id'],
            'league_id': match_data.get('league_id'),
            'home_team_id': match_data.get('home_team_id'),
            'away_team_id': match_data.get('away_team_id'),
            'home_team_name': match_data.get('home_team_name'),
            'away_team_name': match_data.get('away_team_name'),
            'date_event': date_event if date_event else match_data.get('date_event'),
            'home_score': match_data.get('home_score'),
            'away_score': match_data.get('away_score'),
            'season': match_data.get('season'),
            'round': match_data.get('round'),
            'venue': match_data.get('venue'),
            'status': match_data.get('status'),
            'synced_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
        }
        
        # Remove None values (except scores which can be None for upcoming matches)
        firestore_data = {k: v for k, v in firestore_data.items() 
                         if v is not None or k in ['home_score', 'away_score']}
        
        ref = firestore_db.collection('matches').document(event_id)
        
        # Check if match already exists
        if event_id in existing_match_ids:
            # Check if we need to update scores
            try:
                existing_doc = ref.get()
                if existing_doc.exists:
                    existing_data = existing_doc.to_dict()
                    existing_home_score = existing_data.get('home_score')
                    existing_away_score = existing_data.get('away_score')
                    new_home_score = firestore_data.get('home_score')
                    new_away_score = firestore_data.get('away_score')
                    
                    # Update if we have new scores (game completed)
                    if (new_home_score is not None and new_away_score is not None and
                        (existing_home_score is None or existing_away_score is None)):
                        batch.update(ref, {
                            'home_score': new_home_score,
                            'away_score': new_away_score,
                            'synced_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                        })
                        updated += 1
                        batch_count += 1
                    else:
                        skipped += 1
                else:
                    # Document doesn't exist, add it
                    batch.set(ref, firestore_data)
                    synced += 1
                    batch_count += 1
            except Exception as e:
                logger.warning(f"Error checking existing match {event_id}: {e}")
                # If check fails, try to add it
                batch.set(ref, firestore_data)
                synced += 1
                batch_count += 1
        else:
            # New match, add it
            batch.set(ref, firestore_data)
            synced += 1
            batch_count += 1
        
        # Commit batch if it reaches max size
        if batch_count >= max_batch_size:
            batch.commit()
            batch = firestore_db.batch()
            batch_count = 0
            logger.info(f"  Synced {synced} new, updated {updated} matches...")
    
    # Commit remaining batch
    if batch_count > 0:
        batch.commit()
    
    return {
        'synced': synced,
        'updated': updated,
        'skipped': skipped
    }


def sync_leagues(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Sync leagues from SQLite to Firestore"""
    try:
        from prediction.config import LEAGUE_MAPPINGS
    except ImportError:
        LEAGUE_MAPPINGS = {}
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM league")
    leagues = cursor.fetchall()
    
    columns = [description[0] for description in cursor.description]
    synced = 0
    
    for row in leagues:
        league_data = dict(zip(columns, row))
        league_id = league_data['id']
        
        # Skip orphaned league 85
        if league_id == 85:
            continue
        
        league_id_str = str(league_id)
        firestore_data = {
            'id': league_id,
            'name': league_data.get('name', ''),
            'sport': league_data.get('sport', 'Rugby'),
            'alternate_name': league_data.get('alternate_name'),
            'country': league_data.get('country'),
            'synced_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
        }
        
        firestore_data = {k: v for k, v in firestore_data.items() if v is not None}
        
        firestore_db.collection('leagues').document(league_id_str).set(firestore_data, merge=True)
        synced += 1
    
    logger.info(f"✅ Leagues: {synced} synced")
    return synced


def main():
    """Main sync function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync SQLite database to Firestore (excludes duplicates)')
    parser.add_argument('--db', default='data.sqlite', help='SQLite database path')
    parser.add_argument('--project-id', default='rugby-ai-61fd0', help='Firebase project ID')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no writes to Firestore)')
    parser.add_argument('--skip-teams', action='store_true', help='Skip teams sync')
    parser.add_argument('--skip-matches', action='store_true', help='Skip matches sync')
    parser.add_argument('--skip-leagues', action='store_true', help='Skip leagues sync')
    
    args = parser.parse_args()
    
    # Connect to SQLite
    if not os.path.exists(args.db):
        logger.error(f"SQLite database not found: {args.db}")
        return 1
    
    sqlite_conn = sqlite3.connect(args.db)
    logger.info(f"✅ Connected to SQLite database: {args.db}")
    
    # Connect to Firestore
    if args.dry_run:
        logger.info("[DRY RUN] No data will be written to Firestore")
        firestore_db = None
    else:
        if not FIRESTORE_AVAILABLE:
            logger.error("google-cloud-firestore is not installed")
            logger.error("Install it with: pip install google-cloud-firestore")
            return 1
        firestore_db = firestore.Client(project=args.project_id)  # type: ignore
        logger.info(f"✅ Connected to Firestore project: {args.project_id}")
    
    logger.info("\n" + "="*60)
    logger.info("Starting Firestore Sync (Duplicate-Aware)")
    logger.info("="*60)
    
    start_time = datetime.now()
    
    # Get existing IDs to avoid duplicates
    if not args.dry_run and not args.skip_matches:
        existing_match_ids = get_existing_match_ids(firestore_db)
    else:
        existing_match_ids = set()
    
    if not args.dry_run and not args.skip_teams:
        existing_team_ids = get_existing_team_ids(firestore_db)
    else:
        existing_team_ids = set()
    
    # Sync data
    total_synced = 0
    total_updated = 0
    
    if not args.skip_leagues:
        logger.info("\n📋 Syncing leagues...")
        synced = sync_leagues(sqlite_conn, firestore_db) if not args.dry_run else 0
        total_synced += synced
    
    if not args.skip_teams:
        logger.info("\n👥 Syncing teams...")
        synced = sync_teams(sqlite_conn, firestore_db, existing_team_ids) if not args.dry_run else 0
        total_synced += synced
    
    if not args.skip_matches:
        logger.info("\n🏉 Syncing matches...")
        results = sync_matches(sqlite_conn, firestore_db, existing_match_ids) if not args.dry_run else {'synced': 0, 'updated': 0, 'skipped': 0}
        total_synced += results['synced']
        total_updated += results['updated']
        logger.info(f"✅ Matches: {results['synced']} new, {results['updated']} updated, {results['skipped']} skipped")
    
    sqlite_conn.close()
    
    duration = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "="*60)
    logger.info("Sync Complete!")
    logger.info(f"   Total synced: {total_synced}")
    logger.info(f"   Total updated: {total_updated}")
    logger.info(f"   Duration: {duration:.1f}s")
    logger.info("="*60)
    
    return 0


if __name__ == "__main__":
    exit(main())

