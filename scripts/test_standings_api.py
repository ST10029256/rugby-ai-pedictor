#!/usr/bin/env python3
"""
Test script to check if we can pull team standings and points for all leagues
Tests Highlightly API

Usage:
    python scripts/test_standings_api.py
    python scripts/test_standings_api.py --highlightly-key YOUR_KEY
    HIGHLIGHTLY_API_KEY=xxx python scripts/test_standings_api.py
"""

import os
import sys
import argparse
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# League mappings (all 9 leagues) - Our internal IDs
LEAGUE_MAPPINGS = {
    4986: "Rugby Championship",
    4446: "United Rugby Championship",
    5069: "Currie Cup",
    4574: "Rugby World Cup",
    4551: "Super Rugby",
    4430: "French Top 14",
    4414: "English Premiership Rugby",
    4714: "Six Nations Championship",
    5479: "Rugby Union International Friendlies",
}

# Highlightly League ID mappings (from successful API calls)
# Our internal ID -> Highlightly League ID
HIGHLIGHTLY_LEAGUE_IDS = {
    4986: 73119,  # Rugby Championship
    4446: 65460,  # United Rugby Championship
    5069: 32271,  # Currie Cup
    4574: 59503,  # Rugby World Cup
    4551: 61205,  # Super Rugby
    4430: 14400,  # French Top 14
    4414: 11847,  # English Premiership Rugby (CORRECTED: was 5039 which was Austrian league)
    4714: 44185,  # Six Nations Championship
    5479: 72268,  # Rugby Union International Friendlies (Friendly International - no standings as friendlies don't have league tables)
}



def get_highlightly_leagues_from_matches(client) -> Dict[str, int]:
    """Get available leagues from Highlightly API by fetching matches and extracting league IDs"""
    logger.info("\n🔍 Fetching recent matches to discover Highlightly league IDs...")
    try:
        # Fetch recent matches to see what leagues are available
        matches_data = client.get_matches(limit=500)  # Get more matches to find more leagues
        
        if not matches_data or not isinstance(matches_data, dict):
            logger.warning("⚠️ No matches data returned from Highlightly API")
            return {}
        
        matches_list = matches_data.get('data', [])
        if not matches_list:
            logger.warning("⚠️ No matches found in Highlightly API response")
            return {}
        
        logger.info(f"✅ Found {len(matches_list)} matches in Highlightly API")
        
        # Extract unique league IDs and names from matches
        leagues_found = {}  # league_id -> league_name
        for match in matches_list:
            league_info = match.get('league')
            if league_info:
                hl_id = league_info.get('id')
                hl_name = league_info.get('name', '')
                if hl_id and hl_name:
                    leagues_found[hl_id] = hl_name
        
        logger.info(f"✅ Found {len(leagues_found)} unique leagues in matches")
        
        # Create mapping: our league name -> Highlightly league ID
        league_mapping = {}
        
        # Try to match our league names to Highlightly leagues found in matches
        for our_league_id, our_league_name in LEAGUE_MAPPINGS.items():
            best_match = None
            best_score = 0
            
            our_name_lower = our_league_name.lower()
            
            for hl_id, hl_name in leagues_found.items():
                hl_name_lower = hl_name.lower()
                
                # Check for exact or partial matches
                score = 0
                if our_name_lower == hl_name_lower:
                    score = 100
                elif our_name_lower in hl_name_lower or hl_name_lower in our_name_lower:
                    score = 80
                elif any(word in hl_name_lower for word in our_name_lower.split() if len(word) > 3):
                    score = 50
                
                if score > best_score:
                    best_score = score
                    best_match = hl_id
            
            if best_match and best_score >= 50:
                league_mapping[our_league_id] = best_match
                logger.info(f"   ✅ {our_league_name} -> Highlightly ID: {best_match} (name: {leagues_found[best_match]})")
            else:
                logger.warning(f"   ⚠️ No match found for {our_league_name}")
        
        # Also try searching by league name directly
        logger.info("\n🔍 Also trying to search matches by league name...")
        for our_league_id, our_league_name in LEAGUE_MAPPINGS.items():
            if our_league_id in league_mapping:
                continue  # Already found
            
            try:
                # Try searching matches by league name
                matches_by_name = client.get_matches(league_name=our_league_name, limit=10)
                if matches_by_name and matches_by_name.get('data'):
                    match = matches_by_name['data'][0]
                    league_info = match.get('league')
                    if league_info:
                        hl_id = league_info.get('id')
                        if hl_id:
                            league_mapping[our_league_id] = hl_id
                            logger.info(f"   ✅ {our_league_name} -> Highlightly ID: {hl_id} (found via name search)")
            except Exception as e:
                logger.debug(f"   Name search failed for {our_league_name}: {e}")
        
        return league_mapping
        
    except Exception as e:
        logger.error(f"❌ Error fetching leagues from matches: {e}")
        return {}


