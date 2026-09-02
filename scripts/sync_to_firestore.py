#!/usr/bin/env python3
"""
Automated Firestore Sync Script
Syncs SQLite database to Firestore, excluding duplicates and only adding new/updated matches
Designed to run automatically after daily game updates
"""

import sqlite3
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Set, Iterable, Callable, TypeVar
import logging

# Windows console can default to cp1252, which throws UnicodeEncodeError for emoji log messages.
# Force UTF-8 where possible so scheduled runs don't spam logging errors.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

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
rugby_predictor_root = os.path.join(project_root, "rugby-ai-predictor")
if rugby_predictor_root not in sys.path:
    sys.path.insert(0, rugby_predictor_root)

from prediction.team_display_names import display_team_name_for_league

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

T = TypeVar("T")


def _configured_league_ids() -> List[int]:
    try:
        from prediction.config import LEAGUE_MAPPINGS
        return list(LEAGUE_MAPPINGS.keys())
    except Exception:
        return [4414, 4430, 4446, 4551, 4574, 4714, 4986, 5069, 5479, 5480]


def _retry_firestore_call(
    operation: Callable[[], T],
    *,
    description: str,
    max_attempts: int = 5,
) -> T:
    """Retry transient Firestore failures without relying on client retry hooks."""
    try:
        from google.api_core import exceptions as gcp_exceptions
        retryable = (gcp_exceptions.ServiceUnavailable, gcp_exceptions.DeadlineExceeded)
    except Exception:
        retryable = (Exception,)

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except retryable as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            wait = min(60, 2 ** attempt)
            logger.warning(
                f"{description} failed (attempt {attempt}/{max_attempts}): {exc}; "
                f"retrying in {wait}s"
            )
            time.sleep(wait)

    assert last_error is not None
    raise last_error


def _stream_query_paginated(query: Any, batch_size: int = 500) -> Iterable[Any]:
    """Yield Firestore query results in small pages to avoid query timeouts."""
    last_doc = None
    while True:
        page_query = query.limit(batch_size)
        if last_doc is not None:
            page_query = page_query.start_after(last_doc)

        docs = _retry_firestore_call(
            lambda: list(page_query.stream()),
            description="Firestore paginated query",
        )
        if not docs:
            break

        for doc in docs:
            yield doc

        if len(docs) < batch_size:
            break
        last_doc = docs[-1]


def _canonical_match_doc_ids_from_sqlite(sqlite_conn: sqlite3.Connection) -> Set[str]:
    """Return the canonical Firestore doc ids for every live SQLite fixture."""
    canonical_doc_ids: Set[str] = set()
    for event_id, hl_id in sqlite_conn.execute("SELECT id, highlightly_match_id FROM event"):
        try:
            hl_int = int(hl_id) if hl_id is not None else None
        except (TypeError, ValueError):
            hl_int = None
        canonical_doc_ids.add(str(hl_int) if hl_int else str(event_id))
    return canonical_doc_ids


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


def get_existing_teams(firestore_db: Any) -> Dict[int, Dict[str, Any]]:
    """Fetch existing team documents, keyed by id."""
    logger.info("Fetching existing teams from Firestore...")
    existing: Dict[int, Dict[str, Any]] = {}

    try:
        teams_ref = firestore_db.collection('teams')
        for doc in teams_ref.stream():
            data = doc.to_dict() or {}
            if 'id' in data:
                existing[data['id']] = data

        logger.info(f"Found {len(existing)} existing teams in Firestore")
        return existing

    except Exception as e:
        logger.error(f"Error fetching existing teams: {e}")
        return {}


