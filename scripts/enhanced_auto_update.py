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
    4574: {"name": "Rugby World Cup", "sportsdb_id": 4574}
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
        # Try multiple API endpoints
        urls_to_try = [
            f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={sportsdb_id}&s=2024-2025",
            f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={sportsdb_id}&s=2025",
            f"https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id={sportsdb_id}&s=2024",
            f"https://www.thesportsdb.com/api/v1/json/123/eventspastleague.php?id={sportsdb_id}",
            f"https://www.thesportsdb.com/api/v1/json/123/eventsnextleague.php?id={sportsdb_id}"
        ]
        
        for url in urls_to_try:
            try:
                logger.debug(f"Trying URL: {url}")
                response = requests.get(url, timeout=30)
                
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
                        
                        # If we found games, break out of the URL loop
                        if games:
                            break
                    else:
                        logger.debug(f"No events found in {url}")
                        
            except Exception as e:
                logger.debug(f"Error with URL {url}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error fetching games for {league_name}: {e}")
    
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
            
            # Check if event exists
            cursor.execute("""
                SELECT id, home_score, away_score 
                FROM event 
                WHERE home_team_id = ? AND away_team_id = ? AND date_event = ?
            """, (home_team_id, away_team_id, game['date_event']))
            
            existing = cursor.fetchone()
            
            if existing:
                event_id, existing_home_score, existing_away_score = existing
                
                # Update scores if they're available and different
                if (game['home_score'] is not None and game['away_score'] is not None and
                    (existing_home_score != game['home_score'] or existing_away_score != game['away_score'])):
                    
                    cursor.execute("""
                        UPDATE event 
                        SET home_score = ?, away_score = ?
                        WHERE id = ?
                    """, (game['home_score'], game['away_score'], event_id))
                    
                    updated_count += 1
                    logger.info(f"Updated: {game['home_team']} {game['home_score']}-{game['away_score']} {game['away_team']} ({game['date_event']})")
            else:
                # Insert new event
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
                logger.warning(f"⚠️ {league_name}: No games found")
                
        except Exception as e:
            logger.error(f"❌ {league_name}: Failed to update - {e}")
    
    conn.close()
    
    logger.info(f"🎉 Update complete! Total games updated: {total_updated}")
    
    if total_updated > 0:
        logger.info("🔄 Run 'python scripts/detect_completed_matches.py' to retrain models with new data")

if __name__ == "__main__":
    main()
