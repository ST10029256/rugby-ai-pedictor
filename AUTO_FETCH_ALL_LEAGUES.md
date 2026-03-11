# Automatic Game Fetching for All Leagues

## ✅ Current Behavior (After Update)

**YES - The script now automatically fetches all games from all leagues!**

### What Changed:
- **Round scanning is now automatic for ALL leagues** (not just URC)
- No need to use `--scan-rounds` flag anymore
- All leagues will have comprehensive fixture coverage

### How It Works:
1. For each league, the script automatically:
   - Checks `eventsnextleague.php` (limited results)
   - Checks `eventsseason.php` (season-based)
   - **Automatically scans all rounds** (this is where most upcoming games are found)

2. Round limits per league:
   - URC: 18 rounds
   - English Premiership: 18 rounds
   - French Top 14: 26 rounds
   - Super Rugby: 18 rounds
   - Six Nations: 5 rounds
   - Rugby Championship: 6 rounds
   - Currie Cup: 14 rounds
   - World Cup: 30 rounds (placeholder)

### Example:
When you run:
```bash
python scripts/enhanced_auto_update.py
```

It will automatically:
- ✅ Fetch URC games from all 18 rounds
- ✅ Fetch Premiership games from all 18 rounds
- ✅ Fetch Top 14 games from all 26 rounds
- ✅ Fetch all other leagues from their respective rounds
- ✅ Process all leagues without needing any flags

### Why This Matters:
The API test showed that:
- `eventsnextleague.php` only returns 1-2 upcoming games
- `eventsseason.php` often returns past games with scores
- **`eventsround.php` has all the upcoming games** (66 games for URC!)

By automatically scanning rounds, you get comprehensive coverage of all upcoming fixtures.

### Performance Note:
This will make more API calls (potentially 200-300+ calls for all leagues), but ensures you don't miss any upcoming games. The script includes rate limiting delays to avoid API issues.

### Deprecated Flag:
The `--scan-rounds` flag is now deprecated since round scanning is always enabled. It's kept for backward compatibility but has no effect.
