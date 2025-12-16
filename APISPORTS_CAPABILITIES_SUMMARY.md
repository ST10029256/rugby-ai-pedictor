# API-Sports Rugby API - Capabilities Summary

## ✅ What API-Sports Provides

### 1. **League Standings** ✅
**Available for 6 out of 9 leagues:**

| League | API-Sports ID | Standings Available | Teams in Standings |
|--------|---------------|-------------------|-------------------|
| French Top 14 | 16 | ✅ Yes (2023) | 14 teams |
| United Rugby Championship | 76 | ✅ Yes (2023) | 12 teams |
| Rugby Championship | 85 | ✅ Yes (2023) | 4 teams |
| Currie Cup | 37 | ✅ Yes (2023) | 8 teams |
| Six Nations Championship | 51 | ✅ Yes (2023) | 6 teams |
| Super Rugby | 71 | ✅ Yes (2023) | 12 teams |
| Rugby World Cup | 69 | ❌ No | - |
| Rugby Union International Friendlies | 84 | ❌ No | - |
| English Premiership | 5 | ❌ No | - |

**Standings Data Includes:**
- Position
- Team info (id, name, logo)
- Games played
- Goals/points
- Form
- Description

### 2. **Team Images/Logos** ✅
**Available in multiple places:**

#### In Standings:
- ✅ Team logos available
- Format: `https://media.api-sports.io/rugby/teams/{team_id}.png`
- Example: `https://media.api-sports.io/rugby/teams/107.png`

#### In Games:
- ✅ Home team logo
- ✅ Away team logo
- Same format as standings

### 3. **Game Data** ✅
- Fixtures and results
- Team information
- Scores
- Dates and times
- League information

### 4. **What's NOT Available** ❌
- ❌ Lineup data (0 results for all leagues)
- ❌ Player images
- ❌ Player information
- ❌ Match statistics

## Summary

### ✅ Available:
1. **Standings** - 6 leagues
2. **Team Logos** - All leagues (in games and standings)
3. **Game Fixtures** - All leagues
4. **Scores** - All leagues

### ❌ Not Available:
1. **Lineups** - None
2. **Player Images** - None
3. **Player Data** - None

## Recommendation

**Use API-Sports for:**
- ✅ League standings (6 leagues)
- ✅ Team logos/images
- ✅ Game fixtures and scores

**Don't use API-Sports for:**
- ❌ Lineups
- ❌ Player data
- ❌ Player images

## Integration Priority

1. **High Priority:** Team logos (enhance UI)
2. **Medium Priority:** Standings (6 leagues only)
3. **Low Priority:** Game data (already have from TheSportsDB)

