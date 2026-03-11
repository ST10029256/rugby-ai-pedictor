# Win Rate Debug Script

This script helps debug why teams show 0% win rates or inaccurate win/loss calculations.

## Usage

### 1. **FULL COMPREHENSIVE SCAN (RECOMMENDED)**
This scans ALL teams, matches, and identifies all issues:
```bash
python scripts/debug_win_rates.py --full-scan --league-id 4986
```

Or scan all leagues:
```bash
python scripts/debug_win_rates.py --full-scan
```

### 2. Debug a specific team
```bash
python scripts/debug_win_rates.py --team "Newcastle Red Bulls" --league-id 4986
```

### 3. Debug a specific match
```bash
python scripts/debug_win_rates.py --match-id 2310170
```

### 4. Quick scan for issues
```bash
python scripts/debug_win_rates.py --scan --league-id 4986
```

### 5. List all teams in database
```bash
python scripts/debug_win_rates.py --list-teams --league-id 4986
```

## What it shows

### Full Scan Mode (`--full-scan`)
The comprehensive scan shows:
- ✅ **All Teams**: Complete statistics for every team
- ✅ **Win Rate Distribution**: How many teams in each win rate range
- ✅ **Data Quality**: Teams with/without data, teams using fallback
- ✅ **Top/Bottom Performers**: Best and worst teams by win rate
- ✅ **All Issues**: Categorized by type (NO_DATA, INSUFFICIENT_DATA, LEAGUE_FALLBACK, etc.)
- ✅ **Match Issues**: Upcoming matches with teams that have no data
- ✅ **Summary Statistics**: Total teams, matches, issues found

### Individual Team/Match Mode
For each team or match, the script displays:
- ✅ All games with scores and results (WIN/DRAW/LOSS)
- ✅ Win rate calculation breakdown
- ✅ Whether it used league-specific or fallback data
- ✅ Game dates and event IDs
- ✅ Which league each game was from

## Example Output

```
🔍 DEBUGGING TEAM: Newcastle Red Bulls (ID: 123)
League ID filter: 4986
Looking for last 5 games

📊 Step 1: Querying games from league 4986...
   Found 5 games in league 4986

📈 RESULTS:
   Total Games: 5
   Wins: 0
   Draws: 0
   Losses: 5
   Win Rate: 0.0%
   Source: league 4986

📋 GAME DETAILS:
   Game 1 (2025-12-15): Newcastle Red Bulls 14-52 vs Bath Rugby [HOME] - ❌ LOSS
      Event ID: 12345, League: 4986
   Game 2 (2025-12-10): Newcastle Red Bulls 19-36 vs Sale Sharks [HOME] - ❌ LOSS
      Event ID: 12346, League: 4986
   ...
```

## Common Issues to Check

1. **0% win rate with 5 games**: Team actually lost all games (correct)
2. **0% win rate with 0 games**: No data found - check database
3. **Games from wrong league**: League filtering not working
4. **Missing recent games**: Date filtering too restrictive

