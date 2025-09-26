#!/usr/bin/env python3
"""
Automated script to pull upcoming games for all rugby leagues using APIs.
This script can be run periodically to keep the database updated with new fixtures.
"""

import argparse
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from prediction.db import connect, init_db, upsert_league, upsert_team, bulk_upsert_events
from prediction.sportsdb_client import TheSportsDBClient, APISportsRugbyClient
from prediction.config import load_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# League mappings
LEAGUE_MAPPINGS = {
    # Internal DB ID -> (API Provider, API League ID, League Name)
    4986: ("apisports", 85, "Rugby Championship"),      # API-Sports
    4446: ("thesportsdb", None, "United Rugby Championship"),  # TheSportsDB (name-based)
    5069: ("thesportsdb", None, "Currie Cup"),          # TheSportsDB (name-based)
    4574: ("thesportsdb", 4574, "Rugby World Cup"),     # TheSportsDB
}

# API-Sports league mappings (for rugby-specific data)
APISPORTS_LEAGUE_MAPPINGS = {
    4986: 85,  # Rugby Championship
    # Add more API-Sports leagues as needed
}


def safe_to_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int with default fallback."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_upcoming_games_apisports(client: APISportsRugbyClient, league_id: int, api_league_id: int, days_ahead: int = 30) -> List[Dict[str, Any]]:
    """Get upcoming games from API-Sports for a specific league."""
    try:
        current_year = datetime.now().year
        games = []
        
        # Try current year and next year
        for year in [current_year, current_year + 1]:
            try:
                year_games = client.list_games(league_id=api_league_id, season=year)
                if year_games:
                    games.extend(year_games)
                    logger.info(f"Found {len(year_games)} games for {year}")
            except Exception as e:
                logger.warning(f"Failed to get games for {year}: {e}")
        
        # Filter for upcoming games (next 30 days)
        upcoming_games = []
        cutoff_date = datetime.now() + timedelta(days=days_ahead)
        
        for game in games:
            try:
                fixture = game.get("fixture", {})
                date_str = fixture.get("date")
                if date_str:
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    if datetime.now() <= game_date <= cutoff_date:
                        upcoming_games.append(game)
            except Exception as e:
                logger.warning(f"Error parsing game date: {e}")
                continue
        
        logger.info(f"Found {len(upcoming_games)} upcoming games for API-Sports league {api_league_id}")
        return upcoming_games
        
    except Exception as e:
        logger.error(f"Error getting upcoming games from API-Sports: {e}")
        return []


def get_upcoming_games_thesportsdb(client: TheSportsDBClient, league_name: str, days_ahead: int = 30) -> List[Dict[str, Any]]:
    """Get upcoming games from TheSportsDB for a specific league."""
    try:
        # Find the league
        league_info = client.find_rugby_league(league_name)
        if not league_info:
            logger.warning(f"Could not find league: {league_name}")
            return []
        
        league_id = league_info.get("idLeague")
        if not league_id:
            logger.warning(f"No league ID found for: {league_name}")
            return []
        
        logger.info(f"Found league {league_name} with ID: {league_id}")
        
        # Get upcoming games for the next 30 days
        upcoming_games = []
        cutoff_date = datetime.now() + timedelta(days=days_ahead)
        
        for i in range(days_ahead):
            check_date = datetime.now() + timedelta(days=i)
            date_str = check_date.strftime("%Y-%m-%d")
            
            try:
                events = client.get_events_for_day(date_str, sport="Rugby Union", league_id=league_id)
                if events:
                    upcoming_games.extend(events)
                    logger.info(f"Found {len(events)} events for {date_str}")
            except Exception as e:
                logger.warning(f"Error getting events for {date_str}: {e}")
                continue
        
        logger.info(f"Found {len(upcoming_games)} upcoming games for TheSportsDB league {league_name}")
        return upcoming_games
        
    except Exception as e:
        logger.error(f"Error getting upcoming games from TheSportsDB: {e}")
        return []


