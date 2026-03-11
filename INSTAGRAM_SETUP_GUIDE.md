# 📸 Instagram Integration - Complete Setup Guide

## Prerequisites

1. **Instagram Business or Creator Account** (not personal account)
2. **Facebook Page** (must be linked to your Instagram account)
3. **Facebook Developer Account** (free)
4. **Facebook App** (we'll create this)

---

## Step 1: Convert Instagram to Business Account

1. Open Instagram app on your phone
2. Go to **Settings** → **Account**
3. Tap **Switch to Professional Account**
4. Choose **Business** (or Creator)
5. Follow the prompts to complete setup

**Important**: Your Instagram account must be linked to a Facebook Page!

---

## Step 2: Create Facebook App

1. Go to https://developers.facebook.com
2. Click **My Apps** → **Create App**
3. Choose **Business** as app type
4. Fill in:
   - **App Name**: "Rugby AI Predictor" (or your choice)
   - **App Contact Email**: Your email
5. Click **Create App**

---

## Step 3: Add Instagram Graph API Product

1. In your Facebook App dashboard, click **Add Product**
2. Find **Instagram Graph API** and click **Set Up**
3. You'll see the Instagram Graph API product added

---

## Step 4: Get Access Token

### Option A: Using Graph API Explorer (Easiest for Testing)

1. Go to https://developers.facebook.com/tools/explorer/
2. Select your app from the dropdown
3. Click **Generate Token** → **Get User Access Token**
4. Select these permissions:
   - `instagram_basic`
   - `instagram_content_publish` (if needed)
   - `pages_read_engagement`
   - `pages_show_list`
5. Click **Generate Access Token**
6. **Copy the token** - you'll need it!

### Option B: Long-Lived Token (For Production)

1. Get short-lived token from Graph API Explorer (above)
2. Exchange it for long-lived token:

```bash
curl -X GET "https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id={app-id}&client_secret={app-secret}&fb_exchange_token={short-lived-token}"
```

Replace:
- `{app-id}`: Your Facebook App ID
- `{app-secret}`: Your Facebook App Secret (from App Settings)
- `{short-lived-token}`: Token from Graph API Explorer

---

## Step 5: Get Instagram Business Account ID

You need the **Instagram Business Account ID** (not username). Here's how:

### Method 1: Via Facebook Page

1. Go to your Facebook Page
2. Go to **Settings** → **Instagram**
3. You'll see the Instagram Business Account ID

### Method 2: Via Graph API

```bash
curl -X GET "https://graph.facebook.com/v18.0/{page-id}?fields=instagram_business_account&access_token={access-token}"
```

Replace:
- `{page-id}`: Your Facebook Page ID
- `{access-token}`: Your access token

This returns: `{"instagram_business_account":{"id":"123456789"}}`

### Method 3: Using Username (If Account is Public)

If your Instagram account is public and linked to a Page:

```bash
curl -X GET "https://graph.facebook.com/v18.0/{username}?fields=id&access_token={access-token}"
```

---

## Step 6: Configure Your App

### Set Environment Variables

```bash
# Set Instagram Access Token
firebase functions:config:set instagram.access_token="YOUR_LONG_LIVED_TOKEN"

# Set Facebook App credentials (optional, but recommended)
firebase functions:config:set facebook.app_id="YOUR_APP_ID"
firebase functions:config:set facebook.app_secret="YOUR_APP_SECRET"
```

### Or use .env file (for local testing):

```env
INSTAGRAM_ACCESS_TOKEN=your_token_here
FACEBOOK_APP_ID=your_app_id
FACEBOOK_APP_SECRET=your_app_secret
```

---

## Step 7: Add Team Instagram Accounts

Edit `prediction/social_media_fetcher.py` and add your teams:

```python
TEAM_SOCIAL_HANDLES = {
    "Leicester Tigers": {
        "instagram": "123456789",  # Instagram Business Account ID (not username!)
    },
    "Bath Rugby": {
        "instagram": "987654321",  # Instagram Business Account ID
    },
    # Add more teams...
}
```

**Important**: Use the **Instagram Business Account ID** (numeric), not the username!

---

## Step 8: Test the Integration

### Test Locally

```python
from prediction.social_media_fetcher import SocialMediaFetcher

fetcher = SocialMediaFetcher()
posts = fetcher.fetch_instagram_posts("123456789", limit=5)  # Use Business Account ID
print(f"Fetched {len(posts)} posts")
```

### Test in Firebase Functions

1. Deploy:
   ```bash
   cd rugby-ai-predictor
   firebase deploy --only functions
   ```

2. Check logs:
   ```bash
   firebase functions:log --only get_news_feed
   ```

3. Look for:
   - `"Fetched X Instagram posts for {username}"`
   - `"Added X social media news items"`

---

## Troubleshooting

### Error: "Invalid OAuth access token"

- Token expired (short-lived tokens expire in 1-2 hours)
- **Solution**: Use long-lived token (60 days) or Page Access Token (never expires)

### Error: "User not found" or "Invalid user ID"

- Using username instead of Business Account ID
- **Solution**: Use the numeric Business Account ID

### Error: "Missing permissions"

- Token doesn't have required permissions
- **Solution**: Regenerate token with `instagram_basic` permission

### Error: "Instagram account not linked to Facebook Page"

- Instagram account must be Business/Creator and linked to a Page
- **Solution**: Link Instagram to Facebook Page in Instagram settings

### No posts returned

- Account might not have posts
- **Solution**: Check Instagram account has public posts

---

## Rate Limits

- **Instagram Graph API**: 200 requests/hour per user
- **Best Practice**: Cache results, don't fetch too frequently

---

## Production Setup

### Long-Lived Tokens

Long-lived tokens expire in 60 days. For production:

1. **Use Page Access Tokens** (never expire, but tied to Page)
2. **Set up token refresh** (automatically renew before expiry)
3. **Use System User Tokens** (for server-to-server)

### Page Access Token (Recommended)

```bash
curl -X GET "https://graph.facebook.com/v18.0/{page-id}?fields=access_token&access_token={user-access-token}"
```

This returns a Page Access Token that never expires (as long as Page admin doesn't revoke).

---

## Quick Start Checklist

- [ ] Instagram account is Business/Creator
- [ ] Instagram linked to Facebook Page
- [ ] Facebook App created
- [ ] Instagram Graph API product added
- [ ] Access token generated
- [ ] Instagram Business Account ID obtained
- [ ] Environment variables set
- [ ] Team handles added to `social_media_fetcher.py`
- [ ] Functions deployed
- [ ] Tested and working!

---

## Example: Complete Setup for One Team

1. **Team**: "Leicester Tigers"
2. **Instagram Username**: `@leicestertigers`
3. **Instagram Business Account ID**: `123456789` (get from Facebook Page settings)
4. **Access Token**: `EAABwzLix...` (from Graph API Explorer)

**In code:**
```python
TEAM_SOCIAL_HANDLES = {
    "Leicester Tigers": {
        "instagram": "123456789",  # Business Account ID
    }
}
```

**In Firebase:**
```bash
firebase functions:config:set instagram.access_token="EAABwzLix..."
```

**Result**: App will fetch latest 5 posts from @leicestertigers Instagram!

---

## Next Steps

Once Instagram is working:
1. Add more teams to `TEAM_SOCIAL_HANDLES`
2. Set up Twitter/X (see `SOCIAL_MEDIA_SETUP_GUIDE.md`)
3. Set up Facebook (see `SOCIAL_MEDIA_SETUP_GUIDE.md`)

---

**Need Help?** Check Firebase function logs for detailed error messages!

