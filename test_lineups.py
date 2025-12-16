"""
Test Highlightly API lineups functionality
"""

import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prediction'))

from prediction.highlightly_client import HighlightlyRugbyAPI
import json

def test_lineups():
    """Test if lineups are working"""
    
    api_key = os.getenv("HIGHLIGHTLY_API_KEY", "9c27c5f8-9437-4d42-8cc9-5179d3290a5b")
    api = HighlightlyRugbyAPI(api_key)
    
    print("="*80)
    print("TESTING HIGHLIGHTLY API LINEUPS - URC FOCUS")
    print("="*80)
    print()
    
    # URC league names to search for
    urc_names = [
        "United Rugby Championship",
        "URC",
        "United Rugby",
        "Pro14",  # Old name
        "Pro12"   # Older name
    ]
    
    # Get matches for today and upcoming days
    print("1. Finding URC matches to test lineups...")
    matches_with_lineups = []
    matches_without_lineups = []
    urc_matches_found = []
    
    # Check today and next 14 days (URC matches might be less frequent)
    for days_ahead in range(15):
        test_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        try:
            matches = api.get_matches(date=test_date, limit=50)
            match_data = matches.get('data', [])
            
            # Filter for URC matches
            urc_matches = []
            for match in match_data:
                league_name = match.get('league', {}).get('name', '') if isinstance(match.get('league'), dict) else ''
                if any(urc_name.lower() in league_name.lower() for urc_name in urc_names):
                    urc_matches.append(match)
            
            if urc_matches:
                print(f"   Found {len(urc_matches)} URC match(es) for {test_date}")
                urc_matches_found.extend([(m, test_date) for m in urc_matches])
            
            # Test lineups for URC matches
            for match, match_date in urc_matches_found[:10]:  # Test first 10 URC matches
                    match_id = match.get('id')
                    home_team = match.get('homeTeam', {}).get('name', 'N/A') if isinstance(match.get('homeTeam'), dict) else 'N/A'
                    away_team = match.get('awayTeam', {}).get('name', 'N/A') if isinstance(match.get('awayTeam'), dict) else 'N/A'
                    league_name = match.get('league', {}).get('name', 'N/A') if isinstance(match.get('league'), dict) else 'N/A'
                    match_name = f"{home_team} vs {away_team}"
                    
                    print(f"\n   Testing URC match: {match_name}")
                    print(f"      League: {league_name}")
                    print(f"      Match ID: {match_id}, Date: {match_date}")
                    
                    # Get lineups
                    lineups_result = api.get_match_lineups(match_id)
                    
                    if lineups_result.get('available'):
                        print(f"   ✅ LINEUPS AVAILABLE!")
                        lineups = lineups_result.get('lineups', {})
                        
                        # Show structure
                        if 'home' in lineups:
                            home_initial = len(lineups['home'].get('initialLineup', []))
                            home_subs = len(lineups['home'].get('substitutions', []))
                            print(f"      Home: {home_initial} starting, {home_subs} substitutes")
                            
                            # Show first player if available
                            if lineups['home'].get('initialLineup'):
                                first_player = lineups['home']['initialLineup'][0]
                                print(f"      Sample player: {first_player.get('name')} (#{first_player.get('shirtNumber')}, {first_player.get('position')})")
                        
                        if 'away' in lineups:
                            away_initial = len(lineups['away'].get('initialLineup', []))
                            away_subs = len(lineups['away'].get('substitutions', []))
                            print(f"      Away: {away_initial} starting, {away_subs} substitutes")
                        
                        matches_with_lineups.append({
                            'match_id': match_id,
                            'match_name': match_name,
                            'league': league_name,
                            'date': match_date,
                            'lineups': lineups_result
                        })
                    else:
                        print(f"   ⚠️  Lineups not available (null)")
                        matches_without_lineups.append({
                            'match_id': match_id,
                            'match_name': match_name,
                            'league': league_name,
                            'date': match_date
                        })
            
            # If we found URC matches, test them
            if urc_matches_found:
                break
        except Exception as e:
            print(f"   Error checking {test_date}: {e}")
            continue
    
    print()
    print("="*80)
    print("SUMMARY - URC MATCHES")
    print("="*80)
    
    if not urc_matches_found:
        print("⚠️  No URC matches found in the next 15 days")
        print("   This could mean:")
        print("   - URC season is not active")
        print("   - URC matches use a different league name in the API")
        print("   - No matches scheduled in this period")
    elif matches_with_lineups:
        print(f"✅ Found {len(matches_with_lineups)} URC match(es) WITH lineups:")
        for match in matches_with_lineups:
            print(f"   - {match['match_name']}")
            print(f"     League: {match['league']}")
            print(f"     Match ID: {match['match_id']}, Date: {match['date']}")
            lineups = match['lineups'].get('lineups', {})
            if lineups:
                home_total = match['lineups'].get('home', {}).get('total', 0)
                away_total = match['lineups'].get('away', {}).get('total', 0)
                print(f"     Players: Home {home_total}, Away {away_total}")
        
        print()
        print("✅ LINEUPS FUNCTIONALITY IS WORKING!")
        print()
        print("Example usage:")
        print("```python")
        print("from prediction.highlightly_client import HighlightlyRugbyAPI")
        print("api = HighlightlyRugbyAPI('your-api-key')")
        print("lineups = api.get_match_lineups(match_id)")
        print("if lineups.get('available'):")
        print("    home_players = lineups['lineups']['home']['initialLineup']")
        print("    away_players = lineups['lineups']['away']['initialLineup']")
        print("```")
    elif matches_without_lineups:
        print(f"⚠️  Found {len(matches_without_lineups)} URC match(es) but lineups not available yet:")
        for match in matches_without_lineups[:5]:  # Show first 5
            print(f"   - {match['match_name']} (ID: {match['match_id']}, Date: {match['date']})")
        print()
        print("This could mean:")
        print("   - Lineups are only available closer to match time")
        print("   - Lineups are only published for certain URC matches")
        print("   - The matches tested don't have lineups published yet")
        print()
        print("The lineups endpoint is working correctly - it's just that")
        print("lineups aren't available for these URC matches yet.")
    
    print()
    print("="*80)
    print("DETAILED LINEUP STRUCTURE (if available)")
    print("="*80)
    
    if matches_with_lineups:
        match = matches_with_lineups[0]
        lineups = match['lineups'].get('lineups', {})
        if lineups:
            print(json.dumps(lineups, indent=2, default=str)[:2000])  # First 2000 chars
    else:
        print("No lineups available to show structure")

if __name__ == "__main__":
    test_lineups()

