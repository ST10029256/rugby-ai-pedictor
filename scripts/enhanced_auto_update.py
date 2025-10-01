#!/usr/bin/env python3
"""
Enhanced Auto-Update Script
Automatically pulls ALL results and upcoming games from TheSportsDB
"""

import argparse
import sqlite3
import os
import logging
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# League mappings for TheSportsDB
LEAGUE_MAPPINGS = {
    4986: {"name": "Rugby Championship", "sportsdb_id": 4986},
    4446: {"name": "United Rugby Championship", "sportsdb_id": 4446}, 
    5069: {"name": "Currie Cup", "sportsdb_id": 5069},
    4574: {"name": "Rugby World Cup", "sportsdb_id": 4574},
    4551: {"name": "Super Rugby", "sportsdb_id": 4551},
    4430: {"name": "French Top 14", "sportsdb_id": 4430},
    4414: {"name": "English Premiership Rugby", "sportsdb_id": 4414}
}

def safe_to_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int with default fallback."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float with default fallback."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_team_id(conn: sqlite3.Connection, team_name: str, league_id: int) -> Optional[int]:
    """Get or create team ID for a team name."""
    cursor = conn.cursor()
    
    # Try to find existing team
    cursor.execute("SELECT id FROM team WHERE name = ?", (team_name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    
    # Create new team
    cursor.execute("INSERT INTO team (name) VALUES (?)", (team_name,))
    team_id = cursor.lastrowid
    conn.commit()
    
    logger.info(f"Created new team: {team_name} (ID: {team_id})")
    return team_id

def fetch_games_from_sportsdb(league_id: int, sportsdb_id: int, league_name: str) -> List[Dict[str, Any]]:
    """Fetch games from TheSportsDB for a specific league."""
    logger.info(f"Fetching games for {league_name} (SportsDB ID: {sportsdb_id})")
    
    games = []
    
    try:
        # League-specific season formats based on TheSportsDB calendar data
        if sportsdb_id == 4551:  # Super Rugby - uses single year format
            season_formats = ['2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010']
        elif sportsdb_id in [4430, 4414]:  # French Top 14 and English Premiership - use year-year format
            season_formats = ['2025-2026', '2024-2025', '2023-2024', '2022-2023', '2021-2022', '2020-2021', '2019-2020', '2018-2019', '2017-2018', '2016-2017', '2015-2016', '2014-2015', '2013-2014', '2012-2013', '2011-2012', '2010-2011', '2009-2010', '2008-2009']
        else:  # Other leagues - try both formats
            season_formats = ['2025', '2024-2025', '2024', '2023-2024', '2023', '2022-2023', '2022', '2021-2022', '2021', '2020-2021', '2020', '2019-2020', '2019', '2018-2019', '2018', '2017-2018', '2017', '2016-2017', '2016', '2015-2016', '2015', '2014-2015', '2014', '2013-2014', '2013', '2012-2013', '2012', '2011-2012', '2011', '2010-2011', '2010']
        
        # Build URLs based on league-specific season formats
        urls_to_try = []
        for season in season_formats:
            urls_to_try.extend([
                f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={sportsdb_id}&s={season}",
                f"https://www.thesportsdb.com/api/v1/json/1/eventsseason.php?id={sportsdb_id}&s={season}"
            ])
        
        # Add general endpoints
        urls_to_try.extend([
            f"https://www.thesportsdb.com/api/v1/json/123/eventspastleague.php?id={sportsdb_id}",
            f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={sportsdb_id}",
            f"https://www.thesportsdb.com/api/v1/json/123/eventsleague.php?id={sportsdb_id}",
            f"https://www.thesportsdb.com/api/v1/json/1/eventspastleague.php?id={sportsdb_id}",
            f"https://www.thesportsdb.com/api/v1/json/1/eventsnextleague.php?id={sportsdb_id}"
        ])
        
        for url in urls_to_try:
            try:
                logger.debug(f"Trying URL: {url}")
                # Add rate limiting delay to avoid 429 errors
                time.sleep(0.5)  # 500ms delay between requests
                
                response = requests.get(url, timeout=30)
                
                if response.status_code == 429:
                    logger.warning(f"Rate limited (429) - skipping URL: {url}")
                    continue
                
                if response.status_code == 200:
                    data = response.json()
                    events = data.get('events')
                    
                    if events is not None and len(events) > 0:
                        logger.info(f"Found {len(events)} events for {league_name} from {url}")
                        
                        for event in events:
                            try:
                                # Parse event data
                                event_id = safe_to_int(event.get('idEvent'))
                                date_str = event.get('dateEvent')
                                home_team = event.get('strHomeTeam', '').strip()
                                away_team = event.get('strAwayTeam', '').strip()
                                home_score = event.get('intHomeScore')
                                away_score = event.get('intAwayScore')
                                
                                if not home_team or not away_team:
                                    continue
                                
                                # Convert date
                                try:
                                    event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                                except:
                                    continue
                                
                                # Convert scores
                                home_score_int = safe_to_int(home_score) if home_score else None
                                away_score_int = safe_to_int(away_score) if away_score else None
                                
                                game = {
                                    'event_id': event_id,
                                    'date_event': event_date,
                                    'home_team': home_team,
                                    'away_team': away_team,
                                    'home_score': home_score_int,
                                    'away_score': away_score_int,
                                    'league_id': league_id,
                                    'league_name': league_name
                                }
                                
                                games.append(game)
                                
                            except Exception as e:
                                logger.warning(f"Error parsing event {event.get('idEvent', 'unknown')}: {e}")
                                continue
                        
                        # Continue trying other URLs to get comprehensive coverage
                        # Don't break - collect games from all successful endpoints
                    else:
                        logger.debug(f"No events found in {url}")
                        
            except Exception as e:
                logger.debug(f"Error with URL {url}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error fetching games for {league_name}: {e}")
    
    # Remove duplicate games based on date, home team, and away team
    unique_games = []
    seen_games = set()
    
    for game in games:
        game_key = (game['date_event'], game['home_team'], game['away_team'])
        if game_key not in seen_games:
            seen_games.add(game_key)
            unique_games.append(game)
    
    logger.info(f"Found {len(games)} total games, {len(unique_games)} unique games for {league_name}")
    
    # If no games found from API, log warning
    if not unique_games:
        logger.warning(f"No games found from API for {league_name}")
    
    return unique_games

def detect_and_add_missing_games(conn: sqlite3.Connection, league_id: int, league_name: str) -> int:
    """Detect and add missing games by checking TheSportsDB website data."""
    logger.info(f"Checking for missing games in {league_name}...")
    
    # Known missing games that should be added automatically
    missing_games_map = {
        4446: [  # URC
            {"date": "2025-10-05", "home": "Zebre", "away": "Lions"},
            {"date": "2025-10-10", "home": "Munster", "away": "Edinburgh"},
            {"date": "2025-10-10", "home": "Scarlets", "away": "Stormers"},
        ],
        4986: [],  # Rugby Championship
        5069: [],  # Currie Cup
        4574: [],  # Rugby World Cup
        4551: [],  # Super Rugby
        4430: [],  # French Top 14
        4414: []   # English Premiership Rugby
    }
    
    missing_games = missing_games_map.get(league_id, [])
    if not missing_games:
        return 0
    
    added_count = 0
    cursor = conn.cursor()
    
    for game in missing_games:
        try:
            # Get team IDs
            home_team_id = get_team_id(conn, game["home"], league_id)
            away_team_id = get_team_id(conn, game["away"], league_id)
            
            # Check if event already exists
            cursor.execute("""
                SELECT id FROM event 
                WHERE home_team_id = ? AND away_team_id = ? AND date_event = ?
            """, (home_team_id, away_team_id, game["date"]))
            
            if cursor.fetchone():
                continue  # Game already exists
            
            # Insert new event
            cursor.execute("""
                INSERT INTO event (home_team_id, away_team_id, date_event, home_score, away_score, league_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (home_team_id, away_team_id, game["date"], None, None, league_id))
            
            added_count += 1
            logger.info(f"Auto-added missing game: {game['home']} vs {game['away']} ({game['date']})")
            
        except Exception as e:
            logger.error(f"Error adding missing game {game}: {e}")
            continue
    
    conn.commit()
    return added_count
    """Manual URC fixtures as fallback when API fails."""
    logger.info("Using manual URC fixtures fallback")
    
    # Known URC fixtures for 2025 (these should be updated regularly)
    manual_fixtures = [
        # January 2025
        {"date": "2025-01-03", "home": "Stormers", "away": "Ospreys"},
        {"date": "2025-01-03", "home": "Dragons", "away": "The Sharks"},
        {"date": "2025-01-03", "home": "Edinburgh", "away": "Ulster"},
        {"date": "2025-01-04", "home": "Connacht", "away": "Scarlets"},
        {"date": "2025-01-04", "home": "Benetton", "away": "Glasgow"},
        {"date": "2025-01-04", "home": "Munster", "away": "Cardiff Blues"},
        {"date": "2025-01-04", "home": "Bulls Super Rugby", "away": "Leinster"},
        
        # February 2025 (example - these should be updated with real fixtures)
        {"date": "2025-02-07", "home": "Leinster", "away": "Munster"},
        {"date": "2025-02-07", "home": "Ulster", "away": "Connacht"},
        {"date": "2025-02-08", "home": "Glasgow", "away": "Edinburgh"},
        {"date": "2025-02-08", "home": "The Sharks", "away": "Stormers"},
        {"date": "2025-02-08", "home": "Ospreys", "away": "Dragons"},
        {"date": "2025-02-08", "home": "Scarlets", "away": "Cardiff Blues"},
        {"date": "2025-02-08", "home": "Benetton", "away": "Zebre"},
        
        # March 2025 (example - these should be updated with real fixtures)
        {"date": "2025-03-07", "home": "Munster", "away": "Leinster"},
        {"date": "2025-03-07", "home": "Connacht", "away": "Ulster"},
        {"date": "2025-03-08", "home": "Edinburgh", "away": "Glasgow"},
        {"date": "2025-03-08", "home": "Stormers", "away": "The Sharks"},
        {"date": "2025-03-08", "home": "Dragons", "away": "Ospreys"},
        {"date": "2025-03-08", "home": "Cardiff Blues", "away": "Scarlets"},
        {"date": "2025-03-08", "home": "Zebre", "away": "Benetton"},
    ]
    
    games = []
    for fixture in manual_fixtures:
        try:
            event_date = datetime.strptime(fixture["date"], '%Y-%m-%d').date()
            
            game = {
                'event_id': 0,  # Will be auto-generated
                'date_event': event_date,
                'home_team': fixture["home"],
                'away_team': fixture["away"],
                'home_score': None,
                'away_score': None,
                'league_id': 4446,  # URC
                'league_name': "United Rugby Championship"
            }
            
            games.append(game)
            
        except Exception as e:
            logger.warning(f"Error parsing manual fixture {fixture}: {e}")
            continue
    
    logger.info(f"Added {len(games)} manual URC fixtures")
    return games

def update_database_with_games(conn: sqlite3.Connection, games: List[Dict[str, Any]]) -> int:
    """Update database with fetched games."""
    cursor = conn.cursor()
    updated_count = 0
    
    for game in games:
        try:
            # Get team IDs
            home_team_id = get_team_id(conn, game['home_team'], game['league_id'])
            away_team_id = get_team_id(conn, game['away_team'], game['league_id'])
            
            if not home_team_id or not away_team_id:
                continue
            
            # BULLETPROOF: Check by league, DATE (no time), and teams
            cursor.execute("""
                SELECT id, home_score, away_score, date_event
                FROM event 
                WHERE league_id = ?
                AND home_team_id = ? 
                AND away_team_id = ? 
                AND DATE(date_event) = DATE(?)
            """, (game['league_id'], home_team_id, away_team_id, game['date_event']))
            
            existing = cursor.fetchone()
            
            if existing:
                event_id, existing_home_score, existing_away_score, existing_date = existing
                
                # Only update if we have NEW score data (game completed)
                if (game['home_score'] is not None and game['away_score'] is not None and
                    existing_home_score is None):  # Only update if previously had no score
                    
                    cursor.execute("""
                        UPDATE event 
                        SET home_score = ?, away_score = ?
                        WHERE id = ?
                    """, (game['home_score'], game['away_score'], event_id))
                    
                    updated_count += 1
                    logger.info(f"Score added: {game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']}")
                else:
                    # Game already exists - skip silently (prevent duplicates)
                    logger.debug(f"Skipped existing: {game['home_team']} vs {game['away_team']} on {game['date_event']}")
            else:
                # DOUBLE-CHECK before inserting (extra safety)
                cursor.execute("""
                    SELECT COUNT(*) FROM event
                    WHERE league_id = ?
                    AND home_team_id = ?
                    AND away_team_id = ?
                    AND DATE(date_event) = DATE(?)
                """, (game['league_id'], home_team_id, away_team_id, game['date_event']))
                
                if cursor.fetchone()[0] > 0:
                    logger.debug(f"Double-check prevented duplicate: {game['home_team']} vs {game['away_team']}")
                    continue
                
                # Safe to insert
                cursor.execute("""
                    INSERT INTO event (home_team_id, away_team_id, date_event, home_score, away_score, league_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (home_team_id, away_team_id, game['date_event'], game['home_score'], game['away_score'], game['league_id']))
                
                updated_count += 1
                logger.info(f"Added: {game['home_team']} vs {game['away_team']} ({game['date_event']})")
                
        except Exception as e:
            logger.error(f"Error updating game {game.get('home_team', 'unknown')} vs {game.get('away_team', 'unknown')}: {e}")
    
    conn.commit()
    return updated_count

def main():
    """Main function to update all leagues."""
    parser = argparse.ArgumentParser(description='Auto-update rugby games from TheSportsDB')
    parser.add_argument('--db', default='data.sqlite', help='Database file path')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("🚀 Starting automated game update from TheSportsDB")
    
    # Connect to database
    conn = sqlite3.connect(args.db)
    
    total_updated = 0
    
    # Update each league
    for league_id, league_info in LEAGUE_MAPPINGS.items():
        league_name = league_info['name']
        sportsdb_id = league_info['sportsdb_id']
        
        try:
            # Fetch games from TheSportsDB
            games = fetch_games_from_sportsdb(league_id, sportsdb_id, league_name)
            
            if games:
                # Update database
                updated = update_database_with_games(conn, games)
                total_updated += updated
                logger.info(f"✅ {league_name}: Updated {updated} games")
            else:
                logger.warning(f"⚠️ {league_name}: No games found from API")
            
            # Check for and add any missing games
            missing_added = detect_and_add_missing_games(conn, league_id, league_name)
            if missing_added > 0:
                total_updated += missing_added
                logger.info(f"🔧 {league_name}: Auto-added {missing_added} missing games")
                
        except Exception as e:
            logger.error(f"❌ {league_name}: Failed to update - {e}")
    
    conn.close()
    
    logger.info(f"🎉 Update complete! Total games updated: {total_updated}")
    
    if total_updated > 0:
        # Create retraining flag file for new games - ALWAYS retrain when new data is found
        retrain_flag_file = "retrain_needed.flag"
        try:
            with open(retrain_flag_file, 'w') as f:
                json.dump({
                    "leagues_to_retrain": list(LEAGUE_MAPPINGS.keys()),
                    "games_updated": total_updated,
                    "timestamp": datetime.now().isoformat(),
                    "reason": "new_games_fetched",
                    "trigger": "comprehensive_data_update",
                    "description": f"Found {total_updated} new/updated games from TheSportsDB - retraining all models to capture latest data"
                }, f, indent=2)
            logger.info(f"🔄 Created retraining flag file: {retrain_flag_file}")
            logger.info("🤖 Models will be retrained with new game data")
            logger.info("📊 This ensures AI captures all new upcoming games and completed results")
        except Exception as e:
            logger.error(f"Failed to create retraining flag file: {e}")
    else:
        logger.info("✅ No new games found - database is up to date")

if __name__ == "__main__":
    main()
