"""
Test script to verify SportDevs API key works with all endpoints
Tests the new news and lineups endpoints
"""

import os
import sys
from typing import Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add prediction directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prediction'))

from prediction.sportdevs_client import SportDevsClient

def test_base_url(base_url: str, api_key: str, endpoint: str = "leagues", use_rapidapi: bool = False, rapidapi_host: str = "") -> Tuple[bool, str]:
    """Test if a base URL works with the API key"""
    import requests
    
    url = f"{base_url.rstrip('/')}/{endpoint}"
    
    if use_rapidapi:
        # RapidAPI format
        host = rapidapi_host or "rugby-highlights-api.p.rapidapi.com" or "rugby.sportdevs.com"
        headers = {
            "Accept": "application/json",
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": host
        }
    else:
        # Standard SportDevs format
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key
        }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True, f"✅ {base_url} - Status: {response.status_code}"
        else:
            error_msg = response.text[:100] if response.text else "No error message"
            return False, f"❌ {base_url} - Status: {response.status_code} - {error_msg}"
    except Exception as e:
        return False, f"❌ {base_url} - Error: {str(e)[:100]}"

def test_sportdevs_api():
    """Test SportDevs API with current key"""
    
    # Try to get API key from environment or use hardcoded one
    api_key = os.getenv("SPORTDEVS_API_KEY", "qwh9orOkZESulf4QBhf0IQ")
    
    if not api_key:
        print("❌ No API key found!")
        print("   Set SPORTDEVS_API_KEY environment variable or update the script")
        return False
    
    print("="*80)
    print("SPORTDEVS API KEY TEST")
    print("="*80)
    print(f"API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
    print()
    
    # First, test different possible base URLs and auth methods
    print("Testing different base URLs and authentication methods...")
    base_urls = [
        # Standard SportDevs format
        ("https://rugby.sportdevs.com", False, False),
        ("https://api.sportdevs.com", False, False),
        ("https://sportdevs.com/api", False, False),
        ("https://rugby.sportdevs.com/api", False, False),
        ("https://api.sportdevs.com/rugby", False, False),
        # RapidAPI format - different base URL
        ("https://rugby-highlights-api.p.rapidapi.com", True, True),
        ("https://api.rapidapi.com/rugby", True, True),
        ("https://rapidapi.com/sportdevs/api/rugby", True, True),
    ]
    
    working_url = None
    use_rapidapi = False
    rapidapi_host = ""
    for base_url, is_rapidapi, needs_host in base_urls:
        host = "rugby-highlights-api.p.rapidapi.com" if needs_host else ""
        success, message = test_base_url(base_url, api_key, use_rapidapi=is_rapidapi, rapidapi_host=host)
        auth_type = " (RapidAPI)" if is_rapidapi else " (Standard)"
        print(f"   {message}{auth_type}")
        if success:
            working_url = base_url
            use_rapidapi = is_rapidapi
            rapidapi_host = host
            break
    
    print()
    
    if not working_url:
        print("⚠️  None of the tested base URLs worked.")
        print("   This could mean:")
        print("   - The API key is invalid or expired")
        print("   - The API service is down")
        print("   - The API uses a different base URL (check SportDevs documentation)")
        print("   - The API might be accessed through RapidAPI instead")
        print()
        print("   Trying with default URL anyway...")
        working_url = "https://rugby.sportdevs.com"
    else:
        print(f"✅ Found working base URL: {working_url}")
        print()
    
    # Create client with working URL (or default)
    # Note: If RapidAPI works, we may need to update SportDevsClient to support it
    if use_rapidapi:
        print(f"⚠️  RapidAPI format detected - SportDevsClient may need updates for RapidAPI")
        print(f"   RapidAPI Host: {rapidapi_host}")
        print()
    
    client = SportDevsClient(api_key, base_url=working_url)
    
    # Test results
    results = {}
    
    # Test 1: Get Leagues
    print("1. Testing get_leagues()...")
    try:
        leagues = client.get_leagues()
        if leagues:
            print(f"   ✅ SUCCESS: Found {len(leagues)} leagues")
            if len(leagues) > 0:
                league_info = leagues[0]
                league_name = league_info.get('name') or league_info.get('league_name') or league_info.get('title') or 'N/A'
                print(f"   Sample league: {league_name}")
                # Check if it covers any of our 8 leagues
                our_leagues = ["United Rugby Championship", "Currie Cup", "Super Rugby", 
                              "French Top 14", "English Premiership", "Rugby Championship",
                              "Rugby World Cup"]
                for our_league in our_leagues:
                    if our_league.lower() in str(league_name).lower():
                        print(f"   🎯 Found one of your leagues: {league_name}")
                        break
            results['leagues'] = True
        else:
            print("   ⚠️  No leagues returned (may be empty or API issue)")
            results['leagues'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['leagues'] = False
    
    print()
    
    # Test 2: Get Matches
    print("2. Testing get_all_matches()...")
    try:
        matches = client.get_all_matches()
        if matches:
            print(f"   ✅ SUCCESS: Found {len(matches)} matches")
            if len(matches) > 0:
                match = matches[0]
                print(f"   Sample match: {match.get('home_team', 'N/A')} vs {match.get('away_team', 'N/A')}")
            results['matches'] = True
        else:
            print("   ⚠️  No matches returned")
            results['matches'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['matches'] = False
    
    print()
    
    # Test 3: Get Standings
    print("3. Testing get_standings()...")
    try:
        standings = client.get_standings()
        if standings:
            print(f"   ✅ SUCCESS: Found {len(standings)} standings entries")
            results['standings'] = True
        else:
            print("   ⚠️  No standings returned")
            results['standings'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['standings'] = False
    
    print()
    
    # Test 4: Get Match Lineups (NEW)
    print("4. Testing get_match_lineups() [NEW ENDPOINT]...")
    try:
        # Try with a sample match_id if we have matches
        if matches and len(matches) > 0:
            match_id = matches[0].get('id') or matches[0].get('match_id')
            if match_id:
                lineups = client.get_match_lineups(match_id)
                if lineups:
                    print(f"   ✅ SUCCESS: Got lineups for match {match_id}")
                    results['lineups'] = True
                else:
                    print(f"   ⚠️  No lineups returned for match {match_id}")
                    results['lineups'] = False
            else:
                print("   ⚠️  No match_id found in matches")
                results['lineups'] = False
        else:
            print("   ⚠️  No matches available to test lineups")
            results['lineups'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['lineups'] = False
    
    print()
    
    # Test 5: Get Team News (NEW)
    print("5. Testing get_team_news() [NEW ENDPOINT]...")
    try:
        # Try with a sample team_id if we have matches
        if matches and len(matches) > 0:
            team_id = matches[0].get('home_team_id') or matches[0].get('team_id')
            if team_id:
                news = client.get_team_news(team_id, limit=5)
                if news:
                    print(f"   ✅ SUCCESS: Found {len(news)} news items for team {team_id}")
                    results['team_news'] = True
                else:
                    print(f"   ⚠️  No news returned for team {team_id}")
                    results['team_news'] = False
            else:
                print("   ⚠️  No team_id found in matches")
                results['team_news'] = False
        else:
            print("   ⚠️  No matches available to test team news")
            results['team_news'] = None
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['team_news'] = False
    
    print()
    
    # Test 6: Get League News (NEW)
    print("6. Testing get_league_news() [NEW ENDPOINT]...")
    try:
        news = client.get_league_news(limit=5)
        if news:
            print(f"   ✅ SUCCESS: Found {len(news)} league news items")
            results['league_news'] = True
        else:
            print("   ⚠️  No league news returned")
            results['league_news'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['league_news'] = False
    
    print()
    
    # Test 7: Get All News (NEW)
    print("7. Testing get_all_news() [NEW ENDPOINT]...")
    try:
        news = client.get_all_news(limit=5)
        if news:
            print(f"   ✅ SUCCESS: Found {len(news)} news items")
            results['all_news'] = True
        else:
            print("   ⚠️  No news returned")
            results['all_news'] = False
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        results['all_news'] = False
    
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
        print("\n✅ API key is working! At least some endpoints are accessible.")
        print("\n💡 Next steps:")
        print("   - Check if the API covers your 8 leagues")
        print("   - Test news endpoints with specific league IDs")
        print("   - Test lineups with actual match IDs")
    else:
        print("\n❌ API key may be invalid or API is down.")
        print("\n💡 Troubleshooting:")
        print("   1. Check where you got the API key:")
        print("      - SportDevs Dashboard: https://sportdevs.com/dashboard")
        print("      - RapidAPI: https://rapidapi.com")
        print("   2. API keys are NOT interchangeable between platforms!")
        print("   3. If key is from RapidAPI:")
        print("      - Need to use RapidAPI base URL: rugby-highlights-api.p.rapidapi.com")
        print("      - Need RapidAPI headers: X-RapidAPI-Key, X-RapidAPI-Host")
        print("   4. If key is from SportDevs Dashboard:")
        print("      - Verify key is active in dashboard")
        print("      - Check if subscription is active")
        print("   5. 521 errors usually mean:")
        print("      - Server is down (check SportDevs status)")
        print("      - API key is invalid/expired")
        print("      - Wrong platform (RapidAPI vs Dashboard)")
        print("   6. Contact SportDevs support if key should be working")
    
    return passed_tests > 0

if __name__ == "__main__":
    test_sportdevs_api()

