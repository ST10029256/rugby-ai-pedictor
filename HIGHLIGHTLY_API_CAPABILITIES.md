# Highlightly Rugby API - Capabilities & Status

## ✅ API Status: WORKING

Your Highlightly API key is **valid and working**! The API is accessible through RapidAPI.

**API Key:** `9c27c5f8-9437-4d42-8cc9-5179d3290a5b`  
**Base URL:** `https://rugby.highlightly.net`  
**RapidAPI Host:** `rugby-highlights-api.p.rapidapi.com`

## Available Endpoints

### ✅ Working Endpoints:

1. **`get_leagues()`** - ✅ WORKING
   - Returns list of available rugby leagues
   - Can filter by limit and offset

2. **`get_standings(league_id, season)`** - ✅ WORKING
   - Returns league standings/table
   - Requires league_id and season

3. **`get_matches()`** - ⚠️ REQUIRES DATE PARAMETER
   - Returns matches
   - **Must provide date parameter** (format: YYYY-MM-DD)
   - Can filter by: league_id, league_name, date, season
   - Example: `api.get_matches(date="2024-12-15", limit=10)`

4. **`get_match_details(match_id)`** - ✅ AVAILABLE
   - Returns detailed match information
   - May include news/updates in response

5. **`get_match_lineups(match_id)`** - ✅ NEW! DEDICATED LINEUPS ENDPOINT
   - **Dedicated endpoint for team lineups**
   - Returns lineups for both home and away teams
   - Includes: player names, positions, jersey numbers, starting XI, substitutes
   - Falls back to extracting from match_details if dedicated endpoint doesn't exist
   - **This is the best way to get lineups!**

6. **`get_highlights()`** - ⚠️ MAY REQUIRE PARAMETERS
   - Returns match highlights
   - Can filter by match_id, league_id, date

7. **`get_head_to_head(team_id_one, team_id_two)`** - ✅ AVAILABLE
   - Returns head-to-head history between teams

8. **`get_last_five_games(team_id)`** - ✅ AVAILABLE
   - Returns last 5 games for a team

9. **`get_team_stats(team_id, from_date)`** - ✅ AVAILABLE
   - Returns team statistics

## 📋 Key Features for Your Needs

### 1. **LINEUPS** ✅
- **Available in:** `get_match_details(match_id)`
- The match details endpoint includes lineup information
- Structure may vary (check `lineups`, `lineup`, `homeLineup`, `awayLineup` fields)

### 2. **NEWS** ⚠️
- **Status:** No dedicated news endpoints found
- News might be included in:
  - Match details response
  - League information
  - Team information
- **Recommendation:** Check match_details response structure for news fields

### 3. **Your 8 Leagues Coverage** 🎯
Run the test to check which of your leagues are covered:
- Rugby Championship (4986)
- United Rugby Championship (4446)
- Currie Cup (5069)
- Rugby World Cup (4574)
- Super Rugby (4551)
- French Top 14 (4430)
- English Premiership Rugby (4414)
- Rugby Union International Friendlies (5479)

## Usage Examples

### Get Matches (with date):
```python
from prediction.highlightly_client import HighlightlyRugbyAPI
from datetime import datetime

api = HighlightlyRugbyAPI("your-api-key")

# Get matches for today
today = datetime.now().strftime('%Y-%m-%d')
matches = api.get_matches(date=today, limit=10)

# Get matches for specific league
matches = api.get_matches(league_name="United Rugby Championship", date=today)
```

### Get Match Lineups (DEDICATED ENDPOINT):
```python
# Get lineups for a match (BEST METHOD)
match_id = 12345  # From matches response
lineups = api.get_match_lineups(match_id)

# Lineups structure
if 'data' in lineups:
    lineup_data = lineups['data']
    home_players = lineup_data.get('home', [])
    away_players = lineup_data.get('away', [])
    print(f"Home team: {len(home_players)} players")
    print(f"Away team: {len(away_players)} players")
```

### Get Match Details:
```python
# Get full match details (may include additional info)
match_id = 12345
details = api.get_match_details(match_id)
```

### Get Standings:
```python
# Get standings for a league
standings = api.get_standings(league_id=1635, season=2024)
```

## Next Steps

1. **Run the comprehensive test:**
   ```bash
   python test_highlightly_api.py
   ```
   This will:
   - Test all endpoints with proper parameters
   - Check for lineups in match details
   - Check for news fields
   - Verify league coverage

2. **Check match details structure:**
   - Get a match ID from matches endpoint
   - Call `get_match_details(match_id)`
   - Inspect the response structure for:
     - Lineup fields
     - News/updates fields
     - Any other useful data

3. **If news is needed:**
   - Check if news is in match_details response
   - Consider using SportDevs API for news (once subscribed)
   - Or use a separate news API

## Current Limitations

- ⚠️ Matches endpoint requires date parameter
- ⚠️ No dedicated news endpoints (may be in match details)
- ⚠️ Need to verify league coverage for your 8 leagues

## Recommendations

1. **For Lineups:** ✅ Use `get_match_lineups(match_id)` - dedicated endpoint for lineups!
2. **For News:** Check match_details structure first, then consider SportDevs API
3. **For League Coverage:** Run test to see which of your 8 leagues are available

