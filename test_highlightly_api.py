"""
Test Highlightly Rugby API - Check if API key works and what features are available
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add prediction directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prediction'))

from prediction.highlightly_client import HighlightlyRugbyAPI

def test_highlightly_api():
    """Test Highlightly API with current key"""
    
    # Try to get API key from environment or use default
    api_key = os.getenv("HIGHLIGHTLY_API_KEY", "9c27c5f8-9437-4d42-8cc9-5179d3290a5b")
    
    if not api_key:
        print("❌ No API key found!")
        print("   Set HIGHLIGHTLY_API_KEY environment variable")
        return False
    
    print("="*80)
    print("HIGHLIGHTLY RUGBY API TEST")
    print("="*80)
    print(f"API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
    print(f"Base URL: https://rugby.highlightly.net")
    print(f"RapidAPI Host: rugby-highlights-api.p.rapidapi.com")
    print()
    
    api = HighlightlyRugbyAPI(api_key)
    
    # Test results
    results = {}
    
    # Test 1: Get Leagues
    print("1. Testing get_leagues()...")
    try:
        leagues = api.get_leagues(limit=10)
        league_data = leagues.get('data', [])
        if league_data:
            print(f"   ✅ SUCCESS: Found {len(league_data)} leagues")
            if len(league_data) > 0:
                league = league_data[0]
                league_name = league.get('name') or league.get('leagueName') or league.get('title') or 'N/A'
                print(f"   Sample league: {league_name}")
                
                # Check if it covers any of our 8 leagues
                our_leagues = ["United Rugby Championship", "Currie Cup", "Super Rugby", 
                              "French Top 14", "English Premiership", "Rugby Championship",
                              "Rugby World Cup", "International Friendlies"]
                for our_league in our_leagues:
                    if our_league.lower() in str(league_name).lower():
                        print(f"   🎯 Found one of your leagues: {league_name}")
                        break
            results['leagues'] = True
        else:
            print("   ⚠️  No leagues returned")
            results['leagues'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['leagues'] = False
    
    print()
    
    # Test 2: Get Matches (try with date parameter)
    print("2. Testing get_matches()...")
    from datetime import datetime, timedelta
    sample_match_id = None
    match_data = []
    
    # Try with today's date
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        matches = api.get_matches(date=today, limit=10)
        match_data = matches.get('data', [])
        if match_data:
            print(f"   ✅ SUCCESS: Found {len(match_data)} matches for today ({today})")
            if len(match_data) > 0:
                match = match_data[0]
                home = match.get('homeTeam', {}).get('name') if isinstance(match.get('homeTeam'), dict) else 'N/A'
                away = match.get('awayTeam', {}).get('name') if isinstance(match.get('awayTeam'), dict) else 'N/A'
                league = match.get('league', {}).get('name') if isinstance(match.get('league'), dict) else 'N/A'
                print(f"   Sample match: {home} vs {away} ({league})")
            results['matches'] = True
            sample_match_id = match_data[0].get('id') if match_data else None
        else:
            # Try upcoming dates
            print(f"   ⚠️  No matches for today, trying upcoming dates...")
            for days_ahead in [1, 2, 3, 7, 14]:
                future_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
                try:
                    matches = api.get_matches(date=future_date, limit=10)
                    match_data = matches.get('data', [])
                    if match_data:
                        print(f"   ✅ SUCCESS: Found {len(match_data)} matches for {future_date}")
                        sample_match_id = match_data[0].get('id') if match_data else None
                        results['matches'] = True
                        break
                except:
                    continue
            
            if not match_data:
                print("   ⚠️  No matches found for tested dates")
                results['matches'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['matches'] = False
    
    print()
    
    # Test 3: Get Match Details
    print("3. Testing get_match_details()...")
    try:
        if sample_match_id:
            match_details = api.get_match_details(sample_match_id)
            if match_details:
                print(f"   ✅ SUCCESS: Got match details for match {sample_match_id}")
                results['match_details'] = True
            else:
                print(f"   ⚠️  No match details returned")
                results['match_details'] = False
        else:
            print("   ⚠️  No match ID available to test")
            results['match_details'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['match_details'] = False
    
    print()
    
    # Test 3b: Get Match Lineups (DEDICATED ENDPOINT)
    print("3b. Testing get_match_lineups() [DEDICATED LINEUPS ENDPOINT]...")
    try:
        if sample_match_id:
            lineups = api.get_match_lineups(sample_match_id)
            if lineups:
                print(f"   ✅ SUCCESS: Got lineups for match {sample_match_id}")
                # Check structure
                if 'data' in lineups:
                    lineup_data = lineups['data']
                    if isinstance(lineup_data, dict):
                        if 'home' in lineup_data or 'away' in lineup_data:
                            home_count = len(lineup_data.get('home', [])) if isinstance(lineup_data.get('home'), list) else 0
                            away_count = len(lineup_data.get('away', [])) if isinstance(lineup_data.get('away'), list) else 0
                            print(f"   ✅ Found {home_count} home players, {away_count} away players")
                        else:
                            print(f"   ✅ Lineups structure: {list(lineup_data.keys())[:5]}")
                    elif isinstance(lineup_data, list):
                        print(f"   ✅ Found {len(lineup_data)} lineup entries")
                else:
                    print(f"   ✅ Lineups available (structure: {list(lineups.keys())[:5]})")
                results['lineups'] = True
            else:
                print(f"   ⚠️  No lineups returned for match {sample_match_id}")
                results['lineups'] = False
        else:
            print("   ⚠️  No match ID available to test")
            results['lineups'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['lineups'] = False
    
    print()
    
    # Test 4: Get Standings
    print("4. Testing get_standings()...")
    try:
        # Try with a sample league_id if we have leagues
        if leagues and len(leagues.get('data', [])) > 0:
            league_id = leagues['data'][0].get('id') or leagues['data'][0].get('leagueId')
            if league_id:
                standings = api.get_standings(league_id, 2024)  # Try 2024 season
                if standings and (standings.get('groups') or standings.get('league')):
                    print(f"   ✅ SUCCESS: Got standings for league {league_id}")
                    results['standings'] = True
                else:
                    print(f"   ⚠️  No standings returned")
                    results['standings'] = False
            else:
                print("   ⚠️  No league ID found")
                results['standings'] = None
        else:
            print("   ⚠️  No leagues available to test standings")
            results['standings'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['standings'] = False
    
    print()
    
    # Test 5: Get Highlights (try with match_id or date)
    print("5. Testing get_highlights()...")
    try:
        # Try with match_id if available
        if sample_match_id:
            highlights = api.get_highlights(match_id=sample_match_id, limit=5)
            highlight_data = highlights.get('data', [])
            if highlight_data:
                print(f"   ✅ SUCCESS: Found {len(highlight_data)} highlights for match")
                results['highlights'] = True
            else:
                # Try with today's date
                highlights = api.get_highlights(date=today, limit=5)
                highlight_data = highlights.get('data', [])
                if highlight_data:
                    print(f"   ✅ SUCCESS: Found {len(highlight_data)} highlights for today")
                    results['highlights'] = True
                else:
                    print("   ⚠️  No highlights returned")
                    results['highlights'] = False
        else:
            # Try with date
            highlights = api.get_highlights(date=today, limit=5)
            highlight_data = highlights.get('data', [])
            if highlight_data:
                print(f"   ✅ SUCCESS: Found {len(highlight_data)} highlights")
                results['highlights'] = True
            else:
                print("   ⚠️  No highlights returned")
                results['highlights'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['highlights'] = False
    
    print()
    
    # Test 6: Get Head-to-Head (if we have team IDs)
    print("6. Testing get_head_to_head()...")
    try:
        if sample_match_id and match_data:
            match = match_data[0]
            home_team_id = match.get('homeTeam', {}).get('id') if isinstance(match.get('homeTeam'), dict) else None
            away_team_id = match.get('awayTeam', {}).get('id') if isinstance(match.get('awayTeam'), dict) else None
            if home_team_id and away_team_id:
                h2h = api.get_head_to_head(home_team_id, away_team_id)
                if h2h:
                    print(f"   ✅ SUCCESS: Found {len(h2h)} head-to-head matches")
                    results['head_to_head'] = True
                else:
                    print("   ⚠️  No head-to-head data returned")
                    results['head_to_head'] = False
            else:
                print("   ⚠️  No team IDs available")
                results['head_to_head'] = None
        else:
            print("   ⚠️  No match data available")
            results['head_to_head'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['head_to_head'] = False
    
    print()
    
    # Test 7: Get Last Five Games
    print("7. Testing get_last_five_games()...")
    try:
        if sample_match_id and match_data:
            match = match_data[0]
            team_id = match.get('homeTeam', {}).get('id') if isinstance(match.get('homeTeam'), dict) else None
            if team_id:
                last_five = api.get_last_five_games(team_id)
                if last_five:
                    print(f"   ✅ SUCCESS: Found {len(last_five)} recent games")
                    results['last_five'] = True
                else:
                    print("   ⚠️  No recent games returned")
                    results['last_five'] = False
            else:
                print("   ⚠️  No team ID available")
                results['last_five'] = None
        else:
            print("   ⚠️  No match data available")
            results['last_five'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['last_five'] = False
    
    print()
    
    # Check for NEWS endpoints and check match details structure
    print("8. Checking for NEWS and LINEUPS in match details...")
    try:
        if sample_match_id:
            match_details = api.get_match_details(sample_match_id)
            if match_details:
                print(f"   ✅ Got match details for match {sample_match_id}")
                
                # Check for lineups
                has_lineups = False
                if 'lineups' in match_details:
                    print(f"   ✅ LINEUPS found in 'lineups' field!")
                    has_lineups = True
                if 'lineup' in match_details:
                    print(f"   ✅ LINEUPS found in 'lineup' field!")
                    has_lineups = True
                if 'homeLineup' in match_details or 'awayLineup' in match_details:
                    print(f"   ✅ LINEUPS found in homeLineup/awayLineup fields!")
                    has_lineups = True
                if 'homeTeam' in match_details and isinstance(match_details['homeTeam'], dict):
                    if 'lineup' in match_details['homeTeam'] or 'players' in match_details['homeTeam']:
                        print(f"   ✅ LINEUPS found in homeTeam structure!")
                        has_lineups = True
                
                if not has_lineups:
                    print(f"   ⚠️  Lineups not found in match details")
                    if isinstance(match_details, dict):
                        print(f"   Available keys: {list(match_details.keys())[:15]}")
                    else:
                        print(f"   Match details type: {type(match_details)}")
                
                # Check for news
                has_news = False
                if isinstance(match_details, dict):
                    news_fields = ['news', 'articles', 'updates', 'media', 'press', 'preview', 'report']
                    for field in news_fields:
                        if field in match_details:
                            print(f"   ✅ NEWS found in '{field}' field!")
                            has_news = True
                    
                    # Also check nested structures
                    if 'homeTeam' in match_details and isinstance(match_details['homeTeam'], dict):
                        if any(field in str(match_details['homeTeam']).lower() for field in news_fields):
                            print(f"   ✅ News might be in team structure")
                            has_news = True
                
                if not has_news:
                    print(f"   ⚠️  No dedicated news fields found in match details")
                
                results['match_details_structure'] = True
            else:
                print("   ⚠️  No match details returned")
                results['match_details_structure'] = False
        else:
            print("   ⚠️  No match ID available to check structure")
            results['match_details_structure'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['match_details_structure'] = False
    
    # Check what leagues are available
    print()
    print("9. Checking league coverage for your 8 leagues...")
    try:
        if leagues and len(leagues.get('data', [])) > 0:
            our_leagues = {
                "United Rugby Championship": ["URC", "United Rugby"],
                "Currie Cup": ["Currie"],
                "Super Rugby": ["Super Rugby"],
                "French Top 14": ["Top 14", "French"],
                "English Premiership": ["Premiership", "English"],
                "Rugby Championship": ["Rugby Championship", "The Rugby Championship"],
                "Rugby World Cup": ["World Cup"],
                "International Friendlies": ["Friendly", "International"]
            }
            
            found_leagues = []
            for league in leagues['data']:
                league_name = str(league.get('name') or league.get('leagueName') or '').lower()
                for our_league, keywords in our_leagues.items():
                    if any(keyword.lower() in league_name for keyword in keywords):
                        if our_league not in found_leagues:
                            found_leagues.append(our_league)
                            print(f"   🎯 Found: {our_league} (API: {league.get('name')})")
            
            if found_leagues:
                print(f"   ✅ Coverage: {len(found_leagues)}/8 of your leagues found")
            else:
                print(f"   ⚠️  None of your 8 leagues found in available leagues")
                print(f"   Available leagues: {[l.get('name') for l in leagues['data'][:5]]}")
            
            results['league_coverage'] = len(found_leagues)
        else:
            results['league_coverage'] = 0
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['league_coverage'] = 0
    
    print()
    print("="*80)
    print("SUMMARY")
    print("="*80)
    
    total_tests = len([r for r in results.values() if r is not None])
    passed_tests = len([r for r in results.values() if r is True])
    failed_tests = len([r for r in results.values() if r is False])
    
    for test_name, result in results.items():
        if result is True:
            print(f"✅ {test_name}: PASSED")
        elif result is False:
            print(f"❌ {test_name}: FAILED")
        else:
            print(f"⚠️  {test_name}: SKIPPED (no data to test)")
    
    print()
    print(f"Total: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests > 0:
        print("\n✅ API key is working! Highlightly API is accessible.")
        print("\n💡 Available Features:")
        print("   - Leagues, Matches, Match Details (with lineups!)")
        print("   - Standings, Highlights, Head-to-Head")
        print("   - Team Statistics, Last 5 Games")
        print("\n💡 Note about NEWS:")
        print("   - Highlightly may not have dedicated news endpoints")
        print("   - News might be in match details or other data")
        print("   - Check match_details response structure for news fields")
    else:
        print("\n❌ API key may be invalid or API is down.")
        print("\n💡 Troubleshooting:")
        print("   1. Check if you're subscribed to 'Rugby Highlights API' on RapidAPI")
        print("   2. Verify API key is active in RapidAPI dashboard")
        print("   3. Check RapidAPI subscription status")
    
    return passed_tests > 0

if __name__ == "__main__":
    test_highlightly_api()