def sync_teams(
    sqlite_conn: sqlite3.Connection,
    firestore_db: Any,
    existing_teams: Dict[int, Dict[str, Any]],
) -> int:
    """Sync teams from SQLite to Firestore.

    Existing documents are refreshed when the source row has changed, so
    corrections such as Currie Cup "Bulls" becoming "Blue Bulls" reach the app
    instead of being skipped forever.
    """
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM team")
    teams = cursor.fetchall()
    
    columns = [description[0] for description in cursor.description]
    synced = 0
    updated = 0
    skipped = 0
    
    batch = firestore_db.batch()
    batch_count = 0
    max_batch_size = 500
    
    for row in teams:
        team_data = dict(zip(columns, row))
        team_id = team_data['id']

        existing = existing_teams.get(team_id)
        if existing is not None:
            changed = any(
                existing.get(field) != team_data.get(field)
                for field in ('name', 'league_id', 'alternate_name', 'country')
                if team_data.get(field) is not None
            )
            if not changed:
                skipped += 1
                continue
            updated += 1

        team_id_str = str(team_id)
        firestore_data = {
            'id': team_id,
            'name': team_data.get('name', ''),
            'league_id': team_data.get('league_id'),
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
    
    logger.info(
        f"✅ Teams: {synced} written ({updated} refreshed, {synced - updated} new), "
        f"{skipped} unchanged"
    )
    return synced


def sync_matches(sqlite_conn: sqlite3.Connection, firestore_db: Any, existing_match_ids: Set[str]) -> Dict[str, int]:
    """
    Sync matches from SQLite to Firestore
    Only syncs new matches or updates existing ones with new scores
    Returns: dict with counts of synced, updated, and skipped matches
    """
    cursor = sqlite_conn.cursor()

    try:
        from prediction.highlightly_leagues import ensure_highlightly_match_id_column
        ensure_highlightly_match_id_column(sqlite_conn)
    except Exception:
        pass

    # Shared bookmaker odds, refreshed hourly by scripts/refresh_match_odds.py.
    # Carrying them on the fixture means the app can prefill the odds boxes from
    # data it already has, instead of every viewer firing one odds request per
    # fixture on screen.
    odds_by_match: Dict[int, Dict[str, Any]] = {}
    try:
        for row in sqlite_conn.execute(
            """
            SELECT match_id, home_odds, away_odds, bookmaker_count, fetched_at
            FROM match_odds WHERE bookmaker_count > 0
            """
        ):
            odds_by_match[int(row[0])] = {
                'odds_home': row[1],
                'odds_away': row[2],
                'odds_bookmaker_count': row[3],
                'odds_fetched_at': row[4],
            }
    except sqlite3.OperationalError:
        # Table appears the first time the odds refresh runs.
        pass

    # Get all matches from SQLite
    cursor.execute("""
        SELECT 
            e.id,
            e.league_id,
            e.date_event,
            e.timestamp,
            e.home_team_id,
            e.away_team_id,
            e.home_score,
            e.away_score,
            e.season,
            e.round,
            e.venue,
            e.status,
            e.highlightly_match_id,
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
        hl_match_id = match_data.get('highlightly_match_id')
        try:
            hl_match_id_int = int(hl_match_id) if hl_match_id is not None else None
        except (TypeError, ValueError):
            hl_match_id_int = None
        # Prefer Highlightly IDs as document keys to avoid collisions with unrelated
        # local autoincrement event IDs already present in Firestore.
        doc_id = str(hl_match_id_int) if hl_match_id_int else event_id
        
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
        
        timestamp_raw = match_data.get('timestamp')
        kickoff_iso = None
        if timestamp_raw:
            try:
                from prediction.kickoff_times import normalize_kickoff_iso, has_meaningful_kickoff_time

                if has_meaningful_kickoff_time(timestamp_raw):
                    kickoff_iso = normalize_kickoff_iso(timestamp_raw)
            except Exception:
                kickoff_iso = str(timestamp_raw) if timestamp_raw else None

        firestore_data = {
            'id': hl_match_id_int or match_data['id'],
            'league_id': match_data.get('league_id'),
            'home_team_id': match_data.get('home_team_id'),
            'away_team_id': match_data.get('away_team_id'),
            'home_team_name': display_team_name_for_league(
                match_data.get('home_team_name'), match_data.get('league_id')
            ),
            'away_team_name': display_team_name_for_league(
                match_data.get('away_team_name'), match_data.get('league_id')
            ),
            'date_event': date_event if date_event else match_data.get('date_event'),
            'timestamp': kickoff_iso or timestamp_raw,
            'kickoff_at': kickoff_iso,
            'home_score': match_data.get('home_score'),
            'away_score': match_data.get('away_score'),
            'season': match_data.get('season'),
            'round': match_data.get('round'),
            'venue': match_data.get('venue'),
            'status': match_data.get('status'),
            'highlightly_match_id': hl_match_id_int or match_data.get('highlightly_match_id'),
            'sqlite_event_id': match_data['id'],
            'synced_at': SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
        }
        firestore_data.update(odds_by_match.get(int(match_data['id']), {}))

        # Remove None values (except scores which can be None for upcoming matches)
        firestore_data = {k: v for k, v in firestore_data.items() 
                         if v is not None or k in ['home_score', 'away_score']}
        
        ref = firestore_db.collection('matches').document(doc_id)
        
        # Check if match already exists
        if doc_id in existing_match_ids:
            # Check if we need to update scores / kickoffs
            try:
                existing_doc = ref.get()
                if existing_doc.exists:
                    existing_data = existing_doc.to_dict() or {}
                    # Never overwrite an unrelated fixture that happens to share a local id.
                    existing_league = existing_data.get('league_id')
                    new_league = firestore_data.get('league_id')
                    if (
                        existing_league is not None
                        and new_league is not None
                        and int(existing_league) != int(new_league)
                        and not hl_match_id_int
                    ):
                        skipped += 1
                        continue

                    existing_home_score = existing_data.get('home_score')
                    existing_away_score = existing_data.get('away_score')
                    new_home_score = firestore_data.get('home_score')
                    new_away_score = firestore_data.get('away_score')
                    
                    # Update if we have new scores (game completed) and/or better kickoff times.
                    patch = {}
                    if (new_home_score is not None and new_away_score is not None and
                        (existing_home_score is None or existing_away_score is None)):
                        patch['home_score'] = new_home_score
                        patch['away_score'] = new_away_score

                    new_kickoff = firestore_data.get('kickoff_at') or firestore_data.get('timestamp')
                    existing_kickoff = existing_data.get('kickoff_at') or existing_data.get('timestamp')
                    try:
                        from prediction.kickoff_times import has_meaningful_kickoff_time
                        new_has_time = has_meaningful_kickoff_time(new_kickoff)
                        existing_has_time = has_meaningful_kickoff_time(existing_kickoff)
                    except Exception:
                        new_has_time = bool(new_kickoff)
                        existing_has_time = bool(existing_kickoff)
                    if new_has_time and (not existing_has_time or str(new_kickoff) != str(existing_kickoff)):
                        if firestore_data.get('kickoff_at'):
                            patch['kickoff_at'] = firestore_data['kickoff_at']
                        if firestore_data.get('timestamp'):
                            patch['timestamp'] = firestore_data['timestamp']
                        if firestore_data.get('date_event') is not None:
                            patch['date_event'] = firestore_data['date_event']

                    # Keep team/league metadata aligned when this is clearly the same
                    # fixture. Odds are included because they are refreshed hourly and
                    # the app reads them straight off the fixture.
                    for key in (
                        'home_team_name',
                        'away_team_name',
                        'home_team_id',
                        'away_team_id',
                        'league_id',
                        'highlightly_match_id',
                        'sqlite_event_id',
                        'odds_home',
                        'odds_away',
                        'odds_bookmaker_count',
                        'odds_fetched_at',
                    ):
                        if firestore_data.get(key) is not None and existing_data.get(key) != firestore_data.get(key):
                            patch[key] = firestore_data[key]

                    if patch:
                        patch['synced_at'] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
                        batch.update(ref, patch)
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
                logger.warning(f"Error checking existing match {doc_id}: {e}")
                # If check fails, try to add it
                batch.set(ref, firestore_data)
                synced += 1
                batch_count += 1
        else:
            # New match, add it
            batch.set(ref, firestore_data)
            synced += 1
            batch_count += 1
            existing_match_ids.add(doc_id)

        # If we wrote under Highlightly id, remove any leftover sqlite-id clone doc
        # so nightly sync cannot leave duplicate fixtures in the app.
        if hl_match_id_int and event_id != doc_id and event_id in existing_match_ids:
            clone_ref = firestore_db.collection('matches').document(event_id)
            try:
                clone_doc = clone_ref.get()
                if clone_doc.exists:
                    clone_data = clone_doc.to_dict() or {}
                    clone_hl = clone_data.get('highlightly_match_id')
                    same_fixture = (
                        str(clone_hl) == str(hl_match_id_int)
                        or (
                            clone_data.get('league_id') == firestore_data.get('league_id')
                            and str(clone_data.get('home_team_name') or '').lower()
                            == str(firestore_data.get('home_team_name') or '').lower()
                            and str(clone_data.get('away_team_name') or '').lower()
                            == str(firestore_data.get('away_team_name') or '').lower()
                        )
                    )
                    if same_fixture:
                        batch.delete(clone_ref)
                        batch_count += 1
                        existing_match_ids.discard(event_id)
                        logger.info(f"Pruned sqlite-id clone match doc {event_id} (canonical {doc_id})")
            except Exception as prune_err:
                logger.debug(f"Clone prune skipped for {event_id}: {prune_err}")
        
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


def prune_orphaned_matches(
    sqlite_conn: sqlite3.Connection,
    firestore_db: Any,
    existing_match_ids: Optional[Set[str]] = None,
) -> int:
    """Delete match docs whose SQLite fixture is gone.

    Deduplication removes fixtures from SQLite, but the documents this script
    previously wrote for them stay behind and show up as duplicate matches in
    the app. Only docs carrying a `sqlite_event_id` are considered, so records
    created by anything other than this sync are left alone.
    """
    live_event_ids = {
        int(r[0]) for r in sqlite_conn.execute("SELECT id FROM event")
    }
    if not live_event_ids:
        logger.warning("SQLite has no events; skipping orphan prune")
        return 0

    canonical_doc_ids = _canonical_match_doc_ids_from_sqlite(sqlite_conn)
    deleted = 0
    batch = firestore_db.batch()
    batch_count = 0

    def maybe_delete_orphan(doc: Any) -> None:
        nonlocal deleted, batch, batch_count
        data = doc.to_dict() or {}
        raw = data.get('sqlite_event_id')
        if raw is None:
            return
        try:
            event_id = int(raw)
        except (TypeError, ValueError):
            return
        if event_id in live_event_ids:
            return

        batch.delete(doc.reference)
        batch_count += 1
        deleted += 1
        if batch_count >= 400:
            batch.commit()
            batch = firestore_db.batch()
            batch_count = 0
            logger.info(f"  Pruned {deleted} orphaned match docs...")

    if existing_match_ids is not None:
        # Fast path: only inspect Firestore docs that are no longer canonical.
        # This avoids streaming the entire 200k+ match collection in one query.
        candidates = sorted(doc_id for doc_id in existing_match_ids if doc_id not in canonical_doc_ids)
        logger.info(f"Checking {len(candidates)} non-canonical Firestore match docs for orphans...")

        matches_ref = firestore_db.collection('matches')
        for start in range(0, len(candidates), 500):
            refs = [matches_ref.document(doc_id) for doc_id in candidates[start:start + 500]]
            docs = _retry_firestore_call(
                lambda refs=refs: list(firestore_db.get_all(refs)),
                description="Firestore orphan candidate lookup",
            )
            for doc in docs:
                if doc.exists:
                    maybe_delete_orphan(doc)
    else:
        # Fallback when we do not already have the Firestore id set in memory.
        logger.info("No cached Firestore match ids; scanning configured leagues in pages...")
        for league_id in _configured_league_ids():
            query = firestore_db.collection('matches').where('league_id', '==', int(league_id))
            scanned = 0
            for doc in _stream_query_paginated(query):
                scanned += 1
                maybe_delete_orphan(doc)
            if scanned:
                logger.info(f"  Scanned {scanned} match docs for league {league_id}")

    if batch_count > 0:
        batch.commit()

    logger.info(f"✅ Orphaned matches: {deleted} deleted")
    return deleted


def prune_upcoming_firestore_clones(firestore_db: Any, days_back: int = 2, days_ahead: int = 180) -> int:
    """Delete upcoming non-canonical match docs (doc id != highlightly_match_id)."""
    from datetime import timedelta, timezone as tz

    try:
        from prediction.config import LEAGUE_MAPPINGS
        league_ids = list(LEAGUE_MAPPINGS.keys())
    except Exception:
        league_ids = [4414, 4430, 4446, 4551, 4574, 4714, 4986, 5069, 5479, 5480]

    now = datetime.now(tz.utc)
    start = now - timedelta(days=days_back)
    end = now + timedelta(days=days_ahead)
    deleted = 0
    batch = firestore_db.batch()
    batch_count = 0

    for league_id in league_ids:
        try:
            docs = list(
                firestore_db.collection('matches')
                .where('league_id', '==', int(league_id))
                .where('date_event', '>=', start)
                .where('date_event', '<=', end)
                .stream()
            )
        except Exception as exc:
            logger.warning(f"Clone prune query failed for league {league_id}: {exc}")
            continue

        by_hl: Dict[str, list] = {}
        for doc in docs:
            data = doc.to_dict() or {}
            hl = data.get('highlightly_match_id')
            try:
                hl_s = str(int(hl)) if hl is not None else ''
            except (TypeError, ValueError):
                hl_s = ''
            if not hl_s:
                continue
            by_hl.setdefault(hl_s, []).append(doc)

        for hl_s, group in by_hl.items():
            canonical_exists = any(doc.id == hl_s for doc in group) or firestore_db.collection('matches').document(hl_s).get().exists
            for doc in group:
                if doc.id == hl_s:
                    continue
                # Always remove non-canonical clones. If no canonical exists yet,
                # the clone is still unsafe (sqlite-id collision risk) and should go.
                if canonical_exists or doc.id != hl_s:
                    batch.delete(doc.reference)
                    deleted += 1
                    batch_count += 1
                    logger.info(
                        f"Pruned upcoming clone {doc.id} (HL {hl_s}, canonical={'yes' if canonical_exists else 'no'})"
                    )
                    if batch_count >= 400:
                        batch.commit()
                        batch = firestore_db.batch()
                        batch_count = 0

    if batch_count:
        batch.commit()
    return deleted


def sync_leagues(sqlite_conn: sqlite3.Connection, firestore_db: Any) -> int:
    """Sync leagues from SQLite to Firestore"""
    try:
        from prediction.config import LEAGUE_MAPPINGS
        from prediction.db import ensure_configured_leagues
    except ImportError:
        LEAGUE_MAPPINGS = {}
        ensure_configured_leagues = None  # type: ignore

    if LEAGUE_MAPPINGS and ensure_configured_leagues is not None:
        ensured = ensure_configured_leagues(sqlite_conn, LEAGUE_MAPPINGS)
        logger.info(f"Ensured {ensured} configured leagues in SQLite before Firestore sync")

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
    parser.add_argument(
        '--skip-prune-clones',
        action='store_true',
        help='Skip pruning upcoming sqlite-id clone docs after match sync',
    )
    parser.add_argument(
        '--skip-prune-orphans',
        action='store_true',
        help='Skip deleting match docs whose SQLite fixture no longer exists',
    )
    
    args = parser.parse_args()
    
    # Connect to SQLite
    if not os.path.exists(args.db):
        logger.error(f"SQLite database not found: {args.db}")
        return 1
    
    sqlite_conn = sqlite3.connect(args.db)
    logger.info(f"Connected to SQLite database: {args.db}")
    
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
        logger.info(f"Connected to Firestore project: {args.project_id}")
    
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
        existing_teams = get_existing_teams(firestore_db)
    else:
        existing_teams = {}
    
    # Sync data
    total_synced = 0
    total_updated = 0
    total_pruned = 0
    total_orphans = 0
    
    if not args.skip_leagues:
        logger.info("\nSyncing leagues...")
        synced = sync_leagues(sqlite_conn, firestore_db) if not args.dry_run else 0
        total_synced += synced
    
    if not args.skip_teams:
        logger.info("\nSyncing teams...")
        synced = sync_teams(sqlite_conn, firestore_db, existing_teams) if not args.dry_run else 0
        total_synced += synced
    
    if not args.skip_matches:
        logger.info("\nSyncing matches...")
        results = sync_matches(sqlite_conn, firestore_db, existing_match_ids) if not args.dry_run else {'synced': 0, 'updated': 0, 'skipped': 0}
        total_synced += results['synced']
        total_updated += results['updated']
        logger.info(f"Matches: {results['synced']} new, {results['updated']} updated, {results['skipped']} skipped")

        if not args.dry_run and not args.skip_prune_clones:
            logger.info("\nPruning upcoming duplicate clone docs...")
            total_pruned = prune_upcoming_firestore_clones(firestore_db)
            logger.info(f"Pruned {total_pruned} upcoming clone docs")

        if not args.dry_run and not args.skip_prune_orphans:
            logger.info("\nPruning match docs with no SQLite fixture...")
            total_orphans = prune_orphaned_matches(sqlite_conn, firestore_db, existing_match_ids)
    
    sqlite_conn.close()
    
    duration = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "="*60)
    logger.info("Sync Complete!")
    logger.info(f"   Total synced: {total_synced}")
    logger.info(f"   Total updated: {total_updated}")
    logger.info(f"   Total pruned clones: {total_pruned}")
    logger.info(f"   Total pruned orphans: {total_orphans}")
    logger.info(f"   Duration: {duration:.1f}s")
    logger.info("="*60)
    
    return 0


if __name__ == "__main__":
    exit(main())

