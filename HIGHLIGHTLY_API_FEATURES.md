# What You Get from Highlightly API

## 📊 Overview

The **Highlightly API** provides **enhanced rugby data** that supplements your AI predictions with real-time and historical information. It's **optional** - your app works without it, but it adds valuable features.

## 🎯 Key Features Provided

### 1. **Live Match Data** ⚽
- Real-time match information
- Match details (venue, date, time, status)
- Lineups and team rosters
- Match events and timeline

### 2. **Live Betting Odds** 💰
- Current odds from multiple bookmakers
- Home/Away win odds
- Draw odds
- Various betting markets
- **Note**: Currently disabled in code (using manual odds instead)

### 3. **Team Statistics** 📈
- Team performance metrics
- Recent form (last 5-10 games)
- Win rates and streaks
- Goals scored/conceded averages
- Home/Away performance splits

### 4. **Head-to-Head History** 🆚
- Historical matchups between teams
- Previous results
- Win/loss records
- Score history

### 5. **League Standings** 🏆
- Current league table
- Team positions
- Points, wins, losses
- Goal differences

### 6. **Match Highlights** 🎬
- Video highlights (if available)
- Match summaries
- Key moments

## 🔄 How It Enhances Predictions

### Without Highlightly API:
- ✅ AI model predictions (67-70% accuracy)
- ✅ Historical data from your database
- ✅ Basic team statistics

### With Highlightly API:
- ✅ **All of the above** PLUS:
- ✅ **Live odds** from bookmakers (market sentiment)
- ✅ **Recent team form** (last 5 games performance)
- ✅ **Head-to-head** historical data
- ✅ **Current standings** (league position context)
- ✅ **Match details** (venue, lineups, etc.)
- ✅ **Dynamic confidence** scoring based on data availability

## 💡 Example Enhanced Prediction

```json
{
  "predicted_winner": "Home",
  "confidence": 0.75,
  "home_win_prob": 0.68,
  "predicted_home_score": 28,
  "predicted_away_score": 22,
  
  "enhanced_data": {
    "live_odds": {
      "Bet365": {"home": 1.85, "away": 2.10},
      "William Hill": {"home": 1.90, "away": 2.05}
    },
    "team_form": {
      "home": {
        "win_rate": 0.80,
        "last_5_games": ["W", "W", "L", "W", "W"]
      },
      "away": {
        "win_rate": 0.60,
        "last_5_games": ["W", "L", "W", "W", "L"]
      }
    },
    "head_to_head": [
      {"date": "2024-10-15", "home_score": 32, "away_score": 18},
      {"date": "2024-05-20", "home_score": 24, "away_score": 28}
    ],
    "standings": {
      "home_position": 2,
      "away_position": 5
    }
  }
}
```

## ⚠️ Important Notes

1. **Optional**: Your app works perfectly without Highlightly API
2. **Cost**: Highlightly API may have usage limits/costs
3. **Odds Disabled**: The odds feature is currently disabled in code (returns empty)
4. **Fallback**: If API fails, predictions still work with AI model only

## 🔑 Where to Get API Key

If you want to use Highlightly:
1. Sign up at: https://rugby.highlightly.net (or their provider)
2. Get your API key
3. Set as environment variable: `HIGHLIGHTLY_API_KEY`

## 📝 Current Status in Your Code

- **Found in code**: `expert_ai_app.py` line 129 has a hardcoded key: `'9c27c5f8-9437-4d42-8cc9-5179d3290a5b'`
- **Used in**: `EnhancedRugbyPredictor` class
- **Optional**: Functions work without it

## 🎯 Recommendation

**For Firebase Cloud Functions:**
- You can **skip** `HIGHLIGHTLY_API_KEY` if you don't have one
- Your predictions will still work with AI models
- Enhanced features (odds, form, H2H) won't be available
- Basic predictions remain fully functional

**If you want enhanced features:**
- Get a Highlightly API key
- Set it as environment variable
- Enhanced predictions will include live data

