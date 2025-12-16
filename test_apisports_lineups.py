#!/usr/bin/env python3
"""
Test API-Sports API for lineup images and league support
"""

import os
import requests
import json

# Your 9 leagues with correct API-Sports IDs
LEAGUES = {
    85: "Rugby Championship",              # API-Sports ID: 85
    76: "United Rugby Championship",       # API-Sports ID: 76
    37: "Currie Cup",                      # API-Sports ID: 37
    69: "Rugby World Cup",                 # API-Sports ID: 69
    71: "Super Rugby",                     # API-Sports ID: 71
    16: "French Top 14",                   # API-Sports ID: 16
    5: "English Premiership Rugby (ID 5)", # API-Sports ID: 5
    13: "English Premiership Rugby (ID 13)", # API-Sports ID: 13 (test both)
    51: "Six Nations Championship",        # API-Sports ID: 51
    84: "Rugby Union International Friendlies" # API-Sports ID: 84
}

def test_apisports_api():
    """Test API-Sports API for lineup images and league support"""
    
    # Get API key from environment
    api_key = os.getenv('APISPORTS_API_KEY', '')
    
    if not api_key:
        print("ERROR: APISPORTS_API_KEY not found in environment")
        print("   Set it with: $env:APISPORTS_API_KEY='your-key' (PowerShell)")
        print("   Or: export APISPORTS_API_KEY='your-key' (Bash)")
        print("   Or check GitHub Secrets if running in Actions")
        return
    
    print("=" * 80)
    print("Testing API-Sports Rugby API for Lineup Images")
    print("=" * 80)
    print(f"API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else '***'}\n")
    
    base_url = "https://v1.rugby.api-sports.io"
    headers = {"x-apisports-key": api_key}
    
    # Test 1: Get available leagues
    print("1. Checking available leagues...")
    try:
        response = requests.get(f"{base_url}/leagues", headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"   Response keys: {list(data.keys())}")
        
        if 'response' in data:
            leagues = data['response']
            print(f"   Found {len(leagues)} leagues")
            
            # Verify our league IDs exist
            print("\n   Verifying your league IDs:")
            found_count = 0
            for api_id, league_name in LEAGUES.items():
                found = False
                for league in leagues:
                    if league.get('id') == api_id:
                        print(f"   [OK] {league_name}: ID {api_id} exists as '{league.get('name')}'")
                        found = True
                        found_count += 1
                        break
                if not found:
                    print(f"   [X] {league_name}: ID {api_id} NOT FOUND in API-Sports")
            
            print(f"\n   Verified {found_count} of {len(LEAGUES)} league IDs")
        else:
            print(f"   Unexpected response structure: {list(data.keys())}")
            print(f"   Full response: {json.dumps(data, indent=2)[:500]}")
    except Exception as e:
        print(f"   ERROR: {e}")
        if hasattr(e, 'response'):
            print(f"   Response: {e.response.text[:200]}")
    
    # Test 2: Get a sample game to check for lineup/image data
    print("\n2. Checking game data structure for lineups/images across all your leagues...")
    
    # Use correct league IDs provided by user
    test_leagues = [
        (16, "French Top 14", [2024, 2023, 2022]),
        (76, "United Rugby Championship", [2024, 2023, 2022]),
        (85, "Rugby Championship", [2024, 2023, 2022]),
        (69, "Rugby World Cup", [2024, 2023, 2022]),
        (37, "Currie Cup", [2024, 2023, 2022]),
        (51, "Six Nations", [2024, 2023, 2022]),
        (71, "Super Rugby", [2024, 2023, 2022]),
        (84, "Rugby Union International Friendlies", [2024, 2023, 2022]),
        (5, "English Premiership (ID 5)", [2024, 2023, 2022]),
        (13, "English Premiership (ID 13)", [2024, 2023, 2022]),
    ]
    
    sample_games_by_league = {}
    fixture_ids_by_league = {}
    
    for league_id, league_name, seasons in test_leagues:
        print(f"\n   Testing league: {league_name} (ID: {league_id})")
        for season in seasons:
            try:
                games_response = requests.get(
                    f"{base_url}/games",
                    headers=headers,
                    params={"league": league_id, "season": season},
                    timeout=10
                )
                
                if games_response.status_code == 200:
                    games_data = games_response.json()
                    if 'response' in games_data and len(games_data['response']) > 0:
                        sample_game = games_data['response'][0]
                        # API-Sports uses 'id' directly, not 'fixture.id'
                        fixture_id = sample_game.get('id')
                        sample_games_by_league[league_id] = sample_game
                        fixture_ids_by_league[league_id] = fixture_id
                        print(f"   [OK] Found {len(games_data['response'])} games for {league_name} season {season}")
                        print(f"   Using fixture ID: {fixture_id}")
                        break
            except Exception as e:
                print(f"   Error: {e}")
    
    # Test first league found for detailed structure
    if sample_games_by_league:
        first_league_id = list(sample_games_by_league.keys())[0]
        sample_game = sample_games_by_league[first_league_id]
        fixture_id = fixture_ids_by_league[first_league_id]
        
        print(f"\n   Detailed analysis for first league found:")
        print(f"\n   Game data structure:")
        print(f"   Game keys: {list(sample_game.keys())}")
        
        # Check for lineup/image related fields
        all_keys = list(sample_game.keys())
        image_fields = [k for k in all_keys if 'image' in k.lower() or 'photo' in k.lower() or 'logo' in k.lower()]
        lineup_fields = [k for k in all_keys if 'lineup' in k.lower() or 'squad' in k.lower() or 'player' in k.lower()]
        
        if image_fields:
            print(f"   [OK] Image fields found: {image_fields}")
        else:
            print(f"   [X] No image fields found in game data")
        
        if lineup_fields:
            print(f"   [OK] Lineup fields found: {lineup_fields}")
        else:
            print(f"   [X] No lineup fields found in game data")
        
        # Check teams data
        if 'teams' in sample_game:
            print(f"\n   Teams data:")
            for team_key in ['home', 'away']:
                if team_key in sample_game['teams']:
                    team = sample_game['teams'][team_key]
                    team_keys = list(team.keys())
                    print(f"   {team_key} team keys: {team_keys}")
                    team_images = [k for k in team_keys if 'image' in k.lower() or 'logo' in k.lower()]
                    if team_images:
                        print(f"   [OK] {team_key} team has images: {team_images}")
                        # Show actual image URLs if available
                        for img_key in team_images:
                            img_val = team.get(img_key)
                            if img_val:
                                print(f"      {img_key}: {img_val[:80]}...")
    else:
        print("   [X] Could not find any games to test")
    
    # Test 3: Check for lineups endpoint with actual fixture IDs from all leagues
    print("\n3. Testing lineups endpoint across all leagues with games...")
    
    if fixture_ids_by_league:
        print(f"   Testing {len(fixture_ids_by_league)} leagues for lineup data...\n")
        
        leagues_with_lineups = []
        leagues_without_lineups = []
        
        for league_id, fixture_id in fixture_ids_by_league.items():
            league_name = next((name for lid, name, _ in test_leagues if lid == league_id), f"League {league_id}")
            try:
                response = requests.get(
                    f"{base_url}/lineups",
                    headers=headers,
                    params={"fixture": fixture_id},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results_count = data.get('results', 0)
                    
                    if results_count > 0 and 'response' in data and len(data['response']) > 0:
                        lineup_data = data['response'][0]
                        print(f"   [OK] {league_name} (ID {league_id}): Lineups available!")
                        print(f"        Fixture {fixture_id} has {results_count} lineup result(s)")
                        print(f"        Lineup keys: {list(lineup_data.keys())}")
                        
                        # Check for players with images
                        has_player_images = False
                        for team_key in ['home', 'away']:
                            if team_key in lineup_data:
                                team_lineup = lineup_data[team_key]
                                for key in ['players', 'startXI', 'starters', 'squad', 'lineup']:
                                    if key in team_lineup:
                                        players = team_lineup.get(key, [])
                                        if players and len(players) > 0:
                                            first_player = players[0]
                                            player_images = [k for k in first_player.keys() if 'image' in k.lower() or 'photo' in k.lower()]
                                            if player_images:
                                                has_player_images = True
                                                print(f"        [OK] Players have images: {player_images}")
                                                break
                        
                        if not has_player_images:
                            print(f"        [X] No player images found")
                        
                        leagues_with_lineups.append((league_id, league_name))
                    else:
                        print(f"   [X] {league_name} (ID {league_id}): No lineup data (results: {results_count})")
                        leagues_without_lineups.append((league_id, league_name))
                else:
                    print(f"   [X] {league_name} (ID {league_id}): Error {response.status_code}")
                    leagues_without_lineups.append((league_id, league_name))
            except Exception as e:
                print(f"   [X] {league_name} (ID {league_id}): Error - {str(e)[:50]}")
                leagues_without_lineups.append((league_id, league_name))
        
        # Summary
        print(f"\n   SUMMARY:")
        print(f"   Leagues WITH lineup data: {len(leagues_with_lineups)}")
        for lid, name in leagues_with_lineups:
            print(f"      - {name} (ID {lid})")
        print(f"   Leagues WITHOUT lineup data: {len(leagues_without_lineups)}")
        for lid, name in leagues_without_lineups:
            print(f"      - {name} (ID {lid})")
    else:
        print("   [X] No fixture IDs available - skipping lineup test")
    
    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    test_apisports_api()
