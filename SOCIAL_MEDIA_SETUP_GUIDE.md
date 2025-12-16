# 📱 Social Media Integration Setup Guide

## Why Social Media Posts Aren't Auto-Fetching

Your news system **can embed** social media posts, but it doesn't **automatically fetch** them because:

1. **API Access Required**: X/Twitter, Instagram, and Facebook require API access
2. **Authentication Needed**: Each platform needs API keys/tokens
3. **Costs**: Twitter/X API is now **paid** (Basic tier ~$100/month)
4. **Complex Setup**: Requires app registration and OAuth flows

## ✅ What's Already Working

- **Embedding**: If you provide a URL, the system can embed it
- **Parsing**: Supports Instagram, X/Twitter, YouTube URLs
- **AI Explanations**: Generates context for embedded posts

## 🚀 How to Enable Auto-Fetching

### Option 1: Twitter/X API (Recommended for Real-Time Updates)

**Cost**: ~$100/month for Basic tier

1. **Get Twitter API Access**:
   - Go to https://developer.twitter.com
   - Apply for API access (may take days/weeks)
   - Subscribe to Basic tier ($100/month)

2. **Get Bearer Token**:
   - Create a Twitter App
   - Generate Bearer Token

3. **Set Environment Variable**:
   ```bash
   firebase functions:config:set twitter.bearer_token="YOUR_BEARER_TOKEN"
   ```

4. **Redeploy**:
   ```bash
   firebase deploy --only functions
   ```

### Option 2: Instagram Graph API

**Requirements**: Business/Creator account + Facebook Page

1. **Create Facebook App**:
   - Go to https://developers.facebook.com
   - Create new app
   - Get App ID and App Secret

2. **Link Instagram to Facebook Page**:
   - Instagram account must be Business/Creator
   - Must be linked to a Facebook Page

3. **Get Access Token**:
   - Use Facebook Graph API Explorer
   - Generate long-lived token

4. **Set Environment Variables**:
   ```bash
   firebase functions:config:set instagram.access_token="YOUR_TOKEN"
   firebase functions:config:set facebook.app_id="YOUR_APP_ID"
   firebase functions:config:set facebook.app_secret="YOUR_APP_SECRET"
   ```

### Option 3: Facebook Graph API

**Requirements**: Facebook Page

1. **Create Facebook App** (same as Instagram)

2. **Get Page Access Token**:
   - Use Graph API Explorer
   - Select your Page
   - Generate token

3. **Set Environment Variable**:
   ```bash
   firebase functions:config:set facebook.access_token="YOUR_TOKEN"
   ```

## 📋 Team Social Media Handles

You need to map team names to their social media handles. Edit `prediction/social_media_fetcher.py`:

```python
TEAM_SOCIAL_HANDLES = {
    "Leicester Tigers": {
        "twitter": "LeicesterTigers",
        "instagram": "leicestertigers",
        "facebook": "LeicesterTigers"  # Page ID or username
    },
    "Bath Rugby": {
        "twitter": "bathrugby",
        "instagram": "bathrugby",
        "facebook": "BathRugby"
    },
    # Add all your teams here
}
```

## 🔧 Integration Steps

1. **Copy Files**:
   ```bash
   cp prediction/social_media_fetcher.py rugby-ai-predictor/prediction/
   ```

2. **Update Firebase Functions** (`rugby-ai-predictor/main.py`):
   
   In `get_news_service()` function, add:
   ```python
   from prediction.social_media_fetcher import SocialMediaFetcher
   
   social_media_fetcher = SocialMediaFetcher()
   
   return NewsService(
       db_path=db_path,
       predictor=predictor,
       sportdevs_client=sportdevs_client,
       sportsdb_client=sportsdb_client,
       social_media_fetcher=social_media_fetcher  # Add this
   )
   ```

3. **Deploy**:
   ```bash
   cd rugby-ai-predictor
   firebase deploy --only functions
   ```

## ⚠️ Important Notes

### Rate Limits
- **Twitter**: 300 requests/15min (Basic tier)
- **Instagram**: 200 requests/hour
- **Facebook**: Varies by app tier

### Costs
- **Twitter**: $100/month minimum (Basic tier)
- **Instagram**: Free (but requires Business account)
- **Facebook**: Free (but requires app approval)

### Alternatives

If API costs are too high, consider:

1. **RSS Feeds**: Some teams have RSS feeds
2. **Web Scraping**: ⚠️ May violate ToS
3. **Manual Input**: Users can paste URLs
4. **Third-Party Aggregators**: Services that aggregate social media

## 🎯 Current Status

- ✅ **Embedding**: Works (if URLs provided)
- ✅ **Parsing**: Works (Instagram, X, YouTube)
- ⚠️ **Auto-Fetching**: Requires API setup (see above)

## 💡 Quick Start (Without APIs)

If you don't want to set up APIs right now:

1. **Manual URLs**: Users can paste social media URLs
2. **Embedding**: System will automatically embed them
3. **AI Explanations**: System generates context

The system works perfectly for **embedding** posts, just not **auto-fetching** them.

---

**Summary**: Social media auto-fetching requires API access and setup. The embedding system works now - you just need to provide URLs. To auto-fetch, you'll need to set up API access for each platform you want to use.