def map_apisports_game_to_event(game: Dict[str, Any], league_id: int) -> Dict[str, Any]:
    """Map API-Sports game data to internal event format."""
    fixture = game.get("fixture", {})
    teams = game.get("teams", {})
    league = game.get("league", {})
    
    date_iso = fixture.get("date")
    venue = (fixture.get("venue") or {}).get("name")
    status = (fixture.get("status") or {}).get("long")
    
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    
    # Create deterministic IDs
    home_name = home.get("name", "").strip()
    away_name = away.get("name", "").strip()
    
    # Generate stable IDs
    import hashlib
    def _stable_id(seed: str, modulo: int = 10_000_000) -> int:
        digest = hashlib.sha1(seed.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return (value % (modulo - 1)) + 1
    
    id_event = _stable_id(f"ev:{league_id}:{date_iso}:{home_name}:{away_name}:{venue or ''}")
    id_home = _stable_id(f"team:home:{league_id}:{home_name}")
    id_away = _stable_id(f"team:away:{league_id}:{away_name}")
    
    return {
        "idEvent": id_event,
        "idLeague": league_id,
        "strSeason": str(league.get("season", datetime.now().year)),
        "dateEvent": date_iso.split('T')[0] if date_iso else None,
        "strTimestamp": date_iso,
        "intRound": None,
        "idHomeTeam": id_home,
        "idAwayTeam": id_away,
        "intHomeScore": None,  # Upcoming games have no scores
        "intAwayScore": None,
        "strStatus": status or "Not Started",
    }


def map_thesportsdb_event_to_event(event: Dict[str, Any], league_id: int) -> Dict[str, Any]:
    """Map TheSportsDB event data to internal event format."""
    return {
        "idEvent": safe_to_int(event.get("idEvent")),
        "idLeague": league_id,
        "strSeason": event.get("strSeason", str(datetime.now().year)),
        "dateEvent": event.get("dateEvent"),
        "strTimestamp": event.get("strTimestamp"),
        "intRound": safe_to_int(event.get("intRound")),
        "idHomeTeam": safe_to_int(event.get("idHomeTeam")),
        "idAwayTeam": safe_to_int(event.get("idAwayTeam")),
        "intHomeScore": safe_to_int(event.get("intHomeScore")),
        "intAwayScore": safe_to_int(event.get("intAwayScore")),
        "strStatus": event.get("strStatus", "Not Started"),
    }


def ensure_teams_exist(conn: sqlite3.Connection, events: List[Dict[str, Any]], league_id: int) -> None:
    """Ensure all teams referenced in events exist in the database."""
    seen_teams = set()
    
    for event in events:
        home_id = event.get("idHomeTeam")
        away_id = event.get("idAwayTeam")
        
        if home_id and home_id not in seen_teams:
            seen_teams.add(home_id)
            # Create placeholder team if it doesn't exist
            team_data = {
                "idTeam": home_id,
                "idLeague": league_id,
                "strTeam": f"Team {home_id}",
                "strTeamShort": None,
                "strAlternate": None,
                "strStadium": None,
                "intFormedYear": None,
                "strCountry": None,
            }
            upsert_team(conn, team_data, league_id=league_id)
        
        if away_id and away_id not in seen_teams:
            seen_teams.add(away_id)
            # Create placeholder team if it doesn't exist
            team_data = {
                "idTeam": away_id,
                "idLeague": league_id,
                "strTeam": f"Team {away_id}",
                "strTeamShort": None,
                "strAlternate": None,
                "strStadium": None,
                "intFormedYear": None,
                "strCountry": None,
            }
            upsert_team(conn, team_data, league_id=league_id)
    
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Automatically pull upcoming games for all rugby leagues")
    parser.add_argument("--db", default="data.sqlite", help="SQLite database path")
    parser.add_argument("--days-ahead", type=int, default=30, help="Number of days ahead to look for games")
    parser.add_argument("--leagues", nargs="*", help="Specific league IDs to update (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    config = load_config()
    
    # Get API keys from environment variables
    thesportsdb_api_key = os.getenv("THESPORTSDB_API_KEY", "1")  # Default to free key
    apisports_api_key = os.getenv("APISPORTS_API_KEY", "")
    
    # Connect to database
    conn = connect(args.db)
    init_db(conn)
    
    # Determine which leagues to update
    leagues_to_update = args.leagues or list(LEAGUE_MAPPINGS.keys())
    if args.leagues:
        leagues_to_update = [int(league_id) for league_id in args.leagues]
    
    logger.info(f"Updating leagues: {leagues_to_update}")
    
    total_events_imported = 0
    
    for league_id in leagues_to_update:
        if league_id not in LEAGUE_MAPPINGS:
            logger.warning(f"Unknown league ID: {league_id}")
            continue
        
        provider, api_league_id, league_name = LEAGUE_MAPPINGS[league_id]
        logger.info(f"Processing league: {league_name} (ID: {league_id}) via {provider}")
        
        try:
            if provider == "apisports":
                # Use API-Sports client
                if not apisports_api_key:
                    logger.warning(f"No API-Sports API key found, skipping {league_name}")
                    continue
                
                client = APISportsRugbyClient(api_key=apisports_api_key)
                games = get_upcoming_games_apisports(client, league_id, api_league_id, args.days_ahead)
                
                # Map games to events
                events = [map_apisports_game_to_event(game, league_id) for game in games]
                
            elif provider == "thesportsdb":
                # Use TheSportsDB client
                client = TheSportsDBClient(
                    base_url="https://www.thesportsdb.com/api/v1/json",
                    api_key=thesportsdb_api_key
                )
                games = get_upcoming_games_thesportsdb(client, league_name, args.days_ahead)
                
                # Map games to events
                events = [map_thesportsdb_event_to_event(game, league_id) for game in games]
                
            else:
                logger.warning(f"Unknown provider: {provider}")
                continue
            
            if not events:
                logger.info(f"No upcoming events found for {league_name}")
                continue
            
            logger.info(f"Found {len(events)} upcoming events for {league_name}")
            
            if args.dry_run:
                logger.info("DRY RUN - Would import the following events:")
                for event in events[:5]:  # Show first 5
                    logger.info(f"  {event.get('dateEvent')} - Event ID: {event.get('idEvent')}")
                if len(events) > 5:
                    logger.info(f"  ... and {len(events) - 5} more")
                continue
            
            # Ensure teams exist
            ensure_teams_exist(conn, events, league_id)
            
            # Import events
            bulk_upsert_events(conn, events, override_league_id=league_id)
            conn.commit()
            
            total_events_imported += len(events)
            logger.info(f"Successfully imported {len(events)} events for {league_name}")
            
        except Exception as e:
            logger.error(f"Error processing league {league_name}: {e}")
            continue
    
    conn.close()
    
    if args.dry_run:
        logger.info("DRY RUN COMPLETE - No changes made to database")
    else:
        logger.info(f"IMPORT COMPLETE - Total events imported: {total_events_imported}")


if __name__ == "__main__":
    main()
