# SportDevs API Status & Next Steps

## Current Status

### ✅ What We Know:
1. **Your API key is valid for RapidAPI** - The key format is correct
2. **You are NOT subscribed** to SportDevs Rugby API on RapidAPI
3. **Direct SportDevs API** (`rugby.sportdevs.com`) returns 521 errors (server down or wrong platform)

### Test Results:
- ❌ Direct SportDevs API: 521 errors (server refusing connections)
- ⚠️ RapidAPI - Rugby Highlights API: 403 "Not subscribed"
- ⚠️ RapidAPI - SportDevs API: 403 "Not subscribed"

## Solution: Subscribe to SportDevs Rugby API on RapidAPI

### Steps:
1. **Go to RapidAPI**: https://rapidapi.com
2. **Search for "SportDevs"** or "SportDevs Rugby"
3. **Subscribe** to the SportDevs Rugby API
4. **Use your existing RapidAPI key** (same one: `qwh9orOkZESulf4QBhf0IQ`)

### After Subscribing:

The `SportDevsClient` has been updated to support RapidAPI format. Use it like this:

```python
from prediction.sportdevs_client import SportDevsClient

# For RapidAPI (after subscribing)
api_key = "qwh9orOkZESulf4QBhf0IQ"
client = SportDevsClient(
    api_key=api_key,
    base_url="https://sportdevs.p.rapidapi.com",  # or check RapidAPI docs for correct URL
    use_rapidapi=True,
    rapidapi_host="sportdevs.p.rapidapi.com"  # Check RapidAPI docs for correct host
)

# Test it
leagues = client.get_leagues()
matches = client.get_all_matches()
news = client.get_league_news()
lineups = client.get_match_lineups(match_id=123)
```

## Alternative: Use SportDevs Dashboard

If you prefer direct API access (not through RapidAPI):

1. **Go to SportDevs Dashboard**: https://sportdevs.com/dashboard
2. **Get a direct API key** (different from RapidAPI key)
3. **Check if service is up** (521 errors suggest it might be down)
4. **Use standard format**:
   ```python
   client = SportDevsClient(api_key="your-direct-key")
   ```

## New Features Added

The `SportDevsClient` now includes:
- ✅ `get_match_lineups(match_id)` - Get team lineups
- ✅ `get_team_news(team_id)` - Get news for a team
- ✅ `get_league_news(league_id)` - Get news for a league
- ✅ `get_all_news()` - Get all rugby news
- ✅ RapidAPI support (set `use_rapidapi=True`)

## Your 8 Leagues

Once the API is working, you can check coverage for:
- Rugby Championship (4986)
- United Rugby Championship (4446)
- Currie Cup (5069)
- Rugby World Cup (4574)
- Super Rugby (4551)
- French Top 14 (4430)
- English Premiership Rugby (4414)
- Rugby Union International Friendlies (5479)

## Testing

After subscribing, run:
```bash
python test_sportdevs_api.py
```

This will test all endpoints and show which ones work.