def get_highlightly_leagues(client) -> Dict[str, int]:
    """Get available leagues from Highlightly API and map to our league names"""
    logger.info("\n🔍 Fetching available leagues from Highlightly API...")
    try:
        # Try with max limit of 100 (API limit)
        leagues_data = client.get_leagues(limit=100)
        
        if not leagues_data or not isinstance(leagues_data, dict):
            logger.warning("⚠️ No leagues data returned from Highlightly API, trying matches approach...")
            return get_highlightly_leagues_from_matches(client)
        
        # Extract leagues from response
        leagues_list = leagues_data.get('data', [])
        if not leagues_list:
            logger.warning("⚠️ No leagues found in Highlightly API response, trying matches approach...")
            return get_highlightly_leagues_from_matches(client)
        
        logger.info(f"✅ Found {len(leagues_list)} leagues in Highlightly API")
        
        # Create mapping: our league name -> Highlightly league ID
        league_mapping = {}
        
        # Try to match our league names to Highlightly leagues
        for our_league_id, our_league_name in LEAGUE_MAPPINGS.items():
            best_match = None
            best_score = 0
            
            for hl_league in leagues_list:
                hl_name = hl_league.get('name', '').lower()
                hl_id = hl_league.get('id')
                
                if not hl_name or not hl_id:
                    continue
                
                # Simple matching: check if our league name contains key words
                our_name_lower = our_league_name.lower()
                
                # Check for exact or partial matches
                score = 0
                if our_name_lower == hl_name:
                    score = 100
                elif our_name_lower in hl_name or hl_name in our_name_lower:
                    score = 80
                elif any(word in hl_name for word in our_name_lower.split() if len(word) > 3):
                    score = 50
                
                if score > best_score:
                    best_score = score
                    best_match = hl_id
            
            if best_match and best_score >= 50:
                # Check if this Highlightly ID is already mapped to another league
                if best_match in league_mapping.values():
                    # Find which league already has this ID
                    existing_league = [lid for lid, hl_id in league_mapping.items() if hl_id == best_match]
                    if existing_league:
                        logger.warning(f"   ⚠️ Highlightly ID {best_match} already mapped to {LEAGUE_MAPPINGS[existing_league[0]]}, skipping {our_league_name}")
                else:
                    league_mapping[our_league_id] = best_match
                    logger.info(f"   ✅ {our_league_name} -> Highlightly ID: {best_match}")
            else:
                logger.warning(f"   ⚠️ No match found for {our_league_name}")
        
        # If we didn't find many matches, try the matches approach as fallback
        if len(league_mapping) < len(LEAGUE_MAPPINGS) // 2:
            logger.info(f"\n⚠️ Only found {len(league_mapping)}/{len(LEAGUE_MAPPINGS)} leagues, trying matches approach...")
            matches_mapping = get_highlightly_leagues_from_matches(client)
            # Merge results, preferring matches approach
            for our_id, hl_id in matches_mapping.items():
                if our_id not in league_mapping:
                    league_mapping[our_id] = hl_id
        
        return league_mapping
        
    except Exception as e:
        logger.error(f"❌ Error fetching leagues from Highlightly: {e}")
        logger.info("   Trying matches approach as fallback...")
        return get_highlightly_leagues_from_matches(client)


