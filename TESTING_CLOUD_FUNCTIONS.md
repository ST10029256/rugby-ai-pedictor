# Testing Cloud Functions

## ✅ Deployment Complete

All 4 Cloud Functions are now deployed and available at:
- **Project**: `rugby-ai-61fd0`
- **Region**: `us-central1`

## 🔗 Function URLs

You can test the functions using:

### 1. Get Leagues
```bash
curl -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_leagues \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. Get Upcoming Matches
```bash
curl -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_upcoming_matches \
  -H "Content-Type: application/json" \
  -d '{"league_id": 4446, "limit": 10}'
```

### 3. Get Live Matches
```bash
curl -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_live_matches \
  -H "Content-Type: application/json" \
  -d '{"league_id": 4446}'
```

### 4. Predict Match
```bash
curl -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_match \
  -H "Content-Type: application/json" \
  -d '{
    "home_team": "Leinster",
    "away_team": "Munster",
    "league_id": 4446,
    "match_date": "2025-11-25"
  }'
```

## 🔧 Setting Environment Variables

**Important**: Set these in Firebase Console for functions to work properly:

1. Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/config
2. Click "Add variable" for each:
   - `MODEL_STORAGE_BUCKET` = `rugby-ai-61fd0.firebasestorage.app`
   - `SPORTDEVS_API_KEY` = (your API key)
   - `HIGHLIGHTLY_API_KEY` = (optional, your API key)

Or use Firebase CLI:
```bash
firebase functions:config:set \
  model_storage_bucket="rugby-ai-61fd0.firebasestorage.app" \
  sportdevs_api_key="YOUR_KEY" \
  highlightly_api_key="YOUR_KEY"
```

Then redeploy:
```bash
firebase deploy --only functions
```

## 🧪 Testing from React Frontend

The React app in `public/` can call these functions using:
```javascript
import { predictMatch, getUpcomingMatches } from './firebase';

// Predict a match
const prediction = await predictMatch({
  home_team: "Leinster",
  away_team: "Munster",
  league_id: 4446,
  match_date: "2025-11-25"
});

// Get upcoming matches
const matches = await getUpcomingMatches({
  league_id: 4446,
  limit: 10
});
```

## 📊 Monitoring

View function logs and metrics:
- **Console**: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/logs
- **Metrics**: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/metrics

## 🐛 Troubleshooting

### Function Timeout
- Default timeout: 60 seconds
- Increase in `firebase.json` if needed

### Model Loading Errors
- Check Cloud Storage bucket permissions
- Verify models are uploaded: `gs://rugby-ai-61fd0.firebasestorage.app/models/`

### Firestore Errors
- Check Firestore rules allow function access
- Verify database exists and has data

### Team Not Found
- Check team name spelling
- Verify team exists in Firestore `teams` collection

