# News & Logos - How Your App Gets Content

## 📰 News Sources

Your app gets news from **3 sources**:

### 1. **AI-Generated News** (Primary - Always Available)
- **Source**: Your database + AI analysis
- **Content**: 
  - Match previews with form analysis
  - Lineup change impacts
  - Prediction shifts
  - Team form analysis
- **How it works**: 
  - Analyzes match data from your SQLite database
  - Generates intelligent headlines based on statistics
  - Updates automatically when lineups change
- **No API needed** ✅

### 2. **External News from SportDevs API** (Optional - If Subscribed)
- **Source**: SportDevs Rugby API (`media`, `media-teams`, `media-leagues` endpoints)
- **Content**: 
  - Official team announcements
  - League news
  - Player updates
- **How it works**:
  - Fetches from SportDevs if you have an active subscription
  - Merges with AI-generated news
  - Falls back gracefully if API unavailable
- **Requires**: SportDevs API key (optional)

### 3. **Social Media Embeds** (Instagram/X/YouTube)
- **Source**: Official team social media accounts
- **Content**: 
  - Lineup announcements
  - Match highlights
  - Team updates
- **How it works**:
  - Users/you provide social media URLs
  - App embeds them (never rehosts - zero copyright risk)
  - AI explains why each post matters
- **No API needed** ✅

## 🏉 Team Logos

Your app gets logos from **TheSportsDB API**:

### Logo Source
- **API**: TheSportsDB (`lookupteam` endpoint)
- **Field**: `strTeamBadge` or `strTeamLogo`
- **How it works**:
  1. When displaying a team, app checks if logo is cached
  2. If not, fetches from TheSportsDB using team ID
  3. Caches logo URL for future use
  4. Displays in match cards, news items, etc.

### Logo Display Locations
- ✅ Match cards (home/away team logos)
- ✅ News items (team logos in lineup changes)
- ✅ League standings (team badges)
- ✅ Player impact explorer (team context)

### Fallback
- If logo unavailable, shows team name or placeholder
- Gracefully handles missing logos

## 🔧 Technical Implementation

### News Service Flow
```
1. User opens News Feed
   ↓
2. Backend calls NewsService.get_news_feed()
   ↓
3. Service generates AI news from database
   ↓
4. (Optional) Fetches external news from SportDevs
   ↓
5. Merges and sorts by timestamp
   ↓
6. Returns to frontend
```

### Logo Fetching Flow
```
1. Component needs team logo
   ↓
2. Checks if team_id exists
   ↓
3. Calls NewsService.get_team_logo_url(team_id)
   ↓
4. Service queries TheSportsDB API
   ↓
5. Returns logo URL
   ↓
6. Component displays logo
```

## 📋 API Requirements

### Required APIs (Already Set Up)
- ✅ **TheSportsDB** - For team logos
  - Already configured in your codebase
  - Used for match data, now also for logos

### Optional APIs
- ⚠️ **SportDevs** - For external news
  - Only needed if you want external news articles
  - Falls back gracefully if unavailable
  - Your codebase already has SportDevs client

## 🎯 Current Status

### ✅ Working Now
- AI-generated news from match data
- Social media embed parsing
- Logo fetching infrastructure (needs API client integration)

### 🔄 Needs Integration
- Pass SportDevs client to NewsService (for external news)
- Pass TheSportsDB client to NewsService (for logos)
- Update Firebase functions to pass API clients

## 💡 Example: How News Appears

**Scenario**: Stormers vs Bulls match upcoming

1. **AI News Generated**:
   - "Stormers in strong form ahead of Bulls clash"
   - Based on: Recent win rate, form analysis, head-to-head

2. **External News** (if SportDevs available):
   - "Stormers announce starting XV"
   - From: SportDevs media API

3. **Social Media Embed**:
   - Instagram post from @stormersrugby
   - Shows lineup announcement
   - AI explains: "This lineup affects win probability by +3.2%"

4. **Logos Displayed**:
   - Stormers logo from TheSportsDB
   - Bulls logo from TheSportsDB
   - Shown in match card

## 🚀 Next Steps

1. **Update Firebase Functions** to pass API clients to NewsService
2. **Test Logo Fetching** with real team IDs
3. **Add Logo Caching** to reduce API calls
4. **Integrate SportDevs News** (if you have subscription)

---

**Summary**: Your app generates intelligent news automatically from your data, optionally enhances with external sources, and fetches logos on-demand from TheSportsDB. Everything works gracefully even if external APIs are unavailable!