def test_highlightly_standings(api_key: Optional[str] = None, delay: float = 5.0, leagues_to_test: Optional[Dict[int, str]] = None, use_rapidapi: bool = False):
    """Test Highlightly API for standings"""
    try:
        from prediction.highlightly_client import HighlightlyRugbyAPI
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        # Use provided key, or try environment variables
        if not api_key:
            api_key = os.getenv('HIGHLIGHTLY_API_KEY') or os.getenv('RAPIDAPI_KEY')
        
        if not api_key:
            logger.warning("⚠️ API key not found")
            logger.info("   Set it via: --highlightly-key YOUR_KEY or --rapidapi-key YOUR_KEY")
            logger.info("   Or environment variable: HIGHLIGHTLY_API_KEY or RAPIDAPI_KEY")
            return None
        
        api_type = "RapidAPI" if use_rapidapi else "Highlightly Direct"
        logger.info("\n" + "="*80)
        logger.info(f"TESTING {api_type.upper()} API STANDINGS")
        logger.info("="*80)
        logger.info(f"Using {api_type} API")
        logger.info(f"Using API key: {api_key[:10]}..." if api_key else "No API key")
        logger.info(f"Request delay: {delay} seconds between calls")
        
        client = HighlightlyRugbyAPI(api_key=api_key, use_rapidapi=use_rapidapi)
        
        # Use hardcoded Highlightly league IDs (from successful API calls)
        # If we need to fetch them dynamically, we can do that, but for now use known mappings
        league_mapping = HIGHLIGHTLY_LEAGUE_IDS.copy()
        logger.info(f"✅ Using {len(league_mapping)} pre-mapped Highlightly league IDs")
        
        # Optionally try to fetch leagues if we want to verify/update mappings
        # But skip this to avoid rate limiting
        try_fetch_leagues = False
        if try_fetch_leagues:
            fetched_mapping = get_highlightly_leagues(client)
            if fetched_mapping:
                # Update with fetched mappings where available
                for our_id, hl_id in fetched_mapping.items():
                    league_mapping[our_id] = hl_id
        
        results = {}
        
        # Get current year for season
        current_year = datetime.now().year
        
        # Use provided leagues_to_test or default to all
        if leagues_to_test is None:
            leagues_to_test = LEAGUE_MAPPINGS
        
        for idx, (our_league_id, league_name) in enumerate(leagues_to_test.items()):
            highlightly_league_id = league_mapping.get(our_league_id, our_league_id)
            logger.info(f"\n📊 Testing {league_name} (Our ID: {our_league_id}, Highlightly ID: {highlightly_league_id})...")
            
            # Add delay between requests to avoid rate limiting (except for first request)
            if idx > 0:
                logger.info(f"   ⏳ Waiting {delay}s before next request to avoid rate limiting...")
                time.sleep(delay)
            
            try:
                # Only try 2025 season
                standings = None
                successful_season = None
                year = current_year  # Only 2025
                
                logger.info(f"   Testing season {year} only...")
                try:
                    standings = client.get_standings(league_id=highlightly_league_id, season=year)
                    
                    # Check if rate limited
                    if isinstance(standings, dict) and standings.get('_rate_limited'):
                        rate_limit_headers = standings.get('_rate_limit_headers', {})
                        error_msg = 'Rate limited (429) - API quota exceeded'
                        
                        # Add rate limit header info if available
                        if rate_limit_headers:
                            retry_after = rate_limit_headers.get('Retry-After')
                            limit = rate_limit_headers.get('X-RateLimit-Limit')
                            remaining = rate_limit_headers.get('X-RateLimit-Remaining')
                            reset = rate_limit_headers.get('X-RateLimit-Reset')
                            
                            if retry_after:
                                error_msg += f'. Retry after {retry_after} seconds'
                            if limit:
                                error_msg += f'. Limit: {limit}'
                            if remaining is not None:
                                error_msg += f'. Remaining: {remaining}'
                            if reset:
                                error_msg += f'. Resets at: {reset}'
                            
                            logger.warning(f"   ⚠️ Rate limit headers: {rate_limit_headers}")
                        
                        logger.warning(f"   ⚠️ Rate limited (429) for season {year}")
                        logger.warning(f"   💡 Tip: Wait a few minutes before trying again, or test one league at a time")
                        
                        results[our_league_id] = {
                            'success': False,
                            'data': None,
                            'league_name': league_name,
                            'highlightly_league_id': highlightly_league_id,
                            'error': error_msg,
                            'rate_limit_headers': rate_limit_headers
                        }
                        
                        # If we get rate limited on first request, suggest stopping
                        if idx == 0:
                            logger.error(f"   ❌ Rate limited on first request - API quota may be exhausted")
                            logger.error(f"   💡 Please wait 10-15 minutes before trying again")
                        
                        continue
                    
                    if standings and (standings.get('groups') or standings.get('league')):
                        groups = standings.get('groups', [])
                        if groups and len(groups) > 0:
                            # Check if groups have teams/standings
                            has_teams = any(
                                (g.get('standings') and len(g.get('standings', [])) > 0) or
                                (g.get('teams') and len(g.get('teams', [])) > 0)
                                for g in groups
                            )
                            if has_teams:
                                logger.info(f"✅ Found standings for {league_name} (season {year}, Highlightly ID: {highlightly_league_id})")
                                successful_season = year
                            else:
                                logger.warning(f"   ⚠️ Groups found but no teams/standings data for season {year}")
                        else:
                            logger.warning(f"   ⚠️ No groups found for season {year}")
                    else:
                        logger.warning(f"   ⚠️ Empty or invalid response for season {year}")
                except Exception as year_error:
                    error_msg = str(year_error)
                    if '404' in error_msg:
                        logger.info(f"   ❌ 404 Not Found - no standings for season {year}")
                    elif '429' in error_msg:
                        logger.warning(f"   ❌ 429 Rate Limited - API quota exceeded")
                        logger.warning(f"   ⚠️ Please wait a few minutes before trying again")
                        # If rate limited, stop trying other leagues
                        logger.warning(f"   ⚠️ Stopping further requests due to rate limiting")
                        results[our_league_id] = {
                            'success': False,
                            'data': None,
                            'league_name': league_name,
                            'highlightly_league_id': highlightly_league_id,
                            'error': 'Rate limited (429) - API quota exceeded. Please wait and try again.'
                        }
                        # Mark remaining leagues as rate limited
                        for remaining_id in list(leagues_to_test.keys())[idx+1:]:
                            remaining_name = leagues_to_test[remaining_id]
                            remaining_hl_id = league_mapping.get(remaining_id, remaining_id)
                            results[remaining_id] = {
                                'success': False,
                                'data': None,
                                'league_name': remaining_name,
                                'highlightly_league_id': remaining_hl_id,
                                'error': 'Rate limited (429) - Stopped due to rate limit on previous request'
                            }
                        break  # Exit the loop
                    else:
                        logger.error(f"   ❌ Error for season {year}: {year_error}")
                    standings = None
                
                if standings and successful_season:
                    logger.info(f"   Data type: {type(standings)}")
                    logger.info(f"   Data keys: {list(standings.keys()) if isinstance(standings, dict) else 'N/A'}")
                    
                    # Check for groups
                    if 'groups' in standings:
                        groups = standings.get('groups', [])
                        logger.info(f"   Found {len(groups)} groups")
                        if groups:
                            sample_group = groups[0]
                            logger.info(f"   Sample group keys: {list(sample_group.keys())}")
                            
                            # Check for 'standings' (array of teams) or 'teams'
                            teams = None
                            if 'standings' in sample_group:
                                teams = sample_group.get('standings', [])
                                logger.info(f"   Found {len(teams)} teams in first group (from 'standings')")
                            elif 'teams' in sample_group:
                                teams = sample_group.get('teams', [])
                                logger.info(f"   Found {len(teams)} teams in first group (from 'teams')")
                            
                            if teams and len(teams) > 0:
                                sample_team = teams[0]
                                logger.info(f"   Sample team keys: {list(sample_team.keys())}")
                                # Show sample team data with points/position
                                team_sample = {}
                                for key in ['position', 'points', 'wins', 'losses', 'draws', 'name', 'team_name', 'played', 'won', 'lost', 'drawn']:
                                    if key in sample_team:
                                        team_sample[key] = sample_team[key]
                                if team_sample:
                                    logger.info(f"   Sample team data: {team_sample}")
                            else:
                                logger.warning(f"   ⚠️ No teams found in first group (keys: {list(sample_group.keys())})")
                    
                    # Check for league data
                    if 'league' in standings:
                        league_data = standings.get('league', {})
                        logger.info(f"   League data keys: {list(league_data.keys())}")
                        if league_data.get('name'):
                            logger.info(f"   League name: {league_data.get('name')}")
                        if league_data.get('season'):
                            logger.info(f"   Season: {league_data.get('season')}")
                    
                    # Count total teams across all groups
                    total_teams = 0
                    if 'groups' in standings:
                        for group in standings.get('groups', []):
                            if 'standings' in group:
                                total_teams += len(group.get('standings', []))
                            elif 'teams' in group:
                                total_teams += len(group.get('teams', []))
                    
                    results[our_league_id] = {
                        'success': True,
                        'data': standings,
                        'league_name': league_name,
                        'highlightly_league_id': highlightly_league_id,
                        'season': successful_season,
                        'total_teams': total_teams
                    }
                else:
                    logger.warning(f"⚠️ No standings data returned for {league_name} (tried season {current_year} only)")
                    results[our_league_id] = {
                        'success': False,
                        'data': None,
                        'league_name': league_name,
                        'highlightly_league_id': highlightly_league_id,
                        'error': f'No standings data for season {current_year}'
                    }
            except Exception as e:
                logger.error(f"❌ Error getting standings for {league_name}: {e}")
                results[our_league_id] = {
                    'success': False,
                    'data': None,
                    'league_name': league_name,
                    'highlightly_league_id': highlightly_league_id,
                    'error': str(e)
                }
        
        return results
        
    except ImportError as e:
        logger.error(f"❌ Could not import HighlightlyRugbyAPI: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error testing Highlightly API: {e}")
        return None


