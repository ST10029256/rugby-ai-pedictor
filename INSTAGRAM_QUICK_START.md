# 📸 Instagram Quick Start - 5 Steps

## ✅ Quick Checklist

### Step 1: Instagram Account Setup (5 minutes)
- [ ] Open Instagram app
- [ ] Settings → Account → Switch to Professional Account
- [ ] Choose "Business"
- [ ] Link to Facebook Page (create one if needed)

### Step 2: Facebook App (10 minutes)
- [ ] Go to https://developers.facebook.com
- [ ] Create App → Business type
- [ ] Add "Instagram Graph API" product
- [ ] Get App ID and App Secret (Settings → Basic)

### Step 3: Get Access Token (5 minutes)
- [ ] Go to https://developers.facebook.com/tools/explorer/
- [ ] Select your app
- [ ] Generate Token → Get User Access Token
- [ ] Select permissions: `instagram_basic`, `pages_read_engagement`
- [ ] Copy the token

### Step 4: Get Instagram Business Account ID (5 minutes)

**Option A - Via Facebook Page:**
- [ ] Go to your Facebook Page
- [ ] Settings → Instagram
- [ ] Copy the Instagram Business Account ID (numeric, like `123456789`)

**Option B - Via API:**
```bash
curl "https://graph.facebook.com/v18.0/{page-id}?fields=instagram_business_account&access_token={your-token}"
```

### Step 5: Configure & Deploy (5 minutes)

**A. Set Firebase Config:**
```bash
firebase functions:config:set instagram.access_token="YOUR_TOKEN_HERE"
```

**B. Add Team to Code:**
Edit `rugby-ai-predictor/prediction/social_media_fetcher.py`:
```python
TEAM_SOCIAL_HANDLES = {
    "Your Team Name": {
        "instagram": "123456789",  # Business Account ID (numeric!)
    }
}
```

**C. Deploy:**
```bash
cd rugby-ai-predictor
firebase deploy --only functions
```

**D. Test:**
- Open your app
- Go to News feed
- Should see Instagram posts!

---

## 🎯 What You Need

1. **Instagram Business Account** ✅ (free)
2. **Facebook Page** ✅ (free)
3. **Facebook App** ✅ (free)
4. **Access Token** ✅ (free, expires in 60 days)

**Total Cost: $0** (Instagram Graph API is free!)

---

## ⚠️ Common Mistakes

1. **Using username instead of Business Account ID**
   - ❌ Wrong: `"instagram": "leicestertigers"`
   - ✅ Right: `"instagram": "123456789"`

2. **Using personal Instagram account**
   - ❌ Personal accounts don't work
   - ✅ Must be Business or Creator account

3. **Not linking to Facebook Page**
   - ❌ Instagram must be linked to a Facebook Page
   - ✅ Link in Instagram settings

---

## 🔍 Test It Works

After deploying, check Firebase logs:
```bash
firebase functions:log --only get_news_feed
```

Look for:
- ✅ `"Fetched X Instagram posts"`
- ✅ `"Added X social media news items"`

If you see errors, check `INSTAGRAM_SETUP_GUIDE.md` for troubleshooting!

---

## 📚 Full Guide

For detailed instructions, see: **`INSTAGRAM_SETUP_GUIDE.md`**

---

**Ready?** Start with Step 1! 🚀

