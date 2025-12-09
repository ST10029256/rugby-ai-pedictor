# Setting Environment Variables in PowerShell

## For 2nd Gen Functions (What You're Using)

2nd Gen functions use a different system. You have two options:

### Option 1: Set via Google Cloud Console (Easiest)

1. Go to: https://console.cloud.google.com/run?project=rugby-ai-61fd0
2. Click on each function service (e.g., `predict-match-2jbomp443a`)
3. Click "Edit & Deploy New Revision"
4. Go to "Variables & Secrets" tab
5. Add environment variables:
   - `MODEL_STORAGE_BUCKET` = `rugby-ai-61fd0.firebasestorage.app`
   - `SPORTDEVS_API_KEY` = `qwh9orOkZESulf4QBhf0IQ`
   - `HIGHLIGHTLY_API_KEY` = `9c27c5f8-9437-4d42-8cc9-5179d3290a5b`
6. Click "Deploy"

### Option 2: Use gcloud CLI (Alternative)

```powershell
# Set for a specific Cloud Run service
gcloud run services update predict-match-2jbomp443a `
  --region=us-central1 `
  --update-env-vars="MODEL_STORAGE_BUCKET=rugby-ai-61fd0.firebasestorage.app,SPORTDEVS_API_KEY=qwh9orOkZESulf4QBhf0IQ,HIGHLIGHTLY_API_KEY=9c27c5f8-9437-4d42-8cc9-5179d3290a5b" `
  --project=rugby-ai-61fd0
```

Repeat for each function:
- `get-leagues-2jbomp443a`
- `get-live-matches-2jbomp443a`
- `get-upcoming-matches-2jbomp443a`
- `predict-match-2jbomp443a`

### Option 3: Update Code to Use Defaults (Quick Fix)

Since your code already has defaults, you could update `main.py` to use the hardcoded values as fallbacks. But environment variables are more secure.