def display_standings_summary(highlightly_results: Optional[Dict]):
    """Display a summary of standings retrieval results"""
    logger.info("\n" + "="*80)
    logger.info("STANDINGS RETRIEVAL SUMMARY")
    logger.info("="*80)
    
    print("\n📊 LEAGUE STANDINGS AVAILABILITY (Highlightly API):\n")
    print(f"{'League Name':<45} {'Status':<30}")
    print("-" * 75)
    
    for league_id, league_name in LEAGUE_MAPPINGS.items():
        highlightly_status = "❌ Not tested"
        
        if highlightly_results and league_id in highlightly_results:
            if highlightly_results[league_id]['success']:
                data = highlightly_results[league_id]['data']
                if isinstance(data, dict):
                    if data.get('groups') or data.get('league'):
                        groups = data.get('groups', [])
                        if groups:
                            # Count teams from 'standings' or 'teams' key
                            total_teams = 0
                            for g in groups:
                                if isinstance(g, dict):
                                    if 'standings' in g:
                                        total_teams += len(g.get('standings', []))
                                    elif 'teams' in g:
                                        total_teams += len(g.get('teams', []))
                            
                            # Use stored total_teams if available (more accurate)
                            if 'total_teams' in highlightly_results[league_id]:
                                total_teams = highlightly_results[league_id]['total_teams']
                            
                            highlightly_status = f"✅ {len(groups)} groups, {total_teams} teams"
                        else:
                            highlightly_status = "✅ Data available"
                    else:
                        highlightly_status = "⚠️ Empty"
                else:
                    highlightly_status = "⚠️ Unexpected format"
            else:
                error = highlightly_results[league_id].get('error', 'Unknown error')
                highlightly_status = f"❌ {error[:28]}"
        
        print(f"{league_name:<45} {highlightly_status:<30}")
    
    # Show detailed examples
    print("\n" + "="*80)
    print("DETAILED EXAMPLES")
    print("="*80)
    
    # Find first successful Highlightly result
    if highlightly_results:
        for league_id, result in highlightly_results.items():
            if result['success'] and result['data']:
                print(f"\n📊 Highlightly Example - {result['league_name']}:")
                data = result['data']
                if isinstance(data, dict):
                    print(f"   Top-level keys: {list(data.keys())}")
                    if 'groups' in data and data['groups']:
                        group = data['groups'][0]
                        print(f"   First group keys: {list(group.keys())}")
                        # Check for 'standings' or 'teams'
                        teams = None
                        if 'standings' in group and group['standings']:
                            teams = group['standings']
                        elif 'teams' in group and group['teams']:
                            teams = group['teams']
                        
                        if teams:
                            team = teams[0]
                            print(f"   First team keys: {list(team.keys())}")
                            print(f"   First team sample: {dict(list(team.items())[:8])}")
                break


