#!/usr/bin/env python3
"""
Test API-Sports API for standings and images
"""

import os
import requests
import json

# Your leagues with correct API-Sports IDs
LEAGUES = {
    16: "French Top 14",
    76: "United Rugby Championship",
    85: "Rugby Championship",
    69: "Rugby World Cup",
    37: "Currie Cup",
    51: "Six Nations Championship",
    71: "Super Rugby",
    84: "Rugby Union International Friendlies",
    5: "English Premiership (ID 5)",
    13: "English Premiership (ID 13)"
}

def test_apisports_standings_and_images():
    """Test API-Sports API for standings and images"""
    
    api_key = os.getenv('APISPORTS_API_KEY', '')
    
    if not api_key:
        print("ERROR: APISPORTS_API_KEY not found")
        return
    
    print("=" * 80)
    print("Testing API-Sports for Standings and Images")
    print("=" * 80)
    print(f"API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else '***'}\n")
    
    base_url = "https://v1.rugby.api-sports.io"
    headers = {"x-apisports-key": api_key}
    
    # Test 1: Check standings endpoint
    print("1. Testing STANDINGS endpoint...")
    print("-" * 80)
    
    standings_available = {}
    standings_not_available = {}
    
    for league_id, league_name in LEAGUES.items():
        if league_id == 13:  # Skip duplicate
            continue
            
        print(f"\n   Testing {league_name} (ID: {league_id})...")
        
        # Try different seasons
        for season in [2024, 2023, 2022]:
            try:
                response = requests.get(
                    f"{base_url}/standings",
                    headers=headers,
                    params={"league": league_id, "season": season},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', 0)
                    
                    if results > 0 and 'response' in data and len(data['response']) > 0:
                        standings_data = data['response'][0]
                        print(f"      [OK] Standings available for {season}!")
                        
                        # Check if standings_data is a list or dict
                        if isinstance(standings_data, list):
                            print(f"          Response is a list with {len(standings_data)} items")
                            if len(standings_data) > 0:
                                first_item = standings_data[0]
                                if isinstance(first_item, dict):
                                    print(f"          First item keys: {list(first_item.keys())}")
                                    # Check for league info
                                    if 'league' in first_item:
                                        print(f"          League: {first_item['league'].get('name', 'N/A')}")
                                    
                                    # Check team data in standings
                                    if 'team' in first_item:
                                        team = first_item['team']
                                        print(f"          Team keys: {list(team.keys())}")
                                        image_fields = [k for k in team.keys() if 'image' in k.lower() or 'logo' in k.lower()]
                                        if image_fields:
                                            print(f"          [OK] Team has images: {image_fields}")
                                            for img_key in image_fields:
                                                img_val = team.get(img_key)
                                                if img_val:
                                                    print(f"             {img_key}: {img_val}")
                                        else:
                                            print(f"          [X] No image fields in team data")
                        elif isinstance(standings_data, dict):
                            print(f"          Response is a dict, Keys: {list(standings_data.keys())}")
                            # Check what's in standings
                            if 'league' in standings_data:
                                print(f"          League info: {standings_data['league'].get('name', 'N/A')}")
                            
                            # Check for standings array
                            for key in ['standings', 'table', 'ranking', 'teams']:
                                if key in standings_data:
                                    standings_list = standings_data[key]
                                    if isinstance(standings_list, list) and len(standings_list) > 0:
                                        print(f"          Found {len(standings_list)} teams in '{key}'")
                                        first_team = standings_list[0]
                                        team_keys = list(first_team.keys())
                                        print(f"          Team keys: {team_keys}")
                                        image_fields = [k for k in team_keys if 'image' in k.lower() or 'logo' in k.lower()]
                                        if image_fields:
                                            print(f"          [OK] Team has images: {image_fields}")
                                            for img_key in image_fields:
                                                img_val = first_team.get(img_key)
                                                if img_val:
                                                    print(f"             {img_key}: {img_val[:80]}...")
                                        break
                        
                        standings_available[league_id] = (league_name, season, standings_data)
                        break
                    else:
                        if results == 0:
                            print(f"      [X] No standings data (results: 0)")
                elif response.status_code == 404:
                    print(f"      [X] Standings endpoint not found (404)")
                else:
                    print(f"      [X] Error {response.status_code}: {response.text[:100]}")
            except Exception as e:
                print(f"      [X] Error: {str(e)[:50]}")
        
        if league_id not in standings_available:
            standings_not_available[league_id] = league_name
    
    # Summary for standings
    print("\n" + "=" * 80)
    print("STANDINGS SUMMARY:")
    print(f"   Leagues WITH standings: {len(standings_available)}")
    for lid, (name, season, _) in standings_available.items():
        print(f"      - {name} (ID {lid}) - Season {season}")
    print(f"   Leagues WITHOUT standings: {len(standings_not_available)}")
    for lid, name in standings_not_available.items():
        print(f"      - {name} (ID {lid})")
    
    # Test 2: Check what images are available in games
    print("\n" + "=" * 80)
    print("2. Testing IMAGES available in GAMES...")
    print("-" * 80)
    
    # Get a sample game to check all image types
    print("\n   Getting sample game to check all image types...")
    try:
        # Use Top 14 as sample
        response = requests.get(
            f"{base_url}/games",
            headers=headers,
            params={"league": 16, "season": 2023},
            timeout=10
        )
        
        if response.status_code == 200:
            games_data = response.json()
            if 'response' in games_data and len(games_data['response']) > 0:
                game = games_data['response'][0]
                
                print(f"   Game ID: {game.get('id')}")
                print(f"   League: {game.get('league', {}).get('name', 'N/A')}")
                
                # Check all image fields in game
                all_image_fields = []
                
                # Teams
                if 'teams' in game:
                    for team_key in ['home', 'away']:
                        if team_key in game['teams']:
                            team = game['teams'][team_key]
                            team_images = [k for k in team.keys() if 'image' in k.lower() or 'logo' in k.lower() or 'photo' in k.lower()]
                            if team_images:
                                all_image_fields.extend([f"teams.{team_key}.{k}" for k in team_images])
                                for img_key in team_images:
                                    img_val = team.get(img_key)
                                    if img_val:
                                        print(f"   [OK] {team_key} team {img_key}: {img_val}")
                
                # League
                if 'league' in game:
                    league = game['league']
                    league_images = [k for k in league.keys() if 'image' in k.lower() or 'logo' in k.lower()]
                    if league_images:
                        all_image_fields.extend([f"league.{k}" for k in league_images])
                        for img_key in league_images:
                            img_val = league.get(img_key)
                            if img_val:
                                print(f"   [OK] League {img_key}: {img_val}")
                
                # Country
                if 'country' in game:
                    country = game['country']
                    country_images = [k for k in country.keys() if 'image' in k.lower() or 'logo' in k.lower()]
                    if country_images:
                        all_image_fields.extend([f"country.{k}" for k in country_images])
                        for img_key in country_images:
                            img_val = country.get(img_key)
                            if img_val:
                                print(f"   [OK] Country {img_key}: {img_val}")
                
                print(f"\n   Total image fields found in games: {len(all_image_fields)}")
                if all_image_fields:
                    print(f"   Image types: {all_image_fields}")
                else:
                    print(f"   [X] No images found in game data")
                
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 3: Check teams endpoint for more images
    print("\n" + "=" * 80)
    print("3. Testing TEAMS endpoint for images...")
    print("-" * 80)
    
    try:
        # Get teams for Top 14
        response = requests.get(
            f"{base_url}/teams",
            headers=headers,
            params={"league": 16, "season": 2023},
            timeout=10
        )
        
        if response.status_code == 200:
            teams_data = response.json()
            if 'response' in teams_data and len(teams_data['response']) > 0:
                team = teams_data['response'][0]
                print(f"   [OK] Teams endpoint works")
                print(f"   Team keys: {list(team.keys())}")
                
                team_images = [k for k in team.keys() if 'image' in k.lower() or 'logo' in k.lower() or 'photo' in k.lower()]
                if team_images:
                    print(f"   [OK] Team image fields: {team_images}")
                    for img_key in team_images:
                        img_val = team.get(img_key)
                        if img_val:
                            print(f"      {img_key}: {img_val}")
                else:
                    print(f"   [X] No image fields in team data")
            else:
                print(f"   [X] No teams found (response empty)")
                print(f"   Response keys: {list(teams_data.keys())}")
        else:
            print(f"   [X] Error {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 4: Check standings for team images
    print("\n" + "=" * 80)
    print("4. Checking STANDINGS for team images...")
    print("-" * 80)
    
    if standings_available:
        # Check first league with standings
        first_league_id = list(standings_available.keys())[0]
        league_name, season, standings_data = standings_available[first_league_id]
        print(f"\n   Checking {league_name} (ID {first_league_id}) standings...")
        
        if isinstance(standings_data, list) and len(standings_data) > 0:
            first_team_standing = standings_data[0]
            if 'team' in first_team_standing:
                team = first_team_standing['team']
                print(f"   Team data keys: {list(team.keys())}")
                team_images = [k for k in team.keys() if 'image' in k.lower() or 'logo' in k.lower()]
                if team_images:
                    print(f"   [OK] Standings team has images: {team_images}")
                    for img_key in team_images:
                        img_val = team.get(img_key)
                        if img_val:
                            print(f"      {img_key}: {img_val}")
                else:
                    print(f"   [X] No images in standings team data")
    
    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)

if __name__ == "__main__":
    test_apisports_standings_and_images()