def main():
    """Main function to test standings APIs"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Test standings APIs for all 9 leagues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using RapidAPI (recommended if hitting rate limits):
  python scripts/test_standings_api.py --use-rapidapi --rapidapi-key YOUR_RAPIDAPI_KEY
  
  # Using Highlightly direct API:
  python scripts/test_standings_api.py --highlightly-key YOUR_KEY
  
  # Test single league with RapidAPI:
  python scripts/test_standings_api.py --use-rapidapi --rapidapi-key YOUR_KEY --league-id 4446
  
  # Using environment variables (Windows PowerShell):
  $env:RAPIDAPI_KEY="your_key"; python scripts/test_standings_api.py --use-rapidapi
  
  # Using environment variables (Linux/Mac):
  RAPIDAPI_KEY=your_key python scripts/test_standings_api.py --use-rapidapi
        """
    )
    parser.add_argument('--highlightly-key', type=str, help='Highlightly API key (or set HIGHLIGHTLY_API_KEY env var)')
    parser.add_argument('--rapidapi-key', type=str, help='RapidAPI key (can be used for Highlightly API)')
    parser.add_argument('--use-rapidapi', action='store_true', help='Use RapidAPI endpoint instead of direct Highlightly API')
    parser.add_argument('--league-id', type=int, help='Test only a specific league ID (our internal ID)')
    parser.add_argument('--delay', type=float, default=5.0, help='Delay between requests in seconds (default: 5.0)')
    
    args = parser.parse_args()
    
    # Set environment variables from command-line args if provided
    if args.rapidapi_key:
        os.environ['RAPIDAPI_KEY'] = args.rapidapi_key
        if not args.highlightly_key:
            os.environ['HIGHLIGHTLY_API_KEY'] = args.rapidapi_key
    
    if args.highlightly_key:
        os.environ['HIGHLIGHTLY_API_KEY'] = args.highlightly_key
    
    logger.info("="*80)
    logger.info("TESTING HIGHLIGHTLY API STANDINGS FOR 2025 SEASON ONLY")
    logger.info("="*80)
    logger.info(f"Testing {len(LEAGUE_MAPPINGS)} leagues")
    logger.info(f"Season: {datetime.now().year} (2025) only")
    logger.info(f"Leagues: {', '.join(LEAGUE_MAPPINGS.values())}")
    
    # Determine which API key to use
    if args.use_rapidapi:
        api_key = args.rapidapi_key or os.getenv('RAPIDAPI_KEY')
        if not api_key:
            logger.error("❌ RapidAPI key required when using --use-rapidapi")
            logger.info("   Set it via: --rapidapi-key YOUR_KEY")
            logger.info("   Or environment variable: RAPIDAPI_KEY")
            return
    else:
        api_key = args.highlightly_key or args.rapidapi_key or os.getenv('HIGHLIGHTLY_API_KEY') or os.getenv('RAPIDAPI_KEY')
    
    # If testing a specific league, filter the mappings
    leagues_to_test = LEAGUE_MAPPINGS
    if args.league_id:
        if args.league_id not in LEAGUE_MAPPINGS:
            logger.error(f"❌ League ID {args.league_id} not found in LEAGUE_MAPPINGS")
            logger.info(f"Available league IDs: {list(LEAGUE_MAPPINGS.keys())}")
            return
        leagues_to_test = {args.league_id: LEAGUE_MAPPINGS[args.league_id]}
        logger.info(f"🎯 Testing only league: {leagues_to_test[args.league_id]} (ID: {args.league_id})")
    
    highlightly_results = test_highlightly_standings(
        api_key=api_key, 
        delay=args.delay, 
        leagues_to_test=leagues_to_test,
        use_rapidapi=args.use_rapidapi
    )
    
    # Display summary
    display_standings_summary(highlightly_results)
    
    # Final summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    
    highlightly_success = sum(1 for r in highlightly_results.values() if r['success']) if highlightly_results else 0
    
    logger.info(f"Highlightly API: {highlightly_success}/{len(LEAGUE_MAPPINGS)} leagues successful")
    
    if highlightly_success > 0:
        logger.info("✅ Highlightly API can retrieve standings data!")
    else:
        logger.warning("⚠️ Highlightly API did not successfully retrieve standings data")
        logger.info("   Consider calculating standings from match results in database")


if __name__ == "__main__":
    main()

